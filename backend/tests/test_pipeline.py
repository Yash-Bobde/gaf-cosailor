"""Tests for PipelineService (services/pipeline.py).

The pipeline streams each lead through research → enrich → persist
independently, bounded by a concurrency limit. These tests pin down the
properties that make it production-safe:
  * work is saved per lead as soon as it finishes (a crash loses ≤ in-flight leads)
  * a re-run skips enriched leads and reuses stored research
  * one lead's failure never stops the batch
  * cancellation is cooperative and ends the run as 'cancelled'
  * concurrency never exceeds the configured bound

A FakeRepo records calls in order instead of layering AsyncMocks, so each
test reads as a behavioural spec.
"""
import asyncio
import pytest
from unittest.mock import MagicMock

from app.models.lead import ContractorRecord, LeadInsight


class FakeRepo:
    """In-memory stand-in for LeadRepository that records every call in order."""

    def __init__(self, existing: dict[str, dict] | None = None, cancel_after: int | None = None):
        self.events: list[tuple] = []
        self.existing = existing or {}
        self.cancel_after = cancel_after
        self.run: dict = {}
        self._cancel_checks = 0

    async def upsert_contractors(self, contractors):
        rows = []
        for c in contractors:
            prior = self.existing.get(c.gaf_contractor_id, {})
            rows.append({"id": f"lead-{c.gaf_contractor_id}", "gaf_contractor_id": c.gaf_contractor_id,
                         "status": "scraped", **prior})
        self.events.append(("upsert", len(contractors)))
        return rows

    async def update_pipeline_progress(self, run_id, **kw):
        self.run.update(kw)

    async def update_research(self, lead_id, summary, sources):
        self.events.append(("research_saved", lead_id))

    async def update_enrichment(self, lead_id, insight):
        self.events.append(("enriched", lead_id))

    async def mark_lead_failed(self, lead_id, error):
        self.events.append(("failed", lead_id))

    async def is_cancel_requested(self, run_id):
        self._cancel_checks += 1
        enriched = sum(1 for e in self.events if e[0] == "enriched")
        return self.cancel_after is not None and enriched >= self.cancel_after

    async def finish_pipeline_run(self, run_id, leads_enriched, leads_failed):
        """Mirrors the repository contract: cancel requested → 'cancelled', else 'completed'."""
        status = "cancelled" if await self.is_cancel_requested(run_id) else "completed"
        self.run.update(status=status, leads_enriched=leads_enriched, leads_failed=leads_failed)
        self.events.append(("finished", status))
        return status

    async def fail_pipeline_run(self, run_id, error):
        self.run.update(status="failed", error_message=error)
        self.events.append(("run_failed", error))


def _contractor(i: int) -> ContractorRecord:
    return ContractorRecord(company_name=f"Roofer {i}", gaf_contractor_id=str(i), postal_code="10013")


def _insight() -> LeadInsight:
    return LeadInsight(
        lead_score=8, score_rationale="r", convertibility_score=6,
        convertibility_rationale="c", ai_summary="s",
        talking_points=["a", "b", "c"], recommended_approach="x",
    )


class FakeScraper:
    def __init__(self, contractors=None, error: Exception | None = None):
        self.contractors = contractors or []
        self.error = error
        self.configs = []

    async def scrape_contractors(self, config):
        self.configs.append(config)
        if self.error:
            raise self.error
        return self.contractors


class FakeResearcher:
    def __init__(self, repo: FakeRepo, delay: float = 0.0):
        self.repo, self.delay = repo, delay
        self.in_flight = self.max_in_flight = 0
        self.calls: list[str] = []

    async def research(self, contractor):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        self.calls.append(contractor.gaf_contractor_id)
        self.repo.events.append(("research_call", f"lead-{contractor.gaf_contractor_id}"))
        await asyncio.sleep(self.delay)
        self.in_flight -= 1
        return {"summary": f"research {contractor.gaf_contractor_id}", "sources": []}


class FakeEnricher:
    def __init__(self, fail_ids: set[str] = frozenset()):
        self.fail_ids = fail_ids
        self.research_seen: dict[str, dict] = {}

    async def enrich_async(self, contractor, research, search_postal_code=""):
        self.research_seen[contractor.gaf_contractor_id] = research
        if contractor.gaf_contractor_id in self.fail_ids:
            raise RuntimeError("model timeout")
        return _insight()


def _request(**kw):
    base = dict(postal_code="10013", country_code="us", distance=25, segment="residential", limit=None)
    return MagicMock(**{**base, **kw})


def _service(repo, scraper, researcher, enricher, concurrency=4):
    from app.services.pipeline import PipelineService

    async def repo_factory():
        return repo

    return PipelineService(
        scraper=scraper, researcher=researcher, enricher=enricher,
        repo_factory=repo_factory, concurrency=concurrency,
    )


