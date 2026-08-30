# TASK 095 — CATALOG-VISUAL-ACCEPTANCE-REPAIR-095 v1.0

## Owner directive and authorization

The owner has already approved the bounded restoration of the previous UA ART web design and the full GitHub/Cloud autopilot route. On 2026-08-30 at 10:18 GMT+7 the owner supplied a fresh mobile screenshot showing a critical live regression: the catalog page renders the UA ART header and footer, but the automobile cards, catalog heading and stage controls are not visible.

This is **not an accepted result**. It is a continuation of the previously approved TASK 090 / UA-WEB-DESIGN-ROLLBACK-035 scope.

## Confirmed discrepancy

TASK 090 machine evidence reported 13 `<article class="catalog-card">` nodes and PASS, but the actual mobile browser shows zero visible cards. Therefore the previous verifier produced a false PASS because it checked source DOM markers only and did not verify rendered visibility, usable viewport layout or image loading.

## Priority

P0 / CRITICAL / immediate.

## Required execution

1. Perform a read-only, browser-rendered diagnostic of the public catalog with a cache-buster.
2. Capture mobile viewport 390x844 and desktop viewport 1440x1000 evidence.
3. For every catalog card record computed `display`, `visibility`, `opacity`, bounding rectangle, hidden ancestors, active filter state, and image `complete/naturalWidth/currentSrc`.
4. Identify the exact CSS/JavaScript/markup cause of the invisible cards and missing catalog content.
5. Repair only the catalog presentation layer and its visibility/filter/image wiring.
6. Preserve exactly 13 published automobiles and stage counts 13 / 3 / 1 / 7 / 2.
7. Do not modify CRM rows, SQLite, VIN, prices, descriptions, photos, videos or card IDs.
8. Before production: backup the current catalog targets and runtime files; use the shared production lock.
9. Apply an atomic bounded repair only after shadow/browser PASS.
10. Add a mandatory browser-rendered acceptance gate so DOM-only PASS is impossible in future.
11. Verify mobile and desktop twice, including visible cards > 0, visible filters, scrollable card region, no horizontal overflow, and all 13 main images loaded or an explicit valid fallback.
12. On any failure: automatic rollback and factual FAIL report.

## Acceptance criteria

- The catalog heading, five stage filters and all 13 cards are visible and usable in a real browser.
- Mobile screenshot is not header/footer-only.
- Visible card count on default `all` filter is exactly 13.
- Each stage filter shows the exact expected visible count.
- Broken main images: 0.
- Horizontal overflow: 0.
- CRM/media/database writes: 0.
- Immediate and delayed browser-rendered verification: PASS.

## Status reporting

Report factual checkpoints only: DIAGNOSTIC → ROOT CAUSE → SHADOW PASS → BACKUP → ATOMIC REPAIR → MOBILE PASS → DESKTOP PASS → DELAYED PASS / ROLLBACK.
