/**
 * ScoreBar — a compact labelled 1–10 meter (e.g. "Fit 7", "Opportunity 4").
 * Ten segments keep the scale legible at a glance without a chart library.
 */
interface ScoreBarProps {
  label: string;
  value: number | null;
}

export function ScoreBar({ label, value }: ScoreBarProps) {
  const filled = value ?? 0;
  return (
    <div className="flex items-center gap-2" role="img" aria-label={`${label} ${value ?? 'not scored'} of 10`}>
      <span className="w-20 text-xs text-ink-soft">{label}</span>
      <span className="flex gap-[2px]" aria-hidden="true">
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={`h-2 w-1.5 rounded-[1px] ${i < filled ? 'bg-ink' : 'bg-line'}`}
          />
        ))}
      </span>
      <span className="w-4 text-right font-mono text-xs tabular-nums text-ink">{value ?? '–'}</span>
    </div>
  );
}
