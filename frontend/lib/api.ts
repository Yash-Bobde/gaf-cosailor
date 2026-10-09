/**
 * HTTP client functions for the Cosailor Insights backend API.
 *
 * Thin, stateless wrappers around fetch(). Every call uses cache: 'no-store'
 * so router.refresh() during a pipeline run always shows fresh leads.
 */
import type {
  Lead,
  PaginatedLeadsResponse,
  PipelineRunParams,
  PipelineStartResult,
  PipelineStatusResponse,
} from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

/** Fetch a filtered, sorted page of leads (filtering and sorting happen server-side). */
export async function getLeads(
  page: number = 1,
  limit: number = 20,
  scoreTier?: string,
  sortBy?: string,
  segment?: string,
): Promise<PaginatedLeadsResponse> {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  if (scoreTier && scoreTier !== 'all') params.set('score_tier', scoreTier);
  if (sortBy && sortBy !== 'score_desc') params.set('sort_by', sortBy);
  if (segment && segment !== 'all') params.set('segment', segment);
  const res = await fetch(`${API_BASE}/api/leads/?${params.toString()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to fetch leads: ${res.status}`);
  return res.json();
}

/** Fetch a single lead. Returns null on 404; throws on any other failure. */
export async function getLead(id: string): Promise<Lead | null> {
  const res = await fetch(`${API_BASE}/api/leads/${id}`, { cache: 'no-store' });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch lead: ${res.status}`);
  return res.json();
}

/**
 * Start a pipeline run. When one is already active the backend answers 409 with
 * that run's id — we attach to it instead of treating it as an error.
 */
export async function startPipeline(params: PipelineRunParams): Promise<PipelineStartResult> {
  const res = await fetch(`${API_BASE}/api/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (res.status === 409) {
    const body = await res.json().catch(() => null);
    const runId = body?.detail?.run_id;
    if (typeof runId === 'string') return { run_id: runId, attached: true };
  }
  if (!res.ok) throw new Error(`Failed to start pipeline: ${res.status}`);
  const data = await res.json();
  return { run_id: data.run_id, attached: false };
}

/** Ask the worker to stop after the leads it is currently processing. */
export async function cancelPipeline(runId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/pipeline/${runId}/cancel`, { method: 'POST' });
  // 409 = the run already finished; nothing left to cancel.
  if (!res.ok && res.status !== 409) throw new Error(`Failed to cancel pipeline: ${res.status}`);
}

/** Poll the current state of a pipeline run. */
export async function getPipelineStatus(runId: string): Promise<PipelineStatusResponse> {
  const res = await fetch(`${API_BASE}/api/pipeline/status/${runId}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Pipeline run not found: ${res.status}`);
  return res.json();
}

/** Most recent run of any status, used to restore an active run after a page refresh. */
export async function getLatestPipelineRun(): Promise<PipelineStatusResponse | null> {
  const res = await fetch(`${API_BASE}/api/pipeline/latest`, { cache: 'no-store' });
  // 204 = no run has been started yet (older backends answered 404).
  if (res.status === 204 || res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch latest run: ${res.status}`);
  return res.json();
}
