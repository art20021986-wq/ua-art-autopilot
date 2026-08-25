# CLOUD REPORT 001 — PythonAnywhere Autopilot Runner

Task: `tasks/task_001.md` (MODE: CRITICAL, MAX_ROUNDS: 10)
Round: 1
Role: Cloud (code author). No production system was reached from this side.

## Scope executed

Built the first safe runner for `/home/Carix/autopilot`. Everything produced
lives under `cloud/`. The UA ART production project was not modified, not
published, and not reachable from this environment (`/home/Carix` does not
exist here). No CRITICAL action was performed.

## Deliverables

| File | Purpose |
| --- | --- |
| `cloud/autopilot_runner.py` | The runner. Stdlib only, Python 3.7+, ~2000 lines including a built-in self test. |
| `cloud/runner_install.md` | PythonAnywhere installation, configuration, scheduling, troubleshooting. |
| `cloud/patch_manifest.example.json` | Manifest template; validated against the runner's own schema checker. |
| `cloud/cloud_report_001.md` | This report. |

## How each required behavior is implemented

**1. Works from a local clone.** `repo_root` defaults to
`/home/Carix/autopilot/ua-art-autopilot`. Each run fetches and fast-forwards
before reading anything (`git_sync`, disable with `--no-sync`).

**2. Reads the latest task and Cloud output.** `discover_latest_task()` picks
the highest `tasks/task_NNN.md`, parses `MODE:` and `MAX_ROUNDS:`, and records
the task SHA256. `list_cloud_outputs()` inventories `cloud/` with SHA256 and
size into the report.

**3. Nothing is executed just because it exists.** A patch is only touched
when `cloud/patches/<task_id>/patch_manifest.json` passes strict validation:
all five keys (`task_id`, `mode`, `allowed_files`, `expected_tests`,
`rollback_source`) present, unknown keys rejected, `task_id` matching the
newest task. Payload files under `patches/<task_id>/files/` are **copied**,
never imported or executed. `expected_tests` must name entries of an internal
registry of ten Python test functions — a free-form string such as `"rm -rf /"`
is rejected without execution (self test scenario 8). Paths are rejected when
absolute, traversal-bearing, symlinked, or denylisted (`*.db`, `*.sqlite*`,
`.env`, `*token*`, `*secret*`, media, archives, `backups/`, `.git/`, `.ssh/`).

**4. Pre-patch safeguards, in this order.** CPU guard → manifest validation →
whitelist verification → target existence + SHA256 capture → payload
resolution → backup manifest → sandbox → tests. Each gate stops the run on
failure with production untouched.

* *CPU guard*: PythonAnywhere API `daily_cpu_used/limit`; at `>= 85%` the run
  stops with `DEFERRED_CPU_LIMIT` before any sandbox, SHA walk, or copy. The
  token is read only from `$PA_API_TOKEN` or `/home/Carix/.autopilot/pa_api.json`,
  never from the repository, and never reaches a report (exceptions are
  logged by type name only). Without a token it falls back to load average
  (defer at `>= 2.00` per CPU) and refuses heavy work when no signal exists.
  Scans are additionally bounded (20000 files, 4000 sandbox files, 2 MB per
  patched file).
* *Backup manifest*: targets copied to `/home/Carix/autopilot_backups/<task>/round<NN>-<utc>/files/`
  plus `backup_manifest.json` holding pre-change SHA256 per file. Each copy is
  re-hashed and compared; a mismatch aborts before any write. The runner
  refuses to back up if `backup_root` resolves inside the repository, so
  backups cannot be pushed.
* *Whitelist*: `whitelist_roots` is **empty by default**, which disables
  SAFE_PATCH entirely until the owner declares the real writable directories.
  Every declared file must resolve inside a configured root (realpath-based,
  so symlinks cannot escape).
* *Targets*: each declared file must already exist as a regular file; its
  SHA256 is captured and written into the report before anything changes.

**5. READ_ONLY runs automatically.** No manifest, or an invalid one, degrades
to READ_ONLY: integrity observations only, `PRODUCTION_CHANGED: NO`.

**6. SAFE_PATCH gate.** Applied only when backup PASS, whitelist PASS, sandbox
PASS, all tests PASS, UA-0001…UA-0008 unchanged, CRM integrity PASS or not
applicable, and — after apply — unexpected changes `= 0`. The sandbox is a
temporary copy of the production slice; the patch is applied there first and
the resulting diff must equal `allowed_files` exactly (no extra, no missing).
Seven tests are mandatory on every patch round regardless of the manifest:
`sandbox_diff_matches_manifest`, `no_forbidden_patterns`, `no_secrets_in_patch`,
`file_size_guard`, `ua_baseline_unchanged`, `crm_db_untouched`,
`no_production_publication`.

**7. CRITICAL never auto-applies.** The effective mode is always the stricter
of the task's `MODE:` and the manifest's `mode`, so a manifest cannot downgrade
a CRITICAL task. CRITICAL performs the full read-only preparation and stops at
`STATUS: WAITING_OWNER_APPROVAL`, `PRODUCTION_CHANGED: NO`,
`OWNER_APPROVAL_REQUIRED: YES`. Approval is an owner-written file outside the
repository, bound to the manifest SHA256; editing the manifest invalidates it.
Even with approval, runner v1 does not execute CRITICAL automatically —
`--apply-critical` exits with a notice, so the approved change stays under
explicit owner supervision.

