# Test Matrix — TASK 101 (to be executed only in a future Sandbox task)

Status: SPECIFICATION ONLY. No test in this document has been executed against a live system in this task. All rows are PENDING until run in Sandbox with real evidence attached.

## 1. Language × Country coverage (RU/UA/GE × 8 countries)

| # | Language | Country code | Homepage link works | podbor.html loads 5 correct models | Form submits with correct `lang`+`s` | Result |
|---|---|---|---|---|---|---|
| 1 | ru | korea | PENDING | PENDING | PENDING | PENDING |
| 2 | ru | japan | PENDING | PENDING | PENDING | PENDING |
| 3 | ru | usa | PENDING | PENDING | PENDING | PENDING |
| 4 | ru | europe | PENDING | PENDING | PENDING | PENDING |
| 5 | ru | china | PENDING | PENDING | PENDING | PENDING |
| 6 | ru | canada | PENDING | PENDING | PENDING | PENDING |
| 7 | ru | uae | PENDING | PENDING | PENDING | PENDING |
| 8 | ru | georgia | PENDING | PENDING | PENDING | PENDING |
| 9 | uk | korea..georgia (8 rows) | PENDING | PENDING | PENDING | PENDING |
| 10 | ka | korea..georgia (8 rows) | PENDING | PENDING | PENDING | PENDING |

(Full matrix = 3 languages × 8 countries = 24 combinations, each with 3 checks above; expand rows 9-10 into 8 rows each when executed.)

## 2. Viewport / device coverage

| Width | Device class | 4x2 grid intact, no h-scroll | 44px min touch targets | WhatsApp widget not overlapping | Result |
|---|---|---|---|---|---|
| 360px | mobile | PENDING | PENDING | PENDING | PENDING |
| 375px | mobile (iPhone SE class) | PENDING | PENDING | PENDING | PENDING |
| 390px | mobile (iPhone 12/13/14) | PENDING | PENDING | PENDING | PENDING |
| 430px | mobile (iPhone Pro Max) | PENDING | PENDING | PENDING | PENDING |
| 768px | tablet | PENDING | PENDING | PENDING | PENDING |
| 1024px | tablet landscape / small laptop | PENDING | PENDING | PENDING | PENDING |
| 1440px | desktop | PENDING | PENDING | PENDING | PENDING |
| iPhone Safari (real device) | mobile Safari specific | PENDING | PENDING | PENDING | PENDING |

## 3. 16-card integrity (card guard)

| Check | Method | Result |
|---|---|---|
| All 16 IDs UA-0001..UA-0016 present BEFORE == present AFTER | card_guard_manifest.schema.json comparison | PENDING |
| VIN unchanged per card | hash compare | PENDING |
| Price unchanged per card | value compare | PENDING |
| Mileage/engine/stage unchanged per card | value compare | PENDING |
| Photo/video count unchanged per card | count compare | PENDING |
| Media hashes unchanged per card, order preserved | SHA-256 compare | PENDING |
| CTA present per card | boolean check | PENDING |
| Diagnostic/VIN/container links unchanged | value compare | PENDING |
| Public URL HTTP 200 for all 16 AFTER | HTTP GET | PENDING |
| Dedicated UA-0009 SAFE CHECK gate | manual + field diff | PENDING — must read PASS explicitly before any publish per REC-0005 |

## 4. Homepage counters (source-of-truth)

| Check | Result |
|---|---|
| Server-rendered HTML (no JS) shows correct total (matching live catalog count, not hardcoded 13) | PENDING |
| Server-rendered stage breakdown matches live catalog (not hardcoded 3/1/7/2) | PENDING |
| Adding a hypothetical UA-0017 in catalog data updates homepage counters without further code edits (regression-proof test) | PENDING |
| No new hardcoded literal count introduced in template | PENDING — verify via code review, not just visual check |

## 5. WhatsApp / Telegram / WebApp / CRM contract

| Check | Result |
|---|---|
| Existing 5 country codes still submit successfully via Telegram WebApp | PENDING |
| New 3 country codes (canada, uae, georgia) submit successfully | PENDING |
| `z_canada`, `z_uae`, `z_georgia` deep-links resolve correctly | PENDING |
| Old deep-links (`z_korea` etc.) still resolve correctly | PENDING |
| Georgian UTF-8 text in free-text field not truncated/corrupted end-to-end | PENDING |
| Exactly one CRM entry created per submission (no duplicates) | PENDING |
| Country (order_country) never confused with delivery stage (catalog_stage) in payload | PENDING |

## 6. Accessibility / UX

| Check | Result |
|---|---|
| Country items have visible focus state (keyboard nav) | PENDING |
| Country items have hover state (desktop) | PENDING |
| Country items have active/pressed state | PENDING |
| Minimum 44px height for all 8 country controls | PENDING |
| aria labels present and localized in ru/uk/ka | PENDING |
| Two-line country names do not break 4x2 grid | PENDING |

## 7. Sign-off condition

This matrix converts from PENDING to PASS/FAIL only after execution in a dedicated Sandbox task with attached machine evidence (screenshots, HTTP responses, hash diffs). No row may be marked PASS in this document without that evidence.
