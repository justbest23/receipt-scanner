"""
Uitkyk scraper — full catalog import from uitkyk.online (nopCommerce).

Strategy: crawl every category page-by-page, fetch each product card via
/archsearch/getproduct/{id}, parse name + price, normalize with Claude Haiku.

Why not autocomplete?  The /searchtermautocomplete endpoint only works for
specific multi-word product names (e.g. "clover milk"), not generic ingredient
terms (e.g. "milk" returns Robertson's spices). Full-catalog import + local
DB lookup is far more reliable.
"""

import re
import csv
import io
import logging
import asyncio
from typing import Optional

import httpx

from .base import ProductResult, BaseScraper

logger = logging.getLogger(__name__)

STORE = "uitkyk"
BASE  = "https://uitkyk.online"

# Top-level category IDs (from category filter widget on the search page)
CATEGORIES = {
    2375: "Deli",
    2376: "Fruit & Vegetables",
    2377: "Bakery",
    2379: "Butchery",
    2380: "Health & Beauty",
    2381: "Household",
    2382: "Pet Care",
    2383: "Outdoor",
    2384: "Groceries",
}


class UitkykScraper(BaseScraper):
    STORE_NAME = STORE

    async def search(self, query: str) -> list[ProductResult]:
        """
        Single-query search is not reliable on Uitkyk.
        Callers should use import_full_catalog() instead and query the DB.
        This fallback does a best-effort autocomplete search.
        """
        return await _autocomplete_search(query, self._ua)

    async def import_full_catalog(self) -> list[ProductResult]:
        """
        Crawl every category and every page, return all products.
        Typically ~300–500 products; takes ~2-3 minutes with polite delays.
        """
        all_ids: list[str] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": self._ua, "Referer": f"{BASE}/search",
                     "HX-Request": "true"},
            follow_redirects=True,
        ) as client:
            # Step 1: collect all product IDs from all categories
            for cat_id, cat_name in CATEGORIES.items():
                page = 1
                while True:
                    ids, max_page = await _fetch_category_page(client, cat_id, page)
                    new = [i for i in ids if i not in seen_ids]
                    seen_ids.update(new)
                    all_ids.extend(new)
                    logger.info(f"Uitkyk catalog: {cat_name} p{page}/{max_page} → {len(new)} new IDs")
                    if page >= max_page or not ids:
                        break
                    page += 1
                    await asyncio.sleep(0.8)

            logger.info(f"Uitkyk catalog: {len(all_ids)} unique product IDs across all categories")

            # Step 2: fetch each product card
            results: list[ProductResult] = []
            for i, pid in enumerate(all_ids):
                product = await _fetch_product(client, pid)
                if product:
                    results.append(product)
                if i > 0 and i % 20 == 0:
                    logger.info(f"Uitkyk catalog: fetched {i}/{len(all_ids)} products")
                    await asyncio.sleep(0.5)
                else:
                    await asyncio.sleep(0.15)

        logger.info(f"Uitkyk catalog import complete: {len(results)} products")
        return results


