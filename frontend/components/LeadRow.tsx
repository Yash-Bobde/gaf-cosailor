/**
 * LeadRow — one line of the call sheet.
 *
 * The whole row links to the lead brief (stretched link on the company name);
 * the phone button sits above that link so a rep can dial straight from the list.
 */
import Link from 'next/link';
import { Phone, ChevronRight } from 'lucide-react';
import type { Lead } from '@/lib/types';
import { callTier, firstSentence, formatMiles, locationLine, pendingLabel, telHref } from '@/lib/format';
import { RoofPitch } from './RoofPitch';
import { ScoreBar } from './ScoreBar';
import { TierBadge } from './TierBadge';

interface LeadRowProps {
  lead: Lead;
  rank: number;
  delayMs: number;
}

function MetaLine({ lead }: { lead: Lead }) {
  const miles = formatMiles(lead.distance_miles);
  const parts = [
    locationLine(lead),
    miles,
    lead.segment ? (lead.segment === 'residential' ? 'Residential' : 'Commercial') : null,
    lead.rating !== null ? `★ ${lead.rating.toFixed(1)} (${lead.review_count ?? 0})` : null,
  ].filter(Boolean);
  return <p className="mt-0.5 text-sm text-ink-soft md:truncate">{parts.join(' · ')}</p>;
}

function WhyLine({ lead }: { lead: Lead }) {
  if (lead.status !== 'enriched') {
    return (
      <p className="mt-2 flex items-center gap-2 text-sm text-ink-faint">
        {lead.status !== 'failed' && <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />}
        {pendingLabel(lead.status)}
      </p>
    );
  }
  const why = firstSentence(lead.ai_summary);
  return why ? <p className="mt-2 line-clamp-2 text-sm leading-relaxed text-ink">{why}</p> : null;
}

function CallButton({ phone, company }: { phone: string | null; company: string }) {
  if (!phone) return null;
  return (
    <a
      href={telHref(phone)}
      aria-label={`Call ${company}`}
      className="relative z-10 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-line-strong bg-card text-ink transition-colors duration-150 hover:border-accent hover:text-accent"
    >
      <Phone className="h-4 w-4" aria-hidden="true" />
    </a>
  );
}

export function LeadRow({ lead, rank, delayMs }: LeadRowProps) {
  const tier = callTier(lead);
  return (
    <li
      className="rise group relative grid grid-cols-[auto_1fr_auto] items-start gap-x-4 gap-y-3 border-b border-line px-4 py-5 transition-colors duration-150 hover:bg-card sm:px-6 md:grid-cols-[2.5rem_3.5rem_1fr_12.5rem_auto]"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <span className="hidden pt-1 font-mono text-sm tabular-nums text-ink-faint md:block">
        {String(rank).padStart(2, '0')}
      </span>

      <div className="flex flex-col items-center gap-0.5">
        <RoofPitch value={lead.priority_index} tier={tier.tier} />
        <span className="font-mono text-xs tabular-nums text-ink-soft">
          {lead.priority_index !== null ? lead.priority_index.toFixed(1) : '—'}
        </span>
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-semibold leading-snug text-ink">
            <Link href={`/leads/${lead.id}`} className="after:absolute after:inset-0 after:content-['']">
              {lead.company_name}
            </Link>
          </h3>
          <TierBadge info={tier} />
        </div>
        <MetaLine lead={lead} />
        <WhyLine lead={lead} />
      </div>

      <div className="col-span-3 flex flex-col gap-1.5 pl-16 empty:hidden md:col-span-1 md:flex md:pl-0 md:pt-1.5">
        {lead.status === 'enriched' && (
          <>
            <ScoreBar label="Fit" value={lead.lead_score} />
            <ScoreBar label="Opportunity" value={lead.convertibility_score} />
          </>
        )}
      </div>

      <div className="col-start-3 row-start-1 flex items-center gap-1 md:col-start-auto md:row-start-auto">
        <CallButton phone={lead.phone} company={lead.company_name} />
        <ChevronRight
          className="hidden h-5 w-5 text-ink-faint transition-transform duration-150 group-hover:translate-x-0.5 md:block"
          aria-hidden="true"
        />
      </div>
    </li>
  );
}
