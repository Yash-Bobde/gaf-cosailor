import type { TierInfo } from '@/lib/format';

const STYLES: Record<TierInfo['tier'], string> = {
  'call-first': 'bg-accent text-white border-accent',
  'this-week': 'bg-card text-ink border-ink',
  nurture: 'bg-transparent text-ink-soft border-line-strong',
  pending: 'bg-transparent text-ink-faint border-dashed border-line-strong',
  failed: 'bg-bad-tint text-bad border-bad',
};

/** The action label a rep reads first: Call first / This week / Nurture / Needs retry. */
export function TierBadge({ info }: { info: TierInfo }) {
  return (
    <span
      title={info.hint}
      className={`inline-flex items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-semibold tracking-wide ${STYLES[info.tier]}`}
    >
      {info.label}
    </span>
  );
}
