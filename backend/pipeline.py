"""
pipeline.py — Two-stage vision pipeline

Stage 1: Vendor detection  (fast LLM call — just the store name)
Stage 2: Full extraction   (full LLM call with vendor-specific prompt)

No auto-save. Returns extracted data to the caller for user review before DB commit.
"""

import json
import base64
import logging
import os
import httpx

from vendor import detect_vendor, build_vendor_prompt_section

logger = logging.getLogger("pipeline")

OLLAMA_URL   = os.getenv("OLLAMA_URL",   "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2-vision:11b")


# ── Base extraction prompt ────────────────────────────────────────────────────
# Vendor-specific rules are injected at {vendor_section}

_BASE_PROMPT = """You are a receipt parser. Read this receipt image carefully and extract all data.

Return ONLY a valid JSON object. No explanation, no markdown, no code fences.

{vendor_section}

JSON STRUCTURE:
{{
  "store": {{
    "name": "string or null",
    "confidence": 0.0-1.0
  }},
  "date": {{
    "value": "YYYY-MM-DD or null",
    "confidence": 0.0-1.0
  }},
  "items": [
    {{
      "receipt_name": "exact text as printed on receipt",
      "display_name": "human-readable decoded name",
      "category": "see category list below",
      "quantity": number,
      "unit_type": "unit | weight_kg | weight_g",
      "weight_kg": null or number,
      "unit_price": null or number,
      "per_kg_price": null or number,
      "total_price": null or number,
      "vat_applicable": true or false,
      "confidence": 0.0-1.0,
      "flag": null or "short warning string"
    }}
  ],
  "subtotal": null or number,
  "vat_total": null or number,
  "total": null or number,
  "currency": "ZAR",
  "tax_groups": null or [
    {{ "rate": "0%",  "tax": 0.00, "gross": 0.00, "net": 0.00 }},
    {{ "rate": "15%", "tax": 0.00, "gross": 0.00, "net": 0.00 }}
  ]
}}

CATEGORY LIST:
fruit | vegetable | dairy | meat | seafood | bakery | pantry | frozen |
beverages | snacks | alcohol | household | toiletries | clothing | footwear |
accessories | beauty | homeware | sport | discount | other

GENERAL RULES (apply when no vendor-specific rule overrides):
- date must always be formatted as YYYY-MM-DD
- quantity is 1 unless an explicit multiplier appears on the receipt (e.g. "2 @", "2 x", "Qty: 3")
- per_kg_price = total_price / weight_kg when weight_kg is known, else null
- Negative price lines are discounts — include them with negative total_price, category=discount
- If a RATE/TAX/GROSS/NET table appears at the bottom, extract it into tax_groups and use the TAX
  value from the 15% row as vat_total
- confidence >0.85 = high, 0.70-0.85 = moderate, <0.70 = low
- Set flag when a value looks wrong or ambiguous

SOUTH AFRICAN VAT ZERO-RATING (fallback when no vendor VAT indicator is available):
Zero-rated: fresh/frozen/dried fruit and veg, bread and bread flour, eggs, plain milk and maas,
cooking oil, rice, samp, maize meal, oats, dried beans/lentils, tinned pilchards/sardines,
peanut butter.
Everything else: 15% VAT."""


# ── Public API ────────────────────────────────────────────────────────────────

def run_pipeline(image_path: str, model: str | None = None) -> dict:
    """
    Full two-stage pipeline.
    Returns dict with: extracted, vendor, model_used, llm_error, status, image_path
    Does NOT save to DB — caller handles that after user review.
    """
    use_model = model or OLLAMA_MODEL

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    # Stage 1: vendor detection
    logger.info(f"Stage 1: vendor detection ({use_model})")
    vendor_profile = detect_vendor(image_b64, model=use_model)
    vendor_name    = vendor_profile.get("name", "Unknown")
    logger.info(f"Vendor: {vendor_name}")

    # Stage 2: extraction with vendor-specific prompt
    logger.info(f"Stage 2: extraction with {vendor_name} profile")
    vendor_section = build_vendor_prompt_section(vendor_profile)
    prompt         = _BASE_PROMPT.format(vendor_section=vendor_section)

    extracted, llm_error = _extract(image_b64, prompt, use_model)

    return {
        "image_path":     image_path,
        "vendor":         vendor_name,
        "vendor_profile": vendor_profile.get("name", "Unknown"),
        "extracted":      extracted,
        "model_used":     use_model,
        "llm_error":      llm_error,
        "status":         "partial" if llm_error else "success",
    }


# ── Internal ──────────────────────────────────────────────────────────────────

def _extract(image_b64: str, prompt: str, model: str = OLLAMA_MODEL) -> tuple[dict, str | None]:
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":  model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "num_predict": 3000,
                    "num_ctx":     4096,
                },
            },
            timeout=300.0,
        )
        response.raise_for_status()
        raw   = response.json().get("response", "")
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)

        # Normalise date to YYYY-MM-DD regardless of what the LLM emitted
        date_obj = parsed.get("date", {})
        if isinstance(date_obj, dict) and date_obj.get("value"):
            try:
                from dateutil import parser as _dp
                parsed["date"]["value"] = _dp.parse(date_obj["value"], dayfirst=True).strftime("%Y-%m-%d")
            except Exception:
                pass

        logger.info(f"Extraction OK — {len(parsed.get('items', []))} items")
        return parsed, None

    except httpx.ConnectError:
        msg = f"Cannot reach Ollama at {OLLAMA_URL}"
        logger.error(msg); return {}, msg
    except httpx.HTTPStatusError as e:
        msg = f"Ollama HTTP {e.response.status_code}: {e.response.text[:200]}"
        logger.error(msg); return {}, msg
    except json.JSONDecodeError as e:
        msg = f"LLM returned invalid JSON: {e}"
        logger.error(msg); return {}, msg
    except Exception as e:
        msg = f"Unexpected error: {e}"
        logger.error(msg, exc_info=True); return {}, msg


def check_ollama_health() -> dict:
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        r.raise_for_status()
        models      = [m["name"] for m in r.json().get("models", [])]
        model_ready = any(OLLAMA_MODEL.split(":")[0] in m for m in models)
        return {
            "reachable":        True,
            "model_loaded":     model_ready,
            "available_models": models,
            "configured_model": OLLAMA_MODEL,
        }
    except Exception as e:
        return {"reachable": False, "error": str(e), "configured_model": OLLAMA_MODEL}
