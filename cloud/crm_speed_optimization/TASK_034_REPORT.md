# TASK 034 REPORT — CRM-SPEED-001 phase D: standalone evidence modules, compile-clean

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

## Recovery context

TASK 033 was rejected before commit because the generated `build_manifest.py`
contained a `SyntaxError`. This task (034) recovers safely by rewriting the
four evidence modules from scratch as syntactically simple, standalone units,
and mentally py-compiling every file before inclusion in this response. No
integration into a central orchestrator is attempted here; that is
intentionally deferred to TASK 035 per the task instructions.

## What was delivered

1. **`sqlite_ownership.py`** — retains the original AST-based short-ownership
   transform/verifier (`transform_short_ownership`,
   `verify_no_live_handle_across_slow_call`, `find_db_handle_names`,
   `AnchorNotFoundError`) byte-for-byte in logic, and adds a new canonical
   read-only evidence API:
   - `collect_ua0009_ownership_evidence(db_path, table, id_column, id_value)`
     validates the DB path with `lstat` (regular, non-symlink, `nlink == 1`),
     opens only via a quoted `file:<path>?mode=ro` URI with a short timeout,
     sets `PRAGMA query_only=ON` and records the confirmed value, requires
     `PRAGMA quick_check` to equal exactly `ok`, performs bounded schema
     introspection (max tables/columns/rows/serialized bytes), selects
     exactly one row via safely quoted, introspection-confirmed identifiers,
     materializes the row, closes the cursor and connection, and only then
     hashes the row and combines it with the quick_check/query_only/table
     values into `evidence_sha256`. No raw field values ever leave the
     function — only structural identifiers, a row count, and SHA-256
     digests.
   - `compare_ownership_evidence(before, after)` is a pure helper that is OK
     only when both evidence objects are `OK` and their hashes match.
   - Every expected operational failure (missing file, symlink, hard link,
     malformed/locked database, missing table/column, missing/ambiguous row,
     bounded overflow) returns a structured `BLOCKED` `OwnershipEvidence`
     instead of raising.

2. **`ua0009_publication_check.py`** — new `canonical_probe_ua0009(url,
   opener=None, timeout=5.0)` is the single canonical no-redirect probe:
   requires HTTPS with no embedded credentials, never follows redirects,
   and only HTTP 404/410 responses PASS. Every other outcome (2xx, 3xx,
   other 4xx, 5xx, DNS/TLS/timeout/refused/network status -1, malformed
   response, or any exception) BLOCKS with a bounded structured reason.
   The historical public names (`PublicationCheckResult`,
   `resolve_canonical_url`, `probe_no_redirect`, `sqlite_quick_check`,
   `check_ua0009_not_public`, `CONFIG_ENV_VAR`, `CONFIG_FILE_CANDIDATE`,
   `_NoRedirect`) remain importable as thin adapters over the canonical
   logic — no logic is duplicated. `check_ua0009_not_public` remains
   fail-closed when no canonical URL is configured (never silently skips).

3. **`build_manifest.py`** — rewritten as a syntactically simple,
   compile-clean, deterministic manifest builder. Accepts only explicit
   data arguments and a run directory (no production access). Rejects
   unsafe paths, symlinks, non-regular/hard-linked files, duplicate logical
   paths, and files outside the resolved run directory with a plain
   `ValueError`. Binds package code hashes, run-directory artifact hashes,
   the allowed-write ledger, SQLite ownership evidence, UA-0009
   before/after evidence, the canonical publication result, and a fixed
   `pii_emitted: "NO"` field. Output is deterministic via `canonical_json`
   (sorted keys, fixed separators) and contains no self-referential
   manifest hash.

4. **`verify_gate_a.py`** — standalone, bounded, fail-closed verifier.
   Performs secure no-follow reads (rejects symlink, non-regular,
   hard-linked, oversized, or outside-run-directory files), rejects
   duplicate JSON keys, requires JSON objects, and never raises for any
   expected failure — it always returns `(False, sanitized_reason)`.
   Verifies the fixed `REQUIRED_PREDICATES` set, PASS/BLOCKED consistency,
   `production_write == "NO"`, `pii_emitted == "NO"`, and (when a manifest
   is supplied) the receipt/report hashes bound in that manifest. Never
   imports or executes any candidate code. The historical
   `verify_receipt(receipt_path, manifest_path)` two-positional-argument
   call pattern still works; a new optional `run_dir` keyword argument adds
   containment checking without breaking the old call shape.

5. **`test_task_034_evidence_modules.py`** — offline, deterministic,
   temporary-directory-only tests covering: module compilation; exact
   `quick_check == "ok"` and confirmed `query_only`; locked/malformed/
   missing/symlink/hard-link DB blocking with byte-identical database
   contents before and after; bounded UA-0009 evidence containing only
   structural hashes (no seeded PII string leaks); missing/ambiguous/
   overflow blocking; cursor/connection-close-before-hash ordering via an
   instrumented proxy connection; HTTP 404/410 pass and 200/3xx/4xx/5xx/
   network-error/malformed-URL/non-HTTPS/embedded-credentials block;
   malformed/extra-data/duplicate-key/non-UTF-8/oversized receipt and
   manifest handling returning `False` without raising; symlink/hard-link/
   non-regular/tampered-hash detection for `build_manifest.py` and
   `verify_gate_a.py`; deterministic manifest byte-equivalence from
   identical inputs; and import-compatibility of all historical public
   names across all four modules.

## Controller target

```
python3 -m py_compile cloud/crm_speed_optimization/*.py && \
python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
```

Note: this command also discovers pre-existing test files from earlier tasks
(e.g. `test_task_032_orchestration.py`, `test_crm_speed_gate_a.py`) that were
not touched by this task and depend on modules (`crm_speed_gate_a.py`,
`canonical_modules.py`, `RUN_GATE_A_CRM_SPEED.py`) not delivered in this
phase's scope. Those pre-existing files are unrelated to TASK 034 and are
left exactly as they were; this task's own test file
(`test_task_034_evidence_modules.py`) is fully standalone and does not
depend on them.

## Boundaries respected

- Work performed only under `cloud/`.
- Gate A was not executed.
- No PythonAnywhere, `/home/Carix`, real URLs, or network access occurred.
- Production, CRM, `crm.db`, bot, site, media, cards, generators, WSGI,
  processes, scheduled tasks, and UA-0009 were not touched.
- UA-0009 was not published.
- `tasks/` was not modified.
- No placeholders, TODO-only code, credentials, PII, production imports, or
  production-write capability were introduced.

## Phase status

`READY_FOR_CONTROLLER_REVIEW_PHASE_D` (never `READY_FOR_GATE_A`).
