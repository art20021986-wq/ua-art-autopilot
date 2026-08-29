# TASK 073 — Rejected prototype tooling

Per the R3 correction from Codex's real GET-only live probe
(`cloud/task_073/evidence/live_probe.json`, generated 2026-08-29T02:33Z), any
R1 prototype named below is marked REJECTED_PROTOTYPE_DO_NOT_DEPLOY and must
never be used for a live Gate A or Gate B run:

- `tools/live_audit_controller.py` — returned NOT_IMPLEMENTED_WITHOUT_LIVE_CREDENTIALS, no real GET evidence.
- `tools/keyboard_transformer.py` — operated on an invented dict, not live Python source; no AST anchors.
- `tools/publish_guard.py` — wrote two files sequentially with no catalog/index build and no rollback of the first file on second-file failure.
- `tools/installer.py` — unused `target_paths`, basename-collision backup, incomplete rollback.
- `tools/public_verifier.py` — checked a single page and an invented revision header that does not exist on the real site.
- `workflows/gate_b_manual_dispatch.yml` — contained placeholder `echo` steps instead of real actions.

These files are not present in this branch's history at the time this task
was executed; this note exists so any copy of them found elsewhere is
treated as rejected and is never wired into the real Gate B controller
(`gate_b_controller_v2.py`). Only the `_v2` files under `cloud/task_073/tools/`
and `cloud/task_073/workflows/` are release candidates.
