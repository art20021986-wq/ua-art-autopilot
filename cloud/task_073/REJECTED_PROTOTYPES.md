# TASK 073 - Rejected prototypes (do not deploy)

Marked `REJECTED_PROTOTYPE_DO_NOT_DEPLOY` per owner-directed ROUND 3/4/5 review.
Kept for history only; V4 (`patcher_v4.py`, `gate_a_v4.py`, `gate_b_installer_v4.py`,
`gate_b_controller_v4.py`, `gate_b_postcheck_v4.py`) is the only reviewable candidate.

- R1 tools (`tools/live_audit_controller.py`, `keyboard_transformer.py`,
  `publish_guard.py`, `installer.py`, `public_verifier.py`,
  `workflows/gate_b_manual_dispatch.yml`): not implemented against live
  credentials, work on a synthetic dict instead of live Python source,
  incomplete rollback, placeholder echo steps in Gate B workflow.
- V2/V3 series: keyboard-outer-removal transforms searched for literal
  `InlineKeyboardButton(...sea_loaded...)` strings instead of the real
  `S.STATUSES.items()` comprehension filters; SEO068 stale-precondition
  transform searched for `os.path.exists(...diag...)` instead of the real
  `any(_ua_seo068_os.path.isfile(...))` block; publisher used a synthetic
  HTML renderer instead of the real `_master`/`_ua9_sobrat_katalog`
  helpers; Gate B used unverified `always_on_tasks/{id}` restart shape and
  did not snapshot public targets before writing them.

Corrected root causes are addressed only in the V4 series described in
`GATE_A_V4_REPORT.md`.
