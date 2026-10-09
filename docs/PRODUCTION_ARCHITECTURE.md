# Production architecture — future design (NOT implemented)

> **Status: design only.** Nothing in this document is built. The submitted app runs the
> pipeline as a FastAPI `BackgroundTask` with a single global run guard, no authentication
> and a backend-only Supabase key. That is a deliberate case-study/demo boundary. This page
> describes how the same code evolves to serve hundreds or thousands of sales reps.

## 1. What exists today (demo architecture)

| Concern | Today | Why it is not production-grade |
|---|---|---|
| Execution | `BackgroundTasks` inside the web process | Work dies with the process; cannot scale horizontally |
| Concurrency | `one_running_pipeline` partial unique index (global) | Serializes every user behind one run |
| Recovery | Startup marks orphaned runs `failed`; per-lead work is persisted, so a manual re-run resumes | No automatic resume, no leases |
| Cancellation | `cancel_requested` in the DB, read before scrape, before each lead, and at finalization (conditional update) | Correct for one worker; no per-tenant scoping |
| Auth | None | Anyone who can reach the API can read leads and start paid runs |
| Data access | Backend holds the only Supabase key; RLS disabled | Fine for a single-tenant demo; unsafe for multi-tenant |
| Cost control | `limit` per run (dashboard default 10) | No quota, no budget, no per-rep rate limit |

What carries over unchanged: the router → service → repository layering, typed stage errors
(`ScrapeError`, `ResearchError`), per-lead persistence, score clamping and grounding. The
worker will call the same `PipelineService` stage functions.

## 2. Authentication and authorization

- **Identity:** Supabase Auth (or the company IdP via OIDC/SAML). The browser holds only a
  user session JWT — never a service key, never a `NEXT_PUBLIC_*` secret.
- **API boundary:** FastAPI verifies the JWT on every request (JWKS, audience, expiry) and
  derives `user_id`, `org_id` and `role` from claims — never from the request body.
- **Roles:** `rep` (read own territory's leads, start runs within quota), `manager` (all
  territories in the org, retry/dead-letter actions), `admin` (org settings, budgets).
- **Mutation endpoints** (`POST /run`, `/cancel`, retries) require an authenticated role;
  there is no anonymous mode outside a clearly named local `DEMO_MODE=1`.

## 3. Tenancy and ownership model

```
organizations(id, name, monthly_budget_usd, max_concurrent_runs)
memberships(org_id, user_id, role)
territories(id, org_id, postal_code, distance, segment)          -- what a rep covers
contractors(id, gaf_contractor_id UNIQUE, scraped facts…)        -- global public GAF data
lead_insights(id, org_id, contractor_id, research…, scores…,     -- per-org, paid-for AI output
              UNIQUE(org_id, contractor_id))
pipeline_runs(id, org_id, territory_id, requested_by, status, …)
lead_jobs(id, run_id, org_id, contractor_id, state, attempts, …) -- see §5
audit_log(id, org_id, actor_id, action, target, at)
```

Public GAF facts are shared across orgs (scraped once); research and scores are owned per
org because orgs may use different prompts, models or budgets.

## 4. Row-Level Security

RLS only protects data when requests carry a user identity. Two paths:

1. **Browser → Supabase directly (reads):** enable RLS on every tenant table with policies
   keyed on the JWT, e.g.
   ```sql
   ALTER TABLE lead_insights ENABLE ROW LEVEL SECURITY;
   CREATE POLICY org_read ON lead_insights FOR SELECT
     USING (org_id IN (SELECT org_id FROM memberships WHERE user_id = auth.uid()));
   ```
   Writes from the browser are denied (no INSERT/UPDATE policies).
2. **Workers → Postgres (writes):** use a dedicated worker role (not the Supabase
   `service_role` shared with the API) whose grants are limited to the job and insight
   tables, and every query is scoped by `org_id` from the job row.

The current "RLS disabled + backend-only key" design is acceptable only because there is
exactly one tenant and no browser access to Supabase. It must not ship to real users.

## 5. Durable execution: queue, workers and leases

Postgres-backed queue (fits the existing stack; `pgmq`, Graphile Worker or a `lead_jobs`
table with `FOR UPDATE SKIP LOCKED`). A managed queue (SQS/Cloud Tasks) is an equivalent choice.

```
POST /runs ──► pipeline_runs(queued) ──► scrape job ──► lead_jobs × N (queued)
                                                              │
                          workers claim with SKIP LOCKED ◄────┘
                          lease_expires_at = now() + 5 min, heartbeat every 60 s
                          research → persist → enrich → persist (idempotent writes)
                          success → done | retryable error → queued (backoff) |
                          attempts ≥ 5 or terminal error → dead_letter
```

