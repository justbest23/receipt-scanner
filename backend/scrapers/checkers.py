"""
Checkers scraper — Playwright-based.
URL: https://www.checkers.co.za/search?q={query}

Checkers uses AWS WAF bot detection that returns 0 results to headless browsers.
This scraper makes a best-effort attempt but is frequently blocked.
The CSS class names use CSS Modules hashing so selectors target data-* attributes.
"""
import logging
import random
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE = "https://www.checkers.co.za"


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
                await page.wait_for_timeout(random.randint(2000, 3500))

                # Check result count to detect bot block
                result_count_el = await page.query_selector("[class*='filter-total']")
                if result_count_el:
                    count_text = (await result_count_el.inner_text()).strip()
                    if "0 Result" in count_text:
                        logger.warning("Checkers: 0 results — likely blocked by bot detection")
                        return []

                # Checkers uses CSS Modules (hashed class names) so target by structure
                card_selectors = [
                    "[class*='product-card__name']",   # inside a card
                    "[class*='ProductCard']",
                    "article[class*='product']",
                    "[data-product-id]",
                    "[class*='product-list__item']",
                ]

                for card_selector in card_selectors:
                    cards = await page.query_selector_all(card_selector)
                    if cards:
                        logger.debug(f"Checkers: {len(cards)} cards with '{card_selector}'")
                        for card in cards[:24]:
                            r = await self._extract_card(card, query)
                            if r:
                                results.append(r)
                        break

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
            # Try various name selectors
            name = ""
            for sel in ["[class*='product-card__name']", "h3", "h2", "[class*='name']"]:
                el = await card.query_selector(sel)
                if el:
                    name = (await el.inner_text()).strip()
                    if name:
                        break
            if not name:
                return None

            # Price
            price_raw = ""
            for sel in [
                "[class*='now']", "[class*='price--now']",
                "[class*='product-card__price']", "[class*='Price']", "strong",
            ]:
                el = await card.query_selector(sel)
                if el:
                    price_raw = (await el.inner_text()).strip()
                    if price_raw:
                        break
            price = self._parse_price(price_raw)

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
                name=name,
                price=price,
                url=url,
                image_url=img_url,
            )
        except Exception as e:
            logger.debug(f"Checkers card error: {e}")
            return None
