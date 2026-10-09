"""HTTP-level tests for routers/pipeline.py.

Repository and pipeline-service dependencies are overridden, so these run
without Supabase, Perplexity or OpenAI. TestClient is used without a `with` block, which
skips the app lifespan (the startup DB call).
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.repositories.lead_repository import ActiveRunError
from app.routers import pipeline as pipeline_router


def _run_row(**kw) -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111", "status": "running",
        "leads_scraped": 0, "leads_enriched": 0, "leads_failed": 0,
        "cancel_requested": False, "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None, "error_message": None, "postal_code": "10013",
        "country_code": "us", "distance": 25, "segment": "residential", **kw,
    }


@pytest.fixture
def repo():
    r = MagicMock()
    r.create_pipeline_run = AsyncMock(return_value="11111111-1111-1111-1111-111111111111")
    r.get_pipeline_run = AsyncMock(return_value=_run_row())
    r.request_cancel = AsyncMock(return_value=True)
    return r


@pytest.fixture
def service():
    s = MagicMock()
    s.execute = AsyncMock()
    return s


@pytest.fixture
def client(repo, service):
    app.dependency_overrides[pipeline_router.get_repo] = lambda: repo
    app.dependency_overrides[pipeline_router.get_pipeline_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_run_returns_202_and_schedules_the_pipeline(client, repo, service):
    resp = client.post("/api/pipeline/run", json={"postal_code": "10013", "distance": 25, "limit": 10})

    assert resp.status_code == 202
    assert resp.json()["run_id"] == "11111111-1111-1111-1111-111111111111"
    repo.create_pipeline_run.assert_awaited_once_with(
        postal_code="10013", country_code="us", distance=25, segment="residential",
    )
    service.execute.assert_awaited_once()


def test_run_returns_409_with_active_run_id_when_one_is_running(client, repo, service):
    repo.create_pipeline_run.side_effect = ActiveRunError("active-run-id")

    resp = client.post("/api/pipeline/run", json={})

    assert resp.status_code == 409
    assert resp.json()["detail"]["run_id"] == "active-run-id"
    service.execute.assert_not_awaited()


@pytest.mark.parametrize("body", [{"distance": 30}, {"limit": 0}, {"postal_code": "abc"},
                                  {"segment": "industrial"}])
def test_run_rejects_invalid_parameters(client, body):
    assert client.post("/api/pipeline/run", json=body).status_code == 422


def test_cancel_running_run_returns_202(client, repo):
    repo.get_pipeline_run.return_value = _run_row(cancel_requested=True)

    resp = client.post("/api/pipeline/11111111-1111-1111-1111-111111111111/cancel")

    assert resp.status_code == 202
    assert resp.json()["cancel_requested"] is True


def test_cancel_unknown_run_returns_404(client, repo):
    repo.get_pipeline_run.return_value = None
    assert client.post("/api/pipeline/nope/cancel").status_code == 404


def test_cancel_finished_run_returns_409(client, repo):
    repo.request_cancel.return_value = False
    repo.get_pipeline_run.return_value = _run_row(status="completed")
    assert client.post("/api/pipeline/11111111-1111-1111-1111-111111111111/cancel").status_code == 409


def test_status_includes_new_fields(client, repo):
    resp = client.get("/api/pipeline/status/11111111-1111-1111-1111-111111111111")

    body = resp.json()
    assert resp.status_code == 200
    assert body["segment"] == "residential"
    assert body["leads_failed"] == 0
    assert body["cancel_requested"] is False


def test_delete_all_leads_endpoint_is_gone(client):
    """An unauthenticated 'delete every lead' endpoint must not exist."""
    assert client.delete("/api/leads/").status_code == 405
