# TASK088 Stage 3 renderer candidate

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
Captions match the owner policy: Ukraine includes delivery to Kyiv, Ukrainian
customs and certification; Georgia includes delivery to AUTOPAPA parking №16,
and excludes Georgian customs.

`patch_yadro.patch_yadro(bytes)` and `patch_stranica.patch_stranica(bytes)` return
candidate bytes plus provenance. They never import or execute their target
modules, and never write files. Full input SHA256 and AST-selected original price
statements must match. They replace only the base price statements (plus the old
unqualified “доплат нет” caption in the same price slot) and add the renderer
import. Price-related catalog headings/meta descriptions now distinguish Ukraine
and Georgia rather than claiming every amount includes delivery to Kyiv. Existing
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

40 tests pass with the private generator/master/catalog/HTML snapshots supplied.
Without private snapshots, 16 exact-source tests are explicitly skipped; this is
not equivalent evidence.

The exact-source tests extract only named base renderer AST functions, execute
them with controlled dependencies, and compare before/after results for 18 synthetic
car rows spanning four stages and an 18-item catalog in both generators. No real
CRM rows are read or represented as acceptance evidence. Restoring the original price fragment
and the explicitly scoped catalog price heading produces a byte-identical complete
document. Card identifiers, images, description,
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
