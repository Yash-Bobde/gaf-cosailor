import { SiteHeader } from '@/components/SiteHeader';

export default function LeadDetailLoading() {
  return (
    <div className="min-h-screen" aria-busy="true" aria-label="Loading call brief">
      <SiteHeader backHref="/" />
      <main className="mx-auto max-w-6xl px-4 sm:px-6">
        <div className="skeleton h-4 w-24" />
        <div className="skeleton mt-3 h-10 w-2/3" />
        <div className="skeleton mt-3 h-5 w-1/3" />
        <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-4">
            <div className="skeleton h-24" />
            <div className="skeleton h-40" />
            <div className="skeleton h-24" />
          </div>
          <div className="skeleton h-96 rounded-2xl" />
        </div>
      </main>
    </div>
  );
}