async def _fetch_category_page(
    client: httpx.AsyncClient, cat_id: int, page: int
) -> tuple[list[str], int]:
    try:
        resp = await client.post(
            f"{BASE}/search",
            data={
                "q": "", "adv": "false",
                "cid": str(cat_id),
                "cats[]": str(cat_id),
                "orderby": "0",
                "PageSize": "20",
                "PageNumber": str(page),
                "PageIndex": str(page - 1),
                "f": "",
                "filterType": "category",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        html = resp.text
        ids = re.findall(r'archsearch/getproduct/(\d+)', html)
        pages = [int(p) for p in re.findall(r'PageNumber=(\d+)', html)]
        return ids, max(pages, default=1)
    except Exception as e:
        logger.warning(f"Category page fetch failed (cat={cat_id} p={page}): {e}")
        return [], 1


async def _fetch_product(client: httpx.AsyncClient, product_id: str) -> Optional[ProductResult]:
    try:
        resp = await client.get(
            f"{BASE}/archsearch/getproduct/{product_id}",
            headers={"HX-Request": "true"},
        )
        html = resp.text

        name_m  = re.search(r'class="product-title[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>', html, re.DOTALL)
        price_m = re.search(r'actual-price[^>]*>(.*?)</span>', html, re.DOTALL)
        url_m   = re.search(r'class="product-title[^"]*"[^>]*>.*?<a href="([^"]+)"', html, re.DOTALL)
        img_m   = re.search(r'<img[^>]+src="([^"]+uitkyk\.online[^"]+)"', html)

        if not name_m:
            return None

        name  = re.sub(r'\s+', ' ', name_m.group(1)).strip()
        raw_p = re.sub(r'\s+', ' ', price_m.group(1)).strip() if price_m else ""
        price = _parse_r_price(raw_p)
        url   = url_m.group(1) if url_m else None
        if url and not url.startswith("http"):
            url = BASE + url

        return ProductResult(
            store=STORE,
            name=name,
            price=price,
            url=url,
            image_url=img_m.group(1) if img_m else None,
            in_stock=True,
        )
    except Exception as e:
        logger.warning(f"Product fetch failed (id={product_id}): {e}")
        return None


async def _autocomplete_search(query: str, ua: str) -> list[ProductResult]:
    """
    Fallback: use the autocomplete API for a specific multi-word query.
    Works best with brand+product terms (e.g. 'clover milk'), not generic terms.
    """
    terms = _build_search_terms(query)
    seen: dict[str, ProductResult] = {}

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for term in terms:
            encoded = "+".join(term.lower().split())
            try:
                resp = await client.get(
                    f"{BASE}/searchtermautocomplete",
                    params={"term": encoded},
                    headers={"User-Agent": ua, "Referer": f"{BASE}/",
                             "Accept": "application/json"},
                )
                data = resp.json()
                for item in data:
                    if not item.get("label"):
                        continue
                    url = item.get("producturl", "")
                    if url and not url.startswith("http"):
                        url = BASE + url
                    if url not in seen:
                        seen[url] = ProductResult(
                            store=STORE,
                            name=item["label"],
                            price=_parse_r_price(item.get("price", "")),
                            url=url,
                            image_url=item.get("productpictureurl"),
                            in_stock=True,
                        )
                if seen:
                    break
            except Exception as e:
                logger.warning(f"Autocomplete failed for '{term}': {e}")
            await asyncio.sleep(0.3)

    return list(seen.values())


def _parse_r_price(raw: str) -> Optional[float]:
    cleaned = re.sub(r"[R\s\xa0]", "", raw).replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except (ValueError, AttributeError):
        return None


def _build_search_terms(canonical: str) -> list[str]:
    words = canonical.strip().lower().split()
    skip  = {"a", "an", "the", "and", "or", "of", "with", "in", "for", "fresh", "low"}
    terms = []
    if len(words) >= 2:
        terms.append(canonical.strip())
    for w in words:
        if len(w) >= 4 and w not in skip:
            terms.append(w)
            break
    if canonical.strip() not in terms:
        terms.append(canonical.strip())
    return terms or [canonical.strip()]


# ── Legacy CSV parser (kept for manual imports) ───────────────────────────────

def parse_csv(csv_text: str) -> list[ProductResult]:
    results: list[ProductResult] = []
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    for row in reader:
        name = (row.get("Item") or "").strip()
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
            store=STORE, name=name, price=price,
            unit=_infer_unit(count_str, name), per_kg_price=per_kg,
        ))
    logger.info(f"Uitkyk CSV: parsed {len(results)} items")
    return results


def _parse_count(count_str, total, name):
    if not count_str:
        return total, None
    m = re.match(r"([\d.]+)\s*@\s*([\d.]+)", count_str)
    if m:
        qty, unit_p = float(m.group(1)), float(m.group(2))
        if qty < 10 and "p/kg" in name.lower():
            return total, unit_p
        return unit_p, None
    return total, None


def _infer_unit(count_str, name):
    if "p/kg" in name.lower():
        return "per kg"
    if count_str and "@" in count_str:
        m = re.match(r"([\d.]+)\s*@", count_str)
        if m:
            qty = float(m.group(1))
            return f"{qty} kg" if qty < 10 else f"{int(qty)} units"
    return None
