"""Run state-machine contract tests: cancellation, finalization and terminal states.

These drive the REAL PipelineService and REAL LeadRepository against the
in-memory FakeSupabase, so the cancel flag lives in "the database" exactly as it
does in production — no in-memory shortcut can make a test pass.

Invariants proven here:
  * an accepted cancel can never finish 'completed' (whenever it arrives)
  * no new lead starts once a cancel has been observed
  * cancel is idempotent; completed / failed / cancelled runs are never reopened
  * the one-running-run guard still holds
"""
import asyncio

import pytest

from app.models.lead import ContractorRecord, LeadInsight
from app.repositories.lead_repository import ActiveRunError, LeadRepository
from app.services.pipeline import PipelineService
from tests.fake_supabase import FakeSupabase


def _contractor(i: int) -> ContractorRecord:
    return ContractorRecord(company_name=f"Roofer {i}", gaf_contractor_id=str(i), postal_code="10013")


def _insight() -> LeadInsight:
    return LeadInsight(lead_score=8, score_rationale="r", convertibility_score=6,
                       convertibility_rationale="c", ai_summary="s",
                       talking_points=["a"], recommended_approach="x")


class _Request:
    postal_code, country_code, distance, segment, limit = "10013", "us", 25, "residential", None


class Scraper:
    def __init__(self, contractors, on_scrape=None):
        self.contractors, self.on_scrape, self.calls = contractors, on_scrape, 0

    async def scrape_contractors(self, config):
        self.calls += 1
        if self.on_scrape:
            await self.on_scrape()
        return self.contractors


class Researcher:
    def __init__(self, on_call=None):
        self.calls: list[str] = []
        self.on_call = on_call

    async def research(self, contractor):
        self.calls.append(contractor.gaf_contractor_id)
        if self.on_call:
            await self.on_call(contractor)
        await asyncio.sleep(0)
        return {"summary": f"research about {contractor.company_name}", "sources": []}


class Enricher:
    def __init__(self, on_call=None):
        self.calls: list[str] = []
        self.on_call = on_call

    async def enrich_async(self, contractor, research, search_postal_code=""):
        self.calls.append(contractor.gaf_contractor_id)
        if self.on_call:
            await self.on_call(contractor)
        return _insight()


@pytest.fixture
def db():
    return FakeSupabase()


@pytest.fixture
def repo(db):
    return LeadRepository(db)


async def _new_run(repo) -> str:
    return await repo.create_pipeline_run("10013", "us", 25, "residential")


def _service(repo, scraper, researcher=None, enricher=None, concurrency=1):
    async def factory():
        return repo
    return PipelineService(scraper=scraper, researcher=researcher or Researcher(),
                           enricher=enricher or Enricher(), repo_factory=factory,
                           concurrency=concurrency)


# ── Cancellation timing cases ─────────────────────────────────────────────

async def test_immediate_cancel_before_worker_starts_ends_cancelled(db, repo):
    """The reproduced race: cancel accepted right after POST /run returned."""
    run_id = await _new_run(repo)
    assert await repo.request_cancel(run_id) is True
    scraper = Scraper([_contractor(1)])

    await _service(repo, scraper).execute(run_id, _Request())

    assert db.run(run_id)["status"] == "cancelled"
    assert scraper.calls == 0            # no paid or slow work after an accepted cancel
    assert db.run(run_id)["finished_at"]


async def test_cancel_during_scrape_ends_cancelled_and_starts_no_lead(db, repo):
    run_id = await _new_run(repo)
    researcher = Researcher()

    async def cancel_mid_scrape():
        await repo.request_cancel(run_id)

    scraper = Scraper([_contractor(1), _contractor(2)], on_scrape=cancel_mid_scrape)
    await _service(repo, scraper, researcher).execute(run_id, _Request())

    assert db.run(run_id)["status"] == "cancelled"
    assert researcher.calls == []
    assert db.run(run_id)["leads_scraped"] == 2   # scraped work is still persisted


