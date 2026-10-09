"""Orchestrates the scrape → (research → enrich) per-lead pipeline.

Execution model
---------------
1. Scrape the GAF directory once (browser capture + Coveo pagination).
2. Bulk-upsert every contractor in one round trip (statuses of researched /
   enriched leads are preserved, so re-runs are idempotent and resumable).
3. Stream each unfinished lead through research → persist → enrich → persist,
   with at most `concurrency` leads in flight. Work is saved the moment each
   step finishes, so a crash or cancel loses only the leads in flight — never
   the whole batch — and the dashboard fills in live while the run progresses.

Failure semantics: a stage that cannot produce trustworthy output raises a
typed error (services/errors.py). A ScrapeError fails the whole run; a
ResearchError or any other per-lead error marks only that lead 'failed' (it is
retried on the next run, reusing any saved research) and the batch carries on.
A run 'completes' with zero leads only when GAF explicitly reported none.

Cancellation is cooperative and database-backed: pipeline_runs.cancel_requested
is read before scraping, after scraping, and before every lead starts, so no
new lead begins once a cancel is observed; in-flight leads drain. The final
status is written by a conditional update in the repository, so a run whose
cancel was accepted can never end 'completed', and a finished run is never
reopened.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

from supabase import acreate_client

from app.config import ScraperConfig, settings
from app.repositories.lead_repository import LeadRepository
from app.services.errors import public_error

logger = logging.getLogger(__name__)

# Upper bound for one lead's research + enrichment (web search can be slow).
_LEAD_TIMEOUT_S = 240


async def _default_repo_factory() -> LeadRepository:
    """Give the background task its own Supabase client (not the request-scoped one)."""
    client = await acreate_client(settings.supabase_url, settings.supabase_key)
    return LeadRepository(client)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


@dataclass
class _RunState:
    """Mutable per-run counters shared by the lead workers."""
    enriched: int = 0
    failed: int = 0
    cancelled: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class PipelineService:
    """Coordinates one end-to-end pipeline run."""

    def __init__(
        self,
        scraper,
        researcher,
        enricher,
        repo_factory=_default_repo_factory,
        concurrency: int | None = None,
    ):
        self._scraper = scraper
        self._researcher = researcher
        self._enricher = enricher
        self._repo_factory = repo_factory
        self._concurrency = concurrency or settings.pipeline_concurrency

    async def execute(self, run_id: str, request) -> None:
        """Run the pipeline for one pipeline_runs row.

        Never raises: an unrecoverable error is recorded on the run row (the
        source of truth the UI polls) and logged once, instead of surfacing as a
        second, unhandled traceback from the BackgroundTask runner.
        """
        repo = await self._repo_factory()
        started = time.monotonic()
        state = _RunState()
        try:
            if not await repo.is_cancel_requested(run_id):
                await self._scrape_and_process(repo, run_id, state, request)
            final = await repo.finish_pipeline_run(run_id, state.enriched, state.failed)
            logger.info("run.finished run_id=%s status=%s enriched=%d failed=%d duration_ms=%d",
                        run_id, final, state.enriched, state.failed, _elapsed_ms(started))
        except Exception as exc:
            logger.error("run.failed run_id=%s error=%s", run_id, public_error(exc),
                         exc_info=not getattr(exc, "stage", None))
            try:
                await repo.fail_pipeline_run(run_id, public_error(exc))
            except Exception:
                logger.exception("Could not record failure for run %s", run_id)

    async def _scrape_and_process(self, repo, run_id: str, state: _RunState, request) -> None:
        """Scrape + bulk-upsert, then stream unfinished leads unless a cancel arrived."""
        config = ScraperConfig(
            postal_code=request.postal_code,
            country_code=request.country_code,
            distance=request.distance,
            segment=request.segment,
            limit=request.limit,
        )
        contractors = await self._scraper.scrape_contractors(config)
        rows = await repo.upsert_contractors(contractors)
        state.enriched = sum(1 for r in rows if r.get("status") == "enriched")
        await repo.update_pipeline_progress(
            run_id, leads_scraped=len(rows), leads_enriched=state.enriched,
        )
        by_id = {c.gaf_contractor_id: c for c in contractors}
        pending = [(r, by_id[r["gaf_contractor_id"]]) for r in rows
                   if r.get("status") != "enriched" and r.get("gaf_contractor_id") in by_id]
        logger.info("run.scraped run_id=%s scraped=%d already_enriched=%d pending=%d",
                    run_id, len(rows), state.enriched, len(pending))
        await self._process_all(repo, run_id, state, pending, config.postal_code)

    async def _process_all(self, repo, run_id, state, pending, postal_code) -> None:
        """Run every pending lead with bounded concurrency; stop starting leads on cancel."""
        semaphore = asyncio.Semaphore(self._concurrency)

        async def bounded(row, contractor):
            async with semaphore:
                if await self._should_stop(repo, run_id, state):
                    return
                await self._process_lead(repo, run_id, state, row, contractor, postal_code)

        await asyncio.gather(*(bounded(r, c) for r, c in pending), return_exceptions=True)

    async def _should_stop(self, repo, run_id: str, state: _RunState) -> bool:
        """Read the cancel flag from the database before a lead starts (sticky once seen)."""
        if state.cancelled:
            return True
        try:
            if await repo.is_cancel_requested(run_id):
                logger.info("run.cancel_observed run_id=%s draining in-flight leads", run_id)
                state.cancelled = True
        except Exception:
            logger.warning("Cancel check failed for run %s", run_id, exc_info=True)
        return state.cancelled

    async def _process_lead(self, repo, run_id, state, row, contractor, postal_code) -> None:
        """Research (unless stored), enrich and persist one lead; isolate its failure."""
        started = time.monotonic()
        try:
            insight = await asyncio.wait_for(
                self._research_and_enrich(repo, row, contractor, postal_code),
                timeout=_LEAD_TIMEOUT_S,
            )
            await repo.update_enrichment(row["id"], insight)
            await self._record(repo, run_id, state, enriched=1)
            logger.info("lead.enriched run_id=%s lead_id=%s duration_ms=%d",
                        run_id, row["id"], _elapsed_ms(started))
        except Exception as exc:
            message = public_error(exc)
            logger.warning("lead.failed run_id=%s lead_id=%s stage=%s error=%s",
                           run_id, row["id"], getattr(exc, "stage", "enrich"), message)
            await repo.mark_lead_failed(row["id"], message)
            await self._record(repo, run_id, state, failed=1)

    async def _research_and_enrich(self, repo, row, contractor, postal_code):
        """Reuse saved research when present; otherwise research and save it first.

        Saved research is reused whatever the lead's status (a lead whose
        enrichment failed keeps its paid-for research). A ResearchError
        propagates, so enrichment never runs without evidence.
        """
        saved = (row.get("research_summary") or "").strip()
        if saved:
            research = {"summary": saved, "sources": row.get("research_sources") or []}
        else:
            started = time.monotonic()
            research = await self._researcher.research(contractor)
            logger.info("lead.researched lead_id=%s sources=%d usage=%s duration_ms=%d",
                        row["id"], len(research.get("sources", [])),
                        research.get("usage", {}), _elapsed_ms(started))
            await repo.update_research(row["id"], research["summary"],
                                       research.get("sources", []))
        return await self._enricher.enrich_async(
            contractor, research, search_postal_code=postal_code,
        )

    async def _record(self, repo, run_id, state, enriched=0, failed=0) -> None:
        """Bump counters and publish progress so pollers see live numbers."""
        async with state.lock:
            state.enriched += enriched
            state.failed += failed
            await repo.update_pipeline_progress(
                run_id, leads_enriched=state.enriched, leads_failed=state.failed,
            )
