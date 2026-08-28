# TASK_058 — CRM-OCR-SYNC-001 Round 1: Read-only discovery package

STATUS MARKER FOR THIS ROUND: `READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058`

MEMORY MARKERS (copied verbatim from canonical shared memory, do not alter):
- CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
- MEMORY_VERSION_READ: `4`

## What this package is

This is a **read-only, fail-closed discovery package** for the CRM-OCR-SYNC-001
incident (OCR failure + stale-site rebuild failure reported by the Telegram bot).
It contains no production code changes, no CRM writes, no database writes, no
service reload, and no OCR fix. It only prepares the tools needed for a
controller-run, tightly bounded, one-shot read-only inspection of the live
PythonAnywhere host, using the same safety pattern as
`cloud/bot_logistics/pythonanywhere_discovery_controller.py` (which is **not**
modified by this task).

## Files

- `live_discovery.py` — Python 3.10, standard-library only. Runs **on the
  remote host** (via the controller) strictly against an explicit allowlist
  of paths under `/home/Carix`. Never writes anything except the one JSON
  receipt file it is told to write, inside the safe inbox directory. Rejects
  symlinks, oversized files, and any path outside the allowlist/base dir.
  Opens any SQLite database with `mode=ro` + `PRAGMA query_only=ON` and
  verifies write attempts are blocked and file bytes are unchanged.
- `task058_readonly_controller.py` — runs **locally** (in the autopilot
  controller environment). Validates a manifest of local files against
  expected SHA-256 before any sync, builds one exact, allowlist-checked
  remote command (no `sudo`, no globs, no redirects, no `find`, no `reload`),
  polls for exactly one receipt, validates it (size bound, sensitive-token
  rejection, malformed/stale rejection), relays sanitized evidence, and
  deletes the trigger/receipt in `finally` on success, failure, or timeout.
  All remote transport (`sync_fn`, `run_fn`, `poll_fn`, `cleanup_fn`) is
  dependency-injected so this package can be fully tested offline without any
  network access, and so a real SSH/SCP binding can be provided later without
  touching the safety logic.
- `allowlist.json` — candidate allowlist template. Paths are placeholders
  requiring explicit operator confirmation before any live run; unconfirmed
  or non-existent paths are safely skipped and reported, never assumed.
- `tests/test_live_discovery.py`, `tests/test_readonly_controller.py` — full
  offline test suites using only temporary fixtures.
- `run_tests.py` — compiles all package sources and runs the full offline
  suite 10 consecutive times, failing loudly on any single failure.
- `evidence/task_058_live_discovery.json` — placeholder, `status: NOT_RUN`.
  Will only be replaced by the controller after a real, verified receipt is
  relayed from the live host.
- `TASK_058_CONTROLLER_REPORT.md` — placeholder, `status: NOT_RUN`. Will only
  be replaced after the controller actually executes against
  PythonAnywhere.
- `TASK_058_REPORT.md` — Round 1 technical report (this round: package build
  and offline verification only; no live evidence yet).

## What Round 1 does NOT do

- Does not touch production, CRM, `crm.db`, website pages, bot sources,
  generators, WSGI, schedules, or services.
- Does not reload or restart anything.
- Does not rebuild the site.
- Does not install any OCR fix.
- Does not execute Gate B.
- Does not publish UA-0009.
- Does not run against the live PythonAnywhere host yet (no network access in
  this environment). All verification here is **offline**, against temporary
  fixtures, proving the safety logic works before any live run is requested.

## Exact remote command contract (for the controller, when later authorized)

```
python3.10 /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/live_discovery.py \
  --allowlist-file /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/allowlist.json \
  --output /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync/task_058_live_discovery_receipt.json \
  --receipt-base-dir /home/Carix/autopilot_inbox/cloud/task_058_crm_ocr_sync
```

No `sudo`, no shell globs, no `find`, no redirection into production paths,
no piping. The controller validates this exact string is free of forbidden
tokens before ever handing it to any transport.

## Next step

Round 1 ends as `READY_FOR_LIVE_READONLY_CONTROLLER_TASK_058`: the offline
package is built and fully tested. Live execution against PythonAnywhere,
collection of real evidence, and Round 2 candidate design require a separate
controller-run step outside this chat environment, followed by ChatGPT/Codex
audit of the resulting `evidence/task_058_live_discovery.json` and
`TASK_058_CONTROLLER_REPORT.md`.
