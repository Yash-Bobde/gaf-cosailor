# Cosailor Insights — Frontend

Next.js 15 App Router UI: a ranked **call sheet** of GAF contractors, and a **call brief** per lead
for a roofing-distributor sales rep preparing an outreach call.

## Setup

```bash
npm install
echo "NEXT_PUBLIC_API_URL=http://127.0.0.1:8000" > .env.local   # point at the FastAPI backend
npm run dev                                                     # http://localhost:3000
```

Use `127.0.0.1` rather than `localhost`: Node resolves `localhost` to IPv6 `::1`, which uvicorn
does not listen on by default.

## Key Commands

```bash
npm run dev        # dev server (Turbopack)
npm run build      # production build
npx tsc --noEmit   # type check
npm run lint       # eslint
```

## Design

"Call Sheet": warm paper background, ink type, a single safety-orange accent — the look of a
printed job sheet. Newsreader for headings, Plus Jakarta Sans for body, JetBrains Mono for numbers.

- **Roof-pitch meter** — each lead's priority index drawn as a roofline that gets steeper as the
  score rises, always shown next to the number.
- **Action tiers** — Call first / This week / Nurture, so a rep reads the next action, not a raw score.
- **Streaming results** — while a run is active, leads appear on the sheet one by one as each is
  researched and scored.

## Structure

| Path | Type | Purpose |
|---|---|---|
| `app/page.tsx` | Server | Call sheet page: header, run panel, ranked leads, empty/error states |
| `app/leads/[id]/page.tsx` | Server | Call brief: summary, talking points, approach, decision-makers, sources |
| `components/RunPanel.tsx` | Client | ZIP / radius / segment / max-leads form, live progress, cancel |
| `hooks/usePipelineRun.ts` | Client | Start (attaches on 409), cancel, restore latest run, 3 s polling |
| `components/CallSheet.tsx` | Server | Filters, sort, pagination (URL-driven links) |
| `components/LeadRow.tsx` | Server | One ranked row with click-to-call |
| `components/brief/*` | Server | Call-brief sections and score sidebar |
| `components/RoofPitch.tsx`, `ScoreBar.tsx`, `TierBadge.tsx` | Server | Score visuals |
| `lib/api.ts` | — | All backend calls |
| `lib/format.ts` | — | Tiering and formatting helpers |
