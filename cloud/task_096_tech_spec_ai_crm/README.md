# TASK 096 — TECH-SPEC-AI-CRM-017 v3.0 — Sandbox Package

Status: SANDBOX PACKAGE ONLY. No production or CRM write occurred. No live network calls were made by Claude/Cloud in this delivery (this execution environment has no filesystem access to the real CRM SQLite file and no outbound network access). All artifacts below are ready for the owner-approved controller/PythonAnywhere runner to execute against a **copy** of the CRM database, per the BACKUP → SANDBOX → CANARY → REPORT sequence.

## Scope actually performed by Claude/Cloud in this round
- Designed the sandbox schema for "Дополнительная спецификация" (additional specification).
- Implemented deterministic, offline-testable Python tools for:
  - semantic deduplication against primary CRM fields and existing additional-spec rows;
  - protection of manually entered CRM fields (primary fields are read-only from this pipeline);
  - hard exclusion of purchase/auction/wholesale cost fields (never extracted, stored, logged, or displayed).
- Produced a non-public HTML canary fragment (`canary_preview.html`) demonstrating the new block, marked `noindex` and not linked from any public path.
- Prepared a source-availability checklist for the two approved reference sources (Automobile-Catalog, Auto-Data). Actual HTTP reachability was **not** tested here because this delivery environment has no outbound network access — the checklist and script are provided for the controller to run.
- Wrote a synthetic self-test harness (`selftest.py`) that builds an in-memory SQLite database shaped like UA-0001…UA-0016 and exercises the dedup/protection/price-exclusion logic end to end. This harness was **not executed by Claude in this delivery** (no code-execution capability in this response channel); it is delivered for the controller to run and attach real results to the evidence file.

## What was NOT done (by design / by hard prohibition)
- No read of the real CRM SQLite file (ro-mode or otherwise) — Claude/Cloud has no filesystem path to it in this environment.
- No backup copy was created by Claude/Cloud; the backup step must be performed by the controller/owner-run process with actual access to `/home/Carix/...`.
- No write to any real CRM database, `/home/Carix/video`, `/home/Carix/site`, or any public path.
- No code/config change to CRM bot, client bot, generator, or publication pipeline.
- No service restart, no autopublication.
- No purchase/auction/wholesale price value was requested, computed, or displayed anywhere in these artifacts.

## How the controller should use this package
1. Run `PRAGMA query_only=ON;` open of the live CRM DB (`mode=ro`) and copy it to the closed TASK 096 folder as instructed by the task.
2. Point `selftest.py` and `dedup_check.py` at the **sandbox copy only**.
3. Apply `schema_additional_spec.sql` to the sandbox copy (never to production).
4. Run `source_check.py` from an environment with internet access to confirm both approved sources are reachable.
5. Attach real command output to `evidence.json` (replace the `PENDING_CONTROLLER_EXECUTION` placeholders) and finalize `report.md`.
6. Production write requires a separate explicit owner command; this package does not authorize it.