async def test_cancel_with_no_pending_leads_ends_cancelled(db, repo):
    """Every lead already enriched: nothing to process, cancel must still win."""
    run_id = await _new_run(repo)
    await repo.upsert_contractors([_contractor(1)])
    db.tables["leads"][0]["status"] = "enriched"

    async def cancel_mid_scrape():
        await repo.request_cancel(run_id)

    await _service(repo, Scraper([_contractor(1)], on_scrape=cancel_mid_scrape)).execute(
        run_id, _Request())

    assert db.run(run_id)["status"] == "cancelled"


async def test_cancel_arriving_during_last_lead_cannot_finish_completed(db, repo):
    """Cancel lands after the last lead has started but before finalization."""
    run_id = await _new_run(repo)

    async def cancel_during_enrichment(_contractor):
        await repo.request_cancel(run_id)

    enricher = Enricher(on_call=cancel_during_enrichment)
    await _service(repo, Scraper([_contractor(1)]), enricher=enricher).execute(run_id, _Request())

    run = db.run(run_id)
    assert run["status"] == "cancelled"
    assert run["leads_enriched"] == 1      # the in-flight lead was allowed to drain


async def test_cancel_during_processing_stops_new_leads(db, repo):
    run_id = await _new_run(repo)

    async def cancel_after_first(contractor):
        if contractor.gaf_contractor_id == "0":
            await repo.request_cancel(run_id)

    researcher = Researcher(on_call=cancel_after_first)
    await _service(repo, Scraper([_contractor(i) for i in range(6)]), researcher).execute(
        run_id, _Request())

    assert db.run(run_id)["status"] == "cancelled"
    assert researcher.calls == ["0"]       # concurrency=1: nothing new began after the cancel


async def test_run_without_cancel_completes(db, repo):
    run_id = await _new_run(repo)
    await _service(repo, Scraper([_contractor(1), _contractor(2)])).execute(run_id, _Request())

    run = db.run(run_id)
    assert (run["status"], run["leads_enriched"], run["leads_failed"]) == ("completed", 2, 0)


# ── Repository-level state machine ────────────────────────────────────────

async def test_repeated_cancel_is_idempotent(db, repo):
    run_id = await _new_run(repo)
    assert await repo.request_cancel(run_id) is True
    assert await repo.request_cancel(run_id) is True
    assert db.run(run_id)["cancel_requested"] is True
    assert db.run(run_id)["status"] == "running"


async def test_finish_returns_cancelled_when_cancel_was_requested(db, repo):
    run_id = await _new_run(repo)
    await repo.request_cancel(run_id)

    assert await repo.finish_pipeline_run(run_id, leads_enriched=3, leads_failed=1) == "cancelled"
    assert db.run(run_id)["leads_enriched"] == 3


@pytest.mark.parametrize("terminal", ["completed", "failed", "cancelled"])
async def test_terminal_runs_are_never_reopened_or_overwritten(db, repo, terminal):
    run_id = await _new_run(repo)
    db.run(run_id)["status"] = terminal

    assert await repo.request_cancel(run_id) is False
    assert await repo.finish_pipeline_run(run_id, leads_enriched=9, leads_failed=9) == terminal
    await repo.fail_pipeline_run(run_id, "late failure from a stale worker")

    run = db.run(run_id)
    assert run["status"] == terminal
    assert run["leads_enriched"] == 0
    assert run["error_message"] is None


async def test_second_concurrent_run_is_rejected_with_active_id(repo):
    first = await _new_run(repo)
    with pytest.raises(ActiveRunError) as exc:
        await _new_run(repo)
    assert exc.value.run_id == first


async def test_new_run_allowed_after_previous_run_finishes(repo):
    first = await _new_run(repo)
    await repo.finish_pipeline_run(first, leads_enriched=0, leads_failed=0)
    assert await _new_run(repo) != first
