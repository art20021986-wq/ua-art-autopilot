# UA ART AUTOPILOT — Cloud/Claude communication protocol

This repository is the communication bridge between ChatGPT, Claude/Cloud, and PythonAnywhere.

## Mandatory behavior for every task

1. Read the newest `tasks/task_NNN.md` before doing anything.
2. Never touch UA ART production directly from Claude/Cloud.
3. Put all code, patches, and detailed reports under `cloud/`.
4. Always update `cloud/latest_status.md` before finishing a task.
5. Always commit all task outputs to your task branch.
6. Do not perform CRITICAL actions. Stop and request owner approval through status.

## Required `cloud/latest_status.md` format

```text
TASK_ID: task_NNN
ROUND: N
CLAUDE_STATUS: WORKING | DONE | BLOCKED | WAITING_OWNER
CURRENT_ACTION: <short sentence>
FILES_CREATED: <comma-separated paths or NONE>
PRODUCTION_TOUCHED: NO
OWNER_ACTION_REQUIRED: YES | NO
OWNER_QUESTION: <one short question or NONE>
NEXT_FOR_CHATGPT: <what ChatGPT should inspect or do next>
UPDATED_AT_UTC: <ISO timestamp>
```

## Communication rule

Do not rely on chat text as the durable handoff. The durable handoff is always the GitHub file `cloud/latest_status.md` plus the detailed task report under `cloud/`.

## Owner interaction

Ask the owner only when a visual check or CRITICAL approval is genuinely required. Otherwise continue through the GitHub workflow without owner involvement.
