# Cosailor Insights — Brand Guidelines v1.0

> Last updated: 2026-09-26
> Status: Draft — written down from the shipped frontend, not invented from scratch.
> Source of truth for colour and type values: [`frontend/app/globals.css`](../frontend/app/globals.css)
> and [`frontend/app/layout.tsx`](../frontend/app/layout.tsx). If this document and the code
> disagree, the code wins and this document gets fixed.

**Watch:** [`docs/brand/cosailor-brand-film.mp4`](brand/cosailor-brand-film.mp4), a 54-second
walkthrough of this document. Logo files: [`docs/brand/`](brand/). To re-render the film after
changing the guidelines, edit `brand/film/brand-film.html`, then run
`FFMPEG=<path> node docs/brand/film/render.mjs`.

## Quick Reference

| Element | Value |
|---------|-------|
| Name | **Cosailor Insights** (wordmark: "Cosailor", descriptor: "Insights") |
| Tagline | *GAF contractor call sheet* |
| One-liner | A ranked call sheet of GAF roofing contractors for distributor sales reps |
| Concept | A printed job sheet on a roofing site: warm paper, dark ink, one safety-orange mark |
| Primary colour | Safety orange `#C2410C` |
| Surface | Paper `#F6F4EF` |
| Text | Ink `#1A1D21` |
| Display font | Newsreader (serif, 500–600) |
| Body font | Plus Jakarta Sans (400–700) |
| Data font | JetBrains Mono (400–500) |
| Voice | Direct, grounded, honest about limits |

---

## 1. Who it's for and what we promise

**Audience.** Sales reps at roofing distributors, and the sales managers who send them out.
They are busy, often on the phone or on a small screen, and they already know the trade.
They do not need roofing explained. They need to know who to call, why, and what to say.

**Promise.** *Know who to call first, and walk into the call prepared.*

**Positioning.** Cosailor turns a public contractor directory into a ranked, researched call
sheet. It doesn't replace the rep's judgement. It does the homework before the call.

### Messaging pillars

| Pillar | What we say | Proof we can point to |
|--------|-------------|-----------------------|
| **Priority** | "Call first, this week, or nurture — decided before you pick up the phone." | Priority index = (Fit + Opportunity) ÷ 2 × distance modifier |
| **Preparation** | "Three talking points, a recommended approach, and who to ask for." | Call brief on every lead |
| **Grounded** | "Every name comes from the research, and we show you where." | People kept only if named in full in the research; cited sources listed |
| **Honest** | "When something fails, we say so, and we never fill the gap with a guess." | Failed leads show *Needs retry*; no invented contacts or titles |

