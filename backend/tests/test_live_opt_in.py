"""Opt-in live checks — SKIPPED by default; each needs an explicit flag.

  RUN_LIVE_GAF=1      real GAF residential scrape (ZIP 10013, 25 mi, first 3 results).
                      Free, but depends on gaf.com / Akamai being reachable.
  RUN_LIVE_PERPLEXITY=1  ONE paid Perplexity web-research call (no retries), no DB writes.
  TEST_SUPABASE_URL + TEST_SUPABASE_KEY
                      repository run-lifecycle test against a DEDICATED test
                      project (schema from app/schema.sql). Refuses to run when it
                      points at the same project as backend/.env.

Real credentials are read explicitly from backend/.env or the environment;
conftest.py forces dummies for every other test.

    RUN_LIVE_GAF=1 pytest tests/test_live_opt_in.py -m live -v
"""
import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

pytestmark = pytest.mark.live

_ENV = dotenv_values(Path(__file__).resolve().parents[1] / ".env")


def _flag(name: str) -> bool:
    return os.environ.get(name) == "1"


@pytest.mark.skipif(not _flag("RUN_LIVE_GAF"), reason="set RUN_LIVE_GAF=1 to scrape gaf.com")
async def test_live_gaf_residential_scrape_returns_real_contractors():
    from app.config import ScraperConfig
    from app.services.playwright_scraper import PlaywrightScraper

    contractors = await PlaywrightScraper().scrape_contractors(ScraperConfig(limit=3))

    assert 1 <= len(contractors) <= 3
    assert all(c.gaf_contractor_id for c in contractors)
    assert all((c.gaf_profile_url or "").startswith("https://www.gaf.com/") for c in contractors)
    assert {c.segment for c in contractors} == {"residential"}


@pytest.mark.skipif(not _flag("RUN_LIVE_PERPLEXITY"),
                    reason="set RUN_LIVE_PERPLEXITY=1 (one paid call)")
async def test_live_perplexity_research_contract_single_call():
    from app.models.lead import ContractorRecord
    from app.services.researcher import ContractorResearcher

    key = os.environ.get("LIVE_PERPLEXITY_API_KEY") or _ENV.get("PERPLEXITY_API_KEY")
    preset = _ENV.get("PERPLEXITY_PRESET") or "fast"
    researcher = ContractorResearcher(api_key=key, preset=preset, max_attempts=1)
    # A real GAF-listed contractor near ZIP 10013, so there is something to find and cite.
    result = await researcher.research(ContractorRecord(
        company_name="Allied Brothers Home Corporation", city="Wayne", state="NJ"))

    assert result["summary"].strip()
    assert result["sources"], "the answer cited no search results"
    assert all(u.startswith("http") for u in result["sources"])
    # Citation markers were rewritten as inline links to the cited pages.
    assert any(f"]({u})" in result["summary"] for u in result["sources"])


def _test_db() -> tuple[str, str] | None:
    url, key = os.environ.get("TEST_SUPABASE_URL"), os.environ.get("TEST_SUPABASE_KEY")
    if not url or not key:
        return None
    if url.rstrip("/") == (_ENV.get("SUPABASE_URL") or "").rstrip("/"):
        pytest.fail("TEST_SUPABASE_URL points at the production project — refusing to run")
    return url, key


@pytest.mark.skipif(not os.environ.get("TEST_SUPABASE_URL"),
                    reason="set TEST_SUPABASE_URL/TEST_SUPABASE_KEY to a dedicated test project")
async def test_live_repository_cancel_lifecycle_on_test_project():
    from supabase import acreate_client
    from app.repositories.lead_repository import LeadRepository

    url, key = _test_db()
    repo = LeadRepository(await acreate_client(url, key))
    await repo.interrupt_stale_runs()
    run_id = await repo.create_pipeline_run("10013", "us", 25, "residential")
    try:
        assert await repo.request_cancel(run_id) is True
        assert await repo.request_cancel(run_id) is True
        assert await repo.finish_pipeline_run(run_id, 0, 0) == "cancelled"
        assert await repo.request_cancel(run_id) is False
        assert (await repo.get_pipeline_run(run_id))["status"] == "cancelled"
    finally:
        await repo.fail_pipeline_run(run_id, "live test cleanup")
