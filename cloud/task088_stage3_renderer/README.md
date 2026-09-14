# TASK088 Stage 3 renderer candidate — FINAL v5.0

Status: local candidate, not installed. No CRM, production HTML, workflow, receipt,
or production configuration writes were performed by this package.

## What changes

`uaart_market_prices.py` is a pure renderer installed under that exact module name
alongside the existing generators. It reads independent `price_uah` and
`price_georgia` values as USD; it does not convert, persist, round, migrate or
borrow a value from the other market. A row depending on the legacy `price_total`
fallback is rejected for explicit reconciliation, never silently copied or hidden.
Ukraine appears above Georgia on the card
and on every catalog tile. Missing Georgia remains visible as “Цена уточняется”.
Headings include translated country names and flags. Compact tiles contain only
two country/price rows, at 16px, without delivery descriptions. Full cards include
the FINAL v5.0 descriptions: delivery to Kyiv with customs and certification, and
delivery to the Rustavi car market 🅿️ №16. These descriptions supersede the old
candidate's AUTOPAPA/customs wording. Historical owner-decision files remain
unchanged; the renderer tests assert FINAL v5.0 directly.
Inner spans inherit the price font and color explicitly, preventing the existing
`.catalog-top span` rule from shrinking country names and amounts to 12px.
Actual USD amounts stay together while long country/placeholder text can wrap.

`patch_yadro.patch_yadro(bytes)` and `patch_stranica.patch_stranica(bytes)` return
candidate bytes plus provenance. They never import or execute their target
modules, and never write files. Full input SHA256 and AST-selected original price
statements must match. They replace only the base price statements (plus the old
unqualified “доплат нет” caption in the same price slot) and add the renderer
import. The `stranica.sobrat_glavnuyu` homepage price statement uses the same
compact renderer. Catalog headings, SEO and metadata remain unchanged; restoring
only the price fragments must restore the complete original output. Existing
wrappers remain byte-identical. Unknown source revisions and
reapplication fail closed. Complete candidates are compiled before return.

`patch_catalog_design_guard.patch_catalog_design_guard(bytes)` patches the actual
final catalog price builder. This is essential: both `master_card.obrabotat_obshuyu`
and the transaction publisher rebuild from `catalog_design_guard` and discard the
earlier incoming catalog HTML. Only its price replacement section changes; all 24
other functions, including the immutable-shell and stage audits, remain identical.

`initial_html_prices.migrate_card(html, row)` and `migrate_catalog(html, rows)`
produce initial price-only HTML candidates and before/after evidence. They do not
regenerate pages or execute live modules. Existing UA amounts must match CRM,
article identities must match the complete published set, unknown or duplicate
anchors abort, and existing markers abort reapplication. Catalog shell, photos,
descriptions, specifications, diagnostics and every non-price byte remain intact.
The installer owns snapshot hashes, locks, backup, atomic writes and readback.

`initial_html_prices.migrate_home(html, rows)` recognizes the current four-stage
homepage and preserves every byte. Its stage photos are not individual car-price
previews and must not acquire prices of representative cars. Newly found car
links or price surfaces fail closed instead of being silently ignored. The
current `video/index.html` passes this inventory. The captured `site/index.html`
is an older seven-car homepage with stale prices, not a redirect; it requires
verified routing evidence before it may be excluded as an inactive artifact.

## Exact source baselines

| Source | SHA256 | Wrappers preserved |
|---|---|---:|
| yadro.py | 1c6bddccec30198179f9a179aa67ac8f2e40da1a794c87f2342150eb5d2ec793 | 5 |
| stranica.py | 2794f01c00a49f1a55c66f3e6af4657808f857e9167f59a5da84c9b8430d724a | 7 |
| catalog_design_guard.py | 51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60 | 24 other functions |

These are the complete, hash-verified private snapshots inspected on 2026-09-13.
Their contents are not copied into this public package.

## Verification

From the repository/workspace root:

```bash
UA088_LIVE_SOURCE_DIR=/path/to/private_snapshot python -B -m unittest discover -s cloud/task088_stage3_renderer -p 'test_*.py' -v
```

51 tests pass with the complete current private capture and its hash manifest.
The original partial private snapshot runs 48 tests with three additional
complete-capture checks skipped. The earlier 40/44-test results do not cover the
later homepage/CSS/current-capture checks. Missing private fixtures are explicit
skips, never equivalent acceptance evidence.

