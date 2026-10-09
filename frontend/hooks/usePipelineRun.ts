'use client';

/**
 * usePipelineRun — owns the lifecycle of a pipeline run from the browser.
 *
 * - Restores the latest run on mount (so a refresh mid-run keeps tracking it).
 * - Polls /status every 3 s while the run is active and calls router.refresh()
 *   each tick so leads stream into the Server-rendered call sheet as they finish.
 * - Starting while another run is active attaches to that run (backend 409).
 * - After POLL_FAILURES_BEFORE_WARNING failed polls in a row it reports the
 *   backend as unreachable (and keeps retrying) instead of failing silently.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { cancelPipeline, getLatestPipelineRun, getPipelineStatus, startPipeline } from '@/lib/api';
import type { PipelineRunParams, PipelineStatusResponse } from '@/lib/types';

export const POLL_MS = 3000;
export const POLL_FAILURES_BEFORE_WARNING = 2;
const FINAL_REFRESH_DELAY_MS = 600;
const UNREACHABLE = 'Lost contact with the backend — still retrying. Check that it is running on port 8000.';

function optimisticRun(runId: string, params: PipelineRunParams): PipelineStatusResponse {
  return {
    run_id: runId,
    status: 'running',
    leads_scraped: 0,
    leads_enriched: 0,
    leads_failed: 0,
    cancel_requested: false,
    started_at: new Date().toISOString(),
    finished_at: null,
    error_message: null,
    postal_code: params.postal_code,
    country_code: params.country_code,
    distance: params.distance,
    segment: params.segment,
  };
}

export function usePipelineRun() {
  const router = useRouter();
  const [run, setRun] = useState<PipelineStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [connectionLost, setConnectionLost] = useState(false);
  const runId = run?.run_id;
  const isRunning = run?.status === 'running';
  const status = run?.status;
  const previousStatus = useRef(status);

  // One more refresh once a run reaches a terminal state. A refresh fired from
  // the last poll can be superseded while an earlier one is still settling,
  // which left finished leads showing "Queued" until a manual reload.
  useEffect(() => {
    const wasRunning = previousStatus.current === 'running';
    previousStatus.current = status;
    if (!wasRunning || !status || status === 'running') return;
    const timer = setTimeout(() => router.refresh(), FINAL_REFRESH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [status, router]);

  useEffect(() => {
    let live = true;
    getLatestPipelineRun()
      .then((latest) => { if (live && latest) setRun(latest); })
      .catch(() => { /* backend down — the page shows its own error state */ });
    return () => { live = false; };
  }, []);

  useEffect(() => {
    if (!runId || !isRunning) return;
    let failures = 0;
    const timer = setInterval(async () => {
      try {
        setRun(await getPipelineStatus(runId));
        failures = 0;
        setConnectionLost(false);
        router.refresh();
      } catch {
        failures += 1;   // transient errors are retried on the next tick
        if (failures >= POLL_FAILURES_BEFORE_WARNING) setConnectionLost(true);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [runId, isRunning, router]);

  const start = useCallback(async (params: PipelineRunParams) => {
    setBusy(true);
    setError(null);
    try {
      const result = await startPipeline(params);
      setRun(result.attached ? await getPipelineStatus(result.run_id) : optimisticRun(result.run_id, params));
      router.refresh();
    } catch {
      setError('Could not start the run — the backend did not respond. Start it on port 8000 and try again.');
    } finally {
      setBusy(false);
    }
  }, [router]);

  const cancel = useCallback(async () => {
    if (!runId) return;
    setBusy(true);
    try {
      await cancelPipeline(runId);
      setRun((prev) => (prev ? { ...prev, cancel_requested: true } : prev));
    } catch {
      setError('Could not cancel the run. Try again in a moment.');
    } finally {
      setBusy(false);
    }
  }, [runId]);

  return { run, isRunning, busy, error: error ?? (connectionLost ? UNREACHABLE : null), start, cancel };
}
