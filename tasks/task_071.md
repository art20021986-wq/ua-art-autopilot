# TASK 071 — CRM-ALL-FIELDS-WRITE-071 v1.0

STATUS: IN_WORK
PRIORITY: P0
MODE: ROOT-CAUSE REPAIR / INDEPENDENT GATE A
OWNER_DIRECTIVE: Устранить максимально быстро причину, из-за которой данные CRM не заполняются
PRODUCTION_WRITE: NO
CRM_DB_PRODUCTION_WRITE: NO
PYTHONANYWHERE_SOURCE_WRITE: NO
RUNTIME_LLM_TOKENS_TARGET: 0

## Подтверждённый инцидент

Любые данные открытой карточки могут не сохраниться. Цена `11400` — воспроизводимый пример:
`cars_ui.catch_message → apply_value/set_field → db.update_card_field/log_action → sqlite3.OperationalError: database is locked`.
Telegram ждёт до 1–2 минут и затем показывает `CRM: не читается база crm.db`.

Корневая причина общая для всех полей:
- `db.py::_ua_lock3_connect`, `db.connect`, `trace_zhurnal.py::_ua_connect` и `_Obertka.__enter__` суммарно навязывают 20–30 секунд ожидания;
- одно изменение делает несколько соединений/commit;
- цена дополнительно вызывает `remember_price`, то есть третий commit;
- конкурирующие обработчики и фоновые процессы увеличивают окно lock;
- SQL table/field интерполируются без строгого allowlist.

## Обязательная коррекция TASK 070

TASK 070 нельзя признавать Gate A PASS в текущем виде:
1. `tests/test_real_schema_gate_a.py` использует вымышленные поля `probeg/etap/kontainer/srok`, которых нет в live schema.
2. Реальные поля: `price_uah`, `mileage_km`, `status`/legacy `stage`, `sea_container`, `days_to_kyiv`, `eta_manual` и остальные колонки из evidence.
3. `installer/apply_patches.py --apply` не применяет патчи, а только создаёт backup и печатает NOTE.
4. Standalone candidate использует таблицы `cards/price_history/log_action`, которых нет в реальной CRM-схеме `cars/audit`.
5. Поэтому самотесты TASK 070 не доказывают исправление живого call path.

Использовать подтверждённый GET-only контекст:
- `cloud/task_070/evidence/real_context.json`;
- live SHA: `db.py=b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086`;
- `cars_ui.py=862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b`;
- `trace_zhurnal.py=fc4b95fc749f3d9b785ce69bfce2705b11ade95a560d6fbd901b50de1423d086`;
- `PRAGMA quick_check=ok`, `cars_count=11`, UA-0009 ровно одна.

## Реализация Gate A

1. Через PythonAnywhere API выполнять только GET: скачать полные live `db.py`, `cars_ui.py`, `trace_zhurnal.py` и `crm.db` во временную папку runner. Полные live-файлы и БД не коммитить и не выводить в лог.
2. Создать точечный deterministic patch/controller с полным SHA + AST anchor guard. Полная замена файлов запрещена.
3. Убрать принудительное глобальное расширение timeout/busy_timeout из диагностических обёрток. Диагностика только наблюдает и не меняет timeout, journal mode или транзакцию вызывающего кода.
4. Сохранить публичные API `db.connect`, `db.update_card_field`, `cars_ui.set_field/apply_value/catch_message`; существующие handlers не ломать.
5. Ввести один реальный writer для `cars` и разрешённых полей `clients`. Таблица и поле выбираются только из жёстких mapping allowlist, построенных по реальной схеме evidence.
6. Одна правка: основной UPDATE + audit INSERT в одной короткой транзакции и одном commit/соединении.
7. Цена: `price_uah` + корректный JSON `price_history` для текущего этапа + audit в одной транзакции. После успешной атомарной записи отдельный `remember_price` не вызывается.
8. При `locked/busy/queue timeout`: прямой write budget ≤0.8 с, затем durable process-safe FIFO в отдельной SQLite queue; быстрый ответ `Принято, сохраняю`; `Сохранено` только после commit/ack. Traceback, серверные пути и `database is locked` в Telegram запрещены.
9. Идемпотентность по stable `operation_id`: crash после CRM commit до queue ack не создаёт дубль audit/price_history и не накладывает старое queued-значение поверх более нового.
10. Новая карточка не создаётся входным текстом/фото/голосом. Из открытой карточки обновляется только её `card_id`; пустые поля заполняются, заполненные меняются только при явной команде исправления.
11. Фоновый rebuild сайта, отправка медиа и публикация не входят в синхронный DB path.
12. Правило едино для всех 11 существующих и любых будущих UA-XXXX.

## Независимая Gate A матрица на реальной локальной копии

Workflow/controller должен:
- проверить полные live SHA до трансформации;
- сделать локальные копии source + crm.db; production read-only;
- реально применить patch к временным source-копиям (не no-op), AST compile/import PASS;
- запустить call-path tests через реальные patched функции со stub Telegram layer;
- цена `11400`: read-back той же карточки, ровно одна запись истории, ровно одна audit-запись;
- по 100 операций реальных полей: `price_uah`, `mileage_km`, `status`, `sea_container`, `days_to_kyiv`; без потерь, дублей, cross-card;
- каждое разрешённое scalar-поле `cars` и `clients`: smoke save/read-back;
- под `BEGIN EXCLUSIVE`: acceptance ≤1 с, FIFO drain до 0 после release;
- crash после enqueue, после commit до ack, во время drain/restart: ровно одно применение;
- минимум 2 процесса одновременно enqueue+drain;
- malicious/unknown table/field отклоняются до SQL;
- `quick_check=ok`; cars_count остаётся 11; UA-0001…UA-0011, кроме выбранной тестовой копии, не меняются; UA-0009 hash отдельно проверяется; future UA-XXXX PASS на отдельной копии;
- protected media/photo/video/diagnostics/container/site production SHA не меняются;
- measured p95/p99 и ноль traceback;
- backup + автоматический code-only rollback + сохранение очереди;
- тесты должны падать на старом коде и проходить на patched-копии.

## Выход

Создать under `cloud/task_071/`:
- точечный patch transformer;
- рабочий dry-run/apply installer для локальной копии;
- writer + durable queue + canary guard;
- независимый controller/workflow;
- полный измеримый Gate A report;
- rollback;
- redacted evidence JSON.

Запустить независимый Gate A workflow автоматически. Не ждать владельца.
Только при полном PASS записать:
`TASK_071_GATE_A: PASS_READY_FOR_OWNER_GATE_B`
`ALL_CRM_FIELDS_SAVE: PASS`
`PRICE_11400: PASS`
`UA-0009 INTEGRITY: PASS`
`SAFE TO START PRODUCTION GATE B: YES`

При любом пробеле — FAIL/BLOCKED с точной причиной. Никаких заявлений о production fix до отдельного письменного Gate B владельца.
