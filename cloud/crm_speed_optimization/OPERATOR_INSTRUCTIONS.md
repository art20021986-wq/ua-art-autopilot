# OPERATOR_INSTRUCTIONS — CRM-SPEED-001 Gate A (round 2)

## What this package is

A fail-closed, read-mostly Gate A evaluator. It never installs anything
and never writes outside its own QA run directory
(`/home/Carix/qa/crm_speed_task020/run_*`).

## Before running anything

1. Run the offline test suite first, on the exact Python version used in
   production (3.10 and/or 3.13), from a throwaway checkout:
   ```
   python3 -m unittest cloud/crm_speed_optimization/test_crm_speed_gate_a.py -v
   ```
   Repeat at least 10 full times. Every run must show 0 failures/errors.

2. Set the canonical UA-0009 URL explicitly — Gate A will BLOCK rather
   than guess it:
   ```
   export UA0009_CANONICAL_URL="https://<exact-canonical-domain>/UA-0009.html"
   ```

## Running Gate A (read-mostly evaluation)

```
python3 cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py
```

This creates a unique directory under
`/home/Carix/qa/crm_speed_task020/run_<timestamp>_<pid>/` and writes
`receipt.json` and `report.md` there only. It exits 0 only when every
required evidence entry is `passed: true` and the final status is
`GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`. Any BLOCKED evidence makes it
exit nonzero.

## Verifying a receipt independently

```
python3 cloud/crm_speed_optimization/verify_gate_a.py /home/Carix/qa/crm_speed_task020/run_.../receipt.json
```

## What Gate A does NOT do

- It does not modify `/home/Carix/crm.db`.
- It does not modify any file under `/home/Carix/site`,
  `/home/Carix/video`, or `/home/Carix/public_html`.
- It does not restart the bot, web app, or any scheduled task.
- It does not publish UA-0009.
- It does not install any candidate file into production. That is a
  separate Gate B decision requiring independent review and explicit
  owner approval.

## If Gate A reports BLOCKED

Read `report.md`/`receipt.json` for the exact evidence entry and reason.
Do not attempt to force a pass by editing the receipt. Fix the underlying
condition (e.g. restore a missing required input, resolve DNS/HTTP
issues for the UA-0009 probe, or accept that a transform correctly
BLOCKed on ambiguous real source) and re-run.
