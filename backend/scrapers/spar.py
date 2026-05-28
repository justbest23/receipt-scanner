"""
SPAR scraper — Playwright-based.
URL: https://www.spar.co.za/shop/results?query={query}

SPAR's online shop may redirect to a regional store picker.
If selectors break, check the current search results page structure.
"""
import logging
import random
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE       = "https://www.spar.co.za"
SEARCH_URL = f"{SITE}/shop/results"

SELECTORS = {
    "card": [
        ".product-item",
        "[class*='ProductItem']",
        "[class*='product-card']",
        "li[class*='product']",
        ".product-listing-item",
        "[data-testid='product']",
    ],
    "name": [
        ".product-item__name",
        "[class*='product-name']",
        "[class*='ProductName']",
        "h3",
        "h2",
        ".name",
        "a[class*='name']",
    ],
    "price": [
        ".product-item__price .price",
        ".product-price",
        "[class*='price--current']",
        "[class*='ProductPrice']",
        "strong[class*='price']",
        "[data-testid='price']",
        "span[class*='price']",
    ],
    "unit": [
        ".product-item__pack-size",
        "[class*='pack-size']",
        "[class*='unit']",
        ".product-size",
    ],
}


class SparScraper(BaseScraper):
    STORE_NAME = "spar"

    async def search(self, query: str) -> list[ProductResult]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed")
            return []

        results: list[ProductResult] = []

        async with async_playwright() as p:
            browser, context = await self._new_pw_context(p)
            page = await context.new_page()
            try:
                url = f"{SEARCH_URL}?query={query}"
                logger.info(f"SPAR: navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)

                # Dismiss any store picker or popup
                for popup_sel in [
                    "button[class*='close']",
                    "[data-testid='modal-close']",
                    ".modal__close",
                ]:
                    try:
                        btn = await page.query_selector(popup_sel)
                        if btn:
                            await btn.click()
                            await page.wait_for_timeout(500)
                            break
                    except Exception:
                        pass

                card_sel = ", ".join(SELECTORS["card"])
                try:
                    await page.wait_for_selector(card_sel, timeout=8000)
                except Exception:
                    logger.warning("SPAR: no product cards appeared")

                await page.wait_for_timeout(random.randint(800, 1500))

                for card_selector in SELECTORS["card"]:
                    cards = await page.query_selector_all(card_selector)
                    if cards:
                        logger.debug(f"SPAR: matched '{card_selector}' → {len(cards)} cards")
                        for card in cards[:24]:
                            r = await self._extract_card(card)
                            if r:
                                results.append(r)
                        break

                if not results:
                    logger.warning(f"SPAR: no products extracted for '{query}'")
            except Exception as e:
                logger.error(f"SPAR scrape error: {e}")
            finally:
                await browser.close()

        logger.info(f"SPAR: {len(results)} results for '{query}'")
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
            logger.debug(f"SPAR card extraction error: {e}")
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
