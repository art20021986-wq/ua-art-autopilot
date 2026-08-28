# TASK 070 — CRM-DB-SPEED-LOCK-070 v1.2

STATUS: GATE_A_UNBLOCKED_REAL_CONTEXT_READY
MODE: ROOT-CAUSE REPAIR / REAL-SCHEMA CANDIDATE / CANARY GUARD
OWNER_DIRECTIVE: CONTINUE GATE A; MAXIMUM SPEED; CANARY + CONTINUOUS CONTROL; SAFE AUTO-RECOVERY
PRODUCTION_WRITE: NO
CRM_DB_WRITE: NO
LLM_TOKENS_RUNTIME: 0

## Подтверждённый отказ

При вводе цены `11400` бот ждёт 1–2 минуты и отвечает: `CRM: не читается база crm.db`.
Traceback:
`cars_ui.catch_message → set_field/remember_price → db.update_card_field/log_action → commit → sqlite3.OperationalError: database is locked`.

## Реальный контекст получен — блокировка Gate A снята

Использовать только:
- `cloud/task_070/evidence/real_context.json`;
- probe: `cloud/task_070/read_real_context.py`;
- workflow run: `33212748005` — SUCCESS, GET-only;
- `PRAGMA quick_check=ok`, `cars_count=11`, UA-0009 существует ровно один раз;
- live SHA: `db.py=b732a5c...`, `cars_ui.py=862baea...`, `trace_zhurnal.py=fc4b95f...`.

Evidence подтверждает реальную таблицу `cars(id, auto_number, price_uah, price_history, ...)`, таблицу аудита `audit` и точные функции:
`db.connect/update_card_field/log_action`,
`cars_ui.set_field/apply_value/remember_price/catch_message`,
`trace_zhurnal._ua_connect/_Obertka`.

Владельцу ничего присылать не нужно.

## Точная корневая причина

1. `db.py::_ua_lock3_connect` сам задаёт `timeout=30` и `busy_timeout=30000`.
2. `db.connect` использует `ZAMOK_OZHIDANIE=20`, поэтому очередь одного процесса может ждать 20 секунд.
3. `trace_zhurnal.py::_ua_connect` снова задаёт 30 секунд.
4. `trace_zhurnal.py::_Obertka.__enter__` повышает любой меньший timeout до 30 секунд.
5. `update_card_field` делает UPDATE+commit, затем `log_action` открывает второе соединение и делает второй commit.
6. Цена затем вызывает `remember_price`, который делает третий UPDATE+commit для JSON-поля `price_history`.
7. SQL-идентификаторы `table/field` сейчас интерполируются без жёсткого allowlist.

## Реализация v1.2

1. Создать точечные diff к реальным `db.py`, `cars_ui.py`, `trace_zhurnal.py`; полная замена файлов запрещена.
2. Удалить все глобальные принудительные `30s/30000ms` из `_ua_lock3_connect`, `_ua_connect` и `_Obertka`. Диагностика только наблюдает и не меняет соединение/транзакцию.
3. Все поля `cars` и разрешённые поля `clients` направить через один реальный writer. Таблица и колонка выбираются только из жёстких allowlist-маппингов.
4. Одна операция изменения поля делает основной UPDATE и audit INSERT в одной короткой транзакции и одном commit.
5. Цена `price_uah` + JSON `price_history` + audit записываются одной атомарной операцией; отдельный `remember_price` после commit исключить.
6. Бюджет прямой записи: ≤1 с. При `locked/busy/queue timeout` — durable enqueue и быстрый ответ без traceback.
7. Durable FIFO — отдельная process-safe SQLite queue с атомарными `enqueue/claim/ack/requeue`, fsync/WAL, стабильным `operation_id` и UNIQUE-защитой повторного применения.
8. Replay идемпотентен: crash после DB commit до ack не создаёт дубль истории/аудита и не накладывает старое значение поверх нового.
9. Фоновая публикация сайта, rebuild и отправка медиа не входят в синхронный путь сохранения.
10. Единое правило для всех 11 текущих и любых будущих UA-XXXX. Текущая карточка не заменяется новой и чужие карточки не меняются.

## Скорость и ответ пользователю

- внутренняя DB-операция без lock: p95 ≤0,25 с; p99 ≤1 с;
- текст/число end-to-end: p95 ≤1,5 с, максимум 2 с;
- при lock: durable acceptance ≤1 с и честный статус `Принято, сохраняю`; `Сохранено` только после commit/ack;
- голос/фото: подтверждение приёма ≤7 с;
- `database is locked`, traceback и пути сервера в Telegram: 0;
- runtime LLM tokens для writer/canary/watchdog: 0.

## Canary и постоянный контроль

В Gate A подготовить guard; запускать на production только после отдельного Gate B.

Guard каждые 5 секунд проверяет:
- heartbeat бота и единственность Always-On `start_safe.py`;
- число `locked/busy`, p95/p99 latency;
- queue depth и возраст старейшей операции;
- успех drain/ack;
- `quick_check` по безопасному расписанию;
- неизменность количества карточек и protected SHA.

Безопасное автоматическое действие:
1. единичный lock → durable enqueue, без рестарта;
2. queue>0 → немедленный drain после освобождения БД;
3. oldest queue age >15 с или heartbeat >15 с → один контролируемый restart writer/bot;
4. повторный P0, queue age >30 с, `quick_check != ok`, card-count/SHA mismatch → остановить новые writes, откатить только код к backup, сохранить очередь, отправить один alert;
5. запрет автоматического удаления/исправления данных и запрет бесконечных restart loops;
6. один alert на инцидент + один recovery alert, без спама.

Контроль после Gate B:
- canary 10 минут: 0 P0, SLA PASS, queue возвращается к 0;
- soak 60 минут: 0 потерь/дублей/cross-card;
- пассивный guard 72 часа с журналом latency, lock, queue и recovery;
- любой P0 в canary/soak → автоматический rollback к backup и статус FAIL.

## Gate A — обязательная матрица

- Реальный source/schema evidence используется как preimage; SHA/AST guard до патча.
- Цена `11400`: одна транзакция, read-back той же карточки, одна запись истории и одна audit-запись.
- По 100 операций: цена, пробег, этап, контейнер, срок; без потерь, дублей и cross-card.
- Та же матрица под `BEGIN EXCLUSIVE`: быстрый enqueue, затем FIFO drain=0.
- Crash-points: после enqueue, после commit до ack, во время drain и restart — ровно одно применение.
- ≥2 процесса одновременно enqueue+drain — без потерь/порчи.
- Fuzz неизвестных/вредоносных `table/field` — отказ до SQL.
- `quick_check=ok`; `cars_count=11`; UA-0009 hash неизменен; синтетическая будущая UA-XXXX на копии PASS.
- Protected фото/видео/диагностика/контейнеры/сайт не меняются.
- Backup, rollback, dry-run installer и независимый тест-отчёт обязательны.

## Выход Gate A

Создать under `cloud/task_070/`: точечный patch/installer, real-schema tests, canary guard, rollback и измеримый отчёт.
Production/CRM/PythonAnywhere не менять.
`PASS_READY_FOR_GATE_B` только после независимого прохождения всей матрицы.
Gate B — только отдельным письменным разрешением владельца.
