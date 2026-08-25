# TASK 002 — ARM AUTOPILOT SAFELY FROM REAL PYTHONANYWHERE LAYOUT

MODE: READ_ONLY
MAX_ROUNDS: 10

## Goal
Prepare the next automation round without changing UA ART production. The runner is installed and its first dry-run completed with `PRODUCTION_CHANGED: NO`, `SAFE_PATCH_ARMED: NO`, `STATUS: CONTINUE`.

We now need facts from the real PythonAnywhere tree before any writable whitelist or CRITICAL operation can be enabled.

## Required Cloud deliverables
Create only under `cloud/`:

1. `cloud/discover_layout.py` — **strictly read-only** Python 3.10 script for PythonAnywhere.
2. `cloud/discover_layout_report_spec.md` — exact fields the script prints.
3. `cloud/cloud_report_002.md` — explain the approach and safety guarantees.

Do not create a production patch manifest in this round.

## discover_layout.py requirements
The script must not import UA ART modules and must not execute any project code. It may only inspect filesystem metadata, source text and SQLite in read-only URI mode.

It must print and write `/home/Carix/video/autopilot_discovery.txt` with these facts:

### A. Repository / runner
- git clone path and current branch
- runner path exists
- current `/home/Carix/.autopilot/runner_config.json` parsed values
- whitelist_roots current value
- latest task id

### B. UA ART production layout
Discover, do not assume:
- real root containing `crm.db`
- paths containing `UA-0001...UA-0009` HTML files
- paths containing diagnostic HTML files
- paths containing catalog/home generated HTML
- paths containing generator source files such as `stranica.py`, `stroy3.py`, `yadro.py`, `master_card.py` if present
- count of protected UA-0001...UA-0008 files by directory
- whether UA-0009 public files already exist

### C. CRM
Open `crm.db` only with SQLite URI `mode=ro`.
Print:
- exact absolute path
- `PRAGMA quick_check`
- `PRAGMA journal_mode`
- no writes, no VACUUM, no checkpoint
- whether `cars` contains `auto_number='UA-0009'`
- published state for UA-0009 if schema supports it

### D. Candidate safe whitelist
Do NOT enable anything. Produce recommendations only:
- `RECOMMENDED_PRODUCTION_ROOT`
- `RECOMMENDED_SITE_ROOTS`
- `RECOMMENDED_WHITELIST_ROOTS_SAFE_PATCH`
- explicitly exclude database files, `.ssh`, `.env`, secrets, backups, logs and media unless a future task explicitly requires them
- distinguish generated HTML roots from generator/source roots

### E. Current SQLite/WAL readiness facts
Read only source and DB state. Print:
- current journal_mode
- whether `stroy3.py` and `stranica.py` contain long-lived read-only DB connections (based on source-text analysis only; do not import them)
- whether previous evidence supports WAL as candidate architecture change
- **do not change journal_mode**

### F. Safety proof
End with exactly:

`PRODUCTION_WRITE_PERFORMED: NO`
`CRM_OPEN_MODE: READ_ONLY`
`PROJECT_MODULES_IMPORTED: NO`
`SITE_FILES_CHANGED: 0`
`DATABASE_CHANGED: NO`
`SAFE_TO_CONFIGURE_RUNNER_NEXT: YES/NO`
`NEXT_ACTION: ...`

## Hard prohibitions
- No production write
- No `INSERT/UPDATE/DELETE`
- No `PRAGMA journal_mode=` assignment
- No WAL switch
- No git push from PythonAnywhere in this discovery script
- No restart of `start_safe.py`
- No publication
- No regeneration
- No importing `db.py`, `stranica.py`, `stroy3.py`, `yadro.py`, `master_card.py`, `team_bot.py`
- No reading or printing secrets/tokens/private keys

## Acceptance
Cloud should run static/self-tests in its own environment where possible, but must state clearly that PythonAnywhere production paths cannot be verified until the script runs there.

The script should be safe for the owner to execute once manually, or for a future runner extension to invoke as a registered internal read-only test.
