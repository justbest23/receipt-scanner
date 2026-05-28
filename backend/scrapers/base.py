import asyncio
import random
import logging
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1680, "height": 1050},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 800},
]

# Injected into every Playwright page to suppress automation fingerprints
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', { get: () => false });
Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
Object.defineProperty(navigator, 'languages', { get: () => ['en-ZA', 'en'] });
window.chrome = { runtime: {} };
"""


class ProductResult:
    def __init__(
        self,
        store: str,
        name: str,
        price: Optional[float] = None,
        unit: Optional[str] = None,
        per_kg_price: Optional[float] = None,
        url: Optional[str] = None,
        image_url: Optional[str] = None,
        in_stock: bool = True,
    ):
        self.store = store
        self.name = name
        self.price = price
        self.unit = unit
        self.per_kg_price = per_kg_price
        self.url = url
        self.image_url = image_url
        self.in_stock = in_stock

    def to_dict(self) -> dict:
        return {
            "store": self.store,
            "name": self.name,
            "price": self.price,
            "unit": self.unit,
            "per_kg_price": self.per_kg_price,
            "url": self.url,
            "image_url": self.image_url,
            "in_stock": self.in_stock,
        }


class BaseScraper:
    STORE_NAME: str = "unknown"

    def __init__(self):
        self._ua = random.choice(USER_AGENTS)
        self._viewport = random.choice(VIEWPORTS)

    def _http_headers(self, referer: Optional[str] = None) -> dict:
        h = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-ZA,en;q=0.9,af;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }
        if referer:
            h["Referer"] = referer
        return h

    def _api_headers(self, origin: str, referer: Optional[str] = None) -> dict:
        h = {
            "User-Agent": self._ua,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-ZA,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Origin": origin,
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        if referer:
            h["Referer"] = referer
        return h

    async def _delay(self, min_s: float = 1.5, max_s: float = 4.0):
        await asyncio.sleep(random.uniform(min_s, max_s))

    def _new_client(self, extra_headers: Optional[dict] = None) -> httpx.AsyncClient:
        headers = self._http_headers()
        if extra_headers:
            headers.update(extra_headers)
        return httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=30.0)

    @staticmethod
    def _parse_price(raw: str) -> Optional[float]:
        if not raw:
            return None
        cleaned = (
            str(raw)
            .replace("R", "").replace(" ", "").replace(" ", "")
            .replace(",", ".").strip()
        )
        try:
            return round(float(cleaned), 2)
        except (ValueError, AttributeError):
            return None

    async def _new_pw_context(self, playwright):
        browser = await playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=self._ua,
            viewport=self._viewport,
            locale="en-ZA",
            timezone_id="Africa/Johannesburg",
            extra_http_headers={"Accept-Language": "en-ZA,en;q=0.9"},
        )
        await context.add_init_script(STEALTH_JS)
        return browser, context

    async def search(self, query: str) -> list[ProductResult]:
        raise NotImplementedError
