# TASK 058 — CRM/OCR and CRM→site incident: live read-only discovery

Status: `READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058`

This corrected package investigates two exact bot failures without changing
production:

- `Изображение сохранено, но разобрать его не получилось...`
- `CRM: страницы сайта отстали от базы, и пересобрать их не получилось.`

The first generated package was rejected by Codex audit because it used the
wrong `/home/Carix/mysite` root, contained a self-comparison fixture test, and
had no real PythonAnywhere transport or executable `main()`. Those defects are
removed here.

## Scope and owner authorization

The owner approved read-only diagnosis and subsequently authorized creation
and launch of the attached Kia K5 as **UA-0010**. This package records and
checks that authorization but deliberately does not publish UA-0010. A live
write/rebuild is permitted only in the later, isolated publication task after
this receipt proves the exact production paths and current database/site
state. UA-0009 is checked at the same time under the standing safety rule.

## Exact vehicle fixture contract

- Kia K5, 2018, II покоління (FL)
- USD 11,400; UAH 510,720
- 198,000 km; LPG/gas; 2.0 L
- VIN is tested only through SHA-256 in evidence
- transmission and location are cropped and must stay null/unknown

The two committed JPEG fixtures are mandatory. Tests verify their independent
known SHA-256, exact byte size, and dimensions; missing fixtures fail rather
than skip.

## Components

- `live_discovery.py`: Python 3.10 standard-library-only live reader. It reads
  only exact regular, non-symlink, non-hardlink allowlisted files under
  `/home/Carix`; opens `/home/Carix/crm.db` with SQLite `mode=ro` plus
  `PRAGMA query_only=ON`; snapshots source/database/site identity before and
  after; and writes only one bounded receipt inside the task safe inbox.
- `allowlist.json`: exact production scope. Primary pages are under
  `/home/Carix/video` and `/home/Carix/site`; `/mysite` is forbidden. Existing
  UA-0001…UA-0008 pages are required, while UA-0009 and UA-0010 are optional
  candidates whose absence/presence is evidence.
- `task058_readonly_controller.py`: real PythonAnywhere REST transport. It
  validates the fresh safe-inbox manifest and exact remote bytes, creates one
  temporary allowlisted trigger, polls one receipt, validates it fail-closed,
  relays bounded evidence, then deletes both trigger and receipt in `finally`.
- `tests/`: 29 offline tests covering fixture drift, path attacks, incomplete
  inventory, read-only database identity, receipt sensitivity/staleness,
  false-green prevention, UA-0010 scope, transport allowlists and cleanup.
- `run_tests.py`: compiles the entire package and requires 10 consecutive full
  passes.

## Exact remote command

```text
python3.10 /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/live_discovery.py --allowlist-file /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/allowlist.json --output /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/task_058_live_discovery_receipt.json
```

No shell wildcard, `sudo`, production redirect, import of production modules,
database write, rebuild, service reload, or page publication exists in this
round.

## Verified offline result

`29 tests × 10 consecutive runs = 290 assertions-suite executions`, all PASS.

Safety markers:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
SITE_REBUILT: NO
SERVICE_RELOADED: NO
OCR_FIX_INSTALLED: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
UA_0010_PUBLISHED: NO
```
