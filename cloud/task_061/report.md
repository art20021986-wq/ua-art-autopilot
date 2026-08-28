# TASK 061 — CRM-AI-CARD-001 — Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What was requested

Owner approved CRM-AI-CARD-001 (IMPLEMENT_AND_INSTALL, P0): deterministic,
zero-token local recognition of photo/screenshot/text/voice into CRM draft
fields filtered against the live `ai_filter.ALLOWED` schema, opening the
draft immediately and never routing owner intake to staff. Patch scope was
named as `/home/Carix/team_bot.py` and `/home/Carix/local_ocr.py`.

## What Claude/Cloud actually did

Per the repository's mandatory protocol, Claude/Cloud never touches UA ART
production directly and all code/patches live under `cloud/`. `/home/Carix/`
is a live PythonAnywhere production path, not reachable or readable from this
workspace. Therefore:

1. Implemented the full deterministic recognition engine as a new,
   self-contained module: `cloud/task_061/ai_card_recognition.py`. It uses
   only regex/keyword matching (no network calls, no ML, no tokens) to
   extract: brand, model, year, VIN, mileage, fuel_type, engine_cc,
   transmission. It filters strictly against a caller-supplied
   `allowed_keys` set (intended to be the live `ai_filter.ALLOWED`), so
   nothing outside the live CRM schema is ever produced, and nothing is
   invented for fields that are not found in the source text.
2. Wrote exact, minimal, additive patch instructions for the two named
   production files (`cloud/task_061/local_ocr_patch_notes.md` and
   `cloud/task_061/team_bot_integration_patch.md`), including required
   backup file names (`*.bak_task061`), compile checks, the mandatory
   read-only CRM integrity / UA-0009 presence check, and the requirement to
   restart only the single production bot task — nothing else.
3. Wrote and ran (offline, in this workspace) `cloud/task_061/
   test_ai_card_recognition.py`, which verifies the exact acceptance case:
   Kia, K5, 2018, VIN KNAGU416BKA324445, 198000 km, LPG, 2000 cc, automatic —
   all recovered correctly and unrelated keys are filtered out; unknown/empty
   text yields an empty dict (no invention); narrowing `allowed_keys`
   correctly restricts output to the live schema.

## What Claude/Cloud did NOT do (and why)

- Did not open, read, or write `/home/Carix/team_bot.py` or
  `/home/Carix/local_ocr.py`. These are production files on PythonAnywhere;
  Claude/Cloud has no access to them and is prohibited from touching
  production directly.
- Did not write to `crm.db`.
- Did not restart, reload, or touch any PythonAnywhere task or web app.
- Did not publish or otherwise change UA-0009 or UA-0010.
- Did not run the CRM integrity / UA-0009 presence check against the live
  system (no production access); the check procedure is specified for the
  installer to run.

## Installation (must be performed by the owner-authorized PythonAnywhere
install step, following the notes above)

1. Backup both files with `.bak_task061` suffix.
2. Copy `ai_card_recognition.py` to `/home/Carix/`.
3. Apply the additive wrapper in `local_ocr.py` per
   `local_ocr_patch_notes.md`.
4. Apply the additive owner-intake integration in `team_bot.py` per
   `team_bot_integration_patch.md`, ensuring the staff/manager handoff path
   is never invoked for owner intake.
5. `python3 -m py_compile` both files; abort and roll back on any failure.
6. Run the existing read-only CRM integrity / UA-0009 presence check; abort
   and roll back on failure.
7. Restart only the single production bot task.
8. Verify the acceptance case manually against the supplied screenshot.

## Memory markers (included verbatim as required)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

Consistent with canonical memory: production_write=NO, crm_write=NO,
ua0009_safe_to_publish=NO. This task does not touch UA-0009/UA-0010 and
does not write CRM or production.
