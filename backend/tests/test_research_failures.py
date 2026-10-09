"""Research failure semantics: failed evidence gathering is never "success".

Researcher level
  * 429 / 5xx / network errors are retried, then raise a retryable ResearchError
  * 400 / 401 are not retried and raise a terminal ResearchError
  * empty or malformed model output raises ResearchError
  * error text never contains the API key

Pipeline level
  * a research failure marks only that lead failed; the batch continues
  * enrichment is never called for a lead whose research failed
  * nothing is written to research_summary for a failed research call
  * valid saved research (even on a previously failed lead) is reused without a paid call
"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import wait_none

from app.models.lead import ContractorRecord, LeadInsight
from app.repositories.lead_repository import LeadRepository
from app.services.errors import ResearchError
from app.services.pipeline import PipelineService
from app.services.researcher import ContractorResearcher
from tests.fake_supabase import FakeSupabase

_KEY = "pplx-test-SECRETKEY-000000000000"
_GOOD = {"status": "completed", "output": [
    {"type": "search_results", "results": [{"id": 1, "url": "https://acme.example/about"}]},
    {"type": "message", "content": [{
        "type": "output_text", "text": "Acme Roofing uses GAF Timberline shingles [1]."}]}]}


def _response(status=200, payload=None, json_error=False):
    req = httpx.Request("POST", "https://api.perplexity.ai/v1/agent")
    resp = MagicMock()
    resp.status_code = status
    if status >= 400:
        err = httpx.HTTPStatusError("boom", request=req, response=httpx.Response(status, request=req))
        resp.raise_for_status = MagicMock(side_effect=err)
    else:
        resp.raise_for_status = MagicMock()
    resp.json = MagicMock(side_effect=ValueError("not json")) if json_error \
        else MagicMock(return_value=payload)
    return resp


def _client(post):
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = post
    return client


async def _research(post, sample_contractor, attempts=3):
    researcher = ContractorResearcher(api_key=_KEY, max_attempts=attempts, wait=wait_none())
    with patch("app.services.researcher.httpx.AsyncClient", return_value=_client(post)):
        return await researcher.research(sample_contractor)


@pytest.mark.parametrize("transient", [
    _response(429), _response(503), httpx.ConnectError("reset"), httpx.ReadTimeout("slow"),
])
async def test_transient_failures_are_retried_then_succeed(transient, sample_contractor):
    post = AsyncMock(side_effect=[transient, _response(payload=_GOOD)])
    result = await _research(post, sample_contractor)
    assert post.await_count == 2
    assert result["sources"] == ["https://acme.example/about"]


async def test_exhausted_retries_raise_retryable_research_error(sample_contractor):
    post = AsyncMock(return_value=_response(503))
    with pytest.raises(ResearchError) as exc:
        await _research(post, sample_contractor, attempts=3)
    assert post.await_count == 3
    assert exc.value.retryable is True
    assert "503" in str(exc.value)


@pytest.mark.parametrize("status", [400, 401])
async def test_client_errors_are_terminal_and_not_retried(status, sample_contractor):
    post = AsyncMock(return_value=_response(status))
    with pytest.raises(ResearchError) as exc:
        await _research(post, sample_contractor)
    assert post.await_count == 1
    assert exc.value.retryable is False
    assert _KEY not in str(exc.value)


@pytest.mark.parametrize("payload", [
    {"output": []},
    {"output": [{"type": "message", "content": [{"type": "output_text", "text": "   "}]}]},
])
async def test_empty_model_output_is_a_failure(payload, sample_contractor):
    with pytest.raises(ResearchError, match="empty"):
        await _research(AsyncMock(return_value=_response(payload=payload)), sample_contractor)


@pytest.mark.parametrize("resp", [
    _response(json_error=True), _response(payload=["not", "a", "dict"]),
    _response(payload={"output": "nope"}),
])
async def test_malformed_model_output_is_a_failure(resp, sample_contractor):
    with pytest.raises(ResearchError, match="malformed"):
        await _research(AsyncMock(return_value=resp), sample_contractor)


# ── Pipeline behaviour ────────────────────────────────────────────────────

def _contractor(i) -> ContractorRecord:
    return ContractorRecord(company_name=f"Roofer {i}", gaf_contractor_id=str(i), postal_code="10013")


class _Request:
    postal_code, country_code, distance, segment, limit = "10013", "us", 25, "residential", None


class _Scraper:
    def __init__(self, contractors):
        self.contractors = contractors

    async def scrape_contractors(self, config):
        return self.contractors


class _Researcher:
    def __init__(self, fail_ids=()):
        self.fail_ids, self.calls = set(fail_ids), []

    async def research(self, contractor):
        self.calls.append(contractor.gaf_contractor_id)
        if contractor.gaf_contractor_id in self.fail_ids:
            raise ResearchError("Perplexity research request failed (HTTP 401)", retryable=False)
        return {"summary": f"Research for {contractor.company_name}", "sources": []}


class _Enricher:
    def __init__(self):
        self.calls, self.research_seen = [], {}

    async def enrich_async(self, contractor, research, search_postal_code=""):
        self.calls.append(contractor.gaf_contractor_id)
        self.research_seen[contractor.gaf_contractor_id] = research
        return LeadInsight(lead_score=7, score_rationale="r", convertibility_score=5,
                           convertibility_rationale="c", ai_summary="s",
                           talking_points=["a"], recommended_approach="x")


async def _run(contractors, researcher, enricher, db=None):
    db = db or FakeSupabase()
    repo = LeadRepository(db)
    run_id = await repo.create_pipeline_run("10013", "us", 25, "residential")

    async def factory():
        return repo

    service = PipelineService(scraper=_Scraper(contractors), researcher=researcher,
                              enricher=enricher, repo_factory=factory, concurrency=2)
    await service.execute(run_id, _Request())
    leads = {row["gaf_contractor_id"]: row for row in db.tables["leads"]}
    return db.run(run_id), leads


async def test_research_failure_marks_only_that_lead_failed_and_batch_continues():
    enricher = _Enricher()
    run, leads = await _run([_contractor(1), _contractor(2), _contractor(3)],
                            _Researcher(fail_ids={"2"}), enricher)

    assert leads["2"]["status"] == "failed"
    assert "HTTP 401" in leads["2"]["error_message"]
    assert leads["1"]["status"] == leads["3"]["status"] == "enriched"
    assert (run["status"], run["leads_enriched"], run["leads_failed"]) == ("completed", 2, 1)


async def test_failed_research_never_calls_enrichment_or_saves_empty_research():
    enricher = _Enricher()
    _, leads = await _run([_contractor(1)], _Researcher(fail_ids={"1"}), enricher)

    assert enricher.calls == []
    assert leads["1"]["research_summary"] is None
    assert leads["1"]["status"] == "failed"


async def test_saved_research_on_previously_failed_lead_is_reused_without_paid_call():
    db = FakeSupabase()
    repo = LeadRepository(db)
    await repo.upsert_contractors([_contractor(1)])
    db.tables["leads"][0].update(status="failed", research_summary="Stored research.",
                                 research_sources=["https://s.example"],
                                 error_message="enrichment timed out")
    researcher, enricher = _Researcher(), _Enricher()

    run, leads = await _run([_contractor(1)], researcher, enricher, db=db)

    assert researcher.calls == []
    assert enricher.research_seen["1"] == {"summary": "Stored research.",
                                           "sources": ["https://s.example"]}
    assert leads["1"]["status"] == "enriched"
    assert run["leads_enriched"] == 1


async def test_blank_saved_research_is_not_reused():
    db = FakeSupabase()
    repo = LeadRepository(db)
    await repo.upsert_contractors([_contractor(1)])
    db.tables["leads"][0].update(status="researched", research_summary="   ")
    researcher = _Researcher()

    await _run([_contractor(1)], researcher, _Enricher(), db=db)

    assert researcher.calls == ["1"]
