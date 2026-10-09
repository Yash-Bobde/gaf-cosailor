/**
 * Main-column sections of the call brief: summary, talking points, approach,
 * decision-makers, sources and the raw research.
 */
import ReactMarkdown from 'react-markdown';
import { ExternalLink, UserRound, ChevronDown } from 'lucide-react';
import type { DecisionMaker, Lead } from '@/lib/types';
import { hostname, safeExternalUrl } from '@/lib/format';

export function Section({ title, children, id }: { title: string; children: React.ReactNode; id?: string }) {
  return (
    <section aria-labelledby={id} className="border-t border-line pt-6">
      <h2 id={id} className="mb-3 text-xs font-semibold uppercase tracking-wider text-ink-soft">
        {title}
      </h2>
      {children}
    </section>
  );
}

export function TalkingPoints({ points }: { points: string[] }) {
  if (points.length === 0) return <p className="text-sm text-ink-faint">No talking points yet.</p>;
  return (
    <ol className="flex flex-col gap-4">
      {points.map((point, i) => (
        <li key={i} className="grid grid-cols-[2rem_1fr] gap-3">
          <span className="font-display text-2xl font-semibold leading-none text-accent">{i + 1}</span>
          <p className="text-base leading-relaxed text-ink">{point}</p>
        </li>
      ))}
    </ol>
  );
}

function RoleBadge({ person }: { person: DecisionMaker }) {
  const decides = person.role === 'decision_maker';
  return (
    <span
      title={decides
        ? 'The research names this person with a leadership or purchasing title'
        : 'Named in the research, but buying authority is not established'}
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${
        decides ? 'border-good bg-good-tint text-good' : 'border-line-strong text-ink-soft'
      }`}
    >
      {decides ? 'Decision-maker' : 'Contact'}
    </span>
  );
}

function PersonCard({ person }: { person: DecisionMaker }) {
  const source = safeExternalUrl(person.source_url);
  return (
    <li className="flex items-start gap-3 rounded-xl border border-line bg-card p-4">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-tint text-accent-strong">
        <UserRound className="h-5 w-5" aria-hidden="true" />
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-ink">{person.name}</p>
          <RoleBadge person={person} />
        </div>
        <p className="text-sm text-ink-soft">{person.title ?? 'Title unknown'}</p>
        {person.evidence && (
          <blockquote className="mt-2 border-l-2 border-line-strong pl-3 text-xs leading-relaxed text-ink-soft wrap-anywhere">
            &ldquo;{person.evidence}&rdquo;
          </blockquote>
        )}
        {source ? (
          <a
            href={source}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 inline-flex min-h-8 items-center gap-1 text-xs text-ink-faint underline decoration-line-strong underline-offset-4 hover:text-ink"
          >
            Source: {hostname(source)} <ExternalLink className="h-3 w-3" aria-hidden="true" />
          </a>
        ) : (
          <p className="mt-1 text-xs text-ink-faint">From the web research summary (no direct citation)</p>
        )}
      </div>
    </li>
  );
}

export function DecisionMakers({ people }: { people: DecisionMaker[] }) {
  if (people.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-line-strong px-4 py-4 text-sm leading-relaxed text-ink-soft">
        No named people could be confirmed in the public research. Open the call by asking for the owner or the
        person who signs off on material orders.
      </p>
    );
  }
  return (
    <>
      <p className="mb-3 text-xs leading-relaxed text-ink-faint">
        People are shown only when their full name appears in the web research. &ldquo;Decision-maker&rdquo; means
        the research gives them a leadership or purchasing title; verify before relying on it.
      </p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {people.map((p) => <PersonCard key={`${p.name}-${p.title ?? ''}`} person={p} />)}
      </ul>
    </>
  );
}

export function Sources({ urls }: { urls: string[] }) {
  const safe = urls.map(safeExternalUrl).filter((u): u is string => u !== null);
  if (safe.length === 0) return <p className="text-sm text-ink-faint">No citations were returned for this lead.</p>;
  return (
    <>
      <p className="mb-3 text-xs text-ink-faint">Pages Perplexity cited while researching this contractor.</p>
      <ol className="flex flex-col gap-2">
        {safe.map((url, i) => (
          <li key={url} className="flex items-baseline gap-3 text-sm">
            <span className="font-mono text-xs tabular-nums text-ink-faint">[{i + 1}]</span>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex min-h-8 min-w-0 items-center gap-1 text-ink underline decoration-line-strong underline-offset-4 hover:decoration-accent"
            >
              <span className="truncate">{hostname(url)}</span>
              <ExternalLink className="h-3 w-3 shrink-0 text-ink-faint" aria-hidden="true" />
            </a>
          </li>
        ))}
      </ol>
    </>
  );
}

export function RawResearch({ lead }: { lead: Lead }) {
  if (!lead.research_summary) return null;
  return (
    <details className="group rounded-xl border border-line bg-card">
      <summary className="flex min-h-11 cursor-pointer items-center justify-between px-4 py-3 text-sm font-semibold text-ink">
        Full Perplexity web research
        <ChevronDown className="h-4 w-4 text-ink-faint transition-transform duration-200 group-open:rotate-180" aria-hidden="true" />
      </summary>
      <div className="prose prose-sm max-w-none px-4 pb-4 text-ink-soft prose-headings:text-ink prose-strong:text-ink prose-a:text-accent">
        <ReactMarkdown>{lead.research_summary}</ReactMarkdown>
      </div>
    </details>
  );
}
