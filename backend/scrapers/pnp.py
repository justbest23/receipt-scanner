"""
Pick n Pay scraper — Playwright-based.
URL: https://www.pnp.co.za/search?q={query}

PnP migrated to an Angular/Spartacus SPA (2024). The old Hybris storefront
at /pnpstorefront/ no longer serves products.

The new site requires a delivery-area selection before rendering product prices.
In headless Chrome the Angular app boots but the product search component
does not fire without a store context cookie. Results are therefore unreliable
— this scraper makes a best-effort attempt and returns what it finds.
"""
import logging
import random
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)

SITE = "https://www.pnp.co.za"


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
            page = await context.new_page()
            try:
                url = f"{SITE}/search?q={query}"
                logger.info(f"PnP: navigating to {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=35000)
                await page.wait_for_timeout(4000)

                # Dismiss consent / store-selection dialogs
                for sel in [
                    "button:has-text('Do this later')",
                    "button:has-text('Accept')",
                    "button:has-text('Close')",
                    "[id*='consent'] button",
                ]:
                    try:
                        if await page.locator(sel).count() > 0:
                            await page.locator(sel).first.click()
                            await page.wait_for_timeout(800)
                    except Exception:
                        pass

                # Wait for Angular product list
                try:
                    await page.wait_for_selector(
                        "pnp-product-grid-item, .product-grid-item, [class*='product-grid-item']",
                        timeout=12000,
                    )
                except Exception:
                    logger.warning(f"PnP: no product cards appeared for '{query}'")

                await page.wait_for_timeout(random.randint(1000, 2000))

                for sel in [
                    "pnp-product-grid-item",
                    ".product-grid-item",
                    "[class*='product-grid-item']",
                    "pnp-product-list-item",
                ]:
                    cards = await page.query_selector_all(sel)
                    if cards:
                        logger.debug(f"PnP: {len(cards)} cards with '{sel}'")
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
            name_el = await card.query_selector(
                "[class*='product-name'], [class*='productName'], "
                ".product-title, h3, h2, a[class*='product']"
            )
            price_el = await card.query_selector(
                ".plp-price, [class*='plp-price'], [class*='cur-price'], "
                "[class*='current-price'], .price, [class*='Price']"
            )
            name  = (await name_el.inner_text()).strip() if name_el else ""
            if not name:
                return None
            price = self._parse_price(
                (await price_el.inner_text()).strip() if price_el else ""
            )

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
            logger.debug(f"PnP card error: {e}")
            return None