**8. Automatic rollback.** Any post-apply failure (content mismatch,
unexpected change, protected-baseline violation, CRM failure) restores every
file from the backup and re-verifies the pre-change SHA256. Success is
recorded as `ROLLBACK: PASS` with `PRODUCTION_CHANGED: NO` and the file list
cleared. A failed rollback escalates to `WAITING_OWNER_APPROVAL` with an
explicit warning rather than being silently reported as fine.

**9. One normalized report.** `python/report_NNN.txt` ends with exactly the
block mandated by `docs/UA_ART_AUTOPILOT_V1.md` (`TASK_ID:` … `STATUS:`),
preceded by the execution log, per-test PASS/FAIL lines and the CPU guard
state. The runner stages that single file, commits, and pushes with retry
backoff (2s, 4s, 8s, 16s).

**10. Nothing sensitive reaches GitHub.** Before committing, the report is
scanned for secret shapes (GitHub/Telegram/AWS tokens, private keys,
`password=`, `api_key=`, bearer headers) and the push is refused on a hit. The
staged set must then contain exactly the report file and nothing denylisted;
otherwise the index is reset and the push aborts. Backups, state, tokens and
the cron log all live outside the clone by configuration.

## Production protections

* **UA-0001…UA-0008**: SHA256 inventory stored outside the repository
  (`--init-inventory`), compared before **and** after every patch round. A
  violation fails the round and, in SAFE_PATCH, triggers rollback (self test
  scenario 10).
* **UA-0009**: exercised only in the sandbox; `UA_0009_READY` is reported as
  `YES` solely when every gate passed. No publication path exists in the
  runner.
* **No production publication**: the mandatory `no_production_publication`
  test refuses patches containing `publish(`, `deploy(`, or mass-regeneration
  markers, routing them to CRITICAL.
* **No journal_mode change**: `PRAGMA journal_mode` in patch content is a
  forbidden pattern (self test scenario 5). `crm.db` is opened strictly
  read-only (`file:...?mode=ro`) for `quick_check` and `journal_mode`, the
  value is baselined, and any later change reports `CRM_INTEGRITY: FAIL`.
  Database files can never appear in `allowed_files` (denylist + explicit
  test).

## Verification performed in this environment

`python3 cloud/autopilot_runner.py --self-test` → **54 passed, 0 failed**.
Coverage: path-safety and denylist units; READ_ONLY auto-run; CRITICAL
escalation and owner stop; SAFE_PATCH happy path; failing test blocks apply;
`journal_mode` content blocked; incomplete manifest refused; database target
refused; free-form test command refused; traversal refused; protected-baseline
violation blocks the patch; unexpected change detected with automatic verified
rollback; report field completeness; empty whitelist disabling patching.

Two defects were found by the self test during development and fixed: the HTML
checker silently tolerated unclosed inner tags, and the report file was
rewritten after commit (which would have left the clone dirty and broken the
next fast-forward).

An end-to-end run against a synthetic clone and production tree reproduced the
intended task_001 behavior: a SAFE_PATCH manifest was escalated to CRITICAL by
the task's `MODE:`, all gates reported PASS, the backup landed outside the
repo, `python/report_001.txt` was written, and the production file was left
byte-identical with `STATUS: WAITING_OWNER_APPROVAL`.

The repository was scanned with the runner's own scanner: zero secret matches
and zero denylisted files.

## Assumptions the owner must confirm

1. `production_root` is a placeholder (`/home/Carix/ua_art`). The real UA ART
   path is not visible from Cloud.
2. `whitelist_roots` ships empty on purpose. Until the owner lists the real
   card/template directories, SAFE_PATCH reports `WHITELIST: FAIL` and writes
   nothing. This is intended for round 1, not a defect.
3. `crm_db_path` ships empty; CRM checks report `NOT_APPLICABLE` until set.
4. `protected_globs` assumes UA card files are named `UA-000N*`.
5. A repository-root `.gitignore` is recommended (content in
   `runner_install.md` §11) but was not added, since this round is limited to
   `cloud/`.

## Owner actions required

Nothing to approve in this round — no CRITICAL action was taken or is pending.
The next round needs only configuration input (items 1–4 above) before the
runner can be armed on PythonAnywhere.

---

RUNNER_CODE_READY: YES
NO_SECRETS_IN_REPO: PASS
READ_ONLY_MODE: PASS
SAFE_PATCH_GATES: PASS
CRITICAL_OWNER_GATE: PASS
ROLLBACK_DESIGN: PASS
CPU_GUARD: PASS
PRODUCTION_WRITE_PERFORMED: NO
NEXT_ACTION: Owner installs the runner on PythonAnywhere per cloud/runner_install.md (clone, --self-test, runner_config.json with real production_root and whitelist_roots, optional pa_api.json, --init-inventory), then runs `python3 cloud/autopilot_runner.py --dry-run --no-push` and reports the output so ChatGPT can issue task_002.
