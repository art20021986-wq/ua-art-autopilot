# TASK 076 — CRM-ETA-SYNC-GUARD-004 v1.0

## Honesty statement (read first)

This Claude/Cloud sandbox has no network access to the real UA ART CRM
(`crm.db`), no SSH/API access to PythonAnywhere, and no ability to fetch the
live UA-0009/UA-0010/UA-0011 pages. Because of that:

- **Gate A (read-only live audit) has NOT been executed against real
  production/CRM data by this delivery.** No live SHA, no live SQLite
  `quick_check`, no live HTML parse are claimed here. `evidence/gate_a_evidence.md`
  says exactly that and gives a ready-to-run workflow
  (`workflows/gate_a_readonly.yml`) for the controller/owner environment that
  *does* have read-only secrets, mirroring the pattern already accepted for
  TASK 015/019/021 (CODEX_CONTROLLER independently executes and records
  evidence into canonical shared memory).
- **No production or CRM write of any kind has been performed.**
- What *is* delivered here is a complete, self-contained, offline-testable
  **release candidate** implementing the exact contract from the task:
  a single ETA write transaction, mandatory read-back verification, bounded
  rollback, publisher gating on both `/video` and `/site`, a normalized ETA
  object with manual > stage-rule > neutral priority, and description
  sanitation that removes independent stale dates. All logic is generic
  (keyed by `car_id`), so it fixes the class of bug for all current and
  future cards, not a hardcoded list of three IDs.
- Tests run entirely offline against in-memory fixtures
  (`fixtures/mock_crm.py`, `fixtures/mock_publisher.py`) that reproduce the
  reported symptoms (UA-0009 stale description date, UA-0010 lost update
  after a simulated queue/read-back timeout) and prove the fix. These are
  **synthetic regression tests**, not live production evidence.

## Contents

- `eta_engine.py` — pure ETA normalization/validation/sanitation logic.
- `eta_transaction.py` — the transactional controller
  (write → read-back → bounded rebuild/publish → commit/rollback), with
  pluggable `DbAdapter` / `PublishAdapter` interfaces so it can be wired to
  the real `db.py` / `konteyner.py` / `publikaciya.py` once their exact
  schema and function signatures are confirmed under Gate A.
- `sqlite_adapter_reference.py` — a reference `DbAdapter` implementation
  using a **row-level** `UPDATE` inside `BEGIN IMMEDIATE` (never a full DB
  file replace), matching the task's transaction requirement. Column/table
  names must be verified against the real schema before use.
- `patch_notes.md` — exact integration points for `db.py`, `konteyner.py`,
  `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py`.
- `fixtures/` — offline mock CRM + publisher for tests only.
- `tests/` — unit + integration + regression test suite (unittest, stdlib
  only, zero LLM tokens at runtime).
- `run_tests.py` — offline test runner.
- `workflows/gate_a_readonly.yml` — manual, GET-only, secret-backed Gate A
  workflow template (does nothing destructive; no-ops safely if secrets are
  absent, as they are in this sandbox).
- `workflows/gate_b_manual_production.yml` — manual `workflow_dispatch`
  requiring the exact token `CRM-ETA-SYNC-GUARD-004-V1.0-PRODUCTION-APPROVED`;
  it only verifies the token and stops — it performs **no** production
  action by itself.
- `evidence/gate_a_evidence.md`, `evidence/canary_report.md` — honest status
  of what was and was not executed.
- `task_report.md` — full technical report for ChatGPT/Codex audit.

## Root-cause hypothesis for UA-0010 (to be confirmed by real Gate A)

Based on the owner's timeline (UA-0010 page updated 02:01 and did not
rebuild after the CRM command, while UA-0009/UA-0011 pages did update their
timestamp but kept a stale description date), the transaction controller in
this release candidate is built to make the following failure modes
impossible to report as "success":

1. **DB write succeeds but read-back never matches** (queue/lock/busy or a
   stale cached row) → today this can look like a silent success; in this
   RC it forces `success=False`, a rollback attempt, and a retryable job.
2. **DB write and read-back succeed, but rebuild/publish silently fails or
   times out** → today the CRM may still show "saved" while the live page
   never regenerates (this matches the UA-0010 symptom). In this RC,
   publish failure also blocks success and triggers rollback + retry.
3. **Rebuild succeeds for the dynamic ETA block but the free-text
   description keeps an old hardcoded date** (this matches the UA-0009
   symptom) → `strip_stale_dates()` removes independent absolute dates from
   the description so the ETA component is the single public source of
   truth.

Which exact step failed for UA-0010 in the real system can only be proven by
running Gate A against the real `crm.db` and the real live pages — that
read-only audit is prepared but not yet executed here.
