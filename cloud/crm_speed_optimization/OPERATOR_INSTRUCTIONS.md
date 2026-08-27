# CRM-SPEED-001 Gate A operator instructions

## What this package is

This package contains a candidate optimization for the administrative CRM (text-only admin routes, a debounce queue instead of subprocess rebuild storms, short-lived SQLite ownership, and singleton guards) plus a fail-closed Gate A analysis tool. It does not modify production. It only reads bounded production files and writes evidence beneath an isolated QA directory.

## What Gate A does

Running the launcher performs, in order:

1. Resolves eleven bounded required inputs under `/home/Carix` and rejects symlinks.
2. Verifies the existing safety backup archive by SHA-256.
3. Builds anchor-checked, AST-based patched candidate copies of usercustomize.py (both Python versions), start_safe.py, run_all.py, avtoperedacha.py, samokontrol.py, and cars_ui.py inside `/home/Carix/qa/crm_speed_task020/<run_id>/`.
4. Compiles every candidate.
5. Statically proves the four administrator media routes have no reachable automatic media-send call, proves the debounce queue collapses bursts, proves the singleton guard rejects a duplicate start, and proves the transform is deterministic across ten repetitions.
6. Performs a bounded, read-only SQLite inspection (`PRAGMA query_only = ON`) to record non-PII UA-0009 evidence and confirms the database file is byte-identical before and after.
7. Writes `receipt.json` and `REPORT.md` with `PRODUCTION_WRITE: NO`.

Missing or ambiguous anchors leave that specific candidate file unmodified and the whole run is reported BLOCKED, never guessed.

## How to run it

On PythonAnywhere Bash, a single no-argument command:

```
python3 /home/Carix/cloud_review/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py
```

(Place the package wherever it is copied for review; the launcher only reads the eleven fixed production paths listed in the specification and writes beneath `/home/Carix/qa/crm_speed_task020/`.)

The command can be repeated safely. Each run creates its own timestamped subdirectory and never deletes a previous run.

## What Gate A never does

- It never edits any file under `/home/Carix` outside the QA directory.
- It never touches `/home/Carix/crm.db`.
- It never restarts the bot, web app, or any scheduled task.
- It never writes into `/home/Carix/site`, `/home/Carix/video`, or `public_html`.
- It never publishes UA-0009.
- It never installs anything into production.

## After Gate A

If the run reports `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`, that means the candidates compiled and passed the static/behavioral checks in isolation. It is not a production fix. Installing any candidate into production (Gate B) requires an independent review by ChatGPT and explicit owner approval, and is out of scope for this package.

If the run reports `BLOCKED`, read the `blockers` list in `receipt.json`; each blocker names the exact missing input, anchor mismatch, or failed check.
