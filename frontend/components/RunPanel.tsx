'use client';

/**
 * RunPanel — "build a call list" controls plus live run progress.
 * The only component that polls the backend (via usePipelineRun).
 */
import React, { useEffect, useRef, useState } from 'react';
import { Loader2, Play, Square, CheckCircle2, AlertTriangle, CircleSlash } from 'lucide-react';
import type { PipelineRunParams, PipelineStatusResponse, Segment } from '@/lib/types';
import { runFailureMessage } from '@/lib/format';
import { usePipelineRun } from '@/hooks/usePipelineRun';
import { Field, Segmented } from './RunFields';

type Distance = PipelineRunParams['distance'];
const US_ZIP = /^\d{5}$/;
const DISTANCES: { value: Distance; label: string }[] = [
  { value: 25, label: '25 mi' }, { value: 50, label: '50 mi' }, { value: 100, label: '100 mi' },
];
const SEGMENTS: { value: Segment; label: string }[] = [
  { value: 'residential', label: 'Residential' }, { value: 'commercial', label: 'Commercial' },
];
const LIMITS = [10, 25, 50, 0] as const; // 0 = all contractors found

function isDistance(n: number): n is Distance {
  return n === 25 || n === 50 || n === 100;
}

function RunProgress({ run, busy, onCancel }: { run: PipelineStatusResponse; busy: boolean; onCancel: () => void }) {
  const done = run.leads_enriched + (run.leads_failed ?? 0);
  const pct = run.leads_scraped > 0 ? Math.min(100, (done / run.leads_scraped) * 100) : 0;
  const stage = run.leads_scraped === 0 ? 'Finding contractors on GAF…' : 'Researching and scoring each lead…';
  return (
    <div className="flex flex-col gap-4" aria-live="polite">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <Loader2 className="h-5 w-5 animate-spin text-accent motion-reduce:animate-none" aria-hidden="true" />
          <p className="text-base text-ink">
            {run.cancel_requested ? 'Stopping after the leads in progress…' : stage}
          </p>
        </div>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy || run.cancel_requested}
          className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-lg border border-line-strong bg-card px-4 text-sm font-semibold text-ink transition-colors duration-150 hover:border-bad hover:text-bad disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Square className="h-3.5 w-3.5" aria-hidden="true" /> Cancel run
        </button>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-line" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label="Leads processed">
        <div className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out" style={{ width: `${Math.max(pct, 3)}%` }} />
      </div>
      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <Stat label="Found" value={run.leads_scraped} />
        <Stat label="Scored" value={run.leads_enriched} />
        <Stat label="Failed" value={run.leads_failed ?? 0} />
        <Stat label="Search" value={`${run.postal_code} · ${run.distance} mi · ${run.segment ?? 'residential'}`} />
      </dl>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="text-ink-faint">{label}</dt>
      <dd className="font-mono tabular-nums text-ink">{value}</dd>
    </div>
  );
}

function Outcome({ run }: { run: PipelineStatusResponse }) {
  if (run.status === 'completed') {
    const failed = run.leads_failed ?? 0;
    const text = run.leads_scraped === 0
      ? 'Last run finished: GAF lists no contractors for that search.'
      : `Last run scored ${run.leads_enriched} of ${run.leads_scraped} contractors${failed ? ` — ${failed} need a retry` : ''}.`;
    return <OutcomeLine icon={<CheckCircle2 className="h-4 w-4 text-good" />} text={text} />;
  }
  if (run.status === 'cancelled') {
    return <OutcomeLine icon={<CircleSlash className="h-4 w-4 text-ink-soft" />} text={`Last run cancelled after scoring ${run.leads_enriched} leads. Run again to pick up where it stopped.`} />;
  }
  if (run.status === 'failed') {
    return <OutcomeLine icon={<AlertTriangle className="h-4 w-4 text-warn" />} text={runFailureMessage(run.error_message)} />;
  }
  return null;
}

function OutcomeLine({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <p className="flex items-start gap-2 text-sm text-ink-soft">
      <span className="mt-0.5 shrink-0" aria-hidden="true">{icon}</span>
      {text}
    </p>
  );
}

