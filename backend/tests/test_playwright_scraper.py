"""Tests for PlaywrightScraper (services/playwright_scraper.py).

The scraper uses a Playwright + Coveo API hybrid:
  Phase 1 — headless Chromium loads the GAF locator page and captures the first
             Coveo batch plus the auth token GAF's own page uses.
  Phase 2 — httpx paginates the remaining Coveo pages with that token.

The browser phase is exercised by the live integration check, not unit tests.
These tests cover every pure step (URL building, result mapping, dedupe/limit)
and the async pagination loop with httpx mocked.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import ScraperConfig


def _coveo_result(name="Acme Roofing", contractor_id="123", segment="residential") -> dict:
    return {
        "title": name,
        "clickUri": f"https://www.gaf.com/en-us/roofing-contractors/{segment}/usa/ny/new-york/acme-{contractor_id}",
        "raw": {
            "gaf_contractor_id": contractor_id,
            "gaf_navigation_title": name,
            "gaf_phone": "212-555-0100",
            "gaf_f_city": "New York",
            "gaf_f_state_code": "NY",
            "gaf_postal_code": "10013",
            "gaf_rating": 4.5,
            "gaf_number_of_reviews": 10,
            "gaf_f_contractor_certifications_and_awards_residential": ["GAF Master Elite"],
        },
    }


# ── URL building ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("segment", ["residential", "commercial"])
def test_build_search_url_uses_segment_and_config(segment):
    from app.services.playwright_scraper import build_search_url

    url = build_search_url(ScraperConfig(postal_code="90210", distance=50, segment=segment))
    assert url == (
        f"https://www.gaf.com/en-us/roofing-contractors/{segment}"
        "?postalCode=90210&countryCode=us&distance=50"
    )


def test_build_search_url_defaults_to_case_study_url():
    from app.services.playwright_scraper import build_search_url

    assert build_search_url(ScraperConfig()) == (
        "https://www.gaf.com/en-us/roofing-contractors/residential"
        "?postalCode=10013&countryCode=us&distance=25"
    )


# ── Result mapping ────────────────────────────────────────────────────────

def test_map_coveo_result_uses_real_profile_url_and_segment():
    """GAF's own clickUri is the profile link — a constructed /commercial/{id} URL 404s."""
    from app.services.playwright_scraper import _map_coveo_result

    rec = _map_coveo_result(_coveo_result(contractor_id="9999"), "us", "residential")
    assert rec.gaf_profile_url.endswith("/residential/usa/ny/new-york/acme-9999")
    assert rec.segment == "residential"
    assert rec.gaf_contractor_id == "9999"
    assert rec.certifications == ["GAF Master Elite"]


def test_map_coveo_result_tolerates_missing_fields():
    from app.services.playwright_scraper import _map_coveo_result

    rec = _map_coveo_result({"title": "Bare Co", "raw": {}}, "us", "commercial")
    assert rec.company_name == "Bare Co"
    assert rec.gaf_contractor_id is None
    assert rec.gaf_profile_url is None


def test_finalize_results_dedupes_by_contractor_id_and_applies_limit():
    from app.services.playwright_scraper import _finalize_results

    results = [_coveo_result("A", "1"), _coveo_result("A dup", "1"), _coveo_result("B", "2"),
               _coveo_result("C", "3")]
    recs = _finalize_results(results, ScraperConfig(limit=2))
    assert [r.gaf_contractor_id for r in recs] == ["1", "2"]


def test_extract_certifications_merges_and_deduplicates():
    from app.services.playwright_scraper import _extract_certifications

    raw = {
        "gaf_f_contractor_certifications_and_awards_commercial": ["GAF Master Elite", "WeatherStopper"],
        "gaf_f_contractor_certifications_and_awards_residential": ["GAF Master Elite", "Star"],
    }
    certs = _extract_certifications(raw)
    assert certs.count("GAF Master Elite") == 1
    assert {"WeatherStopper", "Star"} <= set(certs)


def test_extract_certifications_handles_string_fields():
    from app.services.playwright_scraper import _extract_certifications

    raw = {"gaf_f_contractor_certifications_and_awards_commercial": "GAF Certified"}
    assert _extract_certifications(raw) == ["GAF Certified"]


# ── Pagination ────────────────────────────────────────────────────────────

def _mock_async_client(post):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = post
    return client


def _response(results):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"results": results}
    return resp


async def test_paginate_coveo_fetches_remaining_pages():
    from app.services.playwright_scraper import PlaywrightScraper

    pages = [_response([_coveo_result(str(i), str(i)) for i in range(10, 110)]),
             _response([_coveo_result(str(i), str(i)) for i in range(110, 150)])]
    post = AsyncMock(side_effect=pages)
    with patch("app.services.playwright_scraper.httpx.AsyncClient",
               return_value=_mock_async_client(post)):
        extra = await PlaywrightScraper()._paginate_coveo("Bearer t", {"q": ""}, 150, start=10)

    assert len(extra) == 140
    assert post.call_count == 2
    first_body = post.call_args_list[0].kwargs["json"]
    assert first_body["firstResult"] == 10
    assert first_body["numberOfResults"] == 100


async def test_paginate_coveo_stops_on_http_error_and_keeps_partial_results():
    from app.services.playwright_scraper import PlaywrightScraper

    post = AsyncMock(side_effect=[_response([_coveo_result("x", "x")]), RuntimeError("403")])
    with patch("app.services.playwright_scraper.httpx.AsyncClient",
               return_value=_mock_async_client(post)):
        extra = await PlaywrightScraper()._paginate_coveo("Bearer t", {}, 500, start=10)

    assert len(extra) == 1


async def test_paginate_coveo_stops_on_empty_batch():
    from app.services.playwright_scraper import PlaywrightScraper

    post = AsyncMock(return_value=_response([]))
    with patch("app.services.playwright_scraper.httpx.AsyncClient",
               return_value=_mock_async_client(post)):
        extra = await PlaywrightScraper()._paginate_coveo("Bearer t", {}, 500, start=10)

    assert extra == []
    assert post.call_count == 1


def test_coveo_body_is_json_serialisable_after_pagination_patch():
    """Guard: the patched body must still serialise (clientTimestamp is an ISO string)."""
    from app.services.playwright_scraper import _page_body

    body = _page_body({"analytics": {"x": 1}}, first_result=200)
    assert json.loads(json.dumps(body))["firstResult"] == 200
    assert "clientTimestamp" in body["analytics"]
