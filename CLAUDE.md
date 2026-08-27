# UA ART AUTOPILOT — Cloud/Claude communication protocol

This repository is the communication bridge between ChatGPT, Claude/Cloud, and PythonAnywhere.

## Mandatory behavior for every task

1. Read the newest `tasks/task_NNN.md` before doing anything.
2. Never touch UA ART production directly from Claude/Cloud.
3. Put all code, patches, and detailed reports under `cloud/`.
4. Always update `cloud/latest_status.md` before finishing a task.
5. Always create or replace `cloud/owner_reply.md` with a short owner-facing response in Russian.
6. Always commit all task outputs to the task branch.
7. Do not perform CRITICAL actions. Stop and request owner approval through status.

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

## Required `cloud/owner_reply.md` format

Write in clear Russian for the owner, without technical jargon:

```text
# Ответ Claude владельцу
СТАТУС: PASS | FAIL | ЖДЁТ
ЗАДАЧА: <what request was received>
ЧТО СДЕЛАНО: <short factual result>
СОЗДАННЫЕ ФАЙЛЫ: <paths or NONE>
ЧТО НУЖНО ОТ ВЛАДЕЛЬЦА: <one action or НИЧЕГО>
БЕЗОПАСНОСТЬ: production/CRM/PythonAnywhere changed or not
```

Do not claim that anything was uploaded to PythonAnywhere, executed on a server, published, or visually checked unless the task provides verifiable evidence. The detailed technical evidence remains in the task report under `cloud/`.

## Request route

The owner gives a request to ChatGPT/Codex. Codex writes the durable request as the newest `tasks/task_NNN.md`. GitHub Actions starts the Claude worker. Claude writes the requested deliverables, `cloud/latest_status.md`, and `cloud/owner_reply.md`. ChatGPT/Codex audits those files and relays the verified owner reply.

## Communication rule

Do not rely on ordinary Claude chat attachments as the durable handoff. The durable handoff is always GitHub: the newest task under `tasks/`, `cloud/latest_status.md`, `cloud/owner_reply.md`, and the detailed report under `cloud/`.

## Owner interaction

Ask the owner only when a visual check or CRITICAL approval is genuinely required. Otherwise continue through the GitHub workflow without owner involvement.
