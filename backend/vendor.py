"""
vendor.py — Vendor detection and profile management

Stage 1 of the pipeline:
  1. Quick LLM call to identify the vendor from the receipt image
  2. Fuzzy match against known vendor aliases
  3. Load and return the vendor profile
  4. Fall back to unknown.json if no match
"""

import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger("vendor")

OLLAMA_URL    = os.getenv("OLLAMA_URL",   "http://ollama:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL", "llama3.2-vision:11b")
VENDORS_DIR   = Path(__file__).parent / "vendors"

# ── Load all vendor profiles at import time ───────────────────────────────────
_profiles: dict[str, dict] = {}

def _load_profiles():
    for path in VENDORS_DIR.glob("*.json"):
        try:
            profile = json.loads(path.read_text())
            _profiles[path.stem] = profile
            logger.info(f"Loaded vendor profile: {path.stem}")
        except Exception as e:
            logger.warning(f"Failed to load vendor profile {path}: {e}")

_load_profiles()


# ── Public API ────────────────────────────────────────────────────────────────

def detect_vendor(image_b64: str, model: str | None = None) -> dict:
    """
    Detects the vendor from a receipt image.
    Returns the matching vendor profile dict.
    Always returns something — falls back to 'unknown' profile.
    """
    raw_name = _ask_llm(image_b64, model=model)
    logger.info(f"LLM vendor detection returned: '{raw_name}'")

    profile = _match_profile(raw_name)
    logger.info(f"Matched vendor profile: {profile.get('name', 'unknown')}")
    return profile


def get_profile(vendor_name: str) -> dict:
    """Get a profile by vendor name or slug. Falls back to unknown."""
    # Try exact slug match first
    slug = vendor_name.lower().replace(" ", "_").replace("'", "").replace("&", "and")
    if slug in _profiles:
        return _profiles[slug]
    # Try alias match
    return _match_profile(vendor_name)


def list_vendors() -> list[str]:
    """Return list of known vendor names."""
    return [p["name"] for p in _profiles.values() if p.get("name") != "Unknown"]


def build_vendor_prompt_section(profile: dict) -> str:
    """
    Converts a vendor profile into a prompt section to inject into the extraction prompt.
    """
    lines = []
    name = profile.get("name", "Unknown")
    lines.append(f"VENDOR: {name}")
    lines.append("")

    # Store name normalisation
    store_rules = profile.get("store_name_rules", {})
    if store_rules.get("always_output"):
        lines.append(f"STORE NAME: Always output \"{store_rules['always_output']}\" as the store name regardless of what appears on the receipt.")
        lines.append("")

    # VAT indicator
    vat = profile.get("vat_indicator", {})
    if vat.get("type") == "price_suffix":
        lines.append(f"VAT MARKING: {vat['description']}")
        lines.append(f"  Use this instead of guessing from product category — it is printed directly on the receipt.")
        lines.append("")
    elif vat.get("description"):
        lines.append(f"VAT MARKING: {vat['description']}")
        lines.append("")

    # Quantity rules
    qty = profile.get("quantity_rules", {})
    if qty.get("description") and "PLACEHOLDER" not in qty["description"]:
        lines.append(f"QUANTITY RULES: {qty['description']}")
        if qty.get("examples"):
            for ex in qty["examples"]:
                lines.append(f"  - {ex}")
        lines.append("")

    # Product name rules
    names = profile.get("product_name_rules", {})
    if names.get("description") and "PLACEHOLDER" not in names["description"]:
        lines.append(f"PRODUCT NAME RULES: {names['description']}")
        if names.get("patterns"):
            for p in names["patterns"]:
                lines.append(f"  - {p}")
        lines.append("")

    # Weight rules
    weight = profile.get("weight_rules", {})
    if weight.get("description") and "PLACEHOLDER" not in weight["description"] and "Not applicable" not in weight["description"]:
        lines.append(f"WEIGHT AND PER-KG PRICE RULES: {weight['description']}")
        if weight.get("examples"):
            for ex in weight["examples"]:
                lines.append(f"  - {ex}")
        lines.append("")

    # Discount rules
    discounts = profile.get("discount_rules", {})
    if discounts.get("description") and "PLACEHOLDER" not in discounts["description"]:
        lines.append(f"DISCOUNT RULES: {discounts['description']}")
        if discounts.get("examples"):
            for ex in discounts["examples"]:
                lines.append(f"  - {ex}")
        lines.append("")

    # Item count rules
    count_rules = profile.get("item_count_rules", {})
    if count_rules.get("description"):
        lines.append(f"ITEM COUNT: {count_rules['description']}")
        lines.append("")

    # Extra notes
    notes = profile.get("prompt_notes", [])
    active_notes = [n for n in notes if "PLACEHOLDER" not in n]
    if active_notes:
        lines.append("ADDITIONAL VENDOR NOTES:")
        for note in active_notes:
            lines.append(f"  - {note}")
        lines.append("")

    return "\n".join(lines)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ask_llm(image_b64: str, model: str | None = None) -> str:
    """Fast LLM call — just asks for the store/vendor name. Returns empty string on failure."""
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":  model or OLLAMA_MODEL,
                "prompt": "What store or retailer is shown on this receipt? Reply with ONLY the store name, maximum 3 words, nothing else.",
                "images": [image_b64],
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 20,
                },
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Vendor LLM detection failed: {e}")
        return ""


def _match_profile(raw_name: str) -> dict:
    """
    Fuzzy-match a raw vendor name string against all known vendor aliases.
    Returns the matching profile or the unknown fallback.
    """
    if not raw_name:
        return _profiles.get("unknown", {})

    normalised = raw_name.lower().strip()

    # Exact name match wins immediately
    for slug, profile in _profiles.items():
        if slug == "unknown":
            continue
        if profile.get("name", "").lower() == normalised:
            return profile

    # Alias match — prefer the longest alias that appears in what the LLM said.
    # Longest match wins so "shoprite checkers" beats "shoprite" when both are in the input.
    best_profile = None
    best_len = 0
    for slug, profile in _profiles.items():
        if slug == "unknown":
            continue
        for alias in [a.lower() for a in profile.get("aliases", [])]:
            if alias in normalised and len(alias) > best_len:
                best_profile = profile
                best_len = len(alias)

    if best_profile:
        return best_profile

    logger.info(f"No vendor match found for '{raw_name}', using unknown fallback")
    return _profiles.get("unknown", {})
