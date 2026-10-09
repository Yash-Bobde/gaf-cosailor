import { Suspense } from 'react';
import Link from 'next/link';
import { CallSheet, type SegmentFilter, type SheetQuery } from '@/components/CallSheet';
import { RunPanel } from '@/components/RunPanel';
import { SiteHeader } from '@/components/SiteHeader';
import { getLeads } from '@/lib/api';
import type { ScoreTier, SortOption } from '@/lib/types';

const PAGE_SIZE = 20;
const TIERS: ScoreTier[] = ['all', 'high', 'medium', 'low'];
const SORTS: SortOption[] = ['score_desc', 'name_asc', 'recently_enriched'];
const SEGMENTS: SegmentFilter[] = ['all', 'residential', 'commercial'];

type SearchParams = Promise<{ page?: string; score_tier?: string; sort_by?: string; segment?: string }>;

function parseQuery(params: Awaited<SearchParams>): SheetQuery {
  return {
    page: Math.max(1, parseInt(params.page ?? '1', 10) || 1),
    limit: PAGE_SIZE,
    scoreTier: TIERS.includes(params.score_tier as ScoreTier) ? (params.score_tier as ScoreTier) : 'all',
    sortBy: SORTS.includes(params.sort_by as SortOption) ? (params.sort_by as SortOption) : 'score_desc',
    segment: SEGMENTS.includes(params.segment as SegmentFilter) ? (params.segment as SegmentFilter) : 'all',
  };
}

function Notice({ title, body, alert, action }: { title: string; body: string; alert?: boolean; action?: React.ReactNode }) {
  return (
    <div role={alert ? 'alert' : undefined} className="rounded-2xl border border-dashed border-line-strong px-6 py-16 text-center">
      <p className="font-display text-2xl text-ink">{title}</p>
      <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-soft">{body}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

async function Leads({ query }: { query: SheetQuery }) {
  try {
    const { leads, total } = await getLeads(query.page, query.limit, query.scoreTier, query.sortBy, query.segment);
    if (total === 0 && query.scoreTier === 'all' && query.segment === 'all') {
      return (
        <Notice
          title="Your call sheet is empty."
          body="Pick a ZIP code and radius above and build a call list — leads appear here one by one as each contractor is researched and scored."
        />
      );
    }
    return <CallSheet leads={leads} total={total} query={query} />;
  } catch (err) {
    console.error('[Leads] failed to fetch leads', err);
    return (
      <Notice
        alert
        title="Can't reach the leads service."
        body="The backend API isn't responding. Start it on port 8000 (cd backend, then python -m uvicorn app.main:app --port 8000) and try again."
        action={
          <Link href="/" prefetch={false} className="inline-flex h-11 items-center rounded-lg border border-line-strong bg-card px-5 text-sm font-semibold text-ink hover:border-ink">
            Try again
          </Link>
        }
      />
    );
  }
}

function SheetSkeleton() {
  return (
    <div className="rounded-2xl border border-line p-6" aria-busy="true" aria-label="Loading leads">
      <div className="skeleton mb-6 h-9 w-72" />
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="flex gap-4 border-b border-line py-5 last:border-0">
          <div className="skeleton h-10 w-12" />
          <div className="flex-1 space-y-2">
            <div className="skeleton h-5 w-1/3" />
            <div className="skeleton h-4 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

export default async function DashboardPage({ searchParams }: { searchParams: SearchParams }) {
  const query = parseQuery(await searchParams);
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto flex max-w-6xl flex-col gap-6 px-4 pb-16 sm:px-6">
        <div className="pt-2">
          <h1 className="font-display text-3xl font-semibold leading-tight text-ink sm:text-4xl">
            Who to call <em className="text-accent">first.</em>
          </h1>
          <p className="mt-2 max-w-2xl text-base leading-relaxed text-ink-soft">
            GAF-certified contractors near your territory, researched on the open web and ranked by fit,
            opportunity signals and distance.
          </p>
        </div>
        <RunPanel />
        <Suspense key={JSON.stringify(query)} fallback={<SheetSkeleton />}>
          <Leads query={query} />
        </Suspense>
      </main>
    </div>
  );
}
