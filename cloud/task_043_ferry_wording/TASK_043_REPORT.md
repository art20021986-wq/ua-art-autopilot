# TASK 043 REPORT — Correction of TASK 042 candidate + real-discovery/Gate-A package

MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## 1. What was independently found wrong in TASK 042

See `AUDIT_RESPONSE_TABLE.md` for the full point-by-point response to all ten defects from the independent Codex audit of commit `1bb04f1f73714c20e367dd05cbbdb6142995c815`.

## 2. What this round delivers

- `transform.py`: replaces the global case-insensitive regex with (a) an exact-whole-string plain-text transform (`apply_transform`) that never touches phrases embedded in longer ordinary prose, and (b) a structural HTML reconstruction parser (`transform_html`) that only edits visible text nodes and the approved `data-ru`/`data-uk` attributes, never script/style bodies, never other attributes (including `data-stage`), and never unmatched text.
- `discover.py`: a fail-closed, bounded, hardcoded-registry, read-only discovery tool. It requires an exact root match (`/home/Carix` in real use), rejects symlinks/hardlinks/non-regular files, performs a TOCTOU identity check between lstat and fstat, caps files/bytes/matches, redacts secret-shaped lines, classifies every occurrence, deduplicates by (line, content), and queries `crm.db` only via `mode=ro` + `PRAGMA query_only=ON` + `PRAGMA quick_check`, restricted to the nine UA IDs, with no ATTACH/VACUUM/write.
- `gate_a.py`: an isolated Gate A builder that validates every destination path is under one of the three approved task-043 roots (rejecting symlink components and path escapes) before any write, writes atomically (temp file + fsync + `os.replace`), rolls back every file written in the current call on any failure, and provides a `determinism_check` helper that proves output-hash stability across 10 runs.
- `controller.py`: an offline-testable orchestration controller. It enforces account `Carix`, host allowlist, refuses any command containing a reload/restart/Gate-B/publish/vacuum/attach token, validates the receipt JSON with duplicate-key detection, rejects any unsafe `production_touched`/`crm_touched`/`gate_b_executed` flag, scans receipts for secret-shaped terms, and always calls cleanup in a `finally` block.
- `workflow_template.yml`: a reviewed, **disabled** GitHub Actions template. Only the offline test job is wired to run; the real-discovery job is commented out behind `if: false` pending Codex audit and owner approval.
- `tests/`: standard-library `unittest` covering all of section 6's mandatory targets that are testable without real PythonAnywhere access (see below for the honest gap).

## 3. What this round explicitly did NOT do

- No real PythonAnywhere filesystem was read. Claude has no direct shell/filesystem access to `/home/Carix`.
- No real UA-0001..UA-0009 HTML, no real `crm.db`, no real generator source (`stranica.py`, `yadro.py`, `master_card.py`, etc.) was inspected.
- No real Gate A preview/report was published; no public URL was checked.
- No production, CRM, or Gate B action of any kind was performed.
- The nine-card real stage matrix, catalog counts, and real generator candidate diffs described in TASK 043 sections 3 and 4 cannot be produced until the controller in `controller.py` is wired to a real, audited PythonAnywhere API client and executed by that controller (not by Claude directly).

## 4. Test evidence (offline, this repository only)

All tests in `cloud/task_043_ferry_wording/tests/` use only the Python standard library (`unittest`, `html.parser`, `sqlite3`, `hashlib`, `json`, `tempfile`). They were authored to be run via `python3 cloud/task_043_ferry_wording/run_tests.py`. They exercise synthetic fixtures that mirror the *shape* of real anchors (e.g. `data-stage="sea"`, `data-ru="В море"`) because no real card HTML was available to this round. This is the same category of limitation flagged in the TASK 042 audit, and it is repeated here honestly rather than concealed: **synthetic-fixture tests passing does not constitute real-card acceptance.**

## 5. Finish state

**READY_FOR_CODEX_CONTROLLER_AUDIT**

This package is ready for Codex to audit `controller.py` and `workflow_template.yml` for wiring to a real, token-scoped PythonAnywhere API client. Only after that audit, and only after the controller is actually run against real infrastructure with a real receipt produced, can the finish state advance to `READY_FOR_REAL_GATE_A` and then `AWAITING_GATE_B`.

`UA0009_SAFE_TO_PUBLISH`: **NO** (unchanged; no new evidence justifies changing this).

## 6. Safety markers

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```
