# TASK 098 — UA-ART-EDITORIAL-ATLAS-NEWS-001 v2.0 QA REPAIR
## Cross-check, evidence chronology repair, live SEO evidence completion, and specification hardening

## Owner authorization inherited from the active initiative

The owner approved the Editorial Atlas initiative with the command **«Запускай 🍀»**. TASK 097 completed only stages 0–2 and produced a read-only audit package. This task is a strict QA/correction pass over that package. It does not advance to SANDBOX and does not create any public news functionality.

**PRODUCTION — ТОЛЬКО ПО ОТДЕЛЬНОЙ КОМАНДЕ.**

## Absolute prohibitions

- production write: prohibited;
- CRM write: prohibited;
- catalog/card write: prohibited;
- PythonAnywhere/Cloudflare/public-site write: prohibited;
- public news route creation: prohibited;
- autopilot/autopublication enablement: prohibited;
- database creation or DDL execution: prohibited;
- change outside `cloud/`: prohibited;
- bypassing robots, login, paywall, WAF or CAPTCHA: prohibited.

The only allowed external operations are bounded, public, read-only HTTP GET requests made by the workflow before Claude runs. Claude itself must use only the attached evidence.

## Fixed checkpoints

- Original pre-launch checkpoint: `18491a4f83822c0385606b0406da2bae983b89ef`
- Original backup: `backup/editorial-atlas-news-001-prelaunch-20260830`
- TASK 097 result commit: `0f603908dbd290a6b3a4d9c8e348554c69d42c8f`
- QA backup: `backup/editorial-atlas-news-001-post-audit-pre-qa-20260830`

## Why this QA task exists

ChatGPT performed a post-generation cross-check and found concrete defects that must be repaired before any future SANDBOX approval:

1. `evidence.json.generated_at_utc` says `2026-08-30T17:00:00Z`, while the actual TASK 097 result commit is timestamped earlier (`2026-08-30T16:49:39Z`). Evidence chronology must never contain an invented future time.
2. `dedup_scoring_autopilot.md` defines `IMAGE_RIGHTS_CONFIDENCE` as numeric 0–100, but later compares it with the text value `CONFIRMED`. The type contract is inconsistent.
3. `data_model_pipeline.md` presents PostgreSQL-specific types (`TIMESTAMPTZ`, `JSONB`) without naming an engine, while the repository context is heavily SQLite-oriented. It also places a foreign-key reference to `news_stories` before the referenced table in the shown DDL, and includes `NULL` inside an `IN (...)` check for `approval_queue.owner_action`. The schema must be executable in a clearly selected future SANDBOX engine and internally coherent.
4. The publication model describes an atomic database flip but not the atomic promotion of two rendered language pages plus feed/sitemap artifacts. Database atomicity alone is insufficient for static-file publication.
5. TASK 097 confirmed only HTTP 200 for the live `robots.txt` and `sitemap.xml` but did not capture their literal contents. It also did not capture response headers and HTML robots/hreflang tags reliably.
6. The source report states 46 normal responses and 24 blocked/error/unusual responses, but the consolidated acceptance text shows only a partial parenthetical subset. The QA package must contain a complete, machine-derived list of all 24.
7. Redirect anomalies for KR-01, KR-08, EU-05 and KR-10 need a second bounded probe and precise classification. A redirect alone does not prove authenticity.

## Required corrections

### A. Evidence chronology and provenance

Correct `cloud/task_097_editorial_atlas_news/evidence.json`:

- set `generated_at_utc` to the exact workflow-supplied `QA_STARTED_AT_UTC` only if that field is being used as the correction-generation time;
- preserve the original fact that TASK 097 output was committed at `2026-08-30T16:49:39Z` in a new field such as `task097_result_commit_at_utc`;
- add `evidence_corrections` as an append-only array with the original erroneous value, corrected value, reason, QA task ID and QA timestamp;
- never silently overwrite the defect;
- preserve all false safety booleans;
- add references to the new QA evidence files;
- retain `source_probe_rows = 70` and exact geo counts.

Create a separate `cloud/task_098_editorial_atlas_qa/evidence_qa.json` recording:

