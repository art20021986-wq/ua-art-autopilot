# Read-only audit — current repository and site architecture

Evidence discipline: VERIFIED (from the attached machine inventory / probe tables), INFERRED (reasonable derivation), PENDING (unknown, needs live check).

## 1. Purpose of this repository and the Cloud protocol

- **VERIFIED.** `CLAUDE.md` and `README.md` define this repository as the communication bridge between the owner, ChatGPT/Codex, and the Cloud/Claude worker, with PythonAnywhere as the eventual execution target. All Cloud deliverables must live under `cloud/`, plus the two shared status files `cloud/latest_status.md` and `cloud/owner_reply.md`.
- **VERIFIED.** `.github/workflows/claude_autopilot.yml` runs the Cloud worker on `workflow_dispatch`, commits only paths under `cloud/`, and rebases onto `main` with a narrow, fail-closed conflict-resolution rule limited to the two shared status files.
- **VERIFIED.** `docs/pythonanywhere_autosync.md` describes a *separate* automatic sync step that copies `cloud/**` files into a **safe, non-executing inbox** at `/home/Carix/autopilot_inbox/`. It explicitly does **not** execute Cloud-produced code, does **not** overwrite `master_card.py`/`stranica.py`/CRM files, and does **not** reload the web app. Production execution is a distinct, gated step outside this repository's automatic path.

## 2. Current task/workflow/controller contour

- **VERIFIED.** The bounded file inventory lists over 90 `.github/workflows/task*.yml` files (task037 through task097), each tied to one numbered task. The naming convention is `taskNNN_<name>.yml`.
- **VERIFIED.** Nearly every `cloud/task_NNN_*/` folder follows the same recurring pattern: a `controller.py` (or `gate_a*.py`/`gate_b*.py`), a `remote_installer.py` or `patcher.py`, a `postcheck.py`, an `evidence/*.json` folder, and a Markdown report. This is a consistent **Gate A (read-only/dry-run) → Gate B (guarded write)** pattern used across the whole history of the repository.
- **INFERRED.** This Gate A/B pattern is the established safe-change discipline for this repository. Any future NEWS-module code should follow the same pattern (dry-run Gate A, then an explicit, separately-approved Gate B) rather than inventing a new mechanism.
- **VERIFIED.** `cloud/shared_memory/` holds a canonical, append-only JSONL memory (`records.jsonl`) with `OWNER_DIRECTIVE`, `RESULT`, `HYPOTHESIS`, and `TASK` record classes, a `manifest.json`, and generator/verifier scripts. The attached `MEMORY_VERSION_READ=4` and `CONTEXT_BUNDLE_SHA256` in this task's machine context correspond to this mechanism.
- **VERIFIED.** The current canonical memory bundle states `ua0009_safe_to_publish: NO`, `production_write: NO`, `crm_write: NO`, `gate_a_executed: NO`. This is an **unrelated** open item (UA-0009 card publication) from earlier tasks; it is not part of TASK 097's scope, but it confirms the general pattern that publication readiness must be proven with real Gate A evidence, not assumed — the same discipline this task applies to the future NEWS module.

## 3. CRM / catalog intersection points that must never be reused for NEWS

- **VERIFIED (by filename presence only, not content).** The inventory shows many CRM/catalog-related modules referenced across tasks, e.g. `cars_ui_transform.py`, `sqlite_ownership.py`, `safe_writer.py`, `singleton_guard.py`, `cross_process_lock.py` under `cloud/crm_speed_optimization/`, plus catalog-guard and publish-transaction modules under `cloud/task_082_*`, `cloud/task_083_*`, `cloud/task_090_*`. Their *contents* were not re-read in this task (out of scope for a read-only architecture note); only their *existence and naming* is VERIFIED from the inventory.
- **INFERRED.** These modules implement CRM/catalog concurrency control, SQLite ownership, and publish-transaction guarantees for cars/cards. A future NEWS module must not import, patch, or share a runtime/process/lock/queue with any of these. It must have its own DB (or its own tables in a clearly separate namespace), its own lock, and its own queue.
- **VERIFIED.** `docs/pythonanywhere_autosync.md` explicitly names `master_card.py` and `stranica.py` as protected production files that Cloud automation must never overwrite. This constraint is repeated in TASK 097's own instructions and is treated here as an absolute boundary for any future NEWS installer as well.
- **PENDING.** The actual current schema of the live CRM/catalog database (SQLite or otherwise), its table names, and whether any table name could collide with a proposed `news_*` table name were not inspected in this task (no filesystem or DB access was performed). This must be confirmed once a SANDBOX gate with real controller access is opened, before any table is created even in a sandbox DB copy.

