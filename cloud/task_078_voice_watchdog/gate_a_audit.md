# Gate A — свежий GET-only аудит

Статус: `PASS_AUDIT_AND_IN_MEMORY_CANARY`

Время: 2026-08-29T07:00:45Z — 2026-08-29T07:00:46Z.

## Live-факты

- `cars_ui.py` SHA256:
  `50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306`.
- `catch_message` SHA256:
  `152d00158bcd097f61fad4e795340f45113724217b481d56ab32f358549a4fd5`.
- Фиксированный дедлайн 4,65 секунды: подтверждён.
- `asyncio.to_thread(ai.transcribe)` под `wait_for`: подтверждён.
- Killable child для STT в live: отсутствует.
- Supervisor существует и имеет restart loop, но exit code 75 не
  обрабатывает; перезапуск всего процесса в этом релизе запрещён.

## In-memory canary

- Exact source SHA gate: PASS.
- Патч применён только в памяти и скомпилирован: PASS.
- Повторное применение идемпотентно: PASS.
- Вне `catch_message` байты не меняются: PASS.
- Внутри `catch_message` меняется только голосовой блок: PASS.
- Старый дедлайн и неубиваемый STT-thread удалены: PASS.
- Candidate SHA256:
  `60096df9867e544fe6dbc588fc0909c11d851765940d2e78bbd0096085fb4c1f`.

HTTP-методы аудита: только `GET`. Production writes/restart: **NO**.

Полные sanitized-доказательства: `evidence/live_audit.json`.
