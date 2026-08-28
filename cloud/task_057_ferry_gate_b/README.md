# TASK 057 — Ferry Wording GATE B Release Package (PREPARATION ONLY)

STATUS_LABEL: AWAITING_EXACT_GATE_B_APPROVAL_TASK_057

This package prepares — but does NOT execute — the production Gate B release for
the already-audited ferry wording change ("В море" -> "На пароме",
"У морі" -> "На поромі") across UA-0001..UA-0009 and the two generators
(stranica.py, yadro.py), plus index/katalog/info/podbor.html.

## Why the manifest is NOT fully generated in this task

The owner's chat reply «Разрешаю» authorizes *preparation* of this package.
It is not a production execution token, because a binding manifest_sha256
did not exist before this task ran. Per the task's fail-closed requirement,
this package MUST NOT fabricate SHA-256 hashes for the live Gate A evidence
file (`cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json`). Instead
it ships:

1. `build_manifest.py` — a deterministic, offline manifest builder that reads
   the real Gate A evidence file, verifies every required field exactly
   matches the values recorded in this task (status, timestamp, counts,
   all `*_write`/`*_executed`/`*_published` flags), and only then emits
   `release_manifest.json` with real embedded hashes and a canonical
   `manifest_sha256`.
2. `release_manifest.json` — currently a template with
   `"status": "NOT_YET_GENERATED"` and `"manifest_sha256": null`. It becomes
   the binding artifact only after `build_manifest.py` is run by the
   controller against the verified Gate A evidence file on the canonical
   branch.
3. `gate_b_installer.py` — the fail-closed installer. It is NOT executed by
   this task. It refuses to run without (a) a manifest whose canonical hash
   matches its own `manifest_sha256` field and (b) an approval file whose
   content is the exact phrase
   `APPROVE_PRODUCTION TASK_057 MANIFEST_SHA256=<64hex>` where `<64hex>`
   equals the manifest's `manifest_sha256`.
4. `verify_release.py` — read-only integrity checker for the manifest and
   (once generated) for whether candidate/source files described in it are
   present and match, without ever writing to production.
5. `tests/test_gate_b_installer.py` + `run_tests.py` — standard-library tests
   against temporary fixtures (never touching production paths).

## Allowlist (exact, no recursion, no broad find/replace)

```
video/index.html
video/katalog.html
video/info.html
video/podbor.html   (VERIFY_UNCHANGED only — zero-change identity proof)
video/UA-0001.html
video/UA-0002.html
video/UA-0003.html
video/UA-0004.html
video/UA-0005.html
video/UA-0006.html
video/UA-0007.html
video/UA-0008.html
video/UA-0009.html
stranica.py
yadro.py
```

## Safety guarantees implemented in gate_b_installer.py

- Requires exact approval phrase bound to `task_057` and the real
  `manifest_sha256`.
- Re-hashes every live source immediately before any write; aborts on any
  drift versus the manifest's recorded `source_sha256`.
- Verifies every candidate file's bytes/hash/size against the manifest
  before any write.
- Rejects symlinks, hardlinks (`st_nlink > 1`), non-regular files, path
  traversal, and any path outside the fixed allowlist.
- Creates a full timestamped backup of every REPLACE target before the
  first write, and verifies backup hash equals source hash.
- Uses atomic same-filesystem temp-write + fsync + `os.replace`.
- On any failure at any point, restores every already-changed target from
  its verified backup and proves the restored hash matches the original.
- After success, re-verifies every target hash equals the manifest's
  candidate hash.
- Never opens, writes, or migrates `crm.db` or any CRM table.
- Never issues a reload/restart of WSGI, bot, service, or schedule.
- Never creates a new UA-0009 listing; it can only VERIFY_UNCHANGED or
  REPLACE the wording bytes of the already-existing UA-0009 candidate page.
- Emits one strict JSON receipt with before/after/backup hashes, timestamps,
  rollback status, and explicit `production_touched` / `crm_touched` /
  `service_reloaded` / `ua0009_published` markers (all false unless a real
  successful write happened).

## What happens next

1. A controller with repository access runs
   `python3 build_manifest.py --evidence cloud/task_047_ferry_discovery/evidence/ferry_gate_a.json --report cloud/task_047_ferry_discovery/FERRY_GATE_A_REPORT.md --out release_manifest.json`.
2. `build_manifest.py` fails closed if any required Gate A field/hash does
   not match this task's recorded evidence values.
3. On success it prints the real `manifest_sha256`.
4. The owner reviews the generated manifest and, only then, replies with the
   exact phrase from `exact_owner_approval.txt` (with the real hash filled
   in).
5. Only after that exact phrase is recorded may a future task execute
   `gate_b_installer.py` against production, under a new task with explicit
   CRITICAL approval handling.

This task performs none of steps 1–5 above. It only ships the tooling.

## Mandatory markers

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SERVICE_RELOADED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
UA0009_SAFE_TO_PUBLISH: NO
STATUS_LABEL: AWAITING_EXACT_GATE_B_APPROVAL_TASK_057
