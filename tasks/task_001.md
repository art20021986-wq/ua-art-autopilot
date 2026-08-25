# TASK 001 — Build PythonAnywhere Autopilot Runner

MODE: CRITICAL
MAX_ROUNDS: 10

## Objective
Create the first safe runner for `/home/Carix/autopilot` on PythonAnywhere. The runner must synchronize through this GitHub repository and reduce owner actions to visual/critical approvals only.

## Required behavior
1. Work from a local clone of `art20021986-wq/ua-art-autopilot`.
2. Read the latest task from `tasks/` and Cloud output from `cloud/`.
3. Never execute arbitrary files automatically. Only execute a patch when its manifest explicitly names:
   - task id
   - mode
   - allowed files
   - expected tests
   - rollback source
4. Before any SAFE_PATCH/CRITICAL preparation:
   - check CPU quota / local load safeguard
   - create backup manifest
   - verify whitelist
   - verify target files exist and capture SHA256
5. READ_ONLY may run automatically.
6. SAFE_PATCH may apply only after backup + whitelist + sandbox + tests PASS and unexpected changes = 0.
7. CRITICAL must never auto-apply. It must stop at `WAITING_OWNER_APPROVAL`.
8. On SAFE_PATCH failure, rollback automatically and record result.
9. Write one normalized report to `python/report_001.txt` and commit/push it.
10. Do not put secrets, `crm.db`, tokens, customer data, media, or backups into GitHub.

## Production protections
- UA-0001...UA-0008 are protected baseline items.
- Any card/site task must compare protected SHA/inventory before and after.
- UA-0009 must be sandboxed before publication.
- No production publication in this task.
- No SQLite journal_mode change in this task.

## Deliverables from Cloud
Place in `cloud/`:
- `autopilot_runner.py`
- `runner_install.md`
- `patch_manifest.example.json`
- `cloud_report_001.md`

## Acceptance criteria
Cloud report must end with:
`RUNNER_CODE_READY: YES/NO`
`NO_SECRETS_IN_REPO: PASS/FAIL`
`READ_ONLY_MODE: PASS/FAIL`
`SAFE_PATCH_GATES: PASS/FAIL`
`CRITICAL_OWNER_GATE: PASS/FAIL`
`ROLLBACK_DESIGN: PASS/FAIL`
`CPU_GUARD: PASS/FAIL`
`PRODUCTION_WRITE_PERFORMED: NO`
`NEXT_ACTION:`

Do not modify the UA ART production project yet. This task builds the automation bridge only.
