# Спецификация манифеста релиза (Release Manifest Spec) — TASK_010

## Назначение

Манифест — единственный источник истины, связывающий TASK_ID, точные байты файлов-кандидатов, происхождение (commit/Actions run), режим цели и разрешённое действие с двумя раздельными одобрениями (Gate A и Gate B).

## Канонический JSON-формат

Верхнеуровневые поля (обязательные):

- `schema_version` (string) — например `"1.0"`.
- `task_id` (string) — например `"task_010"`.
- `created_at_utc` (string, ISO-8601, UTC, секунды).
- `source_commit_sha` (string, 40 hex) — git commit, из которого собран кандидат.
- `github_actions_run_id` (string) — идентификатор запуска Claude Autopilot Actions.
- `github_actions_run_url` (string) — ссылка на запуск (доказательство происхождения).
- `claude_authored` (bool) — должно быть `true`.
- `files` (array of objects) — список файлов-кандидатов:
  - `path` (string) — относительный путь, обязан начинаться с `cloud/`.
  - `sha256` (string, 64 hex) — хэш точного содержимого файла (бинарный режим, без нормализации переводов строк).
  - `size_bytes` (int).
- `manifest_sha256` (string, 64 hex) — хэш канонизированного манифеста БЕЗ этого поля (вычисляется последним, добавляется отдельно, см. ниже).
- `target_mode` (enum): `"SANDBOX_ONLY"` | `"PRODUCTION_CAPABLE"`.
- `allowed_action` (object):
  - `action_type` (enum): `"NOOP"`, `"COPY_TO_QUARANTINE"`, `"SAFE_SCRIPT_RUN"`, `"PRODUCTION_PUBLISH"`, `"CRM_WRITE"`, `"WSGI_RELOAD"`, `"DELETE"`, `"MASS_REGEN"`.
  - `command_id` (string) — символический ID из хардкод-allowlist на стороне шлюза (НИКОГДА произвольная shell-строка).
  - `target_paths` (array of string) — абсолютные пути на PythonAnywhere, каждый обязан начинаться с одного из хардкод allowlist-корней шлюза.
- `requires_gate_a` (bool).
- `requires_gate_b` (bool).
- `backup_required` (bool).
- `rollback_plan` (string) — человекочитаемое описание отката.
- `visual_check_required` (bool).
- `risk_level` (enum): `"LOW"`, `"MEDIUM"`, `"HIGH"`, `"CRITICAL"`.
- `gate_a` (object|null) — заполняется ТОЛЬКО системой одобрения, не Claude:
  - `approved` (bool), `approved_at_utc`, `owner_phrase_hash` (sha256 фразы одобрения, не сама фраза), `expires_at_utc`.
- `gate_b` (object|null) — аналогично, независимо от `gate_a`.

## Канонизация и хэширование

1. Список `files` сортируется по `path` в порядке байтового сравнения (ASCII/UTF-8 codepoint order).
2. Каждый `sha256` в `files` — `hashlib.sha256(raw_bytes).hexdigest()`, где `raw_bytes` — точное бинарное содержимое файла без каких-либо преобразований (без нормализации CRLF/LF, без BOM-стриппинга).
3. Манифест сериализуется в канонический JSON: `json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=True)`, поле `manifest_sha256` временно исключается из объекта перед сериализацией.
4. `manifest_sha256 = sha256(canonical_json_bytes).hexdigest()`.
5. Финальный манифест = канонический объект + добавленное поле `manifest_sha256`.
6. Любое последующее изменение любого файла (даже одного байта) меняет его `sha256`, следовательно меняет канонический JSON, следовательно меняет `manifest_sha256` → любое ранее выданное одобрение автоматически становится недействительным, так как одобрение хранится вместе с конкретным `manifest_sha256`.

## Неизменяемая связь полей

```
TASK_ID ──┐
          ├─→ files[].sha256 ──→ manifest_sha256 ──┬─→ gate_a approval record (exact match required)
source_commit_sha                                   └─→ gate_b approval record (exact match required)
github_actions_run_id/url (provenance evidence)
target_mode + allowed_action (declares what CAN be done)
backup_required + rollback_plan (mandatory for any mutable target)
visual_check_required (mandatory before gate_b for production)
```

Шлюз обязан отклонить (default deny) любой запрос, если:
- пересчитанный `manifest_sha256` не совпадает с заявленным;
- хотя бы один файловый `sha256` не совпадает с фактическим содержимым;
- `github_actions_run_id`/`source_commit_sha` отсутствуют или не проверяемы;
- `target_mode` = `PRODUCTION_CAPABLE`, а есть только запись `gate_a` без отдельной записи `gate_b`;
- `allowed_action.command_id` отсутствует в хардкод allowlist шлюза;
- любой `target_paths` вне хардкод allowlist-корней.
