# TASK 035 report -- CRM-SPEED-001 phase E: evidence integration and complete compatibility

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Scope

This task integrated the TASK 034 standalone evidence modules
(`sqlite_ownership.py`, `ua0009_publication_check.py`, `build_manifest.py`,
`verify_gate_a.py`) into the real TASK 032 orchestration
(`crm_speed_gate_a.py`), and fixed the four exact regressions reported
by the independent controller on commit
`b45ca4a288a671a945eff64e3b54334d0cd0ce4c`. No production, CRM, bot,
site, media, generator, WSGI, process, scheduled-task, or UA-0009 file
was touched. All work is confined to `cloud/crm_speed_optimization/`.
Gate A was not executed. UA-0009 was not published.

## Regression fixes

1. **`candidates_compile` missing after a cars_ui semantic block
   (phase40/phase60).** `orchestrate_gate_a`'s phase40 now records safe
   compile-only evidence from the exact secure original bytes whenever
   `transform_cars_ui` blocks before producing a candidate:
   `candidates_compile = {status: OK, candidate_origin:
   original_due_to_transform_block, compiled: [...]}` (or a `BLOCKED`
   compile result, still tagged with the same `candidate_origin`, if
   even the original bytes fail to compile). The transform/admin-route
   evidence itself remains `BLOCKED`. Because phase80 is skipped in
   this path, the remaining structural predicates stay missing/BLOCKED,
   so this safe compile evidence never by itself permits a final PASS.

2. **`build_manifest(package_dir, run_dir, receipt)` treated the
   receipt dict as a logical-path mapping.** `build_manifest.py` now
   detects the historical three-positional-argument call form
   structurally (a dict passed as the third positional argument) and
   routes it to a dedicated `_build_historical_manifest()` that hashes
   the existing `receipt.json`/`report.md` on disk directly and binds
   package/candidate/diff/compilation/deterministic/SQLite/UA/
   publication/site/ledger evidence by reading fixed keys out of the
   receipt dict -- `lstat` is never called on a list/dict value. The
   canonical keyword-only call form is preserved unchanged and now also
   accepts a single path string or an explicitly bounded list of path
   strings (<= 20 entries, no duplicates) per logical artifact name;
   a dict value is rejected with a plain `ValueError`.

3. **Verifier only recognized one receipt schema.** `verify_gate_a.py`
   now explicitly recognizes two schemas: historical orchestration
   receipts (`status` in `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` /
   `BLOCKED`, predicates under `evidence`) and standalone focused
   receipts (`status` in `PASS` / `BLOCKED`, predicates under
   `predicates`, `pii_emitted` required). Both require
   `production_write == "NO"`. A receipt containing both `evidence` and
   `predicates` is rejected as `mixed_schema_forms`. For the historical
   schema, every required predicate is checked (in fixed order) before
   any pass/fail-completeness check, so a missing predicate always
   returns exactly `missing_or_malformed_predicate:<key>`. All TASK 034
   hardening (no-follow-equivalent lstat checks, regular/single-link
   identity, bounded size, duplicate-JSON-key rejection, fail-closed
   exception handling) is preserved unchanged.

4. **Historical two-argument `verify_receipt(receipt_path,
   manifest_path)` never checked the report hash.** When `manifest_path`
   is supplied and `report_path` is omitted, `verify_receipt` now
   automatically binds `<run_dir>/report.md` whenever the manifest
   contains a `report_sha256` key, and returns exactly
   `report_hash_mismatch` when the on-disk report no longer matches
   that bound hash.

## Orchestration integration (`crm_speed_gate_a.py`)

- Phase20 now collects read-only, fail-closed UA-0009 SQLite ownership
  evidence once via `sqlite_ownership.collect_ua0009_ownership_evidence`
  (the exact canonical implementation -- no duplicated logic), strictly
  before the candidate workload (transform/compile/structural/publication
  phases). Missing `ua0009_table`/`ua0009_id_column` configuration fails
  closed rather than fabricating evidence; `DEFAULT_CONFIG` leaves these
  unconfigured pending owner-verified schema confirmation.
- Phase100 collects the same canonical evidence again, only after the
  entire workload (phases 40/60/80 have all run, been skipped, or been
  blocked), and compares before/after through the canonical
  `sqlite_ownership.compare_ownership_evidence` helper. Missing,
  non-OK, or changed evidence always maps `ua0009_fingerprint_unchanged`
  to `BLOCKED` -- never fabricated as unchanged.
- Phase80's publication probe now calls
  `ua0009_publication_check.canonical_probe_ua0009` directly with the
  injected opener, instead of a locally duplicated HTTP routine.
- The final receipt now also carries `sqlite_ownership` (before/after,
  serialized via `OwnershipEvidence.to_dict()`, which never includes raw
  row field values -- only structural identifiers and SHA-256 digests),
  `publication_result`, and a fixed `pii_emitted: "NO"` field, alongside
  the existing phases/evidence/site-inventory/allowed-write-ledger/
  `production_write: "NO"` fields.
- Database resources are always closed inside
  `sqlite_ownership.collect_ua0009_ownership_evidence` before any
  hashing/serialization occurs (verified by the pre-existing TASK 034
  `test_cursor_and_connection_closed_before_hashing` test and by this
  task's before/after-ordering test).
- The historical fixture-facing `check_ua0009_not_public()` adapter
  (used only by `_compute_evidence()`/`run_gate_a()` for in-memory
  fixture tests) was intentionally left byte-for-byte unchanged to avoid
  any risk to the existing `test_crm_speed_gate_a.py` fixture suite,
  which this task must not modify or weaken.

## Tests

`cloud/crm_speed_optimization/test_task_035_integration.py` adds
focused, temporary-directory-only tests covering: the four exact
regressions above; historical and canonical manifest determinism;
bounded artifact-path lists and dict-value rejection; historical and
focused verifier schemas (valid, mixed, and missing-predicate cases);
receipt/report tamper detection; canonical
sqlite_ownership/ua0009_publication_check delegation via
monkeypatch-identity assertions; SQLite evidence ordering (before and
after the full workload, not adjacent); PII-seed absence across
receipt/manifest/report; and a compile sanity check over the files this
task touched.

## Controller re-verification command

```
python3 -m py_compile cloud/crm_speed_optimization/*.py && \
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

This command was not executed inside this environment (no test runner
was invoked here); the independent controller is expected to run it and
confirm the previously reported 168 PASS / 2 FAIL / 2 ERROR set is now
fully green (172+ passing, 0 failing), per the task's controller
target.

## Status

Successful phase status: **READY_FOR_CONTROLLER_REVIEW_PHASE_E** (never
`READY_FOR_GATE_A_EXECUTION`). Gate A was not executed. Production and
CRM were not touched. UA-0009 was not published.
