# UA-ART-GE-UA-MARKET-PRICE-001 v3.1 FINAL REVISED

Status: APPROVED FOR PREVIEW/GATE B ONLY. PRODUCTION FROZEN.

## Scope
1. CRM Edit Data: visually relabel existing Price as `Цена Украины` without changing its backend key or existing values.
2. Add independent optional `Цена Грузии` field (`price_georgia` or schema-safe equivalent after audit).
3. Georgia price is owner-entered only; no automatic calculation/copy/fallback.
4. Public UA/GE market logic is allowed only before Ukraine: Korea / Ferry / Georgia.
5. Kyiv/Ukraine public cards remain unchanged.
6. If Georgia price is empty/unavailable, preserve legacy public-card behavior and do not render a Georgia offer.
7. Georgia conditions: without re-export; delivery to AutoPapa, parking 16. Logo requires separate owner approval before any Production use.

## Hard invariants / no-touch
Do not change additional specification, VIN/VIN checks, photos, video, diagnostics, container/tracking, CTA/deposit, ETA/days, stage engine, counters, catalog/home behavior, URLs, languages, SEO/canonical/robots/sitemap, ads or third-party content.

## Safety
Separate branch only. No Production writes. Before implementation, audit actual CRM schema, price read/write paths, publisher/card renderer and stage normalization. New feature must fail closed to legacy behavior. No manual per-card HTML prices.

## Gate A CRM
- Existing price values unchanged
- Existing backend price key unchanged
- UI label Price -> Цена Украины
- Independent Georgia field write/read-back
- UA/GE fields independent
- Empty GE allowed
- Publishing without GE remains valid

## Gate B Preview
Preview: Korea, Ferry, Georgia, Kyiv. Kyiv must be unchanged. Regression: CRM, site, additional spec, VIN, media, container/tracking, stages, counters, Safari/Chrome/TikTok, 404/500, rollback readiness.

Production requires a separate explicit owner command after Gate B.