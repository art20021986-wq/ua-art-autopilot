# TASK 078 — CRM-VOICE-WATCHDOG-005 v1.0

OWNER_DIRECTIVE: `Большая прослушка зависает, сделай автоматический перезапуск.`

## Разрешённый режим

`GET-only AUDIT → SANDBOX/CANARY → release candidate`. Production запрещён
до отдельной письменной команды владельца. Текущую TASK 077 не останавливать.

## Подтверждённая причина в live-коде

`cars_ui.py::catch_message` (`sha256=152d00158bcd097f61fad4e795340f45113724217b481d56ab32f358549a4fd5`)
ставит один `hard_deadline = started + 4.65` для любого голосового/аудио и
запускает `ai.transcribe` через `asyncio.to_thread(...)` под `wait_for`.
Отмена `wait_for` не останавливает уже работающий thread: длинная расшифровка
остаётся в фоне, а новые попытки могут накапливать зависшие workers/CPU.

## Обязательный контракт

1. Длительность timeout вычисляется из `voice_object.duration`:
   `clamp(15, ceil(duration*1.5)+10, 180)` секунд; скачивание имеет отдельный
   bounded timeout 5…30 секунд.
2. STT выполняется в отдельном killable subprocess/process group, не в
   неубиваемом `asyncio.to_thread`. При timeout: `TERM`, ожидание до 3 секунд,
   затем `KILL`; orphan workers после выхода = 0.
3. Один автоматический перезапуск свежего STT-worker. Максимум две попытки на
   одно сообщение. Транскрипция не может записать поля карточки сама.
4. CAS-запись карточки выполняется ровно один раз и только после одной
   успешной транскрипции. Timeout/restart не создаёт новую карточку, дубль
   записи или второе success-сообщение.
5. Перед обработкой сохраняется bounded job-marker без текста/аудио/PII:
   chat/message/file_unique/card/field, attempt, state, timestamps. После
   успешного результата marker закрывается; после рестарта допустим ровно
   один replay того же Telegram file_id.
6. После двух timeout/errors пользователь получает одно понятное failure и
   кнопку «Повторить голосовое»; бот остаётся отзывчивым для текста/кнопок.
7. Перезапуск всего Telegram-процесса разрешён только если GET-аудит докажет
   действующий supervisor. Нужны 3 подряд failed health probes, exit code 75,
   не более 2 process restarts за 10 минут и cooldown. Если supervisor не
   подтверждён — перезапускается только STT-worker, `os._exit` запрещён.
8. Circuit breaker: после 3 STT зависаний за 10 минут — cooldown 5 минут,
   текстовый ввод продолжает работать. Runtime LLM tokens вне STT = 0.
9. `crm_voice_seen` нельзя фиксировать до успеха навсегда: при failure marker
   освобождается, при success остаётся idempotency tombstone.

## Gate A — только чтение

Свежим secret-backed GET получить `cars_ui.py`, `ai.py`, `start_safe.py`,
`crm_online_guard.py` и фактический launcher/supervisor. Зафиксировать SHA,
definition hashes, handler order, текущие timeout/worker/restart semantics и
отсутствие уже существующего kill path. Никаких live writes/restart.

## Sandbox tests

- duration 0/3/30/60/120/600 и границы 15/180;
- короткое голосовое PASS с одной попытки;
- первая попытка зависла → child killed → свежий worker PASS;
- две зависли → одно failure, zero writes, marker retryable;
- cancellation/exception → process group killed, semaphore released;
- 20 параллельных входов → bounded concurrency, event loop отвечает;
- duplicate Telegram update → одна транскрипция/одна CAS write;
- restart budget/cooldown/persistent replay after simulated process restart;
- text/photo handlers не изменены;
- actual `cars_ui.py` in-memory patch compiles against exact audited SHA.

## Выходы

Создать `cloud/task_078_voice_watchdog/`: sanitized audit evidence,
killable worker, handler patcher, tests, sandbox report, installer/controller
с backup/rollback и manual Gate B. Gate B подготовить, не запускать.

Итог: `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` либо FAIL. Не заявлять,
что live CRM перезапуск исправлен, пока production Gate B не разрешён.

## Результат контроллера — 2026-08-29

`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`

- Свежий live Gate A: `PASS_AUDIT_AND_IN_MEMORY_CANARY`.
- Канонический кандидат: `voice_watchdog.py` + `handler_patcher.py`.
- Exact live candidate SHA256:
  `60096df9867e544fe6dbc588fc0909c11d851765940d2e78bbd0096085fb4c1f`.
- Sandbox/regression: 34/34 PASS.
- Production touched: NO.
- Full-process restart: запрещён текущим supervisor-аудитом; только killable
  STT-worker restart.
- Следующий шаг: отдельное письменное разрешение владельца на Gate B.
