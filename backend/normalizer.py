"""
normalizer.py — canonical ingredient name extraction via Claude.

Takes a list of raw product names (e.g. "Clover Full Cream Milk 2L")
and returns a mapping to generic ingredient names (e.g. "Milk").
"""

import json
import logging
import os

logger = logging.getLogger("normalizer")

_PROMPT = """\
You are a grocery ingredient normalizer for South African receipts.

Given a list of grocery product names, return a JSON object that maps each \
original name to a short, generic ingredient category name with NO brand, \
NO size/weight, NO packaging, and NO adjectives unless essential.

Rules:
- Remove brand names (Clover, Pegasus, Albany, Pick n Pay, etc.)
- Remove sizes (2L, 500g, 1kg, 6-pack, etc.)
- Keep the core ingredient/product type
- Use singular form (Tomato not Tomatoes)
- Keep brand only if the brand IS the product (e.g. Coca-Cola, Marmite, Bovril)
- Common mappings: "Full Cream Milk" → "Milk", "White Sugar" → "Sugar", \
"Sliced Brown Bread" → "Brown Bread", "Free Range Eggs" → "Egg", \
"Sunflower Oil" → "Sunflower Oil", "Chicken Breast Fillet" → "Chicken Breast"
- For produce: "Rosa Tomatoes" → "Tomato", "Bulk Onions" → "Onion"
- For prepared/branded foods keep concise: "Lay's Chips" → "Chips"

Return ONLY a valid JSON object, no explanation, no markdown:
{{"original name": "canonical name", ...}}

Product names to normalize:
{names}
"""


def normalize_names(names: list[str]) -> dict[str, str]:
    """Map each name in the list to a canonical ingredient name."""
    if not names:
        return {}

    try:
        import anthropic as _anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping normalization")
        return {}

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping normalization")
        return {}

    client = _anthropic.Anthropic(api_key=api_key)

    # Deduplicate to save tokens
    unique = list(dict.fromkeys(names))
    names_text = "\n".join(f"- {n}" for n in unique)

    try:
        resp = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            max_tokens=4096,
            messages=[{"role": "user", "content": _PROMPT.format(names=names_text)}],
        )
        raw = resp.content[0].text.strip()
        # Strip markdown fences robustly
        import re
        clean = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        clean = re.sub(r'\s*```\s*$', '', clean, flags=re.MULTILINE).strip()
        # Extract first JSON object if there's surrounding text
        m = re.search(r'\{[\s\S]*\}', clean)
        if m:
            clean = m.group(0)
        mapping: dict[str, str] = json.loads(clean)
        if not isinstance(mapping, dict):
            raise ValueError(f"Expected dict, got {type(mapping)}")
        # Return mapping for all original names (deduped result covers duplicates)
        return {n: mapping.get(n, n) for n in names}
    except Exception as e:
        logger.error(f"Normalization failed: {e}")
        return {n: n for n in names}
