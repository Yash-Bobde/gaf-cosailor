/**
 * RoofPitch — the signature score glyph.
 *
 * A roofline whose pitch rises with the priority index: a flat, low roof is a
 * nurture lead, a steep gable is a "call first" lead. The numeric value is
 * always rendered alongside so meaning never relies on shape or colour alone.
 */
import type { CallTier } from '@/lib/format';

interface RoofPitchProps {
  value: number | null;
  tier: CallTier;
  size?: 'sm' | 'lg';
}

const TIER_COLOR: Record<CallTier, string> = {
  'call-first': 'var(--accent)',
  'this-week': 'var(--ink)',
  nurture: 'var(--ink-faint)',
  pending: 'var(--line-strong)',
  failed: 'var(--bad)',
};

/** Peak height in viewBox units: 4 (flat) … 26 (steep) for a 0–10 score. */
function peakY(value: number | null): number {
  const clamped = Math.max(0, Math.min(10, value ?? 0));
  return 30 - (4 + (clamped / 10) * 22);
}

export function RoofPitch({ value, tier, size = 'sm' }: RoofPitchProps) {
  const color = TIER_COLOR[tier];
  const y = peakY(value);
  const dims = size === 'lg' ? 'h-14 w-[4.5rem]' : 'h-9 w-12';
  const label = value === null ? 'Not scored yet' : `Priority ${value.toFixed(1)} out of 10`;

  return (
    <svg viewBox="0 0 48 36" className={dims} role="img" aria-label={label}>
      <line x1="2" y1="34" x2="46" y2="34" stroke="var(--line-strong)" strokeWidth="1.5" />
      <path
        d={`M4 34 L4 30 L24 ${y} L44 30 L44 34`}
        fill={tier === 'pending' ? 'none' : color}
        fillOpacity={tier === 'call-first' ? 0.14 : 0.08}
        stroke={color}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeDasharray={tier === 'pending' ? '3 3' : undefined}
      />
      <path
        d={`M4 30 L24 ${y} L44 30`}
        fill="none"
        stroke={color}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