The exact-source tests extract only named base renderer AST functions, execute
them with controlled dependencies, and compare before/after results for 18 synthetic
car rows spanning four stages, an 18-item catalog in both generators, and the
existing `stranica` homepage with 18 synthetic rows plus an empty list. No real
CRM rows are read or represented as acceptance evidence. Restoring the original
price fragment produces a byte-identical complete document, including headings
and metadata. Card identifiers, images, description,
stage content, links, navigation, scripts, diagnostics and catalog counters outside
the replaced fragment therefore do not change in these tested base renderers.
No module top-level code or live filesystem helpers execute.

The exact master-card function/alias chain was exercised across four synthetic
stages with external specification boundaries and every I/O helper fenced; the
market-price fragment survives intact. The actual final catalog builder was also
exercised with a synthetic approved-shape shell and 18 synthetic rows. Its unchanged
shell fingerprint and catalog audits pass, and restoring only original price nodes
produces identical output. These remain offline tests, not production acceptance.

Actual captured `UA-0010.html` was migrated successfully: existing Ukraine price
is preserved, CRM Georgia price is included, and all image/link/script opening
tags remain identical. The actual golden template plus 18 captured CRM price-only
rows also passes its unchanged final catalog audit, with counts 18 = 5/5/4/4.
Photos in that build are deliberately fixtures; this is not photo acceptance.
The captured card and golden hashes are pinned in the tests. No production writes
or live Telegram acceptance are implied by these offline results.

The actual captured 18-item catalog also passes initial migration and the original,
unmodified catalog guard audit. Its original photos, links, scripts, immutable shell
fingerprint and stage counters remain intact; only the 18 price nodes change.
The captured catalog SHA256 is pinned in `test_captured_pages.py`.

## Required integration gates

This package alone is not Stage 3/4 acceptance. The exact publisher/master chain
was inspected and its final golden-template catalog renderer has a dedicated
patch. Live specification and language injection still require end-to-end checks.
Use the actual `/home/Carix/catalog_design_golden.html` baseline (or root override)
for immutable-shell acceptance. No guard or old receipt may be rewritten merely
to pass these checks.

The caller must provide a fresh source snapshot, shared writer exclusion,
backup/rollback, source installation binding, staged generation, semantic CRM /
card / catalog equality, immutable generation receipt and public readback.
Maintain no regression in all non-price content, and test mobile layout and active
language switching. Telegram price-save/outbox wiring, transactional publication,
60-second latency and actual owner notifications are outside this pure renderer.

FINAL v5.0 Preview Gate is not closed by this package. The original partial
fixtures contain one real full vehicle card and an 18-item catalog. The current
capture additionally exercises all 36 full-card copies and both catalogs against
their capture-manifest hashes, plus the current stage-only homepage and the
distinct stale legacy homepage. The real `ua-site-languages.js` and
`i18n.js` scripts must be exercised in a browser; static translation-attribute
tests do not establish working language switching. The current homepage routing
must remain explicit: the current public `video/index.html` contains stage tiles,
whereas `stranica.sobrat_glavnuyu` builds individual vehicle tiles. A patched
function is not evidence that the production homepage calls it. Complete Preview coverage,
fresh source/DB binding and deployment gates remain required.

## Read-only snapshot audit

`python -B audit_snapshot.py --root /home/Carix` reads the three pinned generator
sources, published CRM price fields, every published full card and both catalogs
under `video/` and `site/`. It builds candidates only in memory and emits JSON to
stdout. `audit_snapshot(Path(root))` exposes the same report to a reviewed caller.
The script itself does not save the report or candidates. The DB connection uses
`mode=ro`, `query_only` and a SQL authorizer; only six published-car fields are
selected. Their fingerprint is compared through separate before/after connections.
This is not a complete protected-DB-row comparison or a server-wide writer lock.

The HTML manifest covers root-level HTML plus recursive `video/` and `site/` HTML.
Every captured hash is checked again after in-memory migration; new, missing,
unreadable or drifting files fail. Sources also receive a final hash check.
Missing current homepage/browser/full-chain/full-row acceptance is explicit in
the report. The CLI exits 1 because those mandatory Preview checks remain open,
even when all snapshot checks pass. It cannot authorize Production.
