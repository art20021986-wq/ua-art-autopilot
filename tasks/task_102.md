# TASK 102 — SEO-KOREA-KYIV-001 FINAL

Status: OWNER APPROVED FOR EXECUTION.
Issue: #36.

## Objective
Build ONE self-contained executable file `cloud/seo_korea_kyiv_001/seo_korea_kyiv_001.py` that safely performs the approved SEO-KOREA-KYIV-001 release for https://www.uaart.com.ua.

The executable must support the exact sequence:
QUEUE → BACKUP → SANDBOX → VALIDATION → PRODUCTION only after PASS → LIVE VERIFY → FINAL REPORT.

It must be fail-closed, idempotent, atomic where possible, and must auto-rollback every production path changed by this task if post-write validation fails.

## Current live facts that override stale memory
Audit on 2026-08-31 shows CURRENT LIVE CATALOG = 16 published vehicles, not 13. Stage counters currently visible: Kyiv 3, Georgia 1, Ferry 8, Korea 4. Preserve these 16 cards and their stage distribution unless live source has changed by execution time; derive the baseline dynamically from live/local production immediately before writing and preserve it exactly.

Current public root redirects to `/video/index.html`.
Current content roots are `/home/Carix/video` and `/home/Carix/site`.
Existing SEO guard `cloud/seo_rehab_guard_068` is historical reference only; do NOT run it blindly because its expected card set is stale (UA-0001..UA-0010).

## Owner-approved business facts
- Geography: Kyiv + all Ukraine.
- Separate RU and UA SEO pages. One indexable language per page.
- Customer address: Киев, улица Победы 20.
- Telephone: +380992222020.
- WhatsApp: +380992222002.
- Hours: by appointment / at a time convenient for the buyer.
- Deposit: $500 and it is included in the vehicle price.
- Payment: UAH at NBU exchange rate.
- Georgia → Kyiv: approximately 10 days.
- Price: fixed in the contract and does not change.

Do not invent ratings, reviews, customer counts, auction statistics, guaranteed delivery times, discounts, years of experience, or claims such as #1 / best / cheapest / official dealer.

## One-file runtime architecture
The ONE Python file must run in two contexts without external Python packages:
1. GitHub runner mode when `PYTHONANYWHERE_API_TOKEN` exists and filesystem is not `/home/Carix`: upload its own exact bytes to `/home/Carix/uploads/seo_korea_kyiv_001.py`, create a bounded PythonAnywhere execution trigger, wait for a receipt, delete trigger, and verify public URLs independently.
2. PythonAnywhere mode under `/home/Carix`: perform all local backup/sandbox/validation/write/rollback work, write receipt + final report, and on successful completion archive the executable under `/home/Carix/archive/diagnostics/` while leaving no extra root clutter.

Remote trigger must use existing PythonAnywhere API conventions already proven in `cloud/seo_rehab_guard_068/controller.py`. Never expose tokens.

## Production safety scope
MUST NOT alter business data or application logic:
- VINs
- prices
- mileages
- photos
- videos
- diagnostics media/content
- vehicle stage values
- card counts
- CRM data/database
- bot logic
- publication pipeline
- approved mobile card layout
- container tracking
- existing vehicle CTA semantics except a narrowly proven SEO/contact consistency fix that does not affect business state.

Before any production write snapshot hashes and semantic facts for all currently published cards and catalog/home stage counters. After writes, all protected semantic facts must match baseline. Any mismatch = automatic rollback + RELEASE BLOCKED.

## Backup
Create backup outside root clutter at:
`/home/Carix/archive/backups/SEO-KOREA-KYIV-001_<UTC timestamp>/`
Back up every existing production file that may be replaced. Record SHA-256 before and after. New-file paths must be recorded as non-existent baseline so rollback deletes them.

## Sandbox
Render every proposed changed/new file into:
`/home/Carix/archive/sandbox/SEO-KOREA-KYIV-001_<UTC timestamp>/`
No production write before all sandbox gates pass.

## Technical indexability audit and repair
Dynamically inspect actual production and public responses. Verify/repair only within safe task scope:
- canonical URLs
- meta robots/noindex
- sitemap
- robots behavior
- HTTP/canonical consistency for canonical public pages
- homepage strategy for `/` redirecting to `/video/index.html`
- duplicate `/site/` vs `/video/` variants: only `/video/` should be canonical/indexable public variant; `/site/` duplicates must not compete.
- language separation and reciprocal hreflang only when both equivalents exist.

Important: root `/robots.txt` and `/sitemap.xml` must be tested through public HTTPS. If server routing means writing `/home/Carix/video/robots.txt` does not expose root `/robots.txt`, do not guess; record the exact blocker and do not write unsafe WSGI/source changes unless they are provably necessary, backed up, syntax-checked and isolated to SEO routing.

## First SEO landing package
Create strong indexable pages, not thin keyword duplicates. Use clean stable ASCII slugs under canonical `/video/seo/` (or an equally safe existing public scheme discovered at runtime), with separate RU/UA URLs.

