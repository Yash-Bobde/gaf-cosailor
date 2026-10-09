"""Read-only demo preflight — run before starting (or presenting) the app.

    cd backend
    .venv/Scripts/python scripts/preflight.py        # Windows
    .venv/bin/python scripts/preflight.py            # macOS / Linux

Checks, without printing any secret value, writing to the database, or making
a paid API call:
  1. required env-var NAMES in backend/.env and frontend/.env.local
  2. frontend NEXT_PUBLIC_API_URL uses the documented backend port (8000)
  3. Python packages import; Playwright Chromium is installed
  4. Node / npm available and frontend dependencies installed
  5. Supabase reachable and schema has every column the app reads (SELECT only)
  6. backend /health answers at the frontend's configured API URL (if running)

Exit code 0 = ready (warnings allowed), 1 = a required check failed.
"""
import asyncio
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
EXPECTED_PORT = 8000
BACKEND_VARS = ("SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY", "PERPLEXITY_API_KEY")
FRONTEND_VARS = ("NEXT_PUBLIC_API_URL",)
_LEAD_COLUMNS = ("id,status,segment,decision_makers,research_sources,priority_index,"
                 "convertibility_score,gaf_profile_url,error_message")
_RUN_COLUMNS = "id,status,segment,cancel_requested,leads_failed,leads_scraped,error_message"


class Report:
    """Collects check results and prints them as they happen."""

    def __init__(self):
        self.failed = 0

    def ok(self, msg: str) -> None:
        print(f"[ OK ] {msg}")

    def warn(self, msg: str) -> None:
        print(f"[WARN] {msg}")

    def fail(self, msg: str) -> None:
        self.failed += 1
        print(f"[FAIL] {msg}")


def check_env(report: Report) -> tuple[dict, dict]:
    backend_env = dotenv_values(BACKEND / ".env")
    frontend_env = dotenv_values(FRONTEND / ".env.local")
    for label, env, names in (("backend/.env", backend_env, BACKEND_VARS),
                              ("frontend/.env.local", frontend_env, FRONTEND_VARS)):
        missing = [n for n in names if not env.get(n)]
        if missing:
            report.fail(f"{label}: missing {', '.join(missing)} (see the .env.example next to it)")
        else:
            report.ok(f"{label}: {', '.join(names)} set (values not shown)")
    stale = [n for n in frontend_env if n.startswith("NEXT_PUBLIC_SUPABASE")]
    if stale:
        report.warn(f"frontend/.env.local has unused {', '.join(stale)} - safe to delete")
    return backend_env, frontend_env


def check_api_url(report: Report, frontend_env: dict) -> str | None:
    api_url = (frontend_env.get("NEXT_PUBLIC_API_URL") or "").rstrip("/")
    if not api_url:
        return None
    parsed = urlparse(api_url)
    if parsed.hostname == "localhost":
        report.warn("NEXT_PUBLIC_API_URL uses 'localhost' - Node may resolve it to IPv6; "
                    "use 127.0.0.1")
    if parsed.port != EXPECTED_PORT:
        report.fail(f"NEXT_PUBLIC_API_URL port is {parsed.port}, backend runs on "
                    f"{EXPECTED_PORT} - set NEXT_PUBLIC_API_URL=http://127.0.0.1:{EXPECTED_PORT}")
    else:
        report.ok(f"NEXT_PUBLIC_API_URL points at port {EXPECTED_PORT}")
    return api_url


def check_python(report: Report) -> None:
    missing = []
    for module in ("fastapi", "uvicorn", "supabase", "playwright", "openai", "pgeocode", "tenacity"):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        report.fail(f"Python packages missing: {', '.join(missing)} - pip install -r requirements.txt")
    else:
        report.ok(f"Python {sys.version.split()[0]} with backend packages installed")
    check_chromium(report)


def check_chromium(report: Report) -> None:
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            path = Path(pw.chromium.executable_path)
    except Exception as exc:  # driver missing or broken install
        report.fail(f"Playwright unavailable ({type(exc).__name__}) - pip install playwright")
        return
    if path.exists():
        report.ok("Playwright Chromium installed")
    else:
        report.fail("Playwright Chromium not installed - run: python -m playwright install chromium")


def check_node(report: Report) -> None:
    node = shutil.which("node")
    if not node:
        report.fail("Node.js not found on PATH (Node 20+ required)")
        return
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip()
    report.ok(f"Node {version}")
    if (FRONTEND / "node_modules" / "next").exists():
        report.ok("frontend dependencies installed")
    else:
        report.fail("frontend/node_modules missing - run: cd frontend && npm ci")


async def check_database(report: Report, backend_env: dict) -> None:
    url, key = backend_env.get("SUPABASE_URL"), backend_env.get("SUPABASE_KEY")
    if not url or not key:
        return
    from supabase import acreate_client
    try:
        client = await acreate_client(url, key)
        leads = await client.table("leads").select(_LEAD_COLUMNS, count="exact").limit(1).execute()
        await (client.table("pipeline_runs").select(_RUN_COLUMNS)
               .eq("cancel_requested", False).limit(1).execute())
    except Exception as exc:
        report.fail(f"Supabase query failed ({type(exc).__name__}) - check SUPABASE_URL/KEY and "
                    "that app/schema.sql (incl. the 2026-09-24 migration) has been applied")
        return
    report.ok(f"Supabase reachable, schema has required columns ({leads.count} leads stored)")
    if not leads.count:
        report.warn("no leads stored yet - run one small pipeline (Max leads = 1-3) before a demo")


async def check_backend(report: Report, api_url: str | None) -> None:
    if not api_url:
        return
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{api_url}/health")
        resp.raise_for_status()
        report.ok(f"backend /health OK at {api_url}")
    except Exception:
        report.warn(f"backend not answering at {api_url}/health - start it with: "
                    f"python -m uvicorn app.main:app --port {EXPECTED_PORT}")


async def _network_checks(report: Report, backend_env: dict, api_url: str | None) -> None:
    await check_database(report, backend_env)
    await check_backend(report, api_url)


def main() -> int:
    report = Report()
    print("Cosailor Insights preflight (read-only, no paid calls)\n")
    backend_env, frontend_env = check_env(report)
    api_url = check_api_url(report, frontend_env)
    check_python(report)          # sync Playwright API: must run outside an event loop
    check_node(report)
    asyncio.run(_network_checks(report, backend_env, api_url))
    print("\nREADY" if not report.failed else f"\nNOT READY - {report.failed} check(s) failed")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
