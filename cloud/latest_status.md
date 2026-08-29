TASK_ID: task_082
ROUND: 1
CLAUDE_STATUS: DONE
CURRENT_ACTION: Built the full runnable TASK 082 VIN4-title package (helper, offline tests, fail-closed AST/SHA patcher, live fetch/shadow, backup+atomic installer, postcheck, rollback controller, and the CI workflow template) for Codex to install and run.
FILES_CREATED: cloud/task_082_vin4_title/README.md, cloud/task_082_vin4_title/vin4_helper.py, cloud/task_082_vin4_title/test_vin4_helper.py, cloud/task_082_vin4_title/patcher.py, cloud/task_082_vin4_title/anchor_config.example.json, cloud/task_082_vin4_title/fetch_and_shadow.py, cloud/task_082_vin4_title/installer.py, cloud/task_082_vin4_title/postcheck.py, cloud/task_082_vin4_title/controller.py, cloud/task_082_vin4_title/workflow/task082_vin4_title_deploy.yml, cloud/task_082_vin4_title/evidence/sanitized_evidence.md, cloud/task_082_vin4_title/report.md
PRODUCTION_TOUCHED: NO
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE
NEXT_FOR_CHATGPT: Copy cloud/task_082_vin4_title/workflow/task082_vin4_title_deploy.yml into .github/workflows/, then let the workflow's live_deploy job run controller.py's dry-run discovery against the real live cars_ui.py to populate a reviewed anchor_config.json before the patch/install gate can proceed; only then will the controller perform BACKUP -> shadow -> canary -> install -> restart -> postcheck and report a real PASS/FAIL with real 13-row sanitized evidence.
UPDATED_AT_UTC: 2026-08-29T07:36:22Z
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
