# Baseline Audit — TASK 101

## Source of baseline facts

All facts below are taken verbatim from the owner-approved task text (live GET-audit dated 31.08.2026). No new live check was performed by Claude in this task; Claude has no execution access to production, CRM, or PythonAnywhere. Nothing here is claimed as freshly verified beyond what the task provided.

## Confirmed baseline (as stated in task input)

| Fact | Value |
|---|---|
| Total unique cards | 16 (UA-0001…UA-0016) |
| Public card URLs HTTP status | 200 for all 16 |
| Catalog distribution | Kyiv 3, Georgia (stage) 1, On ferry 8, Korea 4, total 16 |
| Homepage server-rendered HTML | still shows stale fallback: total 13, stages 3/1/7/2 |
| JS post-load correction | present, but server HTML and some crawlers still see stale numbers |
| Language switcher | RU \| UA (2 languages) |
| `i18n.js` | accepts only `ru`, `uk` |
| `.countries-inline` block | 5 decorative `span` items: Korea, Japan, USA, Europe, China |
| Country names on homepage | not full links |
| Shared CTA | routes to `podbor.html` with no country pre-selected |
| `podbor.html` supported countries | `korea`, `japan`, `usa`, `europe`, `china` |
| Missing/invalid `strana` param | falls back to `korea` |
| Application submission | passes country code via Telegram WebApp field `s` and deep-link `z_<country>` |

## Missing canonical source-of-truth evidence (required before any real patch can be applied)

The following are NOT available to Claude in this task and are required before `implementation.patch` can move from "template" to "applicable":

1. Exact repository path and current byte content (or SHA-256) of the homepage template that renders the counters (13 / 3-1-7-2) — the actual server-side template/generator file, not the browser-visible HTML only.
2. Exact repository path and current content of `i18n.js` (or equivalent i18n module).
3. Exact repository path and current content of the homepage `.countries-inline` block markup/template.
4. Exact repository path and current content of `podbor.html` (or its generator/template) including the country-to-model binding logic.
5. Exact repository path and current content of the Telegram WebApp submission handler and deep-link parser (`z_<country>` matcher).
6. Exact repository path and current content of the single source-of-truth catalog/count generator that should feed both the homepage counters and the catalog page (task states a single source must exist or be created — its current location is not in evidence).
7. SHA-256 manifest of the 16 live cards (data + media) — not available to Claude; must be produced by an operator/script with live/production read access before any BEFORE/AFTER card-guard comparison can be executed.
8. Confirmation of `UA-0009` specific current field values (VIN, price, stage, media count) — not available to Claude in this task.

## Consequence for this package

Because items 1–8 above are not in evidence, `implementation.patch` in this package is delivered as an **explicitly labeled integration template**, not an applicable diff against real file contents. No exact context lines were invented. `evidence.json` marks all execution-dependent checks as `PENDING`, never `VERIFIED`, and all safety booleans as `false`.
