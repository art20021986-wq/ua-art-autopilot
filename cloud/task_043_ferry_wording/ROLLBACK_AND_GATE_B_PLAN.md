# TASK 043 — Rollback and Gate B plan (non-executable in this round)

This plan is documentation only. Nothing in this file is executed by this task round.

## Rollback (isolated Gate A staging/preview/report only)

1. `gate_a.build_gate_a` already rolls back every file it wrote during a failed call automatically (see `written_paths` cleanup in `gate_a.py`).
2. For a full manual rollback of a completed Gate A run, delete only the exact per-task directories:
   - `/home/Carix/video/preview/task-043-ferry-wording/`
   - `/home/Carix/video/reports/task-043-ferry-wording/`
   - `/home/Carix/autopilot_runs/task_043_ferry_wording/`
3. No production path, no `crm.db`, and no live UA-0001..UA-0009 page is ever touched by Gate A, so no production rollback is ever required by this task.

## Gate B (future, separate, owner-approved task only)

Gate B is explicitly **out of scope** for this task and is not designed, wired, or triggerable by anything in this package. A future Gate B task must, at minimum:

1. Present the full, real, per-card Gate A receipt (all nine UA IDs, real stages, real before/after hashes) to the owner for explicit review.
2. Obtain explicit owner approval for each canonical source file to be modified in production (e.g. `stranica.py`, `yadro.py`, `master_card.py`, specific UA-000N.html pages, BOT CRM renderers).
3. Use a reviewed, tested, atomic production-write mechanism with a verified rollback path and before/after hash verification against the exact same hashes recorded in the Gate A receipt.
4. Never be triggered automatically by this controller or this workflow template.

Until a separate task explicitly authorizes Gate B, `GATE_B_EXECUTED` remains `NO` and `UA0009_SAFE_TO_PUBLISH` remains `NO`.
