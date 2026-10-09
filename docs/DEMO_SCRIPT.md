# Five-minute interviewer demo

Goal: show a real GAF → research → brief pipeline, prove the failure semantics are honest, and
explain the production design without overclaiming. Spend at most **one live lead**.

## Before the interview (10 min, once)

```bash
cd backend  && python scripts/preflight.py          # must end with READY (read-only, free)
cd backend  && python -m uvicorn app.main:app --port 8000
cd frontend && npm run build && npm run start       # production build on http://localhost:3000
```

Open http://localhost:3000/?segment=residential and one enriched lead in a second tab.
Close anything else on ports 3000 / 8000.

## The five minutes

| Time | Show | Say |
|---|---|---|
| 0:00–0:45 | Call sheet filtered to **Residential** | "The brief's URL — residential, ZIP 10013, 25 miles — is the default. Every row is a real GAF contractor, ranked by Fit + Opportunity × distance, with click-to-call." |
| 0:45–1:45 | Open an enriched lead | Walk the brief: summary, talking points, **Who to ask for** (Decision-maker vs Contact badges, the quoted research sentence, citation), **Sources**, **View GAF profile** (real gaf.com profile). Open *Why this rank?*: "the arithmetic is visible; the model can move each score by at most one point; these are priorities, not win probabilities." |
| 1:45–2:45 | Back to the call sheet → set **Max leads = 1** → *Build call list* | Progress streams (found → scored). "Each lead is researched, saved, enriched and saved independently; a crash loses at most the in-flight lead, and saved research is never paid for twice." If the first lead is already enriched, the run finishes in seconds without a Perplexity or OpenAI call — say so. |
| 2:45–3:30 | Failure semantics (talk over README table or the tests) | "A GAF capture failure is a *failed* run, never 'zero leads'. Zero is only reported when GAF itself says `totalCount=0`. A research failure fails only that lead and enrichment never runs without evidence. An accepted cancel can never finish 'completed' — the final write is conditional in the database." Point at `tests/test_run_lifecycle.py` / `test_scrape_failures.py`. |
| 3:30–4:30 | `docs/PRODUCTION_ARCHITECTURE.md` | "This build is a single-tenant demo: BackgroundTask, one global run, no auth, RLS off because only the backend holds the key. Production is a Postgres job queue with leases, retries, dead-letter, idempotency keys, per-territory concurrency, JWT auth, org ownership and RLS — designed here, not built." |
| 4:30–5:00 | Test/CI summary | 205 backend tests (repository against an in-memory Supabase fake), 40 frontend unit tests, 7 Playwright E2E tests on a stub backend, CI with no secrets; live GAF/Perplexity/DB tests are opt-in. |

## Fallbacks

| If… | Do |
|---|---|
| GAF is slow or blocks the scrape | The run shows "failed while reading the GAF directory". That *is* the demo of honest failure — then continue with stored leads. |
| Perplexity or OpenAI errors or is slow | The lead shows *Needs retry* with a plain-language reason; no brief is invented. Continue with stored leads. |
| Backend won't start | Show the frontend's "Can't reach the leads service" state (clear instructions, no stack trace), then the E2E suite: `cd frontend && npm run test:e2e`. |
| No network at all | `cd backend && pytest -q` and `cd frontend && npm run test` run fully offline. |

## Questions to be ready for

- *How do you tell zero results from a broken scraper?* — `parse_coveo_payload` validates the
  response; `totalCount=0` is the only path to an empty completed run.
- *How verified are the decision-makers?* — full name as whole words in the research, title only if
  supported next to the name, role only from a supported leadership/purchasing title, citation only
  if the search tool returned it. Not verified against the cited page or a contact database.
- *What breaks at 1,000 reps?* — the global run guard and in-process execution; see the queue design.
- *Why do Fit scores cluster at 9?* — the weights saturate for Master Elite + strong reviews;
  Opportunity and distance separate them; calibration needs outcome data.
