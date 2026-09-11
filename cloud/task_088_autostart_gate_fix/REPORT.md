# TASK 088 workflow gate fix

## Scope
- Minimal change only in `.github/workflows/uaart_autostart.yml`.
- No site, CRM, Stage 2, marker validation, replay protection, main guard, or `production_allowed=false` changes.

## Change
- Replaced the three duplicated exact-parent equality checks with the same minimal parent-count gate.
- Accepted cases now are:
  - direct commit to `main` where the only parent is `BEFORE_SHA`;
  - normal 2-parent merge commit where the first parent is exactly `BEFORE_SHA`.
- Octopus merges still fail because only 2 or 3 rev-list fields are accepted.

## Files changed
- `.github/workflows/uaart_autostart.yml`
- `automation/packages/task107_r2/test_workflow_contracts.py`

## Targeted tests
- `python3 -m unittest automation.packages.task107_r2.test_workflow_contracts.WorkflowContractTests.test_global_autostart_is_fresh_exact_marker_only automation.packages.task107_r2.test_workflow_contracts.WorkflowContractTests.test_global_autostart_parent_gate_accepts_direct_and_normal_merge_only automation.packages.task107_r2.test_control_plane.ControlPlaneTests.test_autostart_policy_rejects_persisted_checkout_credential automation.packages.task107_r2.test_control_plane.ControlPlaneTests.test_autostart_policy_rejects_rerun_route_gate_removal automation.packages.task107_r2.test_control_plane.ControlPlaneTests.test_autostart_policy_requires_source_pinned_privileged_runtime`
- Result: PASS (5 tests).

## Validation
- Secret scan on changed files: PASS.
- CodeQL: 0 alerts on the last completed validation run.
- Code review requested one additional test refinement; that feedback was addressed by anchoring the behavior test to the workflow text.
- A final `parallel_validation` rerun could not complete because the tool reported insufficient remaining validation time.

## Notes
- Added focused behavior coverage for direct commits, normal 2-parent merges, and rejected parent layouts.
- A broader workflow test sweep in this branch reports unrelated pre-existing failures in `uaart_transaction_watchdog.yml`; this task did not modify that workflow.
- Updated at: 2026-09-11T08:52:27.758704+00:00