function useRunForm(run: PipelineStatusResponse | null) {
  const [zip, setZip] = useState('10013');
  const [distance, setDistance] = useState<Distance>(25);
  const [segment, setSegment] = useState<Segment>('residential');
  const [limit, setLimit] = useState<number>(10);
  const restored = useRef(false);

  // Pre-fill the form once from the last run so "run again" is one click.
  useEffect(() => {
    if (!run || restored.current) return;
    restored.current = true;
    if (run.postal_code) setZip(run.postal_code);
    if (isDistance(run.distance)) setDistance(run.distance);
    if (run.segment) setSegment(run.segment);
  }, [run]);

  const params: PipelineRunParams = {
    postal_code: zip.trim(), country_code: 'us', distance, segment, limit: limit === 0 ? null : limit,
  };
  return { zip, setZip, distance, setDistance, segment, setSegment, limit, setLimit, params, zipValid: US_ZIP.test(zip.trim()) };
}

export function RunPanel() {
  const { run, isRunning, busy, error, start, cancel } = usePipelineRun();
  const form = useRunForm(run);

  return (
    <section aria-label="Build a call list" className="rounded-2xl border border-line bg-card p-5 sm:p-6">
      {isRunning && run ? (
        <RunProgress run={run} busy={busy} onCancel={cancel} />
      ) : (
        <RunForm form={form} busy={busy} onRun={() => start(form.params)} />
      )}
      {(error || (run && !isRunning)) && (
        <div className="mt-4 flex flex-col gap-1 border-t border-line pt-4" aria-live="polite">
          {error && <p className="text-sm text-bad" role="alert">{error}</p>}
          {run && !isRunning && <Outcome run={run} />}
        </div>
      )}
    </section>
  );
}

function RunForm({ form, busy, onRun }: { form: ReturnType<typeof useRunForm>; busy: boolean; onRun: () => void }) {
  const zipError = form.zip.length > 0 && !form.zipValid;
  return (
    <form
      className="grid grid-cols-2 gap-4 lg:grid-cols-[7rem_7rem_auto_auto_1fr] lg:items-end"
      onSubmit={(e) => { e.preventDefault(); if (form.zipValid) onRun(); }}
    >
      <Field label="ZIP code" htmlFor="run-zip">
        <input
          id="run-zip" inputMode="numeric" autoComplete="postal-code" maxLength={5}
          value={form.zip} onChange={(e) => form.setZip(e.target.value)}
          aria-invalid={zipError} aria-describedby={zipError ? 'run-zip-error' : undefined}
          className={`h-11 w-full rounded-lg border bg-card px-3 font-mono text-base text-ink ${zipError ? 'border-bad' : 'border-line-strong'}`}
        />
        {zipError && <span id="run-zip-error" className="text-xs text-bad">Enter a 5-digit US ZIP</span>}
      </Field>
      <Field label="Max leads" htmlFor="run-limit">
        <select
          id="run-limit" value={form.limit} onChange={(e) => form.setLimit(Number(e.target.value))}
          className="h-11 w-full cursor-pointer rounded-lg border border-line-strong bg-card px-3 text-base text-ink"
        >
          {LIMITS.map((n) => <option key={n} value={n}>{n === 0 ? 'All found' : n}</option>)}
        </select>
      </Field>
      <Field label="Radius" wide>
        <Segmented label="Radius" value={form.distance} options={DISTANCES} onChange={form.setDistance} disabled={busy} />
      </Field>
      <Field label="Segment" wide>
        <Segmented label="Segment" value={form.segment} options={SEGMENTS} onChange={form.setSegment} disabled={busy} />
      </Field>
      <button
        type="submit" disabled={busy || !form.zipValid}
        className="col-span-2 inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-accent px-5 text-sm font-semibold text-white transition-colors duration-150 hover:bg-accent-strong disabled:cursor-not-allowed disabled:opacity-50 lg:col-span-1 lg:justify-self-end"
      >
        {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Play className="h-4 w-4" aria-hidden="true" />}
        Build call list
      </button>
    </form>
  );
}
