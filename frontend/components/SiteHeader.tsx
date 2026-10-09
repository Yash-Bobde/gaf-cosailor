import Link from 'next/link';

/** Wordmark + tagline shared by every page. */
export function SiteHeader({ backHref }: { backHref?: string }) {
  return (
    <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
      <Link href="/" className="flex min-h-11 items-center gap-2.5" aria-label="Cosailor Insights home">
        <svg viewBox="0 0 32 24" className="h-6 w-8" aria-hidden="true">
          <path d="M2 22 L2 18 L16 4 L30 18 L30 22" fill="var(--accent-tint)" stroke="var(--accent)" strokeWidth="2.5" strokeLinejoin="round" />
        </svg>
        <span className="font-display text-xl font-semibold tracking-tight text-ink">Cosailor</span>
        <span className="hidden text-sm text-ink-faint sm:inline">Insights · GAF contractor call sheet</span>
      </Link>
      {backHref && (
        <Link
          href={backHref}
          className="inline-flex h-10 items-center rounded-full border border-line-strong px-4 text-sm text-ink-soft transition-colors duration-150 hover:border-ink hover:text-ink"
        >
          ← Call sheet
        </Link>
      )}
    </header>
  );
}