- task ID and input/output commit checkpoints;
- workflow QA timestamp;
- files inspected and corrected;
- live SEO probe rows;
- redirect probe rows;
- complete 24-source non-normal list;
- `production_touched=false`, `crm_touched=false`, `catalog_touched=false`, `public_files_touched=false`, `autopublication_enabled=false`;
- all remaining PENDING checks.

### B. Image-rights contract

Correct `cloud/task_097_editorial_atlas_news/dedup_scoring_autopilot.md` so the future model has two explicit fields:

- `IMAGE_RIGHTS_STATUS` enum: `UNKNOWN | OWNED | LICENSED | REUSABLE | PROHIBITED`;
- `IMAGE_RIGHTS_CONFIDENCE` numeric 0–100 describing confidence in the documented status.

Future autopilot eligibility must require:

- `IMAGE_RIGHTS_STATUS IN ('OWNED','LICENSED','REUSABLE')`;
- `IMAGE_RIGHTS_CONFIDENCE >= 95`;
- a durable rights-evidence reference for the specific asset.

No string/numeric type mismatch may remain. An article may publish without a hero image only if the future design has a sanctioned owned fallback illustration; it must never use an unverified source image.

### C. Data model and executable future SANDBOX contract

Correct `cloud/task_097_editorial_atlas_news/data_model_pipeline.md`:

1. Explicitly select **a separate SQLite 3 database file for the first SANDBOX**, because the observed repository context is SQLite-oriented. State that this is a SANDBOX decision only; a future PostgreSQL migration would require a separate migration specification.
2. Provide SQLite-compatible DDL or clear engine-neutral logical schema plus a complete SQLite DDL appendix.
3. Use ISO-8601 UTC text timestamps or another explicitly SQLite-compatible representation; no unexplained `TIMESTAMPTZ` or `JSONB`.
4. Start with `PRAGMA foreign_keys = ON;`, define journal/timeout guidance, and create referenced tables before referencing tables.
5. Remove `NULL` from `CHECK (owner_action IN (...))`; the column itself may be nullable.
6. Add a durable neutral fact-card model (`story_fact_cards` or equivalent) with versioning and source attribution so UA/RU are generated from the same facts.
7. Add an image-assets/rights table with the two corrected rights fields and evidence URI/hash.
8. Add a durable publication outbox/manifest so bilingual page generation, feed generation and sitemap promotion can be coordinated.
9. Specify atomic publication across filesystem artifacts:
   - render both UA/RU pages and metadata into a private staging directory;
   - validate both;
   - prepare a publication manifest;
   - atomically promote a versioned release pointer/directory;
   - regenerate RSS/news-sitemap from committed DB state;
   - on any failure, keep the old release pointer and neither new language URL public;
   - idempotency key prevents duplicate promotion.
10. Keep the database, lock, queue and publication directory separate from CRM/catalog.
11. Do not execute DDL.

### D. Live SEO evidence completion

Use the workflow-attached evidence to correct `cloud/task_097_editorial_atlas_news/seo_routing_audit.md` and create `cloud/task_098_editorial_atlas_qa/live_seo_evidence.md`.

For each requested live URL, report requested URL, HTTP status, final URL, content type, selected headers, title, canonical, meta robots, hreflang links and error:

- `https://www.uaart.com.ua/`
- `https://uaart.com.ua/`
- `https://www.uaart.com.ua/video/index.html`
- `https://www.uaart.com.ua/video/podbor.html`
- `https://www.uaart.com.ua/robots.txt`
- `https://www.uaart.com.ua/sitemap.xml`

The workflow also attaches bounded literal bodies/excerpts of `robots.txt` and `sitemap.xml`. Classify findings as VERIFIED/PENDING; do not infer absence from an empty extractor field. Do not modify either file.

### E. Redirect/domain anomaly QA

Use the workflow-attached second probe and create a precise table in `cloud/task_098_editorial_atlas_qa/redirect_domain_qa.md` for:

- `https://www.motie.go.kr/`
- `https://www.motir.go.kr/`
- `https://english.motir.go.kr/`
- `https://koreajoongangdaily.joins.com/`
- `https://www.koreajoongangdaily.com/`
- `https://europe.autonews.com/`
- `https://www.autonews.com/europe/`
- `https://www.hyundaimotorgroup.com/news/`
- `https://www.hyundaimotorgroup.com/en/news/`

