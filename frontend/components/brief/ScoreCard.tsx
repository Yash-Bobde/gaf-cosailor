/**
 * Sidebar of the call brief: priority verdict, the two scores with their
 * rationale and how they combine, contact actions (call, website, GAF profile)
 * and the GAF facts a rep should mention.
 */
import { Phone, Globe, Star, MapPin, BadgeCheck, ExternalLink } from 'lucide-react';
import type { Lead } from '@/lib/types';
import {
  DISTANCE_MODIFIERS, callTier, formatDate, formatMiles, hostname, safeExternalUrl, telHref, websiteHref,
} from '@/lib/format';
import { RoofPitch } from '../RoofPitch';
import { ScoreBar } from '../ScoreBar';
import { TierBadge } from '../TierBadge';

function Verdict({ lead }: { lead: Lead }) {
  const tier = callTier(lead);
  return (
    <div className="flex items-center gap-4">
      <RoofPitch value={lead.priority_index} tier={tier.tier} size="lg" />
      <div>
        <p className="font-mono text-3xl tabular-nums text-ink">
          {lead.priority_index !== null ? lead.priority_index.toFixed(1) : '—'}
          <span className="text-base text-ink-faint"> / 10</span>
        </p>
        <div className="mt-1 flex items-center gap-2">
          <TierBadge info={tier} />
        </div>
        <p className="mt-1 text-xs text-ink-faint">{tier.hint}</p>
      </div>
    </div>
  );
}

function Score({ label, value, why }: { label: string; value: number | null; why: string | null }) {
  return (
    <div>
      <ScoreBar label={label} value={value} />
      {why && <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{why}</p>}
    </div>
  );
}

/** Shows the arithmetic behind the rank so a rep (or manager) can sanity-check it. */
function RankExplanation({ lead }: { lead: Lead }) {
  if (lead.lead_score === null || lead.convertibility_score === null || lead.priority_index === null) return null;
  const band = lead.distance_band ?? 'near';
  const modifier = DISTANCE_MODIFIERS[band];
  return (
    <details className="group text-sm text-ink-soft">
      <summary className="flex min-h-10 cursor-pointer items-center text-xs font-semibold uppercase tracking-wider text-ink-soft underline decoration-line-strong underline-offset-4">
        Why this rank?
      </summary>
      <p className="mt-2 leading-relaxed">
        Priority = (Fit {lead.lead_score} + Opportunity {lead.convertibility_score}) ÷ 2 × {modifier.toFixed(2)}{' '}
        ({band} distance) = <span className="font-mono text-ink">{lead.priority_index.toFixed(2)}</span>.
      </p>
      <p className="mt-2 leading-relaxed">
        Fit comes from GAF certification, rating and review count. Opportunity comes from signals found in the
        web research (competitor brands, growth, new certifications). The AI may move each score by at most one
        point. These are rules-based priorities, not predicted win rates.
      </p>
    </details>
  );
}

function Contact({ lead }: { lead: Lead }) {
  const action = 'inline-flex min-h-11 w-full items-center gap-2.5 rounded-lg border px-4 py-2 text-sm font-semibold transition-colors duration-150';
  const secondary = `${action} border-line-strong bg-card text-ink hover:border-ink`;
  const profile = safeExternalUrl(lead.gaf_profile_url);
  return (
    <div className="flex flex-col gap-2">
      {lead.phone && (
        <a href={telHref(lead.phone)} className={`${action} border-accent bg-accent text-white hover:bg-accent-strong`}>
          <Phone className="h-4 w-4" aria-hidden="true" /> Call {lead.phone}
        </a>
      )}
      {lead.website && (
        <a href={websiteHref(lead.website)} target="_blank" rel="noopener noreferrer" className={secondary}>
          <Globe className="h-4 w-4" aria-hidden="true" /> {hostname(websiteHref(lead.website))}
        </a>
      )}
      {profile && (
        <a href={profile} target="_blank" rel="noopener noreferrer" className={secondary}>
          <BadgeCheck className="h-4 w-4" aria-hidden="true" /> View GAF profile
          <ExternalLink className="ml-auto h-3.5 w-3.5 text-ink-faint" aria-hidden="true" />
          <span className="sr-only">(opens gaf.com in a new tab)</span>
        </a>
      )}
    </div>
  );
}

function Facts({ lead }: { lead: Lead }) {
  const miles = formatMiles(lead.distance_miles);
  return (
    <dl className="flex flex-col gap-3 text-sm">
      {lead.rating !== null && (
        <div className="flex items-center gap-2">
          <Star className="h-4 w-4 text-warn" aria-hidden="true" />
          <dt className="sr-only">Rating</dt>
          <dd className="text-ink">
            {lead.rating.toFixed(1)} <span className="text-ink-faint">· {lead.review_count ?? 0} GAF reviews</span>
          </dd>
        </div>
      )}
      {miles && (
        <div className="flex items-center gap-2">
          <MapPin className="h-4 w-4 text-ink-faint" aria-hidden="true" />
          <dt className="sr-only">Distance</dt>
          <dd className="text-ink">
            {miles} from search ZIP <span className="text-ink-faint">· {lead.distance_band ?? 'near'} band</span>
          </dd>
        </div>
      )}
      {lead.certifications.length > 0 && (
        <div>
          <dt className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-soft">GAF certifications</dt>
          <dd className="flex flex-wrap gap-1.5">
            {lead.certifications.map((c) => (
              <span key={c} className="rounded-md border border-line bg-paper px-2 py-1 text-xs text-ink">{c}</span>
            ))}
          </dd>
        </div>
      )}
    </dl>
  );
}

export function ScoreCard({ lead }: { lead: Lead }) {
  const updated = formatDate(lead.enriched_at);
  return (
    <aside aria-label="Priority and contact" className="flex flex-col gap-6 rounded-2xl border border-line bg-card p-5 sm:p-6">
      <Verdict lead={lead} />
      <div className="flex flex-col gap-4 border-t border-line pt-5">
        <Score label="Fit" value={lead.lead_score} why={lead.score_rationale} />
        <Score label="Opportunity" value={lead.convertibility_score} why={lead.convertibility_rationale} />
        <RankExplanation lead={lead} />
      </div>
      <div className="border-t border-line pt-5"><Contact lead={lead} /></div>
      <div className="border-t border-line pt-5"><Facts lead={lead} /></div>
      {updated && <p className="text-xs text-ink-faint">Researched {updated}</p>}
    </aside>
  );
}
