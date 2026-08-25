# TASK 003 — UA-0009 RELEASE GATE: SQLITE + CRM COMPLETENESS + SANDBOX

MODE: READ_ONLY
MAX_ROUNDS: 10

## Owner directive
Mobile internet is available; do not wait for Wi-Fi. Start the three release-gate tracks for UA-0009 now, with minimum owner involvement.

## Goal
Produce one read-only PythonAnywhere probe that determines exactly what remains before UA-0009 can be safely published. Do NOT publish or modify production in this task.

## Three tracks

### 1. SQLite stability decision
Read current crm.db in URI mode=ro and inspect source text only. Determine:
- current journal_mode and quick_check
- current busy_timeout configuration from source text where safely discoverable
- stroy3.py and stranica.py connection lifetime facts (connect, SELECT/fetch, last DB use, close, long work while reader lives)
- evidence for/against targeted early-close fix
- evidence for/against WAL as the safer architecture change
- exact recommendation: TARGETED_FIX / WAL_CANDIDATE / MORE_PROOF_NEEDED
No journal_mode change in this task.

### 2. UA-0009 CRM completeness
Read crm.db mode=ro. Locate UA-0009 by auto_number and VIN if present. Print all non-secret fields needed for publication and explicitly classify:
- PRESENT
- MISSING
- OWNER_INPUT_REQUIRED
- CAN_DERIVE_SAFELY_FROM_EXISTING_UA0009_DATA
Do not copy values from another vehicle.
Check at least: auto_number, VIN, make/model/year, mileage, engine/fuel, transmission, drivetrain, color, price, stage/status, published, photos/videos/diagnostic references.
Check VIN duplicates and auto_number duplicates.

### 3. UA-0009 sandbox readiness
Without importing or executing UA ART modules and without writing production:
- locate existing UA-0001..UA-0008 public card/site/diag files
- locate any UA-0009 public files
- identify the actual generator/source paths used by the existing cards from source text/config evidence
- determine whether enough UA-0009 data exists to build a sandbox card
- compute protected inventory/SHA for UA-0001..UA-0008 where bounded and safe
- state the exact sandbox build prerequisites and release acceptance gates

## Deliverables under cloud/
Create:
1. `cloud/ua0009_release_probe.py` — Python 3.10, stdlib only, strictly read-only to production; writes only `/home/Carix/video/ua0009_release_gate.txt`.
2. `cloud/ua0009_release_report_spec.md`
3. `cloud/cloud_report_003.md`
4. update `cloud/latest_status.md`

The probe must not read or print secrets, tokens, private keys, customer PII unrelated to UA-0009, or database blobs/base64 payloads. For media/list fields print counts and safe filenames/paths only.

## Mandatory final block from probe
SQLITE_QUICK_CHECK: PASS/FAIL
SQLITE_JOURNAL_MODE: ...
SQLITE_RELEASE_RECOMMENDATION: TARGETED_FIX/WAL_CANDIDATE/MORE_PROOF_NEEDED
UA0009_EXISTS_IN_CRM: YES/NO
UA0009_VIN_DUPLICATES: <n>
UA0009_AUTO_NUMBER_DUPLICATES: <n>
UA0009_REQUIRED_FIELDS_COMPLETE: YES/NO
UA0009_MISSING_FIELDS: ...
UA0009_OWNER_INPUT_REQUIRED: ...
UA0009_PUBLIC_FILES_EXIST: YES/NO
UA0001_0008_BASELINE_CAPTURED: PASS/FAIL
UA0009_SANDBOX_READY: YES/NO
SAFE_TO_PREPARE_FIX_TASK: YES/NO
SAFE_TO_BUILD_UA0009_SANDBOX_NEXT: YES/NO
SAFE_TO_PUBLISH_UA0009_NOW: NO
PRODUCTION_WRITE_PERFORMED: NO
DATABASE_CHANGED: NO
SITE_FILES_CHANGED: 0
NEXT_ACTION: ...

## Hard prohibitions
- no production writes
- no INSERT/UPDATE/DELETE
- no journal_mode assignment/WAL switch
- no restart
- no publication/regeneration
- no importing UA ART modules
- no direct UPDATE of UA-0009
- no copying data from another car

## Acceptance
Cloud must self-test/static-check the probe in its environment and explicitly state production paths are only verified after PythonAnywhere executes the probe. This task is the read-only release gate; subsequent task(s) may implement the proven SQLite fix and sandbox build, with CRITICAL owner approval where required.
