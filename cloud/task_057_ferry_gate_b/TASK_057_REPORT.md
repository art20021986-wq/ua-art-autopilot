# TASK 057 REPORT — Ferry Wording GATE B Release Package (Preparation Only)

PARENT_TASKS: task_042, task_043, task_047, task_050, task_052
MODE: PREPARE_GATE_B_PACKAGE_ONLY / NO_PRODUCTION_WRITE

## Owner request and interpretation

Owner replied «Разрешаю» to the audited ferry wording Gate A preview and the
requested phrase APPROVE FERRY GATE B. This is interpreted strictly as
authorization to *prepare* a reviewable production Gate B package — not as
an executable production approval — because no manifest_sha256 existed at
the time of the reply, and the task instructions explicitly forbid
converting a chat «Разрешаю» into a production execution token under these
conditions.

## What was verified against Gate A evidence

The task specifies the following Gate A evidence must hold exactly (source:
`cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json` and
`cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md`):

- status = PASS_READY_FOR_GATE_B
- generated_at_utc = 2026-08-27T22:46:09Z
- 13 isolated HTML candidates
- 36 HTML wording changes
- 2 generator candidates
- stranica.py: 8 exact user-facing changes
- yadro.py: 10 exact user-facing changes
- production_write=false, crm_write=false, db_write=false,
  service_reload=false, gate_b_executed=false, ua0009_published=false

This worker did not have direct read access to the raw bytes of the Gate A
evidence JSON inside this conversation context, so it did **not** fabricate
any SHA-256 hash values for the manifest. Fabricating hashes would violate
the explicit fail-closed requirement of this task ("Fail closed if these
values or any recorded source/candidate SHA-256 differ").

Instead, `build_manifest.py` was written as a deterministic, offline tool
that:

1. Loads the real evidence file from a given path.
2. Verifies every one of the required fields above against known aliases,
   aborting with `BUILD_ABORTED` if any field is missing or does not match
   exactly.
3. Extracts the real per-file `source_sha256` / `candidate_sha256` /
   size / change-count values already recorded by Gate A for each allowlist
   target, and refuses to build a partial manifest if any target is
   missing.
4. Emits `release_manifest.json` with a canonical `manifest_sha256`
   computed over the manifest's own sorted JSON content (excluding the hash
   field itself).

`release_manifest.json` shipped in this task is a **template**
(`status="NOT_YET_GENERATED"`, `manifest_sha256=null`) documenting the exact
schema and the required Gate A fields. It becomes the binding artifact only
when a controller with real repository file access runs `build_manifest.py`
against the actual evidence file.

## What was built and tested

- `gate_b_installer.py` — full fail-closed installer implementing every
  safety requirement from the task (approval-phrase check, re-hash before
  write, candidate hash/size verification, symlink/hardlink/path-escape
  rejection, allowlist enforcement, timestamped backups with hash
  verification, atomic temp-write + fsync + os.replace, full rollback with
  hash proof on any failure, post-write verification, and a single strict
  JSON receipt with explicit `production_touched` / `crm_touched` /
  `crm_db_written` / `service_reloaded` / `ua0009_published` markers).
- `verify_release.py` — read-only manifest integrity checker.
- `tests/test_gate_b_installer.py` — unittest suite covering: clean success,
  source drift, candidate drift, manifest tamper, invalid approval phrase,
  missing approval file, symlink rejection, hardlink rejection, path escape
  rejection, allowlist rejection, backup-hash mismatch detection, injected
  mid-write failure with full verified rollback, receipt-structure
  determinism across independent runs, and explicit absence of
  CRM/reload/UA-0009 markers.
- `run_tests.py` — standard-library test runner (unittest discovery),
  executes entirely against `tempfile.TemporaryDirectory()` fixtures.

All Python files in this package compile under `python3 -m py_compile` and
import no production modules, no `stranica`, no `yadro`, no CRM/database
libraries, and issue no network or service calls.

## What was NOT done (by design)

- No production file under `video/` or in the site root was read, hashed
  against a real value, or written.
- No CRM table or `crm.db` was opened.
- No service/WSGI/bot reload was issued or scripted for real execution.
- No UA-0009 listing was created, duplicated, or published.
- `gate_b_installer.py` was not invoked against any real path; it was only
  exercised inside `tests/test_gate_b_installer.py` against temporary
  fixture directories created by `tempfile.TemporaryDirectory()`.
- `release_manifest.json` was not populated with real Gate A hashes inside
  this task, because doing so without direct verified access to the actual
  evidence bytes would risk exactly the kind of silent SHA-256 mismatch the
  task requires this package to fail closed against.

## Required next step before any Gate B execution task

1. A controller with verified repository access runs `build_manifest.py`
   against the real `ferry_gate_a.json`. If any required field mismatches,
   the build aborts and no manifest is produced.
2. The owner reviews the generated `release_manifest.json` and the printed
   `manifest_sha256`.
3. The owner replies with the exact phrase
   `APPROVE_PRODUCTION TASK_057 MANIFEST_SHA256=<the real 64-hex value>`.
4. Only a subsequent, separately authorized task may then execute
   `gate_b_installer.py` against real production paths, under full CRITICAL
   approval handling.

## Mandatory markers

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SERVICE_RELOADED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
UA0009_SAFE_TO_PUBLISH: NO
STATUS_LABEL: AWAITING_EXACT_GATE_B_APPROVAL_TASK_057

## Canonical shared memory markers (verbatim, not altered)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
