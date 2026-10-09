"""Shared Supabase async client — initialized once, reused across requests.

Creating a new acreate_client() per request adds a full TCP+TLS handshake on
every call. This module holds a process-level singleton so the connection is
established once on the first request and reused for all subsequent ones.

Note: the pipeline background task deliberately creates its OWN client
(see pipeline.py) to avoid sharing a session across the request/background-task
boundary. This singleton is for the router (short-lived HTTP requests) only.
"""
from supabase import AsyncClient, acreate_client
from app.config import settings

_client: AsyncClient | None = None


async def get_supabase() -> AsyncClient:
    """Return the shared async Supabase client, creating it on first call."""
    global _client
    if _client is None:
        _client = await acreate_client(settings.supabase_url, settings.supabase_key)
    return _client
