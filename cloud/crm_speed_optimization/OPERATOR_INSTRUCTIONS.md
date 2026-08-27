# OPERATOR INSTRUCTIONS — CRM-SPEED-001 Gate A package (round 3)

## What this package is

A reviewable, offline-testable Gate A candidate generator and evidence
aggregator for CRM-SPEED-001. It has NOT been executed against production.
Gate A itself has never run on PythonAnywhere from this package.

## Before any execution

1. Independently review every file under `cloud/crm_speed_optimization/`.
2. Run `python3 -m py_compile *.py` on the target Python version(s)
   (3.10 and 3.13).
3. Run `python3 -m unittest test_crm_speed_gate_a -v` at least 10
   consecutive times and require 100% pass on every run.
4. Only after independent review and explicit owner approval may
   `RUN_GATE_A_CRM_SPEED.py` be considered for execution on
   PythonAnywhere. That execution is a separate, owner-approved action
   outside the scope of this cloud/ delivery.

## What Gate A will do when eventually executed (Gate B still required for install)

- Read bounded, explicitly listed production inputs (never a recursive
  scan) and reject any symlink among them.
- Verify the existing backup archive hash before doing anything else.
- Build candidate, text-only, non-executing transformations of
  `cars_ui.py`, `usercustomize.py`, and `avtoperedacha.py` in memory /
  inside an isolated QA run directory only.
- Compile and statically re-scan every candidate; any dynamic dispatch,
  aliasing, or unresolved callable in the four admin routes blocks the
  whole run.
- Probe the exact configured UA-0009 HTTPS URL and require a clean,
  no-redirect 404/410; any network ambiguity blocks the run.
- Compare bounded site/public inventories and protected file fingerprints
  before and after; any unexpected change blocks the run.
- Emit a JSON receipt and Markdown report inside the run directory only,
  ending in `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` or `BLOCKED`.

## What this package never does

- It never writes to `/home/Carix` outside the resolved QA run directory.
- It never restarts the bot, web app, or any scheduled task.
- It never publishes UA-0009.
- It never installs anything into production. Installation is Gate B, a
  fully separate, owner-approved action after independent review of Gate A
  evidence.
