"""
Woolworths scraper — Playwright-based (API no longer returns JSON).
URL: https://www.woolworths.co.za/store/cat/Food/?q={query}
"""
import logging
from typing import Optional
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE = "https://www.woolworths.co.za"


class WoolworthsScraper(BaseScraper):
    STORE_NAME = "woolworths"

    async def search(self, query: str) -> list[ProductResult]:
        return await self._playwright_search(query)

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
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                await self._delay(3, 5)

                cards = await page.query_selector_all("[class*='product-card']")
                logger.info(f"Woolworths: {len(cards)} cards for '{query}'")

                for card in cards[:24]:
                    try:
                        name_el = await card.query_selector(
                            "[class*='product-card__name'] a, "
                            "[class*='product-card__name'], "
                            ".range--title a, h3"
                        )
                        price_el = await card.query_selector(
                            ".product__price, [class*='product__price'], "
                            ".price:not([class*='per-kg']):not([class*='was'])"
                        )
                        name  = (await name_el.inner_text()).strip() if name_el else ""
                        price = self._parse_price(
                            (await price_el.inner_text()).strip() if price_el else ""
                        )
                        if not name:
                            continue

                        # Per-kg price
                        pkg_el = await card.query_selector(
                            "[class*='per-kg'], [class*='pricePerKg'], [class*='per_kg']"
                        )
                        per_kg = self._parse_price(
                            (await pkg_el.inner_text()).strip() if pkg_el else ""
                        )

                        link_el = await card.query_selector("a[href*='/prod/']")
                        url_val = None
                        if link_el:
                            href = await link_el.get_attribute("href")
                            if href:
                                url_val = href if href.startswith("http") else f"{SITE}{href}"

                        img_el  = await card.query_selector("img[src*='woolworthsstatic']")
                        img_url = await img_el.get_attribute("src") if img_el else None

                        results.append(ProductResult(
                            store=self.STORE_NAME,
                            name=name,
                            price=price,
                            per_kg_price=per_kg,
                            url=url_val,
                            image_url=img_url,
                        ))
                    except Exception as e:
                        logger.debug(f"Woolworths card error: {e}")

                if not results:
                    logger.warning(f"Woolworths: no products extracted for '{query}'")
            except Exception as e:
                logger.error(f"Woolworths scrape error: {e}")
            finally:
                await browser.close()

        logger.info(f"Woolworths: {len(results)} results for '{query}'")
        return results
