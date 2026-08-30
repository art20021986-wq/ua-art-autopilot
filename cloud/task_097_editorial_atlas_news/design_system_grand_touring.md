# EDITORIAL GRAND TOURING — visual and interaction design system (specification only)

## 1. Concept

A classic automotive road journal, crossed with a modern international route atlas, produced inside a closed UA ART editorial atelier. The intended feeling: noble, precise, calmly premium, technological, international, trustworthy — with zero visual noise.

**Explicitly rejected:** a generic WordPress blog template; visual imitation of AUTO.RIA/Reuters/Bloomberg; dozens of identical cards; loud red as a primary color; cheap neon; heavy tabloid clutter; scrolling news tickers; chaotic animation.

## 2. Palette (for brand-compatibility audit, not yet applied to any live page)

| Token | Hex | Role |
|---|---|---|
| Grand Black | `#101113` | Primary dark background / primary text on light |
| Graphite | `#1A1C1F` | Secondary dark surface, card backgrounds on dark theme |
| Warm Ivory | `#F3EFE6` | Primary light background |
| Paper White | `#FAF8F2` | Card/content background on light theme |
| Heritage Gold | `#C6A15B` | Primary accent — Country Seal ring, Route Spine stroke, active state |
| Muted Gold | `#A88749` | Secondary accent — hover/pressed states, subdued dividers |
| Silver Mist | `#C8CCD1` | Neutral borders, disabled states, meta text on dark |
| Signal Red | `#A8342F` | Reserved strictly for genuine urgency labels (e.g. a mass recall alert badge) — never decorative |

**Accessibility note (INFERRED contrast check, not a verified WCAG audit):** Grand Black text on Warm Ivory, and Warm Ivory text on Grand Black, both read as high-contrast pairs suitable for body text. Heritage Gold on Grand Black is adequate for large display text (headlines, seals) but should **not** be used for body-copy-sized text without an explicit contrast re-check against WCAG AA (4.5:1) before implementation — flagged as a build-time requirement, not asserted as already passing.

## 3. Typography direction (category recommendation, no specific licensed font asserted as already secured)

- **Display/headline:** an editorial serif with restrained flourish (evaluate options in the "contemporary literary/editorial serif" category) for section titles and story headlines.
- **Body/UI:** a humanist sans-serif with clean numerals (evaluate options in the "neutral humanist grotesque" category) for body text, labels, and UI controls, to guarantee legibility for dates, prices, and document numbers.
- **Numerals:** tabular figures required wherever numbers are compared (Impact Compass, Story Dossier counts).

## 4. Signature components

### Route Spine
A thin decorative line motif tracing a route (e.g. Korea → Georgia → Ukraine) used as a section divider under a headline group or behind a hero image. Rendered as a subtle Heritage-Gold gradient stroke on dark, or Muted-Gold on light. Never a literal live map or live-tracking widget — purely an editorial ornament reinforcing the "atlas" identity.

### Country Seal
A small circular editorial mark combining a country abbreviation and the story's event date, rendered as a thin Heritage-Gold ring on Grand Black or Warm Ivory. Explicitly an editorial mark, not an imitation of any government stamp or coat of arms. Generated per story, shown on the story card and in the Story Dossier.

### Impact Compass
A four-quadrant qualitative indicator: **price**, **timing**, **availability**, **paperwork**. Each quadrant shows a directional cue (up/down/neutral) plus one short qualitative sentence ("may increase", "processing likely slower for a few weeks") — never a fabricated numeric percentage unless the fact card itself contains a sourced number. No quadrant is shown if the fact card does not support a judgement for it.

### Story Dossier
A right-rail panel on desktop / an expandable panel on mobile showing: number of corroborating sources, a confidence label (derived from FACT_CONFIDENCE, shown qualitatively, e.g. "Підтверджено кількома джерелами"), first-published and last-updated dates, and a link to the correction log.

### Source Ledger
A footer block on every article listing every corroborating source: domain mark, class A/B/C badge, an outbound link, and the note "перевірено редакцією" / "проверено редакцией". This is the visible, artistic realization of the transparency requirement — it never hides or omits a source used.

### Route Pulse
A calm, vertical timeline widget on the homepage showing the most recent story updates along the route metaphor. Bounded item count, manual/staggered refresh only (page load or explicit "show more"), no auto-refreshing ticker, no live-tracking simulation.

## 5. Layout notes (desktop/mobile — see `information_architecture_and_wireframes.md` for the actual wireframes)

- Desktop: a three-column rhythm on the homepage (Route Pulse rail / story grid / secondary rail), collapsing to a single column with the Route Pulse moved below the fold on mobile.
- Article page: hero image (16:9) with Route Spine beneath the headline, body text in a constrained measure (≈65–75 characters per line) for readability, Story Dossier as a right rail on desktop and a collapsible panel on mobile, Source Ledger always at the article's end.
- Owner candidate card: a dense, single-scroll card exposing every field listed in `editorial_policy_ua_ru.md` §3, with the four action buttons fixed at the bottom on mobile.
- Autopilot settings screen: the master switch is rendered OFF by default with a two-step confirmation (toggle + explicit "Подтвердить включение автопилота" action), and the eligibility thresholds from `dedup_scoring_autopilot.md` are shown read-only, not editable inline, to avoid accidental threshold weakening.

## 6. Accessibility and motion

- Respect `prefers-reduced-motion`: disable the Route Spine's animated gradient sweep and the Route Pulse's transition animation; keep both fully readable in a static state.
- All interactive controls (approve/publish/delete/defer/audit buttons) must have a visible focus ring and a minimum 44×44px touch target on mobile.
- Color is never the only signal for status (e.g. "needs review" also carries a text label, not just a color chip).

## 7. Image ratios and performance budget

- Hero: 16:9. Card: 4:3. Seal/avatar: 1:1.
- Prefer static/server-rendered HTML for the news hub and article pages; lazy-load below-the-fold imagery; avoid heavy client-side animation libraries; inline only critical CSS for the above-the-fold hero and Route Spine.

## 8. Explicit non-goal for this task

No CSS, no component code, and no live page were produced or deployed. This is a design specification for a future, separately-approved build step.
