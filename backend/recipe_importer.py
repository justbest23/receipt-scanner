"""
recipe_importer.py — fetch a recipe URL and extract structured data.

Strategy (in order):
  1. Parse schema.org/Recipe JSON-LD  (works on AllRecipes, BBC Good Food,
     Woolworths Food, most SA food blogs, Food Network, etc.)
  2. Parse <script type="application/ld+json"> with @graph containing Recipe
  3. Raise ValueError if nothing is found — caller should surface this to user.

Ingredient strings are then parsed into {ingredient_name, quantity, unit}.
"""

import json
import re
import logging
from typing import Optional
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Fraction / unicode helpers ────────────────────────────────────────────────

_UNICODE_FRACTIONS = {
    "½": "0.5", "¼": "0.25", "¾": "0.75",
    "⅓": "0.333", "⅔": "0.667",
    "⅛": "0.125", "⅜": "0.375", "⅝": "0.625", "⅞": "0.875",
}

# Maps unit strings → canonical unit stored in DB
_UNITS: dict[str, str] = {
    # volume
    "cup": "cup", "cups": "cup",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "ml": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    # weight
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "mg": "mg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "pound": "lb", "pounds": "lb",
    # count / non-metric
    "piece": "unit", "pieces": "unit",
    "can": "unit", "cans": "unit",
    "tin": "unit", "tins": "unit",
    "clove": "unit", "cloves": "unit",
    "head": "unit", "heads": "unit",
    "bunch": "unit", "bunches": "unit",
    "sprig": "unit", "sprigs": "unit",
    "stalk": "unit", "stalks": "unit",
    "slice": "unit", "slices": "unit",
    "sheet": "unit", "sheets": "unit",
    "handful": "unit", "handfuls": "unit",
    "pinch": "unit", "pinches": "unit",
    "dash": "unit", "dashes": "unit",
    "drop": "unit", "drops": "unit",
    "rasher": "unit", "rashers": "unit",
    # SA-isms
    "pakkie": "unit", "pak": "unit",
    "braai": "unit",  # "2 braai chops"
}

# Size adjectives that appear before the ingredient (not units)
_SIZE_WORDS = {"small", "medium", "large", "big", "extra-large", "xl"}


# ── Public API ────────────────────────────────────────────────────────────────

async def fetch_recipe(url: str) -> dict:
    """
    Fetch *url* and return a dict ready to create a recipe:
      {name, servings, instructions, source_url, ingredients: [{ingredient_name, quantity, unit, notes}]}
    Raises ValueError if no recipe schema is found.
    """
    html = await _get_html(url)
    schema = _extract_schema(html)

    if not schema:
        raise ValueError(
            "Could not find a recipe on that page. "
            "The site may not use standard schema.org markup."
        )

    name         = schema.get("name") or "Imported Recipe"
    servings     = _parse_servings(schema.get("recipeYield"))
    instructions = _parse_instructions(schema.get("recipeInstructions", []))
    raw_ings     = schema.get("recipeIngredient", [])

    ingredients = [parse_ingredient_string(s) for s in raw_ings if s.strip()]

    return {
        "name":         name.strip(),
        "servings":     servings,
        "instructions": instructions,
        "source_url":   url,
        "ingredients":  ingredients,
    }


