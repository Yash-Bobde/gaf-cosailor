"""GAF contractor directory scraper — Playwright + Coveo API hybrid.

GAF's contractor locator is a React SPA whose data comes from a Coveo search
backend (POST *.coveo.com/rest/search/v2). DOM scraping yields nothing because
cards render asynchronously, so the scraper talks to the same API the page does:

1. gaf_browser.capture_first_page — headless Chromium loads the locator once
   (getting past Akamai) and captures GAF's own Coveo token, request body and
   the first 10 results.
2. _paginate_coveo — plain httpx POSTs fetch the remaining pages (100 per call)
   with that token and the browser's cookies.

Windows note: uvicorn on Windows runs a SelectorEventLoop, which cannot spawn
the Playwright driver subprocess. scrape_contractors therefore runs the
scrape in a worker thread that owns a fresh ProactorEventLoop.
"""
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone

import httpx

from app.config import ScraperConfig
from app.models.lead import ContractorRecord
from app.services.errors import ScrapeError
from app.services.gaf_browser import SEC_CH_UA, USER_AGENT, capture_first_page

logger = logging.getLogger(__name__)

GAF_SEARCH_URL = (
    "https://www.gaf.com/en-us/roofing-contractors/{segment}"
    "?postalCode={postal_code}&countryCode={country_code}&distance={distance}"
)

_COVEO_API_URL = (
    "https://gafmaterialscorporationproduction3yalqk12.org.coveo.com"
    "/rest/search/v2?organizationId=gafmaterialscorporationproduction3yalqk12"
)

# Results per httpx pagination page (Coveo accepts up to 100).
_PAGE_SIZE = 100


def build_search_url(config: ScraperConfig) -> str:
    """Return the GAF locator URL for a config — the only place the URL is assembled."""
    return GAF_SEARCH_URL.format(
        segment=config.segment,
        postal_code=config.postal_code,
        country_code=config.country_code,
        distance=config.distance,
    )


def _coerce_str(val) -> str | None:
    if isinstance(val, list):
        return val[0] if val else None
    return val or None


def _extract_certifications(raw: dict) -> list[str]:
    commercial = raw.get("gaf_f_contractor_certifications_and_awards_commercial") or []
    residential = raw.get("gaf_f_contractor_certifications_and_awards_residential") or []
    if isinstance(commercial, str):
        commercial = [commercial]
    if isinstance(residential, str):
        residential = [residential]
    seen: set[str] = set()
    result: list[str] = []
    for cert in commercial + residential:
        if cert and cert not in seen:
            seen.add(cert)
            result.append(cert)
    return result


def _map_coveo_result(result: dict, country_code: str, segment: str) -> ContractorRecord:
    """Map one Coveo search hit to a ContractorRecord.

    The profile link is GAF's own clickUri — it contains a location slug, so it
    cannot be rebuilt from the contractor id alone.
    """
    raw = result.get("raw", {})
    name = _coerce_str(raw.get("gaf_navigation_title")) or result.get("title", "Unknown")
    contractor_id = str(raw.get("gaf_contractor_id", "")).strip() or None
    return ContractorRecord(
        company_name=name,
        gaf_contractor_id=contractor_id,
        city=_coerce_str(raw.get("gaf_f_city")),
        state=_coerce_str(raw.get("gaf_f_state_code")),
        postal_code=_coerce_str(raw.get("gaf_postal_code")),
        country_code=country_code,
        phone=_coerce_str(raw.get("gaf_phone")),
        gaf_profile_url=result.get("clickUri") or _coerce_str(raw.get("uri")),
        certifications=_extract_certifications(raw),
        rating=raw.get("gaf_rating"),
        review_count=raw.get("gaf_number_of_reviews"),
        segment=segment,
    )


def _finalize_results(results: list[dict], config: ScraperConfig) -> list[ContractorRecord]:
    """De-duplicate hits by contractor id (Coveo pages can overlap) and apply the limit."""
    seen: set[str] = set()
    unique: list[dict] = []
    for r in results:
        key = str(r.get("raw", {}).get("gaf_contractor_id", "")).strip() or r.get("title", "")
        if key and key not in seen:
            seen.add(key)
            unique.append(r)
    if config.limit is not None:
        unique = unique[: config.limit]
    return [_map_coveo_result(r, config.country_code, config.segment) for r in unique]


