# TASK 017 — Correct TASK 014/016 Gate A runner after safety audit

## Authority and scope

Owner request: continue correcting TASK 014 with PythonAnywhere access.

This task authorizes **Gate A only**: read real inputs, create isolated preview artifacts and public reports under the report namespace. It does **not** authorize any production-card, generator, CRM, database, live-index, or media mutation. Gate B remains locked.

## Why TASK 016 must not be executed

Independent review found that the TASK 016 candidate can produce a false green result:

1. It omits the real public-card server path likely represented by `/home/Carix/video/UA-0001.html` … `UA-0008.html`.
2. CRM discovery omits `/home/Carix/crm.db`.
3. generator discovery omits `master_card.py`, `stranica.py`, and `yadro.py`.
4. Its injected links point to generic `./diagnostics.html` and `./tracking.html`, while companion files are card-specific.
5. It guesses an insertion point before `</body>` if the structural anchor is absent.
6. `EMPTY_STATE_TEXT in html_text or True` makes empty-state validation always pass.
7. final `AWAITING_GATE_B` ignores per-card FAIL results.
8. media containment is checked against the preview root instead of approved real media roots.
9. manifest generation is not cryptographically bound to the launcher.
10. required immutable milestones and final evidence fields are incomplete.

Do not run or reuse TASK 016 as-is.

## Verified live read-only evidence

As of 2026-08-27, public GET requests return HTTP 200 for:

- `https://www.uaart.com.ua/video/UA-0001.html` through `UA-0008.html`
- `UA-0009.html` is not published and redirects to `/video/index.html`

Observed live coverage:

| card | `mcf-diag-cta` | `mcf-track` / tracking text |
|---|---:|---:|
| UA-0001 | 1 | 0 |
| UA-0002 | 1 | 0 |
| UA-0003 | 0 | 0 |
| UA-0004 | 0 | 0 |
| UA-0005 | 0 | 1 |
| UA-0006 | 0 | 1 |
| UA-0007 | 0 | 0 |
| UA-0008 | 1 | 0 |

Every current live card contains exactly one purchase anchor matching an anchor element whose class list includes both `dejstvie` and `kn_kupit`. Treat exactly-one purchase anchor as the mandatory structural insertion anchor.

Existing diagnostics use a card-specific href such as `UA-0008-diag.html`.
Existing real tracking links on UA-0005/0006 must be preserved as evidence and rendered on their card-specific tracking pages.

## Required implementation

Replace the unsafe TASK 016 Gate A package with a corrected, reviewable TASK 017 package.

### 1. Bounded real-input discovery

Search only bounded, explicit candidates; do not recursively scan the account.

Card candidates must include at minimum:

- `/home/Carix/video/{CODE}.html`
- `/home/Carix/video/cards/{CODE}.html`
- `/home/Carix/video/cards/{CODE}/index.html`
- `/home/Carix/site/{CODE}.html`
- `/home/Carix/public_html/video/{CODE}.html`
- `/home/Carix/public_html/cards/{CODE}.html`
- `/home/Carix/mysite/{CODE}.html`
- `/home/Carix/{CODE}.html`

where `CODE` is exactly `UA-0001` … `UA-0009`.

CRM candidates must include `/home/Carix/crm.db` plus the existing bounded candidates.

Generator candidates must include bounded paths for:
- `master_card.py`
- `stranica.py`
- `yadro.py`
- existing named generator/template candidates from TASK 016.

For UA-0001…UA-0008, missing real source HTML is a hard BLOCKED result. Never synthesize or substitute a demo card. UA-0009 may be built only from actual CRM/generator source evidence; otherwise report `UA-0009 PUBLICATION READINESS: BLOCKED`.

### 2. Strict preview transform

Operate on copies only under:
`/home/Carix/video/reports/ua_cards_unified/preview/`

For each source card:

