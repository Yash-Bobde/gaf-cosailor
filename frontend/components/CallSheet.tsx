/**
 * CallSheet — the ranked lead list with filters and pagination.
 *
 * A Server Component: filters, sort and paging are plain links that update the
 * URL search params, so every view is shareable and needs no client JS.
 */
import Link from 'next/link';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { Lead, ScoreTier, SortOption } from '@/lib/types';
import { LeadRow } from './LeadRow';

export type SegmentFilter = 'all' | 'residential' | 'commercial';

export interface SheetQuery {
  page: number;
  limit: number;
  scoreTier: ScoreTier;
  sortBy: SortOption;
  segment: SegmentFilter;
}

interface CallSheetProps {
  leads: Lead[];
  total: number;
  query: SheetQuery;
}

const TIER_FILTERS: { value: ScoreTier; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'high', label: 'Fit 8–10' },
  { value: 'medium', label: 'Fit 5–7' },
  { value: 'low', label: 'Fit 1–4' },
];

const SEGMENT_FILTERS: { value: SegmentFilter; label: string }[] = [
  { value: 'all', label: 'All segments' },
  { value: 'residential', label: 'Residential' },
  { value: 'commercial', label: 'Commercial' },
];

const SORTS: { value: SortOption; label: string }[] = [
  { value: 'score_desc', label: 'Priority' },
  { value: 'recently_enriched', label: 'Newest' },
  { value: 'name_asc', label: 'A–Z' },
];

function href(query: SheetQuery, patch: Partial<SheetQuery>): string {
  const next = { ...query, ...patch };
  const params = new URLSearchParams();
  if (next.page > 1) params.set('page', String(next.page));
  if (next.scoreTier !== 'all') params.set('score_tier', next.scoreTier);
  if (next.sortBy !== 'score_desc') params.set('sort_by', next.sortBy);
  if (next.segment !== 'all') params.set('segment', next.segment);
  const qs = params.toString();
  return qs ? `/?${qs}` : '/';
}

function Pill({ active, to, children }: { active: boolean; to: string; children: React.ReactNode }) {
  return (
    <Link
      href={to}
      scroll={false}
      aria-current={active ? 'true' : undefined}
      className={`inline-flex h-10 items-center rounded-full border px-4 text-sm transition-colors duration-150 ${
        active
          ? 'border-ink bg-ink text-paper'
          : 'border-line-strong text-ink-soft hover:border-ink hover:text-ink'
      }`}
    >
      {children}
    </Link>
  );
}

function Toolbar({ query, total }: { query: SheetQuery; total: number }) {
  return (
    <div className="flex flex-col gap-3 border-b border-line px-4 pb-4 sm:px-6 md:flex-row md:items-center md:justify-between">
      <div className="flex flex-col gap-2">
        <nav aria-label="Filter by fit score" className="flex flex-wrap gap-2">
          {TIER_FILTERS.map((f) => (
            <Pill key={f.value} active={query.scoreTier === f.value} to={href(query, { scoreTier: f.value, page: 1 })}>
              {f.label}
            </Pill>
          ))}
        </nav>
        <nav aria-label="Filter by segment" className="flex flex-wrap gap-2">
          {SEGMENT_FILTERS.map((f) => (
            <Pill key={f.value} active={query.segment === f.value} to={href(query, { segment: f.value, page: 1 })}>
              {f.label}
            </Pill>
          ))}
        </nav>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-ink-faint">{total} contractors</span>
        <nav aria-label="Sort" className="flex rounded-full border border-line-strong p-0.5">
          {SORTS.map((s) => (
            <Link
              key={s.value}
              href={href(query, { sortBy: s.value, page: 1 })}
              scroll={false}
              aria-current={query.sortBy === s.value ? 'true' : undefined}
              className={`inline-flex h-10 items-center rounded-full px-3.5 text-sm transition-colors duration-150 ${
                query.sortBy === s.value ? 'bg-accent-tint font-semibold text-accent-strong' : 'text-ink-soft hover:text-ink'
              }`}
            >
              {s.label}
            </Link>
          ))}
        </nav>
      </div>
    </div>
  );
}

function Pager({ query, total }: { query: SheetQuery; total: number }) {
  const pages = Math.max(1, Math.ceil(total / query.limit));
  if (pages <= 1) return null;
  const first = (query.page - 1) * query.limit + 1;
  const last = Math.min(total, query.page * query.limit);
  const btn = 'inline-flex h-10 items-center gap-1 rounded-full border border-line-strong px-4 text-sm transition-colors duration-150';
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between px-4 py-5 sm:px-6">
      <span className="text-sm text-ink-faint tabular-nums">
        {first}–{last} of {total}
      </span>
      <div className="flex gap-2">
        {query.page > 1 ? (
          <Link href={href(query, { page: query.page - 1 })} className={`${btn} hover:border-ink`}>
            <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Prev
          </Link>
        ) : (
          <span className={`${btn} cursor-not-allowed opacity-40`} aria-disabled="true">
            <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Prev
          </span>
        )}
        {query.page < pages ? (
          <Link href={href(query, { page: query.page + 1 })} className={`${btn} hover:border-ink`}>
            Next <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </Link>
        ) : (
          <span className={`${btn} cursor-not-allowed opacity-40`} aria-disabled="true">
            Next <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </span>
        )}
      </div>
    </nav>
  );
}

function EmptyFilter() {
  return (
    <div className="px-6 py-16 text-center">
      <p className="font-display text-xl text-ink">No contractors match this filter.</p>
      <p className="mt-2 text-sm text-ink-soft">
        <Link href="/" className="underline decoration-line-strong underline-offset-4 hover:text-ink">
          Show all leads
        </Link>
      </p>
    </div>
  );
}

export function CallSheet({ leads, total, query }: CallSheetProps) {
  const offset = (query.page - 1) * query.limit;
  return (
    <section aria-label="Call sheet" className="rounded-2xl border border-line bg-paper pt-4">
      <Toolbar query={query} total={total} />
      {leads.length === 0 ? (
        <EmptyFilter />
      ) : (
        <ol>
          {leads.map((lead, i) => (
            <LeadRow key={lead.id} lead={lead} rank={offset + i + 1} delayMs={Math.min(i, 12) * 25} />
          ))}
        </ol>
      )}
      <Pager query={query} total={total} />
    </section>
  );
}
