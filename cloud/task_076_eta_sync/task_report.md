# TASK 076 report — CRM-ETA-SYNC-GUARD-004 v1.0

## Memory markers (verbatim, do not alter)

- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4

## Request

Owner reported that for UA-0009, UA-0010, UA-0011 the CRM status and ETA
were set to 30 days, but the live cards did not all reflect it consistently
(stale description date on some, no rebuild at all on UA-0010). The task
asked for a root-cause-fixing release candidate covering all current and
future cards, plus a read-only Gate A audit and a prepared (not executed)
Gate B.

## What was actually done in this sandbox

1. No live/CRM read access was available (no network, no secrets, no copy
   of `crm.db` or the six named source files, no access to the live pages).
   Gate A could **not** be executed for real; this is stated plainly in
   `evidence/gate_a_evidence.md` rather than fabricated.
2. A generic, ID-list-free release candidate was built implementing the
   full mandatory contract:
   - `eta_engine.py`: single-transaction ETA computation
     (`days_to_kyiv` and `eta_manual` derived from one base date so they are
     always mutually consistent), stage-3 15-day rule preserved from
     TASK 075, manual > stage > neutral priority resolver, and a regex-based
     stale-date stripper for free-text descriptions.
   - `eta_transaction.py`: `EtaSyncController` enforcing write → verified
     read-back of both fields → bounded rebuild/publish across card,
     catalogs, `/video`, `/site` → commit, with automatic rollback and a
     retryable job on any partial write, read-back mismatch, timeout, or
     publisher failure. Success is only ever returned when every step
     passed.
   - `sqlite_adapter_reference.py`: a reference row-level (`BEGIN
     IMMEDIATE` + single-row `UPDATE`) adapter, explicitly never replacing
     the full DB file, to be adapted to the real schema after Gate A
     confirms column names.
   - `patch_notes.md`: exact integration points for `db.py`, `konteyner.py`,
     `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py`.
3. A full offline test suite (`tests/`) using in-memory fixtures
   (`fixtures/mock_crm.py`, `fixtures/mock_publisher.py`) reproduces the
   reported symptoms and exercises every required scenario: N=0,1,30,400;
   invalid/negative/>400 rejected; idempotent repeat; injected failures
   after the first DB field, read-back mismatch, queue timeout, publisher
   failure, partial rebuild-card failure, delayed-rebuild-overwrite
   protection; and a protected-row (UA-0001) unaffected check.
4. `workflows/gate_a_readonly.yml` is a manual, GET-only workflow that a
   controller/owner session with real secrets can run; it safely no-ops in
   this sandbox (no secrets configured) and always runs the offline suite.
5. `workflows/gate_b_manual_production.yml` requires the exact token
   `CRM-ETA-SYNC-GUARD-004-V1.0-PRODUCTION-APPROVED` via manual
   `workflow_dispatch`, verifies it, prints the mandatory pre-write safety
   checklist (exclusive window, backup, SHA gate, row-level transaction,
   atomic file replace, exact launcher restart, immediate + >=60s delayed
   public check, automatic rollback + rollback verification), and
   intentionally performs **no** production action.

## What was NOT done

- No real Gate A read-only audit against production/CRM.
- No sandbox/canary run against the real UA ART system.
- No production or CRM write of any kind.
- The exact live root cause for UA-0010 (CRM write vs read-back vs queue vs
  publisher vs rebuild) is **not proven** — only a generic fix that makes
  every one of those failure classes non-silent is delivered.

## Verdict

`FAIL` for the live Gate A requirement (could not be executed from this
environment) / `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` for the
offline code-and-test layer only. Gate B remains fully un-run and requires
both (a) a real, controller-executed Gate A pass, and (b) the owner's exact
approval token, before any production write is even attempted.

Consistent with canonical shared memory: `production_write: NO`,
`crm_write: NO`, `ua0009_safe_to_publish: NO` remain unchanged by this
task.
