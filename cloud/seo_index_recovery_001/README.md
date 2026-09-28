# UA ART SEO index recovery 001

Installed 27 September 2026, with public verification at 16:15 UTC.

The site returned redirects for missing pages, offered an obsolete second sitemap,
and omitted descriptions and photo alt text from car cards. This release fixes
those defects in the existing publication path, using only Python standard libraries.

## Runtime responsibilities

- `ua_seo_metadata.py`: deterministic HTML metadata and limited semantic edits;
  reads the rendered CRM facts, preserves scripts/forms/media/business attributes.
- `ua_seo_sitemap.py`: derives canonical URLs from the published catalog; the root
  route and legacy static sitemap share the same generator.
- `candidate_builder.py`: hash-guarded edits to existing generator/write functions
  and the original WSGI fallback. Existing wrappers stay in the same order.
- `deploy.py`: previews changes, backs up exact files, checks drift, uses the existing
  publication locks, applies atomic file writes and supports guarded rollback.

No new recurrent repair task, library, external service, CRM migration or price change.
The catalog golden template receives the same head-only SEO changes so its existing
layout guard continues to validate the output without relaxing that guard.

## Validation and production state

Five unit tests passed locally and on production Python 3.10. Complete before/after
checks passed for 49 HTML files (26 public pages plus 23 catalog/card copies).
`public_verification.json` records HTTP 200 and unique title/description/canonical
for all 26 public URLs, identical 26-entry maps, the root 301 and an unknown-page 404.
736 gallery img elements now have descriptive alt; 22 empty lightbox image templates
were left intact. No full browser mobile emulation was performed.

A real publisher dry-run for UA-0021 returned success without changing production
files. Post-install hashes matched all 59 release files. The normal always-on CRM
process was paused for installation and returned to Running.

## Deployment record

Production directory: `/home/Carix/seo_20260927/package_v3/`.
Plan and backups: `release/plan.json`, `release/before/`, `release/after/`.
Plan SHA-256: `2c38372b1a69bdf8fe37d4fc311d932d9c48f413a39ce13b787a48b24edb73a4`.

This repository package records an already installed release. Do not rerun prepare
against changed production sources. The source hashes intentionally reject drift.
To roll back, pause the existing CRM task, run `deploy.py rollback` in the deployed
package, resume the task and verify the web app. It refuses concurrent file changes.
New unreferenced pure modules remain on disk after rollback.

## Open external items

The separate `uaart.com.ua` apex host still returns 404 for internal paths. Its own
hosting must permanently redirect to `https://www.uaart.com.ua`, preserving path
and query; the accessible PythonAnywhere www webapp does not own that host.
Google Search Console access was not available, so no sitemap submission or URL
index request is claimed. HTTP-to-HTTPS remains the host's existing forced-HTTPS
redirect. Language URL architecture, country landing pages and schema are later work.
