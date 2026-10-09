"""Data-access layer for leads and pipeline runs.

All Supabase calls are isolated here so that routers and services never import
or instantiate the Supabase client directly. The interface follows the standard
repository pattern: upsert / get / update / mark-failed for leads, plus a set
of pipeline-run tracking helpers used by PipelineService.
"""
import logging
import re
from datetime import datetime, timezone

from postgrest.exceptions import APIError

from app.models.lead import ContractorRecord, LeadInsight

logger = logging.getLogger(__name__)

# Leads in these states keep their status (and paid-for work) when re-scraped.
_PROTECTED_STATUSES = ("researched", "enriched")
_UPSERT_CHUNK = 500
_UNIQUE_VIOLATION = "23505"
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


class ActiveRunError(Exception):
    """Raised when a pipeline run is requested while another is still running."""

    def __init__(self, run_id: str | None):
        super().__init__(f"Pipeline run {run_id} is already running")
        self.run_id = run_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _contractor_row(c: ContractorRecord) -> dict:
    """Map a ContractorRecord to the scraped columns of the leads table."""
    return {
        "company_name": c.company_name,
        "gaf_contractor_id": c.gaf_contractor_id,
        "address": c.address,
        "city": c.city,
        "state": c.state,
        "postal_code": c.postal_code,
        "country_code": c.country_code,
        "phone": c.phone,
        "website": c.website,
        "gaf_profile_url": c.gaf_profile_url,
        "certifications": c.certifications,
        "years_in_business": c.years_in_business,
        "service_area": c.service_area,
        "rating": float(c.rating) if c.rating else None,
        "review_count": c.review_count,
        "segment": c.segment,
    }


