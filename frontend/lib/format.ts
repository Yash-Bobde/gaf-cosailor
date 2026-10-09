/**
 * Pure presentation helpers shared by Server and Client Components.
 */
import type { Lead } from './types';

export type CallTier = 'call-first' | 'this-week' | 'nurture' | 'pending' | 'failed';

export interface TierInfo {
  tier: CallTier;
  label: string;
  hint: string;
}

const TIERS: Record<CallTier, TierInfo> = {
  'call-first': { tier: 'call-first', label: 'Call first', hint: 'Strong fit and clear opportunity signals' },
  'this-week': { tier: 'this-week', label: 'This week', hint: 'Good fit — worth a call soon' },
  nurture: { tier: 'nurture', label: 'Nurture', hint: 'Keep warm, low urgency' },
  pending: { tier: 'pending', label: 'In progress', hint: 'Research still running' },
  failed: { tier: 'failed', label: 'Needs retry', hint: 'Research or scoring failed — the next run retries it' },
};

/** Distance multipliers used by the backend priority index (scorer.py). */
export const DISTANCE_MODIFIERS = { near: 1.0, mid: 0.95, far: 0.9 } as const;

/** Bucket a lead's priority index into the action a rep should take. */
export function callTier(lead: Pick<Lead, 'status' | 'priority_index'>): TierInfo {
  if (lead.status === 'failed') return TIERS.failed;
  if (lead.status !== 'enriched' || lead.priority_index === null) return TIERS.pending;
  if (lead.priority_index >= 7.5) return TIERS['call-first'];
  if (lead.priority_index >= 5.5) return TIERS['this-week'];
  return TIERS.nurture;
}

/** Human status label for leads that have not finished enrichment. */
export function pendingLabel(status: Lead['status']): string {
  if (status === 'failed') return 'Research failed — retried on the next run';
  if (status === 'researched') return 'Scoring…';
  return 'Queued for research';
}

/**
 * Rep-facing explanation of why a lead failed. The raw backend message is never
 * shown: it is mapped to a plain-language cause, and nothing is invented to fill
 * the gap.
 */
export function leadFailureMessage(error: string | null): string {
  const text = (error ?? '').toLowerCase();
  if (text.includes('research')) {
    return 'Web research for this contractor failed, so no brief was written — nothing was guessed.';
  }
  if (text.includes('timed out')) {
    return 'Research took too long and was stopped before a brief was written.';
  }
  return 'Scoring this contractor failed before a brief was written.';
}

/** Rep-facing summary of a failed run (messages are sanitized server-side). */
export function runFailureMessage(error: string | null): string {
  const message = error ?? '';
  if (message.startsWith('Server restarted')) {
    return 'Last run was interrupted by a server restart. Run again to resume — scored leads are kept.';
  }
  if (message.includes('GAF')) {
    return `Last run failed while reading the GAF directory (${message}). Nothing was scored — try again in a minute.`;
  }
  return 'Last run failed unexpectedly. Nothing new was scored — try again, and check the backend log if it repeats.';
}

export function locationLine(lead: Pick<Lead, 'city' | 'state'>): string {
  return [lead.city, lead.state].filter(Boolean).join(', ');
}

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** Normalise a scraped website into an absolute URL for <a href>. */
export function websiteHref(website: string): string {
  return /^https?:\/\//i.test(website) ? website : `https://${website}`;
}

/** Only http(s) links are rendered as anchors — never javascript: or data: URLs. */
export function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`;
}

export function formatMiles(miles: number | null): string | null {
  if (miles === null || Number.isNaN(miles)) return null;
  return `${miles < 10 ? miles.toFixed(1) : Math.round(miles)} mi`;
}

/** First sentence of the AI summary — the "why call" line on the call sheet. */
export function firstSentence(text: string | null): string | null {
  if (!text) return null;
  const match = text.match(/^.*?[.!?](\s|$)/);
  return (match ? match[0] : text).trim();
}

export function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