def parse_ingredient_string(raw: str) -> dict:
    """
    Parse a human-readable ingredient string into structured data.

    Examples handled:
      "500g chicken breast, cubed"   → {name: "chicken breast", qty: 500, unit: "g"}
      "2 tbsp olive oil"             → {name: "olive oil",      qty: 2,   unit: "tbsp"}
      "1/2 tsp salt"                 → {name: "salt",           qty: 0.5, unit: "tsp"}
      "1 large onion, finely diced"  → {name: "onion",          qty: 1,   unit: "unit"}
      "pinch of sugar"               → {name: "sugar",          qty: 1,   unit: "unit"}
      "2 x 400g cans tomatoes"       → {name: "tomatoes",       qty: 2,   unit: "unit"}
    """
    s = raw.strip()

    # Normalise unicode fractions
    for uf, repl in _UNICODE_FRACTIONS.items():
        s = s.replace(uf, repl)

    # Strip HTML entities / parenthetical pack-size notes like "(400g)"
    s = re.sub(r"\([^)]*\)", " ", s).strip()

    qty  = 1.0
    unit = "unit"
    name = s

    # ── Handle "N x M..." multiplier form  e.g. "2 x 400g cans tomatoes"
    mx = re.match(r"^(\d+(?:\.\d+)?)\s*[xX×]\s*(.*)", s)
    if mx:
        qty = float(mx.group(1))
        s = mx.group(2).strip()

    # ── Number (possibly mixed number or fraction) at start
    num_pat = (
        r"^"
        r"(\d+(?:\.\d+)?)"              # integer or decimal
        r"(?:\s*[-–]\s*\d+(?:\.\d+)?)?" # range like "1-2" → take first
        r"(?:\s+(\d+)/(\d+))?"          # mixed number: "1 1/2"
        r"(?:\s*/\s*(\d+(?:\.\d+)?))?"  # plain fraction tail: "1/2"
        r"\s*(.*)"
    )
    m = re.match(num_pat, s)
    if m:
        base = float(m.group(1))
        if m.group(2) and m.group(3):   # mixed number: 1 1/2
            base += float(m.group(2)) / float(m.group(3))
        elif m.group(4):                # plain fraction: 1/2 (already partial)
            base = base / float(m.group(4))
        if not mx:                      # don't overwrite multiplier qty
            qty = base
        rest = (m.group(5) or "").strip()
    else:
        rest = s

    # ── Unit detection
    # Try "500g chicken" style (number immediately followed by unit, no space)
    glued = re.match(r"^([a-zA-Z]+)\s+(.*)", rest)
    if glued:
        candidate = glued.group(1).lower().rstrip(".")
        if candidate in _UNITS:
            unit = _UNITS[candidate]
            rest = glued.group(2).strip()
        elif candidate in _SIZE_WORDS:
            rest = glued.group(2).strip()
        # else it's part of the ingredient name

    # Strip preparation notes after comma/semicolon: "onion, finely diced"
    name = re.split(r"[,;]\s*", rest)[0].strip()

    # Clean up leading articles / "of"
    name = re.sub(r"^(of|the|a|an)\s+", "", name, flags=re.IGNORECASE).strip()

    # Final fallback
    if not name:
        name = raw.strip()

    return {
        "ingredient_name": name,
        "quantity":        round(qty, 3),
        "unit":            unit,
        "notes":           None,
    }


# ── Internals ────────────────────────────────────────────────────────────────

async def _get_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-ZA,en;q=0.9",
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


def _extract_schema(html: str) -> Optional[dict]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        # Direct Recipe object
        if isinstance(data, dict) and _is_recipe(data):
            return data

        # Array of objects
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and _is_recipe(item):
                    return item

        # @graph container
        if isinstance(data, dict):
            for item in data.get("@graph", []):
                if isinstance(item, dict) and _is_recipe(item):
                    return item

    return None


def _is_recipe(obj: dict) -> bool:
    t = obj.get("@type", "")
    if isinstance(t, list):
        return any("Recipe" in str(x) for x in t)
    return "Recipe" in str(t)


def _parse_servings(raw) -> int:
    if raw is None:
        return 4
    if isinstance(raw, int):
        return raw
    if isinstance(raw, list):
        raw = raw[0] if raw else "4"
    m = re.search(r"\d+", str(raw))
    return int(m.group()) if m else 4


def _parse_instructions(raw) -> str:
    """Flatten schema.org recipeInstructions to a plain text string."""
    if not raw:
        return ""

    if isinstance(raw, str):
        return raw.strip()

    steps = []
    for i, item in enumerate(raw, 1):
        if isinstance(item, str):
            steps.append(f"{i}. {item.strip()}")
        elif isinstance(item, dict):
            text = item.get("text") or item.get("name") or ""
            if text:
                steps.append(f"{i}. {text.strip()}")

    return "\n".join(steps)
