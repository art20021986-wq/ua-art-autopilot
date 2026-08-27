# TASK 009 — CLAUDE FILE RECEIPT, OPTIMIZATION AND PYTHONANYWHERE HANDOFF TEST

MODE: READ_ONLY_PRODUCTION
MAX_ROUNDS: 3

## Owner directive

The owner requests a real end-to-end test for `cloud/uaart_card_factory_gate.py`.

Claude API worker must:
1. Explicitly confirm that TASK 009 and the current `cloud/uaart_card_factory_gate.py` were received through the GitHub/Anthropic API bridge.
2. Audit the current gate file for correctness, safety, Python 3.10 compatibility, unnecessary complexity, false-positive risks, and ability to inspect UA-0009 without changing production.
3. Optimize/refactor the gate only where objectively useful. Preserve strict read-only behavior for CRM and production. Do not weaken any safety boundary.
4. Return the complete optimized file as `cloud/uaart_card_factory_gate.py` (replace the current cloud deliverable through the worker output).
5. Create `cloud/claude_pythonanywhere_handoff_test.txt` containing a unique TASK 009 test marker and a SHA-256 of the optimized gate content so the downstream PythonAnywhere sync can prove exactly what it received.
6. Create `cloud/cloud_report_009.md`, `cloud/owner_reply.md`, and `cloud/latest_status.md`.

## Critical truthfulness rule

Claude must NOT claim that the ordinary claude.ai chat UI received this task. This task is received by the Anthropic API worker through GitHub; the ordinary Claude chat UI is a separate session.

Claude must NOT claim that the file was installed, uploaded, executed, or verified on PythonAnywhere. Claude has no direct PythonAnywhere evidence in this task. The downstream GitHub `PythonAnywhere Inbox Sync` workflow is responsible for transfer and verification after Claude commits the files.

The owner-facing reply must clearly distinguish:
- RECEIVED_BY_CLAUDE_API: YES/NO
- OPTIMIZATION_COMPLETE: YES/NO
- STATIC_CHECK_EXPECTED: YES/NO (the worker itself will also compile-check Python outputs)
- PYTHONANYWHERE_INSTALL_CONFIRMED_BY_CLAUDE: NO — WAITING_FOR_SYNC_RECEIPT

## Safety requirements

- No production write.
- No CRM write.
- No WSGI/source/site changes.
- No webapp reload.
- No execution on PythonAnywhere.
- No secrets/tokens in outputs.
- The gate may write only to its existing approved sandbox/report locations when later run on PythonAnywhere.
- UA-0001..UA-0008 must remain protected.

## Required deliverables

- `cloud/uaart_card_factory_gate.py`
- `cloud/claude_pythonanywhere_handoff_test.txt`
- `cloud/cloud_report_009.md`
- `cloud/owner_reply.md`
- `cloud/latest_status.md`

## Required owner reply (Russian)

State plainly that Claude API worker received the file/task, whether it changed the file and why, that the optimized file is ready for downstream automatic sync, and that PythonAnywhere installation cannot be called successful until a separate sync receipt proves it. Do not invent installation evidence.

## Acceptance

- CLAUDE_STATUS: DONE
- all five deliverables exist
- optimized Python compiles successfully in the GitHub worker static check
- production touched: NO
- owner action required: NO for Claude processing itself; PythonAnywhere sync may separately require its API token secret if not configured
