"""
Uitkyk parser — no website scraping; Uitkyk is a local store.
Parses the CSV export format:  Count,Item,Cost,Type
e.g.  "0.332 @ 105.00,Porkalicious Magic Rashers P/Kg,34.86,#1"
"""
import csv
import io
import re
import logging
from typing import Optional
from .base import ProductResult

logger = logging.getLogger(__name__)

STORE = "uitkyk"


def parse_csv(csv_text: str) -> list[ProductResult]:
    results: list[ProductResult] = []
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    for row in reader:
        name  = (row.get("Item") or "").strip()
        if not name:
            continue

        cost_str = (row.get("Cost") or "").strip()
        try:
            total_price = float(cost_str) if cost_str else None
        except ValueError:
            total_price = None

        count_str = (row.get("Count") or "").strip()
        price, per_kg = _parse_count(count_str, total_price, name)

        results.append(ProductResult(
            store=STORE,
            name=name,
            price=price,
            unit=_infer_unit(count_str, name),
            per_kg_price=per_kg,
        ))

    logger.info(f"Uitkyk CSV: parsed {len(results)} items")
    return results


def _parse_count(count_str: str, total: Optional[float], name: str):
    """
    count_str examples:
      "2 @ 35.99"   → qty=2, unit_price=35.99
      "0.332 @ 105.00" → weight=0.332 kg, per_kg=105.00
      ""             → unknown qty
    """
    if not count_str:
        return total, None

    m = re.match(r"([\d.]+)\s*@\s*([\d.]+)", count_str)
    if m:
        qty       = float(m.group(1))
        unit_p    = float(m.group(2))
        is_weight = qty < 10 and "p/kg" in name.lower()
        if is_weight:
            return total, unit_p   # price is per-kg
        return unit_p, None        # price is per unit
    return total, None


def _infer_unit(count_str: str, name: str) -> Optional[str]:
    if "p/kg" in name.lower():
        return "per kg"
    if count_str and "@" in count_str:
        m = re.match(r"([\d.]+)\s*@", count_str)
        if m:
            qty = float(m.group(1))
            return f"{qty} kg" if qty < 10 else f"{int(qty)} units"
    return None
