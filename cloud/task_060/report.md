# TASK 060 — Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What was requested
After installing the TASK 059 patch, live inbox #126 (Kia K5 2018) still triggered
"Передал менеджеру" / "менеджеров в системе нет" instead of an AI-built CRM preview.
TASK 060 requires the AI to always parse text/photo/voice intake, never hand off to
staff, normalize multiple AI result shapes against the runtime `ai_filter.ALLOWED`
set, and show a preview with ✅ Разместить for any partial result with ≥1 readable
field — without touching CRM/site/gallery before confirmation.

## What was delivered in this round
- `cloud/task_060/ai_intake_patch.py` — self-contained normalization + preview
  logic implementing all 6 requirements:
  1. `process_intake()` never routes to staff; `route_to_staff` is hardcoded False
     and no "no managers in system" code path exists in this module.
  2. `get_allowed_keys()` reads `ai_filter.ALLOWED` at runtime; nothing else is
     hardcoded, so future ALLOWED changes are respected automatically.
  3. `normalize_ai_result()` supports nested `fields[key].value`, scalar
     `fields[key]`, and flat top-level allowed-key JSON, silently dropping
     unknown keys and empty/missing values instead of rejecting the whole result.
  4. The module intentionally does not call any AI/vision API itself — it is a
     pure post-processing layer, preserving the existing single-call constraint
     (one vision request, max_tokens<=500, no second review). Deadline
     enforcement (photo<=7s, text<=2s, voice<=10s) stays in the caller's
     existing timeout wrapper; this patch adds no extra network calls that
     could push those budgets over.
  5. `process_intake()` returns `ok=True` and a `preview_text` as soon as at
     least one allowed field is found; it performs no DB write, no site
     rebuild, no gallery insert, and no publish action.
  6. Verified against the exact Kia K5 case from inbox #126 (see tests).
- `cloud/task_060/test_ai_intake_patch.py` — offline tests, all passing locally
  (no network, no CRM, no PythonAnywhere access), including the literal Kia K5
  2018 / $11 400 / 510 720 грн / 198 000 km / LPG 2.0 / automatic /
  VIN KNAGU416BKA324445 case: result is `ok=True`, all 10 fields present,
  `route_to_staff=False`.

## What was NOT done in this round (owner action required)
Claude/Cloud never writes to production directly. This module is ready to be
wired into the live bot's photo/text/voice handler (replacing whatever logic
currently produces the "Передал менеджеру" message), but the actual install on
PythonAnywhere — copying the file, taking a backup, applying atomically,
restarting the bot process, and confirming inbox #126 now renders a preview —
must be performed by the owner-authorized deploy step, not by Claude/Cloud.

Required manual/deploy-side steps (to run under existing Gate B controls):
1. `cp <live_intake_module>.py <live_intake_module>.py.bak.$(date +%s)` (backup).
2. Replace the manager-handoff branch in the live intake handler with a call to
   `ai_intake_patch.process_intake(raw_ai_result, ai_filter)`.
3. If `result["ok"]` is True, send `result["preview_text"]` with the
   `✅ Разместить` button; otherwise ask for another photo/voice/text, never a
   manager message.
4. Restart the bot process.
5. Re-send inbox #126's Kia K5 photo (or replay the stored raw AI JSON) and
   confirm the preview shows all 10 fields with no manager message, and that
   CRM DB row count / site files are unchanged before pressing ✅ Разместить.
6. Record the before/after evidence (timestamps, restart log, diff of CRM row
   count) back into `cloud/task_060/`.

UA-0010 was not published, in line with the task's explicit instruction.

## Result
PASS (offline): normalization/preview logic implemented and unit-tested against
the exact failing case, with staff handoff structurally removed from this code
path.
BLOCKED (production install): live PythonAnywhere installation, bot restart,
and live re-test of inbox #126 require an owner-authorized deploy step, which
Claude/Cloud does not perform directly per repository policy.
