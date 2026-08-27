# TASK 028 — integrate canonical cars_ui transform into Gate A

## Safety

Continue CRM-SPEED-001 only under cloud/. Do not execute Gate A or modify Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, or UA-0009.

## Controller result for commit 1cec53a47cc5282e2b8ff5f0549fcd050ed04804

Python compile: PASS.
Unittest discovery found 65 tests:
- new test_cars_ui_transform.py: 14/14 PASS;
- legacy/canonical test_crm_speed_gate_a.py: 49/51 PASS, the same two media tests still FAIL;
- total: 63 PASS, 2 FAIL.

Root cause: Claude added cars_ui_transform.py with a corrected transform, but crm_speed_gate_a.py still defines and uses its old transform_cars_ui and old scan. RUN_GATE_A_CRM_SPEED.py and the end-to-end suite therefore do not exercise the new implementation. The package currently has two competing implementations.

## Required correction

1. Make cloud/crm_speed_optimization/cars_ui_transform.py the single canonical implementation.
2. crm_speed_gate_a.py must import the canonical transformer and use it everywhere:
   - public transform_cars_ui;
   - check_admin_routes_text_only;
   - synthetic end-to-end orchestration;
   - deterministic repeat;
   - actual Gate A candidate generation.
3. Remove the old duplicate _FunctionVisitor/_MediaCallTextTransformer/transform_cars_ui implementation from crm_speed_gate_a.py, or replace it with a thin adapter that calls cars_ui_transform.transform_cars_ui.
4. The adapter may preserve the established Gate A API:
   transform_cars_ui(source, entry_points=None) -> dict containing:
   - status: OK/BLOCKED
   - candidate: str or None
   - reasons: list[str]
   It must normalize the canonical module's single reason field without changing its meaning.
5. Do not keep two scanners for acceptance. If compatibility requires the old scan_reachable_call_graph API for tests, it may be a thin read-only adapter around the canonical scanner; acceptance and transformation must use the canonical result.
6. Add identity/integration assertions:
   - crm_speed_gate_a canonical transformer object/module is cars_ui_transform;
   - monkeypatching the canonical transformer is observed by public Gate A path;
   - RUN_GATE_A_CRM_SPEED imports the same orchestration;
   - end-to-end clean fixture records the canonical cars_ui module/hash in receipt.
7. Run test discovery, not one hard-coded test file:
   python3 -m unittest discover -v -s cloud/crm_speed_optimization -p 'test*.py'
8. Preserve all 65 existing tests, including the two currently failing. Do not delete/skip/rename away their semantics.
9. Full discovered suite must be capable of 10 consecutive green runs.
10. Update status/report/test matrix truthfully. Status READY_FOR_CONTROLLER_REVIEW only, pending controller execution.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
