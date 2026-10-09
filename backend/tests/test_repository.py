"""Tests for LeadRepository (repositories/lead_repository.py).

Uses MagicMock to simulate the Supabase async client without hitting the
database. The Supabase query builder is entirely synchronous until .execute()
which returns a coroutine — the mocks reflect this pattern.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


@pytest.mark.asyncio
async def test_get_all_leads_returns_list_ordered_by_score(sample_lead_row):
    """get_all_leads returns the list from Supabase inside a paginated envelope."""
    from app.repositories.lead_repository import LeadRepository

    mock_result = MagicMock()
    mock_result.data = [sample_lead_row]
    mock_result.count = 1

    mock_table = MagicMock()
    mock_table.select.return_value.order.return_value.range.return_value.execute = AsyncMock(
        return_value=mock_result
    )

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    repo = LeadRepository(client=mock_client)
    result = await repo.get_all_leads()

    assert len(result["leads"]) == 1
    assert result["leads"][0]["company_name"] == "Acme Roofing Inc"
    assert result["total"] == 1


@pytest.mark.asyncio
async def test_get_all_leads_returns_paginated_result(sample_lead_row):
    """get_all_leads returns a dict with leads list, total, page, and limit."""
    from app.repositories.lead_repository import LeadRepository

    mock_result = MagicMock()
    mock_result.data = [sample_lead_row]
    mock_result.count = 42  # total across all pages

    mock_table = MagicMock()
    # .select().order().range().execute()
    mock_table.select.return_value.order.return_value.range.return_value.execute = AsyncMock(
        return_value=mock_result
    )

    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    repo = LeadRepository(client=mock_client)
    result = await repo.get_all_leads(page=1, limit=12)

    assert result["total"] == 42
    assert result["page"] == 1
    assert result["limit"] == 12
    assert len(result["leads"]) == 1
    assert result["leads"][0]["company_name"] == "Acme Roofing Inc"


@pytest.mark.asyncio
async def test_update_enrichment_sets_status_to_enriched():
    """update_enrichment writes all LeadInsight fields and sets status='enriched'."""
    from app.models.lead import LeadInsight
    from app.repositories.lead_repository import LeadRepository

    lead_id = str(uuid4())
    insight = LeadInsight(
        lead_score=9,
        score_rationale="Master Elite",
        convertibility_score=7,
        convertibility_rationale="Competitor brands detected.",
        distance_miles=5.2,
        distance_band="near",
        priority_index=8.0,
        ai_summary="High priority lead.",
        talking_points=["Point 1", "Point 2", "Point 3"],
        recommended_approach="Call owner.",
    )

    mock_result = MagicMock()
    mock_result.data = [{"id": lead_id}]
    # .update().eq().execute() — all sync except execute
    mock_table = MagicMock()
    mock_table.update.return_value.eq.return_value.execute = AsyncMock(return_value=mock_result)
    mock_client = MagicMock()
    mock_client.table.return_value = mock_table

    repo = LeadRepository(client=mock_client)
    await repo.update_enrichment(lead_id, insight)

    call_data = mock_table.update.call_args[0][0]
    assert call_data["decision_makers"] == []
    assert call_data["error_message"] is None
    assert call_data["lead_score"] == 9
    assert call_data["convertibility_score"] == 7
    assert call_data["status"] == "enriched"


# ── Bulk upsert ───────────────────────────────────────────────────────────

def _upsert_client(existing_rows: list[dict]):
    """Mock client: SELECT…in_() returns existing statuses; upsert echoes rows back with ids."""
    table = MagicMock()
    table.select.return_value.in_.return_value.execute = AsyncMock(
        return_value=MagicMock(data=existing_rows)
    )

    def upsert(rows, **kwargs):
        builder = MagicMock()
        builder.execute = AsyncMock(return_value=MagicMock(
            data=[{**r, "id": f"id-{r['gaf_contractor_id']}", "status": r.get("status", "enriched")}
                  for r in rows]
        ))
        return builder

    table.upsert.side_effect = upsert
    client = MagicMock()
    client.table.return_value = table
    return client, table


async def test_upsert_contractors_batches_and_preserves_protected_status():
    """New/failed leads are (re)set to 'scraped'; researched/enriched rows keep their status.

    Protected rows go in a separate upsert WITHOUT a status key — supabase-py's bulk
    upsert defaults missing keys to NULL, so mixing shapes would wipe statuses.
    """
    from app.models.lead import ContractorRecord
    from app.repositories.lead_repository import LeadRepository

    client, table = _upsert_client([
        {"gaf_contractor_id": "2", "status": "enriched"},
        {"gaf_contractor_id": "3", "status": "failed"},
    ])
    contractors = [ContractorRecord(company_name=f"C{i}", gaf_contractor_id=str(i)) for i in (1, 2, 3)]

    rows = await LeadRepository(client).upsert_contractors(contractors)

    assert [r["id"] for r in rows] == ["id-1", "id-2", "id-3"]      # input order preserved
    batches = [c.args[0] for c in table.upsert.call_args_list]
    assert len(batches) == 2
    fresh = next(b for b in batches if "status" in b[0])
    protected = next(b for b in batches if "status" not in b[0])
    assert {r["gaf_contractor_id"] for r in fresh} == {"1", "3"}
    assert all(r["status"] == "scraped" for r in fresh)
    assert [r["gaf_contractor_id"] for r in protected] == ["2"]
    for call in table.upsert.call_args_list:
        assert call.kwargs["on_conflict"] == "gaf_contractor_id"


async def test_upsert_contractors_dedupes_ids_within_a_batch():
    """Postgres rejects ON CONFLICT batches that touch the same row twice."""
    from app.models.lead import ContractorRecord
    from app.repositories.lead_repository import LeadRepository

    client, table = _upsert_client([])
    contractors = [ContractorRecord(company_name="A", gaf_contractor_id="1"),
                   ContractorRecord(company_name="A again", gaf_contractor_id="1")]

    rows = await LeadRepository(client).upsert_contractors(contractors)

    assert len(rows) == 1
    assert len(table.upsert.call_args_list[0].args[0]) == 1


async def test_upsert_contractors_empty_input_makes_no_calls():
    from app.repositories.lead_repository import LeadRepository

    client, table = _upsert_client([])
    assert await LeadRepository(client).upsert_contractors([]) == []
    table.upsert.assert_not_called()


# ── Pipeline runs ─────────────────────────────────────────────────────────

async def test_create_pipeline_run_raises_active_run_error_on_unique_violation():
    """The partial unique index is the source of truth for 'one active run at a time'."""
    from postgrest.exceptions import APIError
    from app.repositories.lead_repository import ActiveRunError, LeadRepository

    table = MagicMock()
    table.insert.return_value.execute = AsyncMock(
        side_effect=APIError({"message": "duplicate key", "code": "23505"})
    )
    table.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[{"id": "active-run"}])
    )
    client = MagicMock()
    client.table.return_value = table

    with pytest.raises(ActiveRunError) as exc_info:
        await LeadRepository(client).create_pipeline_run("10013", "us", 25, "residential")

    assert exc_info.value.run_id == "active-run"


async def test_create_pipeline_run_stores_segment():
    from app.repositories.lead_repository import LeadRepository

    table = MagicMock()
    table.insert.return_value.execute = AsyncMock(return_value=MagicMock(data=[{"id": "r1"}]))
    client = MagicMock()
    client.table.return_value = table

    run_id = await LeadRepository(client).create_pipeline_run("10013", "us", 25, "commercial")

    assert run_id == "r1"
    assert table.insert.call_args.args[0]["segment"] == "commercial"


async def test_request_cancel_only_affects_running_runs():
    from app.repositories.lead_repository import LeadRepository

    table = MagicMock()
    chain = table.update.return_value.eq.return_value.eq.return_value
    chain.execute = AsyncMock(return_value=MagicMock(data=[]))
    client = MagicMock()
    client.table.return_value = table

    assert await LeadRepository(client).request_cancel("r1") is False
    assert table.update.call_args.args[0] == {"cancel_requested": True}
    table.update.return_value.eq.return_value.eq.assert_called_with("status", "running")


async def test_finish_pipeline_run_records_terminal_state():
    """Finalization is conditional; full state-machine cases live in test_run_lifecycle.py."""
    from app.repositories.lead_repository import LeadRepository
    from tests.fake_supabase import FakeSupabase

    db = FakeSupabase()
    repo = LeadRepository(db)
    run_id = await repo.create_pipeline_run("10013", "us", 25, "residential")

    assert await repo.finish_pipeline_run(run_id, leads_enriched=4, leads_failed=1) == "completed"
    run = db.run(run_id)
    assert (run["status"], run["leads_enriched"], run["leads_failed"]) == ("completed", 4, 1)
    assert run["finished_at"]


async def test_get_by_id_returns_none_for_unknown_or_malformed_ids():
    """Unknown ids must be a clean None (→ 404), not a PostgREST error (→ 500)."""
    from app.repositories.lead_repository import LeadRepository

    table = MagicMock()
    table.select.return_value.eq.return_value.limit.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[])
    )
    client = MagicMock()
    client.table.return_value = table
    repo = LeadRepository(client)

    assert await repo.get_lead_by_id("not-a-uuid") is None
    table.select.assert_not_called()
    assert await repo.get_pipeline_run(str(uuid4())) is None


async def test_get_all_leads_filters_by_segment(sample_lead_row):
    """segment narrows the list server-side so totals and pagination stay accurate."""
    from app.repositories.lead_repository import LeadRepository

    table = MagicMock()
    query = table.select.return_value
    query.eq.return_value.order.return_value.range.return_value.execute = AsyncMock(
        return_value=MagicMock(data=[sample_lead_row], count=1)
    )
    client = MagicMock()
    client.table.return_value = table

    result = await LeadRepository(client).get_all_leads(segment="residential")

    query.eq.assert_called_once_with("segment", "residential")
    assert result["total"] == 1