## 4. Where the future NEWS module must be isolated

- **INFERRED / recommended boundary** (not yet built):
 - A dedicated top-level path (documentation/artifact only for now — no code deployed), separate from the CRM/catalog runtime, e.g. a distinct process, distinct working directory, and a distinct SQLite file or distinct schema/namespace if sharing an RDBMS instance is ever considered later.
 - A distinct workflow file class `task_097_*` / future `news_*` workflows, never reusing `claude_autopilot.yml`'s concurrency group or any CRM-bot/client-bot workflow's triggers.
 - A distinct queue and distinct lock file/table, never the CRM's `cross_process_lock.py`/`sqlite_ownership.py` singleton.
 - A distinct "kill switch" flag (see `sandbox_implementation_plan.md`) that cannot be flipped by, or interfere with, any CRM/catalog flag.

## 5. SEO/route risk snapshot (see `seo_routing_audit.md` for full detail)

- **VERIFIED** (from the attached public-route probe): the public homepage `https://www.uaart.com.ua/` and `https://uaart.com.ua/` both resolve (HTTP 200) but the *final URL and self-canonical* is `https://www.uaart.com.ua/video/index.html` — i.e., the live homepage content currently lives under a `/video/` path segment.
- **PENDING.** The literal body of `robots.txt` and `sitemap.xml` (both HTTP 200) was not enumerated in the attached evidence — only their HTTP status was probed, not their content. Whether any draft/preview/`noindex` route is currently exposed in `sitemap.xml` is **PENDING**, not confirmed absent.
- **PENDING.** Whether the homepage or `/video/podbor.html` currently emits an HTML `<meta name="robots">` tag was not captured by the probe columns (they were left blank in the evidence, which this audit treats as "not captured", not as "absent").

## 6. Rollback / idempotency / retry / dead-letter / kill-switch requirements (for the future module)

- **Rollback:** every future NEWS deployment step must be a reversible Git commit plus an explicit feature flag; no direct hand-edit of a live file without a corresponding installer+rollback pair, mirroring the existing Gate A/B convention observed across the repository.
- **Idempotency:** every ingestion/dedup/publish step must be safely re-runnable without side effects (natural keys, `ON CONFLICT DO NOTHING`/upsert semantics) — detailed in `data_model_pipeline.md`.
- **Retry:** bounded retry with exponential backoff and a maximum attempt count; anything exceeding the bound goes to a dead-letter table, never an infinite loop (see `risk_register.md`).
- **Dead-letter:** a durable `failed_jobs`/`dead_letter` table, never a silent drop.
- **Kill switch:** a single, explicit, owner-controlled boolean that, when OFF, guarantees zero autonomous publication (manual mode remains available); detailed in `sandbox_implementation_plan.md`.

## 7. Summary judgement for Stage 1

The repository's established safety pattern (Gate A/B, task-numbered isolation, `cloud/`-only writes, safe-inbox-only sync) is compatible with adding a fully isolated NEWS module later, provided the module (a) never shares a DB file, table, lock, or queue with CRM/catalog code, (b) never reuses a protected production filename, and (c) goes through its own Gate A (dry-run/sandbox) before any Gate B (guarded write) — which itself remains subject to a separate owner approval, exactly as this task requires.
