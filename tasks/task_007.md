# TASK 007 — CLAUDE OWNER REQUEST BRIDGE ACCEPTANCE

MODE: READ_ONLY
MAX_ROUNDS: 1

## Owner outcome

Prove the complete automatic request path:

OWNER CHAT REQUEST -> CODEX -> GITHUB TASK -> CLAUDE WORKER -> GITHUB OWNER REPLY -> CODEX AUDIT -> OWNER CHAT.

The owner must not upload ZIP files to move a normal task between ChatGPT and Claude.

## Scope

This is a bridge acceptance test only.

- Read repository files needed to verify the communication protocol.
- Do not access or change PythonAnywhere.
- Do not access or change CRM.
- Do not access or change UA ART production.
- Do not publish cards.
- Do not create executable production actions.
- Do not invent evidence.

## Required checks

1. Confirm that this exact task was received as `tasks/task_007.md`.
2. Confirm that the worker can return Claude-generated files under `cloud/`.
3. Confirm that `cloud/latest_status.md` follows the protocol.
4. Create a simple Russian response for the owner in `cloud/owner_reply.md`.
5. Record the bridge result and exact safety boundaries in `cloud/claude_bridge_acceptance.md`.

## Deliverables

1. `cloud/claude_bridge_acceptance.md`
2. `cloud/owner_reply.md`
3. `cloud/latest_status.md`

## Required owner reply content

The owner reply must say, in plain Russian:

- Claude received TASK 007 automatically through GitHub.
- Claude returned the reply through GitHub.
- Production, CRM, and PythonAnywhere were not changed.
- No owner action is required for this bridge test.

Do not claim direct access to the ChatGPT conversation. Claude receives the durable task from GitHub, and Codex relays the verified reply to the owner.

## Acceptance

- CLAUDE_STATUS: DONE
- All three deliverables exist.
- No paths outside `cloud/` are written by Claude.
- No production, CRM, or PythonAnywhere action occurs.
- OWNER_ACTION_REQUIRED: NO