class LeadRepository:
    """Async repository wrapping the Supabase leads and pipeline_runs tables."""

    def __init__(self, client):
        self._client = client

    async def upsert_contractor(self, contractor: ContractorRecord) -> dict:
        """Insert or update one contractor row. Thin wrapper over upsert_contractors."""
        rows = await self.upsert_contractors([contractor])
        if not rows:
            raise RuntimeError(f"upsert returned no data for {contractor.company_name}")
        return rows[0]

    async def upsert_contractors(self, contractors: list[ContractorRecord]) -> list[dict]:
        """Bulk insert/update contractors keyed on gaf_contractor_id; rows in input order.

        One SELECT finds existing statuses, then at most two upserts per chunk:
          * new / scraped / failed leads -> written with status='scraped' (retryable)
          * researched / enriched leads  -> written WITHOUT a status key, so their
            status and paid-for research/enrichment are preserved.
        The two shapes are never mixed: supabase-py's bulk upsert sends missing keys
        as NULL, which would wipe the protected statuses.
        """
        unique = list({c.gaf_contractor_id: c for c in contractors if c.gaf_contractor_id}.values())
        if not unique:
            return []
        existing = await self._existing_statuses([c.gaf_contractor_id for c in unique])

        fresh, protected = [], []
        for c in unique:
            row = _contractor_row(c)
            if existing.get(c.gaf_contractor_id) in _PROTECTED_STATUSES:
                protected.append(row)
            else:
                fresh.append({**row, "status": "scraped", "error_message": None})

        written: dict[str, dict] = {}
        for batch in (fresh, protected):
            for i in range(0, len(batch), _UPSERT_CHUNK):
                result = await (
                    self._client.table("leads")
                    .upsert(batch[i:i + _UPSERT_CHUNK], on_conflict="gaf_contractor_id")
                    .execute()
                )
                written.update({r["gaf_contractor_id"]: r for r in result.data or []})
        return [written[c.gaf_contractor_id] for c in unique if c.gaf_contractor_id in written]

    async def _existing_statuses(self, gaf_ids: list[str]) -> dict[str, str]:
        """Return {gaf_contractor_id: status} for ids already in the table."""
        statuses: dict[str, str] = {}
        for i in range(0, len(gaf_ids), _UPSERT_CHUNK):
            result = await (
                self._client.table("leads")
                .select("gaf_contractor_id,status")
                .in_("gaf_contractor_id", gaf_ids[i:i + _UPSERT_CHUNK])
                .execute()
            )
            statuses.update({r["gaf_contractor_id"]: r["status"] for r in result.data or []})
        return statuses

    async def get_all_leads(
        self,
        page: int = 1,
        limit: int = 12,
        score_tier: str | None = None,
        sort_by: str | None = None,
        segment: str | None = None,
    ) -> dict:
        """Return a filtered, sorted page of leads with an accurate total count.

        score_tier filters by lead_score range server-side so pagination totals
        reflect only the matching records — not the full table.
        sort_by controls ordering: 'score_desc' (default), 'name_asc', 'recently_enriched'.
        segment restricts to one GAF directory ('residential' / 'commercial').
        """
        offset = (page - 1) * limit
        query = self._client.table("leads").select("*", count="exact")
        if segment:
            query = query.eq("segment", segment)

        if score_tier == "high":
            query = query.gte("lead_score", 8).lte("lead_score", 10)
        elif score_tier == "medium":
            query = query.gte("lead_score", 5).lte("lead_score", 7)
        elif score_tier == "low":
            query = query.gte("lead_score", 1).lte("lead_score", 4)

        if sort_by == "name_asc":
            query = query.order("company_name", desc=False)
        elif sort_by == "recently_enriched":
            query = query.order("enriched_at", desc=True, nullsfirst=False)
        else:
            query = query.order("priority_index", desc=True, nullsfirst=False)

        try:
            result = await query.range(offset, offset + limit - 1).execute()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fetch leads (page={page}, limit={limit}, "
                f"score_tier={score_tier}, sort_by={sort_by}, segment={segment})"
            ) from exc

        return {
            "leads": result.data or [],
            "total": result.count or 0,
            "page": page,
            "limit": limit,
        }

    async def get_lead_by_id(self, lead_id: str) -> dict | None:
        """Fetch a single lead row by UUID. Returns None if not found or not a UUID."""
        return await self._get_by_id("leads", lead_id)

    async def _get_by_id(self, table: str, row_id: str) -> dict | None:
        """Fetch one row by id. .single() raises on 0 rows, so use limit(1) instead."""
        if not _UUID_RE.match(row_id or ""):
            return None
        result = await self._client.table(table).select("*").eq("id", row_id).limit(1).execute()
        return result.data[0] if result.data else None

    async def update_research(self, lead_id: str, summary: str, sources: list[str]) -> None:
        """Persist web research as soon as it returns and advance status to 'researched'."""
        await (
            self._client.table("leads")
            .update({
                "research_summary": summary,
                "research_sources": sources,
                "status": "researched",
                "researched_at": _now(),
            })
            .eq("id", lead_id)
            .execute()
        )

    async def update_enrichment(self, lead_id: str, insight: LeadInsight) -> None:
        """Persist AI enrichment output and advance the lead status to 'enriched'."""
        await (
            self._client.table("leads")
            .update({
                "lead_score":               insight.lead_score,
                "score_rationale":          insight.score_rationale,
                "convertibility_score":     insight.convertibility_score,
                "convertibility_rationale": insight.convertibility_rationale,
                "distance_miles":           insight.distance_miles,
                "distance_band":            insight.distance_band,
                "priority_index":           insight.priority_index,
                "ai_summary":               insight.ai_summary,
                "talking_points":           insight.talking_points,
                "recommended_approach":     insight.recommended_approach,
                "decision_makers":          [d.model_dump() for d in insight.decision_makers],
                "status":                   "enriched",
                "error_message":            None,
                "enriched_at":              _now(),
            })
            .eq("id", lead_id)
            .execute()
        )

    async def mark_lead_failed(self, lead_id: str, error: str) -> None:
        """Record an enrichment failure. Truncates the error message to 500 characters to fit the column."""
        await (
            self._client.table("leads")
            .update({"status": "failed", "error_message": error[:500]})
            .eq("id", lead_id)
            .execute()
        )

    # ── Pipeline run tracking ──────────────────────────────────────────────

    async def interrupt_stale_runs(self) -> int:
        """Mark any pipeline_runs stuck in 'running' as failed with an interrupted message.

        Called once at server startup so runs orphaned by a previous server
        restart are never left displayed as 'running' forever in the UI.
        Returns the number of rows updated.
        """
        result = (
            await self._client.table("pipeline_runs")
            .update({
                "status": "failed",
                "error_message": "Server restarted — pipeline was interrupted. Re-run to resume (already-enriched leads will be skipped).",
                "finished_at": _now(),
            })
            .eq("status", "running")
            .execute()
        )
        count = len(result.data) if result.data else 0
        if count:
            logger.warning("Marked %d stale pipeline run(s) as failed on startup", count)
        return count

    async def get_latest_pipeline_run(self) -> dict | None:
        """Return the most recent pipeline_runs row regardless of status."""
        result = (
            await self._client.table("pipeline_runs")
            .select("*")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def create_pipeline_run(
        self, postal_code: str, country_code: str, distance: int, segment: str,
    ) -> str:
        """Insert a new 'running' pipeline_runs row and return its UUID.

        A partial unique index (one row WHERE status='running') makes the database
        the arbiter of "only one active run", so two simultaneous clicks cannot
        both start paid pipelines. The loser gets ActiveRunError with the winner's id.
        """
        try:
            result = await (
                self._client.table("pipeline_runs")
                .insert({
                    "postal_code": postal_code,
                    "country_code": country_code,
                    "distance": distance,
                    "segment": segment,
                })
                .execute()
            )
        except APIError as exc:
            if exc.code != _UNIQUE_VIOLATION:
                raise
            active = await self.get_active_pipeline_run()
            raise ActiveRunError(active["id"] if active else None) from exc
        return result.data[0]["id"]

    async def get_active_pipeline_run(self) -> dict | None:
        """Return the currently running pipeline run, if any."""
        result = await (
            self._client.table("pipeline_runs")
            .select("*")
            .eq("status", "running")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    async def get_pipeline_run(self, run_id: str) -> dict | None:
        """Fetch a pipeline run by UUID for status polling. None if unknown."""
        return await self._get_by_id("pipeline_runs", run_id)

    async def update_pipeline_progress(self, run_id: str, **kwargs) -> None:
        """Patch arbitrary columns on a pipeline run (e.g. the leads_scraped counter)."""
        await self._client.table("pipeline_runs").update(kwargs).eq("id", run_id).execute()

    async def request_cancel(self, run_id: str) -> bool:
        """Flag a running run for cooperative cancellation. False if it is not running.

        Idempotent: repeating it on a running run keeps the flag set and returns True.
        """
        result = await (
            self._client.table("pipeline_runs")
            .update({"cancel_requested": True})
            .eq("id", run_id)
            .eq("status", "running")
            .execute()
        )
        return bool(result.data)

    async def is_cancel_requested(self, run_id: str) -> bool:
        """Polled by the worker between leads."""
        result = await (
            self._client.table("pipeline_runs")
            .select("cancel_requested")
            .eq("id", run_id)
            .limit(1)
            .execute()
        )
        return bool(result.data and result.data[0].get("cancel_requested"))

    async def finish_pipeline_run(self, run_id: str, leads_enriched: int, leads_failed: int) -> str:
        """Finalize a running run and return the status that was persisted.

        Two conditional single-statement updates decide the outcome atomically:
          1. 'completed' only WHERE status='running' AND cancel_requested=false
          2. otherwise 'cancelled' WHERE status='running'
        A cancel accepted at any moment therefore can never end 'completed'
        (request_cancel only matches running rows, so it either landed before
        step 1 — and step 1 matches nothing — or it is rejected with 409).
        A run that is already terminal is left untouched and its status returned.
        """
        payload = {"leads_enriched": leads_enriched, "leads_failed": leads_failed,
                   "finished_at": _now()}
        done = await (
            self._client.table("pipeline_runs")
            .update({**payload, "status": "completed"})
            .eq("id", run_id).eq("status", "running").eq("cancel_requested", False)
            .execute()
        )
        if done.data:
            return "completed"
        cancelled = await (
            self._client.table("pipeline_runs")
            .update({**payload, "status": "cancelled"})
            .eq("id", run_id).eq("status", "running")
            .execute()
        )
        if cancelled.data:
            return "cancelled"
        run = await self.get_pipeline_run(run_id)
        return run["status"] if run else "unknown"

    async def fail_pipeline_run(self, run_id: str, error: str) -> None:
        """Mark a still-running run failed with its error (≤500 chars). Terminal runs are untouched."""
        await (
            self._client.table("pipeline_runs")
            .update({
                "status": "failed",
                "error_message": error[:500],
                "finished_at": _now(),
            })
            .eq("id", run_id)
            .eq("status", "running")
            .execute()
        )
