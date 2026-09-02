# TARGET ARCHITECTURE — TASK105

## Seven permanent workflows

### `uaart_fast.yml`
Низкорисковые контентные, SEO и локальные UI-изменения.

### `uaart_standard.yml`
CRM, генераторы, счётчики и связанные функциональные изменения.

### `uaart_critical.yml`
Миграции, безопасность, инфраструктура и массовые production-изменения.

### `uaart_monitor.yml`
Read-only health, uptime, SEO и наблюдаемость без ремонтных записей.

### `uaart_backup.yml`
Единый резервный снимок и проверка восстановимости.

### `uaart_rollback.yml`
Параметризованный атомарный откат и post-rollback verify.

### `uaart_maintenance.yml`
Плановые архивирование, cleanup и проверка дрейфа инфраструктуры.

## Central orchestrator

`automation/task_orchestrator.py` owns classification, task state, resource locks, retry policy,
executor selection, evidence collection and final receipt validation.

## Classification contract

| Class | Default executor | Production path | AI default |
|---|---|---|---|
| FAST | deterministic scripts / GPT-authored patch | backup → deploy → smoke | NO_AI after patch |
| STANDARD | deterministic runner + optional AI review | sandbox → backup → deploy → live verify | GPT_PRIMARY or CLAUDE_REVIEW |
| CRITICAL | isolated implementation + dual gate | full regression → canary → approval → production | explicit budget |

## Resource-aware locking

Lock keys are scoped, for example: `CRM_DB`, `CATALOG_RENDERER`, `HOMEPAGE`, `CARD:UA-0016`,
`CLOUDFLARE_CONFIG`. Read-only work and unrelated resources remain parallel.

## AI routing

Allowed routes: `NO_AI`, `GPT_PRIMARY`, `CLAUDE_REVIEW`, `CLAUDE_PRIMARY`, `DUAL_REVIEW`.
AI is prohibited for HTTP checks, SHA verification, backups, copy/install, regex validation,
queue polling and deterministic tests.

## Final receipt

`state/receipts/TASK_NNN.json` is the only authority allowed to set `FINISHED`.
It must contain target environment, test result, deployment proof, live verification,
unexpected-change count and rollback readiness.
