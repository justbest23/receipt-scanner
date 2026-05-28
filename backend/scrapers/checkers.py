"""
Checkers scraper — Playwright-based.
Checkers uses a heavily JS-rendered React app with bot detection.
URL: https://www.checkers.co.za/search?q={query}

If selectors break, inspect the search page and update SELECTORS below.
"""
import logging
import random
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE = "https://www.checkers.co.za"

# Ordered from most to least specific — first match wins per field
SELECTORS = {
    "card": [
        "[class*='product-card']",
        "[data-testid*='product']",
        "article[class*='product']",
        "[class*='ProductCard']",
        "li[class*='product']",
    ],
    "name": [
        "[class*='product-card__name']",
        "[class*='ProductName']",
        "h3[class*='name']",
        "h2[class*='name']",
        "[data-testid='product-name']",
        "a[class*='product'] span",
        "h3",
    ],
    "price": [
        "[class*='product-card__price'] [class*='now']",
        "[class*='product-card__price']",
        "[class*='price--now']",
        "[data-testid='product-price']",
        "[class*='Price']",
        "strong[class*='price']",
    ],
    "unit": [
        "[class*='product-card__unit']",
        "[class*='ProductUnit']",
        "[class*='pricePerUnit']",
        "[class*='price-per']",
    ],
}


class CheckersScraper(BaseScraper):
    STORE_NAME = "checkers"

    async def search(self, query: str) -> list[ProductResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed — run: playwright install chromium --with-deps")
            return []

        url = f"{SITE}/search?q={query}"
        results: list[ProductResult] = []

        async with async_playwright() as p:
            browser, context = await self._new_pw_context(p)
            page = await context.new_page()
            try:
                logger.info(f"Checkers: navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                # Wait for product cards (up to 8 s)
                card_sel = ", ".join(SELECTORS["card"])
                try:
                    await page.wait_for_selector(card_sel, timeout=8000)
                except Exception:
                    logger.warning("Checkers: no product cards appeared within timeout")

                await page.wait_for_timeout(random.randint(800, 1500))

                for card_selector in SELECTORS["card"]:
                    cards = await page.query_selector_all(card_selector)
                    if cards:
                        logger.debug(f"Checkers: matched card selector '{card_selector}' → {len(cards)} cards")
                        for card in cards[:24]:
                            r = await self._extract_card(card, query)
                            if r:
                                results.append(r)
                        break  # use first selector that matched

                if not results:
                    logger.warning(f"Checkers: no products extracted for '{query}'")
            except Exception as e:
                logger.error(f"Checkers scrape error: {e}")
            finally:
                await browser.close()

        logger.info(f"Checkers: {len(results)} results for '{query}'")
        return results

    async def _extract_card(self, card, query: str) -> ProductResult | None:
        try:
            name = await self._first_text(card, SELECTORS["name"])
            if not name:
                return None

            price_raw = await self._first_text(card, SELECTORS["price"])
            price = self._parse_price(price_raw)

            unit_raw  = await self._first_text(card, SELECTORS["unit"])

            # Detect per-kg pricing from unit text
            per_kg = None
            if unit_raw and "kg" in unit_raw.lower() and price:
                try:
                    per_kg = price  # e.g. "R89.99/kg" means price IS per kg
                except Exception:
                    pass

            # Try to get product URL
            link_el = await card.query_selector("a[href]")
            url = None
            if link_el:
                href = await link_el.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else f"{SITE}{href}"

            # Image
            img_el = await card.query_selector("img[src]")
            img_url = None
            if img_el:
                img_url = await img_el.get_attribute("src")

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
            logger.debug(f"Checkers card extraction error: {e}")
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