**Don't claim:** conversion probability, guaranteed decision-makers, "AI that closes deals", or
real-time/complete coverage of the market. The scores are heuristic and uncalibrated, and the
product says so (see the README's *Scores* section).

---

## 2. Voice & Tone

### Brand Personality

| Trait | We are | We are not |
|-------|--------|------------|
| **Direct** | Lead with the action: "Call first." | Vague, hedging, padded |
| **Grounded** | Specific and sourced: "The research names this person with a purchasing title." | Hype, superlatives, "AI-powered" as a selling point |
| **Honest** | Plain about failures and limits: "Nothing was guessed." | Falsely reassuring, blaming the user |
| **Practical** | Written for someone about to dial: short lines, verbs first | Academic, technical in front of reps |
| **Trade-aware** | Uses the rep's words: contractor, territory, call sheet, Master Elite | Generic SaaS words: users, entities, workflows |

### Tone by context

| Context | Tone | Example from the product |
|---------|------|--------------------------|
| Rank labels | Imperative, 1–2 words | "Call first" · "This week" · "Nurture" · "Needs retry" |
| Empty state | Tell them the next step | "Pick a ZIP code and radius above and build a call list — leads appear here one by one…" |
| Progress | Present tense, what's happening now | "Finding contractors on GAF…" · "Researching and scoring each lead…" |
| Lead failure | Calm, what happened + what didn't | "Web research for this contractor failed, so no brief was written — nothing was guessed." |
| Run failure | Cause, consequence, next step | "Last run was interrupted by a server restart. Run again to resume — scored leads are kept." |
| Evidence labels | Precise about certainty | "Named in the research, but buying authority is not established" |
| Developer docs (README) | Technical, exact, measured claims with dates | "10 leads scored in 35.4 s (one environment, not a guarantee)" |

### Writing rules

1. **Action first.** Put the verb or the outcome at the start of a line.
2. **Say what we know and what we don't.** Label certainty: *Decision-maker* only with a
   supported title, otherwise *Contact*.
3. **Every failure message has three parts:** what happened, what was *not* done (nothing
   guessed, nothing scored), and what to do next.
4. **Never show raw errors to reps.** Map them to plain language; keep the details in logs.
5. **Numbers carry units and context:** "12.4 mi", "Priority 8.1 out of 10", "measured 2026-09-24".
6. **Sentence case** everywhere: buttons, labels, headings. No Title Case, no ALL CAPS in copy.
7. **Em dashes are fine** for a consequence clause ("…failed — the next run retries it").
   Use an ellipsis (…) for in-progress states.

### Words

| Use | Instead of |
|-----|------------|
| call sheet, call brief | dashboard, report, profile page |
| contractor, lead | account, entity, record |
| research, sources | AI insights, intelligence |
| build a call list | run the pipeline (in UI copy) |
| needs retry | error, failed (as a label) |
| priority | score (when you mean the rank) |

### Prohibited Terms

| Avoid |
|-------|
| revolutionary |
| best-in-class |
| seamless |
| supercharge |
| unlock |
| leverage |
| synergy |
| AI-powered (as a headline) |
| guaranteed |
| verified decision-maker |

Why: superlatives we can't prove, SaaS filler, and claims of certainty the data doesn't
support. The value is the call sheet, not the model. Say "use", not "leverage".

---

## 3. Colour

The palette is a job sheet: warm paper, ink-dark type, one safety-orange accent. Orange is
reserved for **the most important thing on screen** — the primary button, the *Call first*
badge, focus rings, progress. If everything is orange, nothing is.

### Primary Colors

| Token | Hex | Role |
|-------|-----|------|
| `--accent` | `#C2410C` | Safety orange. Primary action, *Call first*, focus ring, logo mark stroke |
| `--accent-strong` | `#9A3412` | Hover/pressed for accent; accent text on tint |
| `--accent-tint` | `#FDF0E8` | Logo mark fill, icon chips, soft highlight |

### Neutral Palette

| Token | Hex | Role |
|-------|-----|------|
| `--paper` | `#F6F4EF` | Page background, browser `theme-color` |
| `--card` | `#FFFFFF` | Cards and panels |
| `--ink` | `#1A1D21` | Headings, body text, *This week* badge outline |
| `--ink-soft` | `#4A5059` | Secondary text |
| `--ink-faint` | `#6B7079` | Captions, metadata, *Nurture* glyph |
| `--line` | `#E3DFD6` | Card borders, dividers |
| `--line-strong` | `#CFC9BC` | Input borders, pending states, secondary button outline |

### Semantic Colors

| Token | Hex | Tint | Role |
|-------|-----|------|------|
| `--good` | `#15803D` | `#EAF6EE` | Completed, verified |
| `--warn` | `#A16207` | `#FBF3E0` | Caution, ratings star — **icons only** (see below) |
| `--bad` | `#B91C1C` | `#FCECEC` | Failed, *Needs retry* |

### Contrast (WCAG 2.1, measured)

| Foreground | on Paper | on Card | Verdict |
|------------|----------|---------|---------|
| Ink | 15.39 | 16.91 | AAA |
| Ink soft | 7.40 | 8.13 | AAA |
| Ink faint | 4.53 | 4.98 | AA — smallest safe text colour; don't lighten it |
| Accent | 4.71 | 5.18 | AA |
| Accent strong | 6.65 | 7.31 | AA (6.54 on accent tint) |
| Good | 4.56 | 5.02 | AA (4.52 on good tint — at the limit) |
| Bad | 5.89 | 6.47 | AA (5.65 on bad tint) |
| **Warn** | **4.48** | 4.92 | **Below AA on paper and on its tint (4.45)** — use for icons (3:1 rule), not body text on paper |
| White on accent | 5.18 | — | AA — primary button text |

Colour never carries meaning alone: tiers always show a text label, and the priority glyph
always shows its number.

---

## 4. Typography

### Font Stack

```css
--font-heading: 'Newsreader', Georgia, 'Times New Roman', serif;
--font-body: 'Plus Jakarta Sans', system-ui, 'Segoe UI', Arial, sans-serif;
--font-mono: 'JetBrains Mono', ui-monospace, Consolas, monospace;
```

In code these are exposed as `--font-newsreader`, `--font-jakarta` and `--font-jetbrains`
(Tailwind `font-display`, `font-sans`, `font-mono`).

### Families

All three families are SIL OFL fonts bundled locally in `frontend/app/fonts` (Latin subsets,
variable weight). The app never loads fonts from a CDN.

| Role | Family | Weights | Tailwind | Fallback | Use for |
|------|--------|---------|----------|----------|---------|
| Display | Newsreader (+ italic) | 500–600 | `font-display` | Georgia, serif | Wordmark, page and lead titles, scores, pull-quote summary |
| Body | Plus Jakarta Sans | 400–700 | `font-sans` (default) | system-ui, Segoe UI, Arial | Everything else |
| Data | JetBrains Mono | 400–500 | `font-mono` | ui-monospace, Consolas | Phone numbers, IDs, counts, distances |

### Scale in use

| Element | Class | Notes |
|---------|-------|-------|
| Page / lead title | `font-display text-3xl sm:text-4xl font-semibold leading-tight` | One per page |
| Section score | `font-display text-2xl font-semibold` | Accent colour for the headline number |
| Wordmark | `font-display text-xl font-semibold tracking-tight` | |
| Card heading | `font-display text-lg font-semibold leading-snug` | |
| Body | `text-sm` / `text-base` | `text-sm` is the default on dense screens |
| Caption, badge | `text-xs font-semibold tracking-wide` | Badges only; don't go below `text-xs` for reading text |

Serif for what a rep should *remember* (names, scores); sans for what they *read*; mono for
what they *dial or compare*.

---

## 5. Logo & signature marks

### Wordmark

A low gable roof mark followed by **Cosailor** in Newsreader Semibold, with the descriptor
*Insights · GAF contractor call sheet* in ink-faint body type (hidden below `sm`). Defined
inline in `frontend/components/SiteHeader.tsx`.

- **Mark:** 32 × 24 viewBox, path `M2 22 L2 18 L16 4 L30 18 L30 22`, fill `--accent-tint`,
  stroke `--accent` at 2.5, round joins. Rendered at 32 × 24 px (`h-6 w-8`).
- **Minimum size:** mark 24 px wide; full lockup 120 px wide.
- **Clear space:** at least the mark's height on all sides.
- **Background:** paper or card only. On dark or photographic backgrounds use a solid paper panel.

**Don't:** recolour the mark outside accent/tint, fill it solid orange, rotate or stretch it,
add shadows, set "Cosailor" in the sans font, or drop the capital C.

**Files:** [`brand/logo-mark.svg`](brand/logo-mark.svg),
[`brand/logo-horizontal.svg`](brand/logo-horizontal.svg) (its text uses Newsreader, so convert
it to outlines before sending it outside the team) and [`brand/favicon.svg`](brand/favicon.svg).
The app still serves the default Next.js `frontend/app/favicon.ico`. To switch, copy
`favicon.svg` to `frontend/app/icon.svg` and delete `favicon.ico`.

### RoofPitch glyph

The product's signature data mark (`frontend/components/RoofPitch.tsx`): a roofline whose pitch
rises with the priority index, flat for *Nurture* and a steep gable for *Call first*. Tier
colours: accent (call first), ink (this week), ink-faint (nurture), dashed line-strong
(pending), bad (failed). It always sits next to the number. Don't use it as decoration or
without its value.

---

## 6. Components

| Element | Style |
|---------|-------|
| Primary button | `bg-accent text-white`, hover `bg-accent-strong`, `rounded-lg`, `h-11`, `text-sm font-semibold` |
| Secondary button / link pill | Transparent, `border-line-strong text-ink-soft`, hover `border-ink text-ink`, `rounded-full`, `h-10` |
| Card | `bg-card border border-line rounded-2xl p-5 sm:p-6` |
| Tier badge | `rounded-full border px-2.5 py-0.5 text-xs font-semibold` — Call first: solid accent; This week: ink outline on card; Nurture: line-strong outline; Pending: dashed; Needs retry: bad on bad tint |
| Focus | 2 px accent outline, 2 px offset, on every interactive element |
| Touch targets | At least 44 px tall (`min-h-11` / `h-11`) |
| Icons | [Lucide](https://lucide.dev), 16 px (`h-4 w-4`) in text, `aria-hidden` when decorative |
| Motion | 150 ms colour transitions; 280 ms row "rise"; skeleton shimmer; all disabled under `prefers-reduced-motion` |

### Radius

| Element | Radius |
|---------|--------|
| Buttons, inputs | `rounded-lg` (8 px) |
| Cards, panels | `rounded-2xl` (16 px) |
| Badges, pills, progress | `rounded-full` |

---

## 7. Imagery

The product uses no photography. Keep it that way in-app: the data is the picture.

For decks, social or marketing:

- **Mood:** early-morning job site, practical, unglamorous, confident.
- **Subjects:** real roofing work, such as shingles, ridgelines, a rep's phone and a clipboard.
  No stock handshakes, no glowing "AI brain" imagery.
- **Treatment:** warm, slightly desaturated; paper-toned backgrounds; one orange element at most.
- **Graphics:** flat, 2 px strokes with round joins (matching the mark and RoofPitch), brand palette only.

### Base Prompt Template

```
Documentary photo of residential roofing work at golden hour, warm paper-toned palette
(#F6F4EF background tones, #1A1D21 deep shadows), a single safety-orange (#C2410C) accent,
natural light, clean composition, no text, no logos, no people posing for the camera.
```

---

## 8. Checklist before shipping copy or UI

- [ ] Does the first word tell the rep what to do or what happened?
- [ ] Is every claim about a person, title or score supported, and labelled if it isn't?
- [ ] Does each failure state say what wasn't done and what to try next?
- [ ] Is orange used only for the single most important element?
- [ ] Does text meet AA (ink-faint is the lightest reading colour; warn is icon-only on paper)?
- [ ] Does meaning survive without colour (label + number)?
- [ ] Works at 390 px wide, with 44 px targets and visible focus?

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-26 | Initial guidelines, written down from the shipped frontend (tokens, fonts, SiteHeader, RoofPitch, UI copy) |
