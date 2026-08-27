# TASK 036 REPORT — CRM-SPEED-001 fixture correction

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

Correct the single invalid temporary SQLite fixture inside
`test_sqlite_ownership_evidence_delegates_to_canonical_function` in
`cloud/crm_speed_optimization/test_task_035_integration.py`. No other
test, module, or file was modified. No implementation module was
changed. No production, CRM, PythonAnywhere, or Gate A execution was
performed.

## Root cause (confirmed from controller evidence)

`_make_temp_config()` (in `test_task_032_orchestration.py`) already
creates the temporary `crm.db` with a table `t` that has a column
`id INTEGER`. The TASK 035 test then executed:

```sql
ALTER TABLE t ADD COLUMN id TEXT
```

SQLite raises `sqlite3.OperationalError: duplicate column name: id`
because `id` already exists on `t`. This exception occurred before the
delegation workload under test (`gate_a.orchestrate_gate_a`) ever ran,
so the assertion on `len(calls) == 2` was never reached. This is a test
fixture defect only — the implementation module
`sqlite_ownership.collect_ua0009_ownership_evidence` and its caller in
`crm_speed_gate_a.py` were never at fault.

## Fix applied

In `test_sqlite_ownership_evidence_delegates_to_canonical_function`:

- Removed the duplicate `ALTER TABLE t ADD COLUMN id TEXT` statement.
- Reused the already-existing `id` column (`INTEGER`) created by
  `_make_temp_config()`.
- Inserted exactly one deterministic row: `INSERT INTO t (id) VALUES (1)`,
  which is compatible with `cfg["ua0009_id_value"] = "1"` under SQLite's
  dynamic type affinity/text comparison rules used by the ownership
  evidence collector.
- Preserved the `mock.patch.object` spy on
  `gate_a.sqlite_ownership.collect_ua0009_ownership_evidence` and the
  assertion `self.assertEqual(len(calls), 2)`, unchanged in intent:
  proving the canonical function is delegated to exactly twice
  (before and after the orchestrator's workload).
- The temporary sqlite3 connection is opened, one INSERT executed,
  `conn.commit()` called, and `conn.close()` called — proper
  close/commit ordering with no leaked connection.
- No test was skipped, weakened, renamed, or deleted.
- No production implementation module (`sqlite_ownership.py`,
  `crm_speed_gate_a.py`, `ua0009_publication_check.py`,
  `build_manifest.py`, `verify_gate_a.py`) was modified.
- All other test classes and test methods in the file are preserved
  byte-for-byte relative to the exact current source provided in the
  task, with only the one described fixture correction applied inside
  the single named test method.

## Expected controller outcome

Running:

```
python3 -m py_compile cloud/crm_speed_optimization/*.py && \
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

is expected to produce 188 tests total with zero FAIL/ERROR, including
the corrected `test_sqlite_ownership_evidence_delegates_to_canonical_function`
now actually reaching `gate_a.orchestrate_gate_a` and observing
`len(calls) == 2` for the canonical `collect_ua0009_ownership_evidence`
delegation.

## Safety markers

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Status

This package is READY_FOR_CONTROLLER_REVIEW_PHASE_E_TEST_FIX. It is not
READY_FOR_GATE_A. Independent controller execution of the exact command
above is required before any further status change.
