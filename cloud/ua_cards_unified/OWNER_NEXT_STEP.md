# OWNER_NEXT_STEP.md — TASK_016

## What is already true

- TASK 014's corrected Gate A code has been safely regenerated as
  TASK 016 against current `main`, after the earlier non-fast-forward
  push failure was repaired.
- No production, CRM, or live card files have been touched.
- All new code is confined to `cloud/ua_cards_unified/` in this repo
  and, once delivered by the existing safe-inbox pipeline, to three
  non-public sandbox roots on PythonAnywhere.

## What has NOT happened yet

- This worker (Claude/Cloud, running outside PythonAnywhere) cannot
  itself execute `RUN_GATE_A_TASK016.py` on the PythonAnywhere host.
  It can only prepare the exact, bounded script and manifest.
- Therefore no real Gate A receipt, no real preview, and no real
  per-card pass/fail results exist yet. Maximum honest completion from
  this side is 80%.

## What needs to happen next (automated, no manual owner upload)

1. The existing GitHub → `/home/Carix/autopilot_inbox/` delivery
   mechanism (already used for TASK 013) copies
   `cloud/ua_cards_unified/` into the safe inbox.
2. An already-authorized PythonAnywhere console/task step runs:
   `python3.10 /home/Carix/autopilot_inbox/cloud/ua_cards_unified/RUN_GATE_A_TASK016.py`
   with no arguments.
3. That run produces:
   - `/home/Carix/video/reports/ua_cards_unified/progress.json`
   - `/home/Carix/video/reports/ua_cards_unified/latest_status.html`
   - `/home/Carix/ua_cards_unified_gate_a_receipt/gate_a_receipt.json`
4. Those three artifacts should be relayed back into this repository
   (e.g. into a future task's `cloud/` report) so ChatGPT/Codex can
   verify the real receipt before anyone asks the owner to look at a
   preview link.

## What the owner needs to do

Nothing right now. The owner's earlier authorization already covers
Gate A. The next concrete owner action (if any) will only be requested
after a real, verifiable Gate A receipt and reachable preview exist —
and even then, only to view the preview, never to approve Gate B in
the same step.
