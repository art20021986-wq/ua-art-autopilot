# GATE B PLAN (PRODUCTION) — TASK 072 — NOT EXECUTED

This plan is prepared for a future, owner-approved Gate B. It is **not executed** by
this task and requires separate written owner approval, per the OWNER_DIRECTIVE
constraints and the fact that Gate A itself is currently BLOCKED (see GATE_A_REPORT.md).

## Preconditions before Gate B may even be scheduled

1. Gate A must first reach a genuine PASS against the **real** downloaded live files and
   real temp copy of `crm.db` (see "Required to unblock Gate A" in GATE_A_REPORT.md).
2. Owner must issue an explicit, separate written Gate B approval referencing this task.

## Planned Gate B steps (once unblocked and approved)

1. Take a full production backup of `crm.db` (file-level copy) and record its SHA256
   before any change.
2. Apply the SHA+AST-verified patch to `db.py`, `cars_ui.py` on the live filesystem only
   through the standard PythonAnywhere deployment mechanism (not via this Claude/Cloud
   worker), during a low-traffic window.
3. Deploy `writer.py` and `queue_sidecar.py` as new standalone modules under
   `/home/Carix`, imported by the patched `cars_ui.py`/`db.py` call sites only at the
   exact points identified by the AST anchors.
4. Run the same offline test suite (`tests/`) against a **real temporary copy** of the
   post-patch `crm.db`/code, verifying: `cars_count == 11`, `UA-0009` hash unchanged,
   `PRAGMA quick_check=ok`, all direct/legacy command paths, and queue drain under load.
5. Reload the web app.
6. Manually verify one real card in the live Telegram bot with a short owner-supplied
   test description, confirm `✅ Описание сохранено`, confirm the text is visible in the
   card, then optionally revert that one field if it was only a test.
7. Keep the pre-change backup and rollback plan (`installer.py rollback`, restoring the
   patched files only — `crm.db` itself is never touched by the patch) available for at
   least 72 hours after deployment.
8. Record the Gate B evidence (hashes, timings, before/after `cars_count`, `UA-0009`
   hash) under a new `cloud/task_072/gate_b_evidence/` directory in a follow-up task.

Production is NOT touched by TASK 072 itself. This plan is descriptive only.
