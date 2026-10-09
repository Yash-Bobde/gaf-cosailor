"""HTTP contract tests: FastAPI TestClient → routers → REAL LeadRepository → FakeSupabase.

No live database, browser, Perplexity or OpenAI call is involved; the scraper, researcher and
enricher are deterministic fakes. TestClient runs BackgroundTasks before it
returns the response, so a POST /run completes the whole pipeline inline.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.lead import ContractorRecord, LeadInsight
from app.repositories.lead_repository import LeadRepository
from app.routers import pipeline as pipeline_router
from app.services.errors import ScrapeError
from app.services.pipeline import PipelineService
from tests.fake_supabase import FakeSupabase


class _Scraper:
    def __init__(self, contractors=None, error=None):
        self.contractors, self.error = contractors or [], error

    async def scrape_contractors(self, config):
        if self.error:
            raise self.error
        return self.contractors


class _Researcher:
    async def research(self, contractor):
        return {"summary": f"Owner Maria Lopez runs {contractor.company_name}.",
                "sources": ["https://acme.example"]}


class _Enricher:
    async def enrich_async(self, contractor, research, search_postal_code=""):
        return LeadInsight(lead_score=8, score_rationale="r", convertibility_score=6,
                           convertibility_rationale="c", ai_summary="s",
                           talking_points=["a"], recommended_approach="x")


@pytest.fixture
def db():
    return FakeSupabase()


def _client(db, scraper):
    repo = LeadRepository(db)

    async def factory():
        return repo

    async def fake_get_supabase():
        return db

    service = PipelineService(scraper=scraper, researcher=_Researcher(), enricher=_Enricher(),
                              repo_factory=factory)
    app.dependency_overrides[pipeline_router.get_repo] = lambda: repo
    app.dependency_overrides[pipeline_router.get_pipeline_service] = lambda: service
    return TestClient(app), patch("app.routers.leads.get_supabase", fake_get_supabase)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _contractors(n):
    return [ContractorRecord(company_name=f"Roofer {i}", gaf_contractor_id=str(i),
                             postal_code="10013", segment="residential") for i in range(n)]


def test_run_streams_leads_into_the_list_and_completes(db):
    client, leads_patch = _client(db, _Scraper(_contractors(2)))
    with leads_patch:
        run_id = client.post("/api/pipeline/run", json={"limit": 2}).json()["run_id"]
        status = client.get(f"/api/pipeline/status/{run_id}").json()
        leads = client.get("/api/leads/?segment=residential").json()

    assert (status["status"], status["leads_enriched"], status["leads_failed"]) == ("completed", 2, 0)
    assert leads["total"] == 2
    assert {lead["status"] for lead in leads["leads"]} == {"enriched"}


def test_scrape_failure_is_reported_as_failed_run_with_actionable_message(db):
    client, _ = _client(db, _Scraper(error=ScrapeError("GAF locator page could not be loaded")))
    resp = client.post("/api/pipeline/run", json={})
    status = client.get(f"/api/pipeline/status/{resp.json()['run_id']}").json()

    assert status["status"] == "failed"
    assert status["error_message"] == "GAF locator page could not be loaded"


def test_genuine_zero_result_run_completes(db):
    client, _ = _client(db, _Scraper([]))
    run_id = client.post("/api/pipeline/run", json={}).json()["run_id"]
    status = client.get(f"/api/pipeline/status/{run_id}").json()
    assert (status["status"], status["leads_scraped"]) == ("completed", 0)


def test_second_run_while_one_is_active_returns_409_with_active_id(db):
    client, _ = _client(db, _Scraper([]))
    active = db.insert_row("pipeline_runs", {"postal_code": "10013"})

    resp = client.post("/api/pipeline/run", json={})

    assert resp.status_code == 409
    assert resp.json()["detail"]["run_id"] == active["id"]


def test_cancel_is_idempotent_and_finished_runs_cannot_be_cancelled(db):
    client, _ = _client(db, _Scraper([]))
    running = db.insert_row("pipeline_runs", {"postal_code": "10013"})

    first = client.post(f"/api/pipeline/{running['id']}/cancel")
    second = client.post(f"/api/pipeline/{running['id']}/cancel")
    assert (first.status_code, second.status_code) == (202, 202)

    db.run(running["id"])["status"] = "cancelled"
    assert client.post(f"/api/pipeline/{running['id']}/cancel").status_code == 202

    db.run(running["id"])["status"] = "completed"
    assert client.post(f"/api/pipeline/{running['id']}/cancel").status_code == 409


def test_legacy_decision_makers_without_role_read_back_as_contacts(db):
    client, leads_patch = _client(db, _Scraper([]))
    lead = db.insert_row("leads", {
        "company_name": "Legacy Roofing", "gaf_contractor_id": "L1", "status": "enriched",
        "decision_makers": [{"name": "Maria Lopez", "title": "Owner", "source_url": None}],
    })
    with leads_patch:
        body = client.get(f"/api/leads/{lead['id']}").json()

    assert body["decision_makers"][0]["role"] == "contact"
    assert body["decision_makers"][0]["evidence"] is None


def test_latest_run_is_204_before_any_run_then_returns_the_newest(db):
    client, _ = _client(db, _Scraper([]))
    assert client.get("/api/pipeline/latest").status_code == 204

    run_id = client.post("/api/pipeline/run", json={}).json()["run_id"]
    latest = client.get("/api/pipeline/latest")
    assert latest.status_code == 200
    assert latest.json()["run_id"] == run_id
