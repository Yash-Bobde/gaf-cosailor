import { notFound } from 'next/navigation';
import { SiteHeader } from '@/components/SiteHeader';
import { ScoreCard } from '@/components/brief/ScoreCard';
import { DecisionMakers, RawResearch, Section, Sources, TalkingPoints } from '@/components/brief/BriefSections';
import { getLead } from '@/lib/api';
import { leadFailureMessage, locationLine, pendingLabel } from '@/lib/format';
import type { Lead } from '@/lib/types';

interface Props {
  params: Promise<{ id: string }>;
}

function Title({ lead }: { lead: Lead }) {
  const segment = lead.segment ? `${lead.segment[0].toUpperCase()}${lead.segment.slice(1)} roofing` : null;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-accent">Call brief</p>
      <h1 className="mt-1 font-display text-3xl font-semibold leading-tight text-ink sm:text-4xl">{lead.company_name}</h1>
      <p className="mt-2 text-base text-ink-soft">
        {[locationLine(lead), lead.postal_code, segment].filter(Boolean).join(' · ')}
      </p>
    </div>
  );
}

function StatusNotice({ lead }: { lead: Lead }) {
  const failed = lead.status === 'failed';
  return (
    <div
      role={failed ? 'alert' : 'status'}
      className={`rounded-xl border px-4 py-4 text-sm leading-relaxed ${
        failed ? 'border-bad bg-bad-tint text-ink' : 'border-dashed border-line-strong text-ink-soft'
      }`}
    >
      <p className="font-semibold">{pendingLabel(lead.status)}</p>
      <p className="mt-1">
        {failed
          ? `${leadFailureMessage(lead.error_message)} Run the pipeline again to retry — any saved research is reused, so it is not paid for twice.`
          : 'This brief fills in automatically once the pipeline reaches this contractor.'}
      </p>
    </div>
  );
}

function Brief({ lead }: { lead: Lead }) {
  if (lead.status !== 'enriched') {
    return (
      <div className="flex flex-col gap-6">
        <StatusNotice lead={lead} />
        {lead.research_summary && (
          <Section title="Sources" id="sources">
            <Sources urls={lead.research_sources ?? []} />
          </Section>
        )}
        <RawResearch lead={lead} />
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {lead.ai_summary && (
        <p className="font-display text-xl leading-relaxed text-ink sm:text-2xl">{lead.ai_summary}</p>
      )}
      <Section title="Talking points" id="talking-points">
        <TalkingPoints points={lead.talking_points} />
      </Section>
      {lead.recommended_approach && (
        <Section title="Recommended approach" id="approach">
          <p className="border-l-2 border-accent pl-4 text-base leading-relaxed text-ink">{lead.recommended_approach}</p>
        </Section>
      )}
      <Section title="Who to ask for" id="decision-makers">
        <DecisionMakers people={lead.decision_makers ?? []} />
      </Section>
      <Section title="Sources" id="sources">
        <Sources urls={lead.research_sources ?? []} />
      </Section>
      <RawResearch lead={lead} />
    </div>
  );
}

export default async function LeadDetailPage({ params }: Props) {
  const { id } = await params;
  let lead: Lead | null;
  try {
    lead = await getLead(id);
  } catch (err) {
    console.error('[LeadDetail] failed to fetch lead', err);
    return (
      <div className="min-h-screen">
        <SiteHeader backHref="/" />
        <main className="mx-auto max-w-6xl px-4 sm:px-6">
          <div role="alert" className="rounded-2xl border border-dashed border-line-strong px-6 py-16 text-center">
            <p className="font-display text-2xl text-ink">Can&apos;t reach the leads service right now.</p>
            <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-soft">
              The backend API isn&apos;t responding. Start it on port 8000 (see README), then reload this page.
            </p>
          </div>
        </main>
      </div>
    );
  }
  if (!lead) notFound();

  return (
    <div className="min-h-screen">
      <SiteHeader backHref="/" />
      <main className="mx-auto max-w-6xl px-4 pb-16 sm:px-6">
        <Title lead={lead} />
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="order-2 min-w-0 lg:order-1"><Brief lead={lead} /></div>
          <div className="order-1 min-w-0 lg:order-2 lg:sticky lg:top-6 lg:self-start"><ScoreCard lead={lead} /></div>
        </div>
      </main>
    </div>
  );
}