- Require exactly one purchase anchor with class tokens `dejstvie` and `kn_kupit`. If count is not exactly one, card = FAIL; do not guess or append before `</body>`.
- Normalize preview UI to exactly one diagnostics entry and exactly one tracking entry.
- Canonical links:
  - diagnostics: `{CODE}-diag.html`
  - tracking: `{CODE}-track.html`
- Place the unified entries deterministically adjacent to and immediately before the purchase anchor, reusing the card's existing CTA styles/classes where practical.
- Preserve all unrelated card HTML, text, media references, CTA behavior and real carrier URLs.
- Diagnostics companion page must show real CRM/source diagnostics when present; otherwise an honest explicit empty state.
- Tracking companion page must show verified carrier/container data and the original safe carrier URL when present; otherwise an honest explicit “данные отслеживания уточняются” state.
- Never invent VIN, mileage, auction, diagnostics, carrier, container or status data.

### 3. Media validation

Allow only existing contained media paths under explicit approved source roots such as:

- `/home/Carix/video`
- `/home/Carix/site`
- `/home/Carix/public_html`
- `/home/Carix/mysite`

Resolve paths canonically and reject traversal or escape. Copy only verified media needed by preview pages. Do not use preview root as the only allowed root for real source media.

### 4. Manifest binding and restricted launcher

Produce a manifest that contains:

- exact input paths and SHA-256 hashes;
- exact output paths;
- protected production paths and before hashes;
- allowlisted public report/preview write paths;
- runner file SHA-256;
- timestamp and task ID.

The no-argument launcher must:

- load the manifest;
- verify the runner hash and every bound input hash before execution;
- reject symlinks and path escapes;
- reject any write outside the report namespace;
- execute once;
- record a receipt with manifest hash, runner hash, output hashes and protected before/after hashes.

No production write capability may exist in this Gate A launcher.

### 5. Mandatory validations

A card PASS requires all of the following:

- real input resolved;
- exactly one valid structural anchor;
- exactly one canonical diagnostics entry;
- exactly one canonical tracking entry;
- both card-specific companion hrefs resolve inside preview;
- honest data or honest empty-state text is actually present (no always-true predicate);
- local link/media checks pass;
- deterministic second generation yields byte-identical output.

Any card FAIL/BLOCKED prevents overall `AWAITING_GATE_B`.

Before final Gate A status:

- verify public HTTP 200 for every published preview/report URL;
- verify all protected hashes unchanged;
- compute `UNEXPECTED PROTECTED CHANGES`;
- explicitly test that no production write occurred.

### 6. Progress and final evidence

Publish immutable reports for 20%, 40%, 60%, 80%, and 100% only after that checkpoint's work and checks actually complete. Also maintain:

- `/video/reports/ua_cards_unified/progress.json`
- `/video/reports/ua_cards_unified/latest_status.html`

Do not claim 100% unless every Gate A requirement passes. At 100%, reports must contain actual values for:

- preview URL;
- `CURRENT CARDS SAFE`;
- `UNEXPECTED PROTECTED CHANGES`;
- `UA-0009 PUBLICATION READINESS`;
- `SAFE TO PUBLISH UA-0009`;
- `PRODUCTION WRITE`;
- per-card status UA-0001…UA-0009;
- passed checks;
- errors/blockers;
- remaining time;
- links to manifest, receipt, hashes, per-card evidence and milestone reports.

Expected safe terminal states:

- `AWAITING_GATE_B` only if every Gate A check is PASS and production is unchanged;
- otherwise `BLOCKED` with exact reasons.

## Deliverables

Commit reviewable corrected files under `cloud/ua_cards_unified/`, including:

- corrected runner;
- manifest builder;
- restricted no-argument launcher;
- read-only preflight/audit utility;
- operator instructions;
- explicit owner reply/status.

Do not execute production changes. Do not claim completion from generated code alone. The next action after this GitHub task is independent code review, then PythonAnywhere Gate A execution.
