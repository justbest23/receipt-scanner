"""
claude_pipeline.py — Claude API fallback pipeline

Same two-stage architecture as pipeline.py but calls the Anthropic API
instead of Ollama. Used by POST /scan/claude.
"""

import json
import base64
import logging
import os

from vendor import get_profile, build_vendor_prompt_section
from pipeline import _BASE_PROMPT

try:
    import anthropic as _anthropic
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

logger = logging.getLogger("claude_pipeline")

CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

_MEDIA_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png",  "webp": "image/webp",
}


def run_claude_pipeline(image_path: str) -> dict:
    if not _AVAILABLE:
        return _err(image_path, "anthropic package not installed — rebuild the Docker image")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return _err(image_path, "ANTHROPIC_API_KEY is not set — add it to your .env file")

    client = _anthropic.Anthropic(api_key=api_key)

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    ext        = image_path.rsplit(".", 1)[-1].lower()
    media_type = _MEDIA_TYPES.get(ext, "image/jpeg")

    # Stage 1: vendor detection
    logger.info("Claude Stage 1: vendor detection")
    vendor_name    = _detect_vendor(client, image_b64, media_type)
    logger.info(f"Claude vendor: '{vendor_name}'")

    vendor_profile = get_profile(vendor_name)
    logger.info(f"Matched profile: {vendor_profile.get('name', 'Unknown')}")

    # Stage 2: full extraction
    vendor_section = build_vendor_prompt_section(vendor_profile)
    prompt         = _BASE_PROMPT.format(vendor_section=vendor_section)

    logger.info("Claude Stage 2: extraction")
    extracted, llm_error = _extract(client, image_b64, media_type, prompt)

    return {
        "image_path":     image_path,
        "vendor":         vendor_profile.get("name", "Unknown"),
        "vendor_profile": vendor_profile.get("name", "Unknown"),
        "extracted":      extracted,
        "model_used":     CLAUDE_MODEL,
        "llm_error":      llm_error,
        "status":         "partial" if llm_error else "success",
    }


def _detect_vendor(client, image_b64: str, media_type: str) -> str:
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=30,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text",  "text": "What store or retailer is shown on this receipt? Reply with ONLY the store name, maximum 3 words, nothing else."},
                ],
            }],
        )
        return resp.content[0].text.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Claude vendor detection failed: {e}")
        return ""


def _extract(client, image_b64: str, media_type: str, prompt: str) -> tuple[dict, str | None]:
    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
                    {"type": "text",  "text": prompt},
                ],
            }],
        )
        raw   = resp.content[0].text.strip()
        clean = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)

        date_obj = parsed.get("date", {})
        if isinstance(date_obj, dict) and date_obj.get("value"):
            try:
                from dateutil import parser as _dp
                parsed["date"]["value"] = _dp.parse(date_obj["value"], dayfirst=True).strftime("%Y-%m-%d")
            except Exception:
                pass

        logger.info(f"Claude extraction OK — {len(parsed.get('items', []))} items")
        return parsed, None

    except json.JSONDecodeError as e:
        msg = f"Claude returned invalid JSON: {e}"
        logger.error(msg)
        return {}, msg
    except Exception as e:
        msg = f"Claude API error: {e}"
        logger.error(msg, exc_info=True)
        return {}, msg


def _err(image_path: str, msg: str) -> dict:
    logger.error(msg)
    return {
        "image_path": image_path, "vendor": "Unknown", "vendor_profile": "Unknown",
        "extracted": {}, "model_used": CLAUDE_MODEL, "llm_error": msg, "status": "error",
    }
