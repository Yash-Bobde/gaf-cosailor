"""FastAPI application entry point.

Creates the app, configures CORS for the Next.js dev server, and registers
the leads and pipeline routers under /api/*.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import leads, pipeline
from app.config import settings
from app.database import get_supabase
from app.repositories.lead_repository import LeadRepository


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise shared DB client and recover orphaned pipeline runs."""
    client = await get_supabase()
    repo = LeadRepository(client)
    await repo.interrupt_stale_runs()
    yield


app = FastAPI(title="Cosailor Insights API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # Explicit allowlist from CORS_ORIGINS (default: the local frontend on :3000).
    # No "*.vercel.app"-style wildcard: it would admit anyone's deployment to this
    # unauthenticated API. No cookies are used, so credentials stay off.
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router, prefix="/api/leads", tags=["leads"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])


@app.get("/health")
async def health():
    """Liveness probe used by the frontend and infrastructure to confirm the API is up."""
    return {"status": "ok"}
