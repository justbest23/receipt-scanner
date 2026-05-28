"""
Woolworths scraper — uses their public search JSON API.
Endpoint: https://www.woolworths.co.za/server/search-service/search/results
Falls back to Playwright if the API returns an unexpected structure.
"""
import logging
from typing import Optional
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

API_URL = "https://www.woolworths.co.za/server/search-service/search/results"
SITE    = "https://www.woolworths.co.za"


class WoolworthsScraper(BaseScraper):
    STORE_NAME = "woolworths"

    async def search(self, query: str) -> list[ProductResult]:
        params = {
            "pageSize": "24",
            "q": query,
            "start": "0",
            "suggestedSearchEnabled": "false",
            "newBrowseEnabled": "true",
        }
        headers = self._api_headers(origin=SITE, referer=f"{SITE}/store/cat/Food/")
        headers["Accept"] = "application/json, text/plain, */*"

        try:
            async with self._new_client(extra_headers=headers) as client:
                resp = await client.get(API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

            results = self._parse_api(data, query)
            if results:
                logger.info(f"Woolworths API: {len(results)} results for '{query}'")
                return results
        except Exception as e:
            logger.warning(f"Woolworths API failed ({e}), trying Playwright")

        return await self._playwright_search(query)

    def _parse_api(self, data: dict, query: str) -> list[ProductResult]:
        results = []
        products = (
            data.get("products", {}).get("results", [])
            or data.get("results", [])
            or []
        )
        for p in products[:20]:
            name = p.get("name") or p.get("displayName") or ""
            if not name:
                continue

            price_info = p.get("price", {}) or {}
            raw_price  = price_info.get("formattedValue") or price_info.get("value")
            price      = self._parse_price(str(raw_price)) if raw_price else None

            # Some products list price per kg separately
            raw_ppkg  = p.get("pricePerKg") or price_info.get("pricePerKg")
            per_kg    = self._parse_price(str(raw_ppkg)) if raw_ppkg else None

            unit = p.get("displayUnitOfMeasure") or p.get("unitOfMeasure") or ""
            url  = f"{SITE}{p.get('url', '')}" if p.get("url") else None
            img  = self._first_image(p)

            results.append(ProductResult(
                store=self.STORE_NAME,
                name=name,
                price=price,
                unit=unit or None,
                per_kg_price=per_kg,
                url=url,
                image_url=img,
                in_stock=p.get("availableInSelectedStore", True),
            ))
        return results

    @staticmethod
    def _first_image(p: dict) -> Optional[str]:
        imgs = p.get("images") or []
        if imgs and isinstance(imgs, list):
            return imgs[0].get("url")
        return None

    async def _playwright_search(self, query: str) -> list[ProductResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        url = f"{SITE}/store/cat/Food/?q={query}"
        results: list[ProductResult] = []

        async with async_playwright() as p:
            browser, context = await self._new_pw_context(p)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await self._delay(2, 4)

                cards = await page.query_selector_all(
                    "[class*='product-card'], [class*='product_card'], "
                    "[data-testid='product-card'], article[class*='product']"
                )
                for card in cards[:20]:
                    try:
                        name_el = await card.query_selector(
                            "h3, [class*='product-name'], [class*='productName'], "
                            "[class*='title'], a[class*='product']"
                        )
                        price_el = await card.query_selector(
                            "[class*='price']:not([class*='per-kg']):not([class*='perKg']), "
                            "[data-testid='price'], strong[class*='price']"
                        )
                        name  = (await name_el.inner_text()).strip() if name_el else ""
                        price = self._parse_price(
                            (await price_el.inner_text()).strip() if price_el else ""
                        )
                        if name:
                            results.append(ProductResult(
                                store=self.STORE_NAME,
                                name=name,
                                price=price,
                            ))
                    except Exception:
                        continue
            finally:
                await browser.close()

        logger.info(f"Woolworths Playwright: {len(results)} results for '{query}'")
        return results
