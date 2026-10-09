import Link from 'next/link';
import { SiteHeader } from '@/components/SiteHeader';

export default function NotFound() {
  return (
    <div className="min-h-screen">
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="rounded-2xl border border-dashed border-line-strong px-6 py-16 text-center">
          <p className="font-display text-2xl text-ink">That lead isn&apos;t on the call sheet.</p>
          <Link href="/" className="mt-3 inline-block text-sm text-ink-soft underline underline-offset-4 hover:text-ink">
            Back to the call sheet
          </Link>
        </div>
      </main>
    </div>
  );
}