Required intent pages:
1. RU hub — H1 `Авто из Кореи в Киев под ключ`
2. UA hub — H1 `Авто з Кореї до Києва під ключ`
3. Kia K5 Korea/Kyiv commercial landing
4. Hyundai Sonata Korea/Kyiv commercial landing

Language architecture requirement: each indexable URL contains one language only. If model pages are provided in both RU and UA, they must be separate URLs. Do not stack RU+UA paragraphs in one document.

Each indexable page must have:
- unique title
- unique meta description
- exactly one clear H1
- useful H2/H3 structure
- self canonical
- html lang
- reciprocal hreflang for valid equivalents
- OG title/description/url if safe
- visible FAQ only if FAQPage JSON-LD is emitted
- no hidden keyword blocks
- mobile readable CSS
- no unnecessary base64 media
- natural internal links
- approved contact/business facts only

## Internal linking
Add a small, visually non-disruptive SEO/navigation block only where safe to current `/video/` pages: homepage, catalog, podbor/order, info/conditions. Do not rewrite card templates merely for linking if that creates regression risk. Add links from relevant K5/Sonata cards only if insertion can be proven semantic-neutral and idempotent; otherwise skip and report.

## Structured data
Where supported by visible content:
- Organization / AutoDealer or LocalBusiness on hub/contact-relevant pages
- BreadcrumbList
- FAQPage only for visible FAQ
Do not fabricate aggregateRating/review/availability/price.

## Content hygiene
In public indexable SEO scope:
- no CRM/editor/service instructions
- no debug text
- no raw technical markup shown as copy
- do not duplicate RU+UA prose on one language page
- use owner-approved Georgia → Kyiv wording: approximately 10 days
- use telephone +380992222020 and WhatsApp +380992222002 correctly on new SEO pages.

Existing public catalog currently exposes mixed RU/UA timing strings and a 15-day Georgia line. Do NOT mass-rewrite protected card/catalog content unless the change can be proven to preserve all card facts and layout. Prefer SEO landings + technical indexability first; if a protected-page wording cleanup is unsafe, report it as a follow-up rather than risking release.

## Sitemap
Generate sitemap from actual current canonical public page inventory, not a hard-coded 10/13-card list. Include all currently published vehicle cards dynamically plus homepage/catalog/podbor/info and new SEO landings. Exclude diagnostics/private/admin/runtime/archive/backup/site-duplicate paths. All listed URLs must be absolute HTTPS and return expected public responses.

## Robots
Preserve crawling of public indexable pages and declare the canonical sitemap URL. Do not block CSS/media needed to render pages. Exclude only genuinely private/runtime paths if applicable.

## Gates
### Gate A Technical
PASS only if robots/sitemap/canonical/meta-robots/indexability and language architecture are valid. If root robots/sitemap routing cannot be safely repaired with proven existing routing, BLOCK production and report exact cause.

### Gate B Content
PASS only if required landing intents exist with unique metadata/H1, one language per page, approved facts only, no debug/CRM content, valid visible structured data relationships.

### Gate C Regression
PASS only if live/protected semantic baseline for all current cards remains identical: card IDs, VINs, prices, stages, counts, media counts/links, diagnostics links, primary business CTA behavior and catalog stage counts. Current expected count from audit is 16 but execution must dynamically verify the actual baseline.

### Gate D Live
After production, fetch every new canonical URL plus homepage/catalog/podbor/info and sampled/all card URLs. Verify 200 where appropriate, canonical, meta, hreflang, internal links, sitemap membership and regression baseline. Perform immediate and delayed verification if practical.

## Rollback
Any production validation failure restores every changed existing file byte-for-byte from backup and deletes every file that did not exist before this task. Re-run live regression after rollback. Report rollback result.

## Final report
Write:
`/home/Carix/archive/reports/SEO_KOREA_KYIV_001_FINAL.txt`
Also write machine-readable receipt under an archive/report location accessible to the GitHub runner through the PythonAnywhere Files API.

Report must include:
- files changed
- backup location
- sandbox location
- production URLs
- title/H1/canonical matrix
- robots result
- sitemap result + URL count
- structured data result
- internal linking result
- regression baseline and post-state
- priority Search Console URL list
- rollback status

Final status exactly one of:
`SEO-KOREA-KYIV-001 PRODUCTION PASS — INDEXABLE — RU/UA SEPARATED — LANDINGS LIVE — REGRESSION 0`
or
`SEO-KOREA-KYIV-001 RELEASE BLOCKED — <exact blocker>`

## Deliverable constraints for Claude
Produce the executable and supporting evidence/documentation only under `cloud/seo_korea_kyiv_001/`. The executable must be the only runtime program required. Do not modify existing production code, workflows, tasks, CRM, site data, or old SEO guard from Claude output. GitHub-side triggering/review will be handled separately after code review.
