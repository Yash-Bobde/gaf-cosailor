"""In-memory stand-in for the supabase-py async client.

Implements just enough of the PostgREST query builder (select / insert / update /
upsert + eq / in_ / gte / lte / order / range / limit) for LeadRepository to run
UNCHANGED against it, so repository and pipeline contract tests exercise real
repository code without touching a live database.

It also reproduces the two database guarantees the app relies on:
  * the partial unique index `one_running_pipeline` (a second 'running' row → 23505)
  * the UNIQUE gaf_contractor_id upsert key on leads
"""
import copy
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from postgrest.exceptions import APIError

_RUN_DEFAULTS = {
    "status": "running", "leads_scraped": 0, "leads_enriched": 0, "leads_failed": 0,
    "cancel_requested": False, "finished_at": None, "error_message": None,
}
_LEAD_DEFAULTS = {
    "status": "scraped", "research_summary": None, "research_sources": [],
    "decision_makers": [], "error_message": None, "lead_score": None,
    "priority_index": None, "enriched_at": None,
}


@dataclass
class _Result:
    data: list
    count: int | None = None


class _Query:
    def __init__(self, db: "FakeSupabase", table: str):
        self._db, self._table = db, table
        self._op, self._payload, self._count = "select", None, None
        self._filters: list = []
        self._order: tuple | None = None
        self._range: tuple | None = None
        self._limit: int | None = None
        self._on_conflict: str | None = None

    # ── operations ─────────────────────────────────────────────────────
    def select(self, _cols="*", count=None):
        self._op, self._count = "select", count
        return self

    def insert(self, payload):
        self._op, self._payload = "insert", payload
        return self

    def update(self, payload):
        self._op, self._payload = "update", payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op, self._payload, self._on_conflict = "upsert", payload, on_conflict
        return self

    # ── filters / modifiers ────────────────────────────────────────────
    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        vals = list(vals)
        self._filters.append(lambda r: r.get(col) in vals)
        return self

    def gte(self, col, val):
        self._filters.append(lambda r: r.get(col) is not None and r[col] >= val)
        return self

    def lte(self, col, val):
        self._filters.append(lambda r: r.get(col) is not None and r[col] <= val)
        return self

    def order(self, col, desc=False, nullsfirst=None):
        self._order = (col, desc)
        return self

    def range(self, start, end):
        self._range = (start, end)
        return self

    def limit(self, n):
        self._limit = n
        return self

    # ── execution ──────────────────────────────────────────────────────
    async def execute(self) -> _Result:
        self._db.calls.append((self._table, self._op))
        handler = getattr(self, f"_exec_{self._op}")
        return handler()

    def _matching(self) -> list[dict]:
        return [r for r in self._db.tables[self._table] if all(f(r) for f in self._filters)]

    def _exec_select(self) -> _Result:
        rows = self._matching()
        total = len(rows)
        if self._order:
            col, desc = self._order
            present = sorted((r for r in rows if r.get(col) is not None),
                             key=lambda r: r[col], reverse=desc)
            rows = present + [r for r in rows if r.get(col) is None]
        if self._range:
            rows = rows[self._range[0]: self._range[1] + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Result(copy.deepcopy(rows), total if self._count else None)

    def _exec_update(self) -> _Result:
        changed = []
        for row in self._matching():
            row.update(copy.deepcopy(self._payload))
            changed.append(copy.deepcopy(row))
        return _Result(changed)

    def _exec_insert(self) -> _Result:
        rows = self._payload if isinstance(self._payload, list) else [self._payload]
        return _Result([self._db.insert_row(self._table, r) for r in rows])

    def _exec_upsert(self) -> _Result:
        out = []
        for payload in self._payload:
            key = payload.get(self._on_conflict)
            existing = next((r for r in self._db.tables[self._table]
                             if key is not None and r.get(self._on_conflict) == key), None)
            if existing is not None:
                existing.update(copy.deepcopy(payload))
                out.append(copy.deepcopy(existing))
            else:
                out.append(self._db.insert_row(self._table, payload))
        return _Result(out)


class FakeSupabase:
    """Minimal async Supabase client over in-memory tables."""

    def __init__(self):
        self.tables: dict[str, list[dict]] = {"leads": [], "pipeline_runs": []}
        self.calls: list[tuple] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def insert_row(self, table: str, payload: dict) -> dict:
        defaults = _RUN_DEFAULTS if table == "pipeline_runs" else _LEAD_DEFAULTS
        row = {"id": str(uuid.uuid4()), **copy.deepcopy(defaults), **copy.deepcopy(payload)}
        row.setdefault("started_at" if table == "pipeline_runs" else "created_at",
                       datetime.now(timezone.utc).isoformat())
        if table == "pipeline_runs" and row["status"] == "running" and self._has_running():
            raise APIError({"message": "duplicate key value violates unique constraint "
                                       "\"one_running_pipeline\"", "code": "23505"})
        self.tables[table].append(row)
        return copy.deepcopy(row)

    def _has_running(self) -> bool:
        return any(r["status"] == "running" for r in self.tables["pipeline_runs"])

    def run(self, run_id: str) -> dict:
        return next(r for r in self.tables["pipeline_runs"] if r["id"] == run_id)