def _page_body(base_body: dict, first_result: int) -> dict:
    """Return a new Coveo request body for one page (base body is never mutated)."""
    return {
        **base_body,
        "firstResult": first_result,
        "numberOfResults": _PAGE_SIZE,
        "analytics": {
            **base_body.get("analytics", {}),
            "clientTimestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

def _api_headers(token: str, cookie_header: str) -> dict[str, str]:
    """Browser-like headers for direct Coveo calls, carrying the captured session."""
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.gaf.com",
        "Referer": "https://www.gaf.com/",
        "User-Agent": USER_AGENT,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
    }
    return {**headers, "Cookie": cookie_header} if cookie_header else headers


class PlaywrightScraper:
    """Scrapes GAF contractors via a one-shot browser capture plus Coveo pagination."""

    async def scrape_contractors(self, config: ScraperConfig) -> list[ContractorRecord]:
        """Entry point — runs the scrape on a ProactorEventLoop worker thread."""
        return await asyncio.to_thread(self._run_in_proactor, config)

    def _run_in_proactor(self, config: ScraperConfig) -> list[ContractorRecord]:
        """Run the async scrape inside a fresh event loop owned by this thread."""
        loop = asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._async_scrape(config))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    async def _async_scrape(self, config: ScraperConfig) -> list[ContractorRecord]:
        """Capture page one in the browser, paginate the rest over HTTP, then map.

        Returns [] only when GAF explicitly reported totalCount=0. A capture
        failure, or a positive totalCount that yields no parseable contractor,
        raises ScrapeError so the run is recorded as failed.
        """
        url = build_search_url(config)
        started = time.monotonic()
        first = await capture_first_page(url)
        if first.total_count == 0 and not first.results:
            logger.info("scrape.empty url=%s gaf_total=0", url)
            return []
        if not first.results:
            raise ScrapeError(
                f"GAF reported {first.total_count} contractors but returned none")

        results = list(first.results)
        wanted = first.total_count if config.limit is None else min(first.total_count, config.limit)
        if wanted > len(results):
            if first.token:
                results += await self._paginate_coveo(
                    first.token, first.request_body, wanted,
                    start=len(results), cookie_header=first.cookie_header,
                )
            else:
                logger.warning("scrape.no_token url=%s kept_first_page=%d wanted=%d",
                               url, len(results), wanted)

        contractors = _finalize_results(results, config)
        if not any(c.gaf_contractor_id for c in contractors):
            raise ScrapeError(
                f"GAF returned {len(results)} results but none could be parsed "
                "(no contractor ids) — the response format may have changed")
        logger.info("scrape.done url=%s gaf_total=%d wanted=%d parsed=%d duration_ms=%d",
                    url, first.total_count, wanted, len(contractors),
                    (time.monotonic() - started) * 1000)
        return contractors

    async def _paginate_coveo(
        self,
        token: str,
        base_body: dict,
        total_count: int,
        start: int,
        cookie_header: str = "",
    ) -> list[dict]:
        """Fetch Coveo pages from `start` up to `total_count` with the captured token.

        Sends the browser's cookies and browser-like headers so Akamai treats the
        httpx calls as the same session. Stops (keeping partial results) on the
        first HTTP error or empty page.
        """
        extra: list[dict] = []
        headers = _api_headers(token, cookie_header)
        first_result = start
        async with httpx.AsyncClient(follow_redirects=True) as client:
            while first_result < total_count:
                body = _page_body(base_body, first_result)
                try:
                    resp = await client.post(_COVEO_API_URL, json=body, headers=headers, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    batch = data.get("results", [])
                    if not batch:
                        logger.warning(
                            "Coveo returned empty batch at firstResult=%d (totalCount=%d); stopping",
                            first_result, total_count,
                        )
                        break
                    extra.extend(batch)
                    first_result += len(batch)
                    logger.info(
                        "Coveo page firstResult=%d → +%d results (running total=%d / %d)",
                        first_result - len(batch), len(batch), len(extra) + start, total_count,
                    )
                except Exception:
                    logger.exception(
                        "httpx Coveo pagination failed at firstResult=%d (totalCount=%d, collected=%d)",
                        first_result, total_count, len(extra),
                    )
                    break
        logger.info(
            "Pagination complete: %d additional results fetched (first_batch=%d, total=%d)",
            len(extra), start, len(extra) + start,
        )
        return extra
