"""
Pick n Pay scraper — Playwright-based.
URL: https://www.pnp.co.za/pnpstorefront/pnp/en/All-Products/?q={query}

PnP's storefront requires a store selection cookie; without it you get generic results.
The scraper loads the page and accepts whatever prices are shown.

If selectors break, inspect the search results page and update SELECTORS.
"""
import logging
import random
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE       = "https://www.pnp.co.za"
SEARCH_URL = f"{SITE}/pnpstorefront/pnp/en/All-Products/"

SELECTORS = {
    "card": [
        ".product--details",
        "[class*='product-item']",
        "[class*='ProductItem']",
        "li[class*='product']",
        "article[class*='product']",
        ".product-listing__item",
    ],
    "name": [
        ".product--description a",
        "[class*='product-name']",
        "[class*='ProductName']",
        "h3 a",
        "h2 a",
        ".product--title",
        "a[class*='product']",
    ],
    "price": [
        ".product--cur-price",
        "[class*='current-price']",
        "[class*='price--current']",
        ".priceBadge",
        "[class*='Price'] strong",
        "[data-testid='price']",
    ],
    "unit": [
        "[class*='product--size']",
        "[class*='unit-price']",
        ".product--size",
    ],
}


class PnPScraper(BaseScraper):
    STORE_NAME = "pnp"

    async def search(self, query: str) -> list[ProductResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        results: list[ProductResult] = []

        async with async_playwright() as p:
            browser, context = await self._new_pw_context(p)
            # Set a regional cookie so PnP shows prices
            await context.add_cookies([{
                "name": "ROUTE",
                "value": "pnp",
                "domain": ".pnp.co.za",
                "path": "/",
            }])
            page = await context.new_page()
            try:
                url = f"{SEARCH_URL}?q={query}"
                logger.info(f"PnP: navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)

                card_sel = ", ".join(SELECTORS["card"])
                try:
                    await page.wait_for_selector(card_sel, timeout=8000)
                except Exception:
                    logger.warning("PnP: no product cards appeared")

                await page.wait_for_timeout(random.randint(800, 1500))

                for card_selector in SELECTORS["card"]:
                    cards = await page.query_selector_all(card_selector)
                    if cards:
                        logger.debug(f"PnP: matched '{card_selector}' → {len(cards)} cards")
                        for card in cards[:24]:
                            r = await self._extract_card(card)
                            if r:
                                results.append(r)
                        break

                if not results:
                    logger.warning(f"PnP: no products extracted for '{query}'")
            except Exception as e:
                logger.error(f"PnP scrape error: {e}")
            finally:
                await browser.close()

        logger.info(f"PnP: {len(results)} results for '{query}'")
        return results

    async def _extract_card(self, card) -> ProductResult | None:
        try:
            name = await self._first_text(card, SELECTORS["name"])
            if not name:
                return None

            price_raw = await self._first_text(card, SELECTORS["price"])
            price     = self._parse_price(price_raw)
            unit_raw  = await self._first_text(card, SELECTORS["unit"])

            per_kg = None
            if unit_raw and "/kg" in unit_raw.lower() and price:
                per_kg = price

            link_el = await card.query_selector("a[href]")
            url = None
            if link_el:
                href = await link_el.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else f"{SITE}{href}"

            img_el  = await card.query_selector("img[src]")
            img_url = await img_el.get_attribute("src") if img_el else None

            return ProductResult(
                store=self.STORE_NAME,
                name=name.strip(),
                price=price,
                unit=unit_raw.strip() if unit_raw else None,
                per_kg_price=per_kg,
                url=url,
                image_url=img_url,
            )
        except Exception as e:
            logger.debug(f"PnP card extraction error: {e}")
            return None

    @staticmethod
    async def _first_text(element, selectors: list[str]) -> str:
        for sel in selectors:
            el = await element.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text:
                    return text
        return ""