**Lead job states:** `queued → leased → researched → done`, plus `failed_retryable`,
`dead_letter`, `cancelled`. Only these transitions are legal; each is a conditional
`UPDATE … WHERE state = <expected>` so a stale worker cannot overwrite a newer state (the same
pattern the demo already uses for `finish_pipeline_run`).

- **Leases & heartbeat:** a worker owns a job until `lease_expires_at`; it extends the lease
  while working. An expired lease returns the job to `queued`, so a killed worker loses at most
  one lead's in-flight call — and saved research is reused, as today.
- **Retries & backoff:** retry only retryable classes (HTTP 429/5xx, network, GAF capture
  timeouts) with exponential backoff and jitter; `next_attempt_at` is stored on the row.
- **Dead letter:** terminal errors (401/400, malformed output after N tries) go to
  `dead_letter` with the sanitized error; managers can bulk-retry from the UI.
- **Idempotency:** `POST /runs` accepts an `Idempotency-Key`; lead jobs are unique on
  `(run_id, contractor_id)`; insight writes are upserts on `(org_id, contractor_id)`.
- **Cancellation:** `pipeline_runs.cancel_requested` stays the source of truth. Workers check
  it before claiming and before each stage; a run finalizes `cancelled` via the same
  conditional update. Queued jobs of a cancelled run are moved to `cancelled` in one statement.
- **Progress:** counts are derived (`SELECT state, count(*) FROM lead_jobs WHERE run_id = …`)
  instead of read-modify-write counters, so many workers never race on one row.
- **Realtime:** replace 3-second polling with Supabase Realtime / SSE on run and insight rows.

## 6. Tenant-scoped concurrency, rate and cost limits

- Replace the global `one_running_pipeline` index with a per-territory one:
  `UNIQUE (territory_id) WHERE status IN ('queued','running')`.
- `organizations.max_concurrent_runs` and global Perplexity and OpenAI token buckets (shared by all workers,
  sized to each account's TPM/RPM limits) bound concurrency.
- Budget guard: before a run starts, estimate cost (`leads × avg research+enrichment cost`) and
  refuse runs that would exceed the org's remaining monthly budget; record actual token usage
  per job (the demo already logs `usage` per research and enrichment call).
- Per-rep rate limit on `POST /runs` (e.g. 10/hour) and a hard cap on `limit`.
- Skip re-research of contractors whose research is fresher than N days (reuse is free).

## 7. Observability

Already in the demo: sanitized structured log lines with run and lead IDs —
`scrape.done gaf_total wanted parsed duration_ms`, `lead.researched usage duration_ms`,
`lead.failed stage error`, `run.finished status enriched failed duration_ms`.

Production additions and alert thresholds:

| Signal | Alert when |
|---|---|
| Scrape yield (`parsed / min(gaf_total, limit)`) | < 0.9 for 3 runs (GAF format drift / Akamai) |
| Scrape failures | any `ScrapeError` spike > 3 in 15 min |
| Research failure rate | > 10 % of leads in 1 h |
| Empty-evidence rate (research with 0 citations) | > 25 % in 1 h |
| Lead job age (oldest `queued`) | > 15 min |
| Dead-letter count | > 0 new in 1 h (page) |
| Token spend vs budget | > 80 % of org monthly budget |
| p95 research latency | > 60 s |

Traces carry `run_id`/`lead_id`; prompts and research payloads are not logged (they can contain
personal contact data).

## 8. Data retention and privacy

Decision-maker names are personal data. Store only name, title, source URL and the evidence
sentence; purge research older than 12 months or on request; record reads/exports of contact
data in `audit_log`; honour deletion requests by `gaf_contractor_id` across orgs.

## 9. Migration path from the demo

1. **Versioned migrations:** move `app/schema.sql` into numbered migration files (Supabase CLI
   or Alembic) with a CI check that a fresh database built from migrations matches production.
2. **Auth first:** add JWT verification + `org_id` columns (backfilled to a single default org);
   keep behaviour identical for the one existing tenant.
3. **Introduce `lead_jobs`:** the API enqueues a scrape job instead of a `BackgroundTask`; a
   separate worker process runs the existing `PipelineService` stage methods. Keep the
   BackgroundTask path behind `DEMO_MODE` for local demos.
4. **Per-territory concurrency index**, quotas and budget guard; drop the global index.
5. **Enable RLS** with policies once every table has `org_id`, then allow browser reads via
   Supabase with the user JWT.
6. **Realtime updates** replace polling; add dashboards and the alerts above.

Each step is independently deployable and reversible; steps 1–3 can ship without any UI change.
