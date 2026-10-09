"""Scraper failure semantics: a broken capture must never look like "zero leads".

  * browser / capture exceptions      → ScrapeError → run 'failed'
  * malformed Coveo payloads          → ScrapeError → run 'failed'
  * GAF says totalCount=0             → [] → run 'completed' with zero leads
  * totalCount>0 but nothing parsed   → ScrapeError → run 'failed'
  * error text is sanitized (no tokens / auth headers reach the DB or UI)
"""
from unittest.mock import AsyncMock, patch

import pytest

from app.config import ScraperConfig
from app.repositories.lead_repository import LeadRepository
from app.services.errors import ScrapeError
from app.services.gaf_browser import FirstPage, parse_coveo_payload
from app.services.pipeline import PipelineService
from app.services.playwright_scraper import PlaywrightScraper
from tests.fake_supabase import FakeSupabase


def _hit(contractor_id="123", name="Acme Roofing") -> dict:
    return {"title": name, "clickUri": f"https://www.gaf.com/x/acme-{contractor_id}",
            "raw": {"gaf_contractor_id": contractor_id, "gaf_navigation_title": name}}


# ── Payload validation ────────────────────────────────────────────────────

def test_valid_payload_is_parsed():
    results, total = parse_coveo_payload({"results": [_hit()], "totalCount": 1})
    assert (len(results), total) == (1, 1)


def test_valid_zero_payload_is_accepted():
    assert parse_coveo_payload({"results": [], "totalCount": 0}) == ([], 0)


@pytest.mark.parametrize("payload", [
    None, [], "html", {}, {"results": []}, {"totalCount": 3},
    {"results": "x", "totalCount": 1}, {"results": [], "totalCount": "3"},
    {"results": [], "totalCount": -1}, {"results": [1, 2], "totalCount": 2},
])
def test_malformed_payload_raises_scrape_error(payload):
    with pytest.raises(ScrapeError):
        parse_coveo_payload(payload)


# ── Browser capture ───────────────────────────────────────────────────────

async def test_browser_launch_failure_raises_sanitized_scrape_error():
    from app.services import gaf_browser

    boom = RuntimeError("launch failed; Authorization: Bearer xyz.secret-token-123")
    with patch.object(gaf_browser, "async_playwright", side_effect=boom):
        with pytest.raises(ScrapeError) as exc:
            await gaf_browser.capture_first_page("https://www.gaf.com/x")

    message = str(exc.value)
    assert "secret-token-123" not in message
    assert "Bearer xyz" not in message
    assert "GAF" in message


# ── Scraper-level zero vs failure ─────────────────────────────────────────

def _scrape_with(first_page_or_error) -> list:
    mock = (AsyncMock(side_effect=first_page_or_error)
            if isinstance(first_page_or_error, Exception)
            else AsyncMock(return_value=first_page_or_error))
    with patch("app.services.playwright_scraper.capture_first_page", mock):
        return PlaywrightScraper()._run_in_proactor(ScraperConfig(limit=10))


def test_genuine_zero_results_return_empty_list():
    assert _scrape_with(FirstPage(results=[], total_count=0)) == []


def test_total_count_positive_but_no_results_raises():
    with pytest.raises(ScrapeError, match="reported 12"):
        _scrape_with(FirstPage(results=[], total_count=12))


def test_results_that_parse_to_no_contractor_ids_raise():
    unparseable = [{"title": "No id", "raw": {}}, {"title": "", "raw": {}}]
    with pytest.raises(ScrapeError, match="none could be parsed"):
        _scrape_with(FirstPage(results=unparseable, total_count=2))


def test_capture_error_propagates():
    with pytest.raises(ScrapeError):
        _scrape_with(ScrapeError("GAF locator did not load"))


# ── Pipeline run state ────────────────────────────────────────────────────

class _Request:
    postal_code, country_code, distance, segment, limit = "10013", "us", 25, "residential", 10


class _NeverCalled:
    async def research(self, contractor):  # pragma: no cover - must not run
        raise AssertionError("research must not run")

    async def enrich_async(self, *a, **kw):  # pragma: no cover - must not run
        raise AssertionError("enrichment must not run")


async def _run_pipeline_with_first_page(first_page_or_error):
    db = FakeSupabase()
    repo = LeadRepository(db)
    run_id = await repo.create_pipeline_run("10013", "us", 25, "residential")

    async def factory():
        return repo

    mock = (AsyncMock(side_effect=first_page_or_error)
            if isinstance(first_page_or_error, Exception)
            else AsyncMock(return_value=first_page_or_error))
    service = PipelineService(scraper=PlaywrightScraper(), researcher=_NeverCalled(),
                              enricher=_NeverCalled(), repo_factory=factory)
    with patch("app.services.playwright_scraper.capture_first_page", mock):
        await service.execute(run_id, _Request())
    return db.run(run_id)


async def test_capture_exception_produces_failed_run():
    run = await _run_pipeline_with_first_page(ScrapeError("GAF search results did not load"))
    assert run["status"] == "failed"
    assert "GAF search results did not load" in run["error_message"]


class _FakeBrowser:
    async def close(self):
        pass


class _FakePlaywright:
    """async_playwright() stand-in: launching Chromium yields a do-nothing browser."""

    def __init__(self):
        self.chromium = self

    async def launch(self, **_kw):
        return _FakeBrowser()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_invalid_coveo_response_produces_failed_run():
    """A Coveo body without results/totalCount goes through the REAL capture path."""
    from app.services import gaf_browser

    db = FakeSupabase()
    repo = LeadRepository(db)
    run_id = await repo.create_pipeline_run("10013", "us", 25, "residential")

    async def factory():
        return repo

    service = PipelineService(scraper=PlaywrightScraper(), researcher=_NeverCalled(),
                              enricher=_NeverCalled(), repo_factory=factory)
    raw = AsyncMock(return_value=({"error": "Akamai challenge page"}, []))
    with patch.object(gaf_browser, "async_playwright", _FakePlaywright), \
         patch.object(gaf_browser, "_capture_raw", raw):
        await service.execute(run_id, _Request())

    run = db.run(run_id)
    assert run["status"] == "failed"
    assert "malformed" in run["error_message"]


async def test_valid_zero_total_produces_completed_zero_result_run():
    run = await _run_pipeline_with_first_page(FirstPage(results=[], total_count=0))
    assert (run["status"], run["leads_scraped"], run["leads_enriched"]) == ("completed", 0, 0)
    assert run["error_message"] is None


async def test_positive_total_with_zero_parsed_produces_failed_run():
    run = await _run_pipeline_with_first_page(FirstPage(results=[], total_count=40))
    assert run["status"] == "failed"
    assert "40" in run["error_message"]


async def test_unexpected_exception_message_is_sanitized_in_run_row():
    run = await _run_pipeline_with_first_page(
        RuntimeError("proxy said: authorization=Bearer abc.def.ghi sk-fake-1234567890abcdef"))
    assert run["status"] == "failed"
    assert "abc.def.ghi" not in run["error_message"]
    assert "sk-fake-1234567890abcdef" not in run["error_message"]
