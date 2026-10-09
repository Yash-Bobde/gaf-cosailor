"""FastAPI router for pipeline trigger, cancel and status-polling endpoints.

POST /run               — starts a pipeline BackgroundTask and returns 202 immediately
                          (409 with the active run_id if one is already running).
POST /{run_id}/cancel   — requests cooperative cancellation of a running run.
GET  /latest            — most recent run (204 when none), used to restore UI state.
GET  /status/{run_id}   — current progress for polling.

Dependencies (repository, pipeline service) are injected with Depends so the
HTTP layer is testable without Supabase, Perplexity or OpenAI.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

from app.config import settings
from app.database import get_supabase
from app.models.lead import (
    CancelResponse, PipelineRunRequest, PipelineRunResponse, PipelineStatusResponse,
)
from app.repositories.lead_repository import ActiveRunError, LeadRepository
from app.services.enricher import LeadEnricher
from app.services.pipeline import PipelineService
from app.services.playwright_scraper import PlaywrightScraper
from app.services.researcher import ContractorResearcher

router = APIRouter()


async def get_repo() -> LeadRepository:
    """Repository backed by the shared request-scoped Supabase client."""
    return LeadRepository(await get_supabase())


def get_pipeline_service() -> PipelineService:
    """Wire the production scraper, researcher and enricher."""
    return PipelineService(
        scraper=PlaywrightScraper(),
        researcher=ContractorResearcher(api_key=settings.perplexity_api_key,
                                        preset=settings.perplexity_preset),
        enricher=LeadEnricher(api_key=settings.openai_api_key, model=settings.openai_model),
    )


def _run_to_status(run: dict) -> dict:
    """Map a pipeline_runs DB row to the PipelineStatusResponse shape."""
    return {**run, "run_id": run["id"]}


@router.post("/run", status_code=202, response_model=PipelineRunResponse)
async def run_pipeline(
    body: PipelineRunRequest,
    background_tasks: BackgroundTasks,
    repo: LeadRepository = Depends(get_repo),
    service: PipelineService = Depends(get_pipeline_service),
):
    """Queue a pipeline run and return 202 with a run_id for status polling."""
    try:
        run_id = await repo.create_pipeline_run(
            postal_code=body.postal_code,
            country_code=body.country_code,
            distance=body.distance,
            segment=body.segment,
        )
    except ActiveRunError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "A pipeline run is already in progress.", "run_id": exc.run_id},
        ) from exc

    background_tasks.add_task(service.execute, run_id, body)
    return PipelineRunResponse(
        run_id=run_id,
        status="running",
        message=f"Pipeline started. Poll /api/pipeline/status/{run_id} for progress.",
    )


@router.post("/{run_id}/cancel", status_code=202, response_model=CancelResponse)
async def cancel_pipeline(run_id: str, repo: LeadRepository = Depends(get_repo)):
    """Ask a running pipeline to stop after its in-flight leads finish.

    Idempotent: repeating the call on a running or already-cancelled run is 202.
    A run that finished 'completed' or 'failed' cannot be cancelled (409).
    """
    accepted = await repo.request_cancel(run_id)
    run = await repo.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    if not accepted and run["status"] != "cancelled":
        raise HTTPException(status_code=409, detail=f"Run is {run['status']}, not running")
    return CancelResponse(run_id=run["id"], status=run["status"], cancel_requested=True)


@router.get("/latest", response_model=PipelineStatusResponse,
            responses={204: {"description": "No pipeline run has been started yet"}})
async def latest_pipeline_run(repo: LeadRepository = Depends(get_repo)):
    """Return the most recent pipeline run regardless of status.

    204 (not 404) when none exist: "no runs yet" is a normal first-visit state,
    and a 404 would log a console error in every fresh browser session.
    """
    run = await repo.get_latest_pipeline_run()
    if not run:
        return Response(status_code=204)
    return _run_to_status(run)


@router.get("/status/{run_id}", response_model=PipelineStatusResponse)
async def pipeline_status(run_id: str, repo: LeadRepository = Depends(get_repo)):
    """Return current state of a pipeline run. 404 when run_id is unknown."""
    run = await repo.get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return _run_to_status(run)
