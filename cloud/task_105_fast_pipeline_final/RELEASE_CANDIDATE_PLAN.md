# TASK105 — Release Candidate Plan

Before merge, the branch must satisfy all of the following in one final acceptance run:

1. FAST production receipt PASS.
2. STANDARD 10/10 sandbox and 3/3 production receipt PASS with full public rollback.
3. CRITICAL adapter 21/21 tests, 10/10 cases, Gate A and Gate B PASS.
4. Exactly eight permanent `uaart_*.yml` workflows remain.
5. No task-specific migration workflow remains in the release tree.
6. No tracked `__pycache__` or `.pyc` file remains.
7. Current permanent workflow revisions are YAML-parseable and core Python modules compile/self-test.
8. The reusable FAST workflow executes the route canary and emits a truthful FINISHED receipt.
9. No production, CRM, vehicle-data, Cloudflare or DNS write occurs during release-candidate validation.
10. Only after PASS may PR #37 be merged and the central orchestrator verified on `main`.