Report redirect chain/final URL/status/title/canonical/TLS host and classify:

- VERIFIED_REACHABLE;
- VERIFIED_REDIRECT;
- PENDING_AUTHENTICITY;
- REPLACE_CANDIDATE;
- REJECT.

Reachability and a redirect are not proof of official authenticity. Preserve PENDING where human/official confirmation is still required.

### F. Complete non-normal source list and acceptance QA

Create `cloud/task_098_editorial_atlas_qa/source_probe_qa.md` from the attached original 70-row TSV:

- exact count by geo;
- exact count by HTTP status/error class;
- complete list of all 24 rows not returning a numeric status below 400;
- exact count by TASK 097 decision (`APPROVE_MVP`, `APPROVE_LATER`, `MANUAL_ONLY`, `PENDING`, `REPLACE`, `REJECT`);
- identify any row whose decision conflicts with its explanation;
- do not change the fixed 70-source pool without an explicit documented correction.

Correct `cloud/task_097_editorial_atlas_news/report.md` if its wording could be read as a complete list when it is only an example subset.

### G. QA review of the rest of the package

Cross-check all TASK 097 files for internal consistency. At minimum verify:

- 15 MVP IDs are identical across CSV, source report and consolidated report;
- manual mode remains the only enabled future mode;
- autopilot remains unbuilt/off;
- no design component implies live tracking or unsupported numeric certainty;
- sitemap, canonical and hreflang recommendations remain recommendations only;
- production/CRM/catalog boundaries are consistent;
- no file claims code was deployed.

Document findings and corrections in `cloud/task_098_editorial_atlas_qa/qa_report.md`.

## Deliverables

Create/update all files below:

1. `cloud/task_097_editorial_atlas_news/evidence.json`
2. `cloud/task_097_editorial_atlas_news/dedup_scoring_autopilot.md`
3. `cloud/task_097_editorial_atlas_news/data_model_pipeline.md`
4. `cloud/task_097_editorial_atlas_news/seo_routing_audit.md`
5. `cloud/task_097_editorial_atlas_news/report.md`
6. `cloud/task_098_editorial_atlas_qa/README.md`
7. `cloud/task_098_editorial_atlas_qa/evidence_qa.json`
8. `cloud/task_098_editorial_atlas_qa/live_seo_evidence.md`
9. `cloud/task_098_editorial_atlas_qa/redirect_domain_qa.md`
10. `cloud/task_098_editorial_atlas_qa/source_probe_qa.md`
11. `cloud/task_098_editorial_atlas_qa/qa_report.md`
12. `cloud/latest_status.md`
13. `cloud/owner_reply.md`

## Acceptance criteria

PASS only if:

- all 13 deliverables exist and are non-empty;
- evidence chronology is plausible and correction history is explicit;
- no future timestamp remains for the TASK 097 commit event;
- image-rights fields and gate are type-consistent;
- SQLite SANDBOX DDL is syntactically coherent, ordered and explicitly non-executed;
- owner_action CHECK is corrected;
- neutral fact-card, image rights and publication outbox are represented;
- filesystem/publication atomicity is specified beyond a DB transaction;
- live SEO evidence is reported without a site write;
- all 24 non-normal source rows are listed;
- all safety booleans are false;
- `PRODUCTION_TOUCHED: NO`;
- owner action is not required;
- next step remains a separately approved Stage 3 SANDBOX only.

## Status format

`cloud/latest_status.md` must contain:

- `TASK_ID: task_098`
- `CLAUDE_STATUS: DONE | BLOCKED | WAITING_OWNER`
- `PRODUCTION_TOUCHED: NO`
- `OWNER_ACTION_REQUIRED: NO` when QA is complete;
- the actual corrected/created file list;
- the exact workflow QA timestamp markers;
- MEMORY_VERSION_READ and CONTEXT_BUNDLE_SHA256.

`cloud/owner_reply.md` must give the owner a concise Russian summary: original TASK 097 passed, QA found and corrected the evidence timestamp, image-rights type contract, SQLite/data/publication model, completed the live SEO and redirect probes, and still did not touch production/CRM/catalog.
