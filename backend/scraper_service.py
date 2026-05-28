"""
Scraper service — orchestrates on-demand searches across all stores.

Cache strategy:
  - Results < CACHE_HOURS old are returned immediately.
  - Stale results trigger a background re-scrape; caller gets old data while new
    data is being fetched.
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy.orm import Session
import models

logger = logging.getLogger(__name__)

CACHE_HOURS  = 12
ONLINE_STORES = ["uitkyk", "checkers", "woolworths", "pnp", "spar"]
ALL_STORES    = ONLINE_STORES


# ── Cache helpers ──────────────────────────────────────────────────────────────

def get_cached_results(
    query: str,
    db: Session,
    max_age_hours: int = CACHE_HOURS,
    store: Optional[str] = None,
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    q = (
        db.query(models.StoreListing)
        .filter(
            models.StoreListing.search_query.ilike(f"%{query.lower()}%"),
            models.StoreListing.scraped_at >= cutoff,
        )
    )
    if store:
        q = q.filter(models.StoreListing.store == store)
    listings = q.order_by(models.StoreListing.store, models.StoreListing.price).all()
    return [_to_dict(l) for l in listings]


def is_cache_fresh(query: str, db: Session, max_age_hours: int = CACHE_HOURS) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return (
        db.query(models.StoreListing.id)
        .filter(
            models.StoreListing.search_query.ilike(f"%{query.lower()}%"),
            models.StoreListing.scraped_at >= cutoff,
        )
        .first()
        is not None
    )


def save_results(query: str, store: str, results: list, db: Session):
    from scrapers.base import ProductResult
    for r in results:
        listing = models.StoreListing(
            store=store,
            store_product_name=r.name,
            search_query=query.lower(),
            price=r.price,
            price_per_kg=r.per_kg_price,
            unit_label=r.unit,
            url=r.url,
            image_url=r.image_url,
            in_stock=r.in_stock,
        )
        db.add(listing)
    db.commit()
    logger.info(f"Saved {len(results)} results from {store} for '{query}'")


# ── Scraping ───────────────────────────────────────────────────────────────────

def _get_scraper(store: str):
    if store == "uitkyk":
        from scrapers.uitkyk import UitkykScraper
        return UitkykScraper()
    if store == "checkers":
        from scrapers.checkers import CheckersScraper
        return CheckersScraper()
    if store == "woolworths":
        from scrapers.woolworths import WoolworthsScraper
        return WoolworthsScraper()
    if store == "pnp":
        from scrapers.pnp import PnPScraper
        return PnPScraper()
    if store == "spar":
        from scrapers.spar import SparScraper
        return SparScraper()
    raise ValueError(f"Unknown online store: {store}")


async def scrape_store(store: str, query: str, db: Session) -> list[dict]:
    try:
        scraper = _get_scraper(store)
        results = await scraper.search(query)
        save_results(query, store, results, db)
        return [r.to_dict() for r in results]
    except Exception as e:
        logger.error(f"Scrape failed [{store}]: {e}")
        return []


async def scrape_all_stores(query: str, db: Session) -> dict[str, list[dict]]:
    tasks = [scrape_store(store, query, db) for store in ONLINE_STORES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        store: (r if isinstance(r, list) else [])
        for store, r in zip(ONLINE_STORES, results)
    }


# ── Serialisation ──────────────────────────────────────────────────────────────

def _to_dict(l: models.StoreListing) -> dict:
    return {
        "id":         l.id,
        "store":      l.store,
        "name":       l.store_product_name,
        "price":      l.price,
        "price_per_kg": l.price_per_kg,
        "unit":       l.unit_label,
        "url":        l.url,
        "image_url":  l.image_url,
        "in_stock":   l.in_stock,
        "scraped_at": l.scraped_at.isoformat() if l.scraped_at else None,
    }


def get_cheapest_per_store(results: list[dict]) -> dict[str, Optional[dict]]:
    """For a list of results, return the cheapest item per store."""
    best: dict[str, Optional[dict]] = {}
    for r in results:
        store = r["store"]
        # Use per_kg price if available (apples-to-apples), else unit price
        compare_price = r.get("price_per_kg") or r.get("price")
        if compare_price is None:
            continue
        existing = best.get(store)
        existing_price = (existing or {}).get("price_per_kg") or (existing or {}).get("price")
        if existing is None or compare_price < (existing_price or float("inf")):
            best[store] = r
    return best
