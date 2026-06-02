"""
SPAR scraper — currently unsupported.

www.spar.co.za is an informational site for the SPAR franchise network.
South African SPAR does not have a national online grocery shop — individual
franchise regions operate independently and not all have online ordering.

The old URL (/shop/results?query=) returns 404 as of 2026.

If a regional SPAR online shop URL becomes available, this is where to add it.
"""
import logging
from .base import BaseScraper, ProductResult

logger = logging.getLogger(__name__)


class SparScraper(BaseScraper):
    STORE_NAME = "spar"

    async def search(self, query: str) -> list[ProductResult]:
        logger.info("SPAR: no national online shop available — returning empty results")
        return []
