# TASK 043 — Corrected ferry-wording package (Gate A only, read-only real discovery)

This package supersedes the rejected TASK 042 candidate. It is scoped strictly to:

1. A contextual, structure-aware text/HTML transform that never rewrites arbitrary prose, script bodies, style bodies, or legacy input aliases.
2. A hardened, fail-closed, read-only PythonAnywhere discovery tool bound to a fixed candidate registry.
3. An isolated Gate A builder that only writes under the three approved task-043 roots, with atomic writes, rollback on failure, and 10-run determinism proof.
4. A PythonAnywhere controller (offline-testable against a FakeAPI) that only ever invokes the read-only discovery and isolated Gate A commands, never Gate B, reload, restart, or publish endpoints.
5. A GitHub Actions workflow *template* (not installed/enabled) that Codex can audit before any real run is authorized.

## Honest status

This round did **not** execute against real PythonAnywhere infrastructure. Claude has no direct filesystem or shell access to `/home/Carix`. All discovery/Gate A code in this package is written to be run *by the controller, on request, after independent Codex audit*. No real UA-0001..UA-0009 HTML, no real crm.db, and no real generator source were read in this round.

Finish state for this round: **READY_FOR_CODEX_CONTROLLER_AUDIT**.

`UA0009_SAFE_TO_PUBLISH` remains **NO**.

## Safety markers (this round)

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

## Directory contents

- `transform.py` — contextual anchor-based transform (plain text + structural HTML reconstruction).
- `discover.py` — hardened, bounded, fail-closed read-only discovery tool (root-locked, symlink/hardlink/TOCTOU rejecting, secret-redacting, SQLite read-only exact scope).
- `gate_a.py` — isolated Gate A builder (atomic writes, path-escape rejection, rollback, determinism proof).
- `controller.py` — PythonAnywhere orchestration controller, offline-testable via dependency injection (no real network calls in this package).
- `workflow_template.yml` — reviewed GitHub Actions template, NOT wired into `.github/workflows/`.
- `tests/` — standard-library `unittest` only, no third-party dependency.
- `run_tests.py` — no-argument launcher that discovers and runs every test in `tests/`.
- `TASK_043_REPORT.md` — full technical report.
- `AUDIT_RESPONSE_TABLE.md` — point-by-point response to all ten TASK 042 defects.
- `OPERATOR_INSTRUCTIONS.md` — exact steps for a human/controller to run this for real, later, with approval.
- `ROLLBACK_AND_GATE_B_PLAN.md` — non-executable plan for later stages.

## Memory markers (verbatim, do not alter)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