async def test_each_lead_is_researched_saved_then_enriched_in_order():
    """With concurrency=1 the per-lead streaming order is fully deterministic."""
    repo = FakeRepo()
    svc = _service(repo, FakeScraper([_contractor(1), _contractor(2)]),
                   FakeResearcher(repo), FakeEnricher(), concurrency=1)

    await svc.execute("run-1", _request())

    lead_events = [e for e in repo.events if e[0] in ("research_call", "research_saved", "enriched")]
    assert lead_events == [
        ("research_call", "lead-1"), ("research_saved", "lead-1"), ("enriched", "lead-1"),
        ("research_call", "lead-2"), ("research_saved", "lead-2"), ("enriched", "lead-2"),
    ]
    assert repo.run["status"] == "completed"
    assert repo.run["leads_enriched"] == 2
    assert repo.run["leads_scraped"] == 2


async def test_scraper_receives_segment_distance_and_limit():
    repo = FakeRepo()
    scraper = FakeScraper([_contractor(1)])
    svc = _service(repo, scraper, FakeResearcher(repo), FakeEnricher())

    await svc.execute("run-1", _request(segment="commercial", distance=50, limit=5))

    cfg = scraper.configs[0]
    assert (cfg.segment, cfg.distance, cfg.limit) == ("commercial", 50, 5)


async def test_contractors_are_upserted_in_one_bulk_call():
    repo = FakeRepo()
    svc = _service(repo, FakeScraper([_contractor(i) for i in range(5)]),
                   FakeResearcher(repo), FakeEnricher())

    await svc.execute("run-1", _request())

    assert [e for e in repo.events if e[0] == "upsert"] == [("upsert", 5)]


async def test_rerun_skips_enriched_and_reuses_stored_research():
    repo = FakeRepo(existing={
        "1": {"status": "enriched"},
        "2": {"status": "researched", "research_summary": "stored", "research_sources": ["https://s"]},
    })
    researcher, enricher = FakeResearcher(repo), FakeEnricher()
    svc = _service(repo, FakeScraper([_contractor(1), _contractor(2), _contractor(3)]),
                   researcher, enricher)

    await svc.execute("run-1", _request())

    assert researcher.calls == ["3"]
    assert "1" not in enricher.research_seen
    assert enricher.research_seen["2"] == {"summary": "stored", "sources": ["https://s"]}
    assert repo.run["leads_enriched"] == 3   # 1 already + 2 new


async def test_one_failed_lead_does_not_stop_the_batch():
    repo = FakeRepo()
    svc = _service(repo, FakeScraper([_contractor(1), _contractor(2), _contractor(3)]),
                   FakeResearcher(repo), FakeEnricher(fail_ids={"2"}))

    await svc.execute("run-1", _request())

    assert ("failed", "lead-2") in repo.events
    assert repo.run["status"] == "completed"
    assert repo.run["leads_enriched"] == 2
    assert repo.run["leads_failed"] == 1


async def test_research_is_persisted_even_if_enrichment_fails():
    """Paid research must never be thrown away because a later step failed."""
    repo = FakeRepo()
    svc = _service(repo, FakeScraper([_contractor(1)]),
                   FakeResearcher(repo), FakeEnricher(fail_ids={"1"}))

    await svc.execute("run-1", _request())

    assert ("research_saved", "lead-1") in repo.events


async def test_cancel_stops_new_work_and_marks_run_cancelled():
    repo = FakeRepo(cancel_after=1)
    researcher = FakeResearcher(repo, delay=0.02)
    svc = _service(repo, FakeScraper([_contractor(i) for i in range(10)]),
                   researcher, FakeEnricher(), concurrency=1)

    await svc.execute("run-1", _request())

    assert repo.run["status"] == "cancelled"
    assert len(researcher.calls) < 10
    assert repo.events[-1] == ("finished", "cancelled")


async def test_concurrency_is_bounded():
    repo = FakeRepo()
    researcher = FakeResearcher(repo, delay=0.01)
    svc = _service(repo, FakeScraper([_contractor(i) for i in range(12)]),
                   researcher, FakeEnricher(), concurrency=3)

    await svc.execute("run-1", _request())

    assert researcher.max_in_flight == 3
    assert repo.run["leads_enriched"] == 12


async def test_scrape_failure_marks_run_failed_without_raising():
    """The run row records the failure; execute() does not raise into the task runner."""
    repo = FakeRepo()
    svc = _service(repo, FakeScraper(error=RuntimeError("akamai block")),
                   FakeResearcher(repo), FakeEnricher())

    await svc.execute("run-1", _request())

    assert repo.run["status"] == "failed"
    assert "akamai block" in repo.run["error_message"]


async def test_genuine_zero_result_scrape_completes_with_zero_leads():
    """The scraper returns [] only when GAF explicitly reported totalCount=0
    (capture failures raise ScrapeError — see test_scrape_failures.py)."""
    repo = FakeRepo()
    svc = _service(repo, FakeScraper([]), FakeResearcher(repo), FakeEnricher())

    await svc.execute("run-1", _request())

    assert repo.run["status"] == "completed"
    assert repo.run["leads_enriched"] == 0
