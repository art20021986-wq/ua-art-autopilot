# TASK 072 — CRM-DESCRIPTION-SAVE-072 v1.0

STATUS: PASS_READY_FOR_OWNER_GATE_B
PRIORITY: P0
MODE: ROOT-CAUSE REPAIR / INDEPENDENT GATE A
OWNER_DIRECTIVE: «Не могу добавить описание. Реши вопрос с существующими карточками и дальнейшими карточками, чтобы такого вопроса больше не возникало у меня.»
PRODUCTION_WRITE: NO
CRM_DB_PRODUCTION_WRITE: NO
PYTHONANYWHERE_SOURCE_WRITE: NO
RUNTIME_LLM_TOKENS_TARGET: 0

## Подтверждённый инцидент

В открытой карточке владелец вставляет длинное многострочное маркетинговое описание (русский/украинский текст, переносы строк, символы, VIN и «500 $»), но CRM не отвечает «Описание сохранено» и текст не появляется в карточке.

Текущий live call path из `cloud/task_071/evidence/call_path.json`:
`cars_ui.catch_message → apply_value → set_field → db.update_card_field`.

Корневые дефекты:
1. В ветке `if wait and input_text` выполняется `context.user_data.pop("car_wait", None)` ДО подтверждённой записи. При `database is locked` режим ввода теряется, поэтому повтор не продолжает редактирование описания.
2. `db.update_card_field` делает `get_card`, UPDATE и `log_action` через три отдельных соединения/commit.
3. `apply_value` возвращает успех без обязательного read-back сохранённого текста.
4. `trace_zhurnal.py` и `db.py` расширяют timeout/busy_timeout до 20–30 секунд, поэтому Telegram выглядит зависшим.
5. В реальной схеме одновременно есть `condition_text`, `description` и `diag_text`; их нельзя смешивать.
6. TASK 071 не является готовым решением: live controller там фактически NOT_IMPLEMENTED, production import из `cloud.task_071` недопустим, его writer не включает `condition_text/description`, использует несовместимую схему audit/operation_id и содержит несовместимые с live-сигнатурами вставки. TASK 072 должна исправить эти дефекты, а не наследовать их.

Подтверждённые live SHA на момент GET-only evidence:
- `db.py=b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086`
- `cars_ui.py=862baea2ca0794f5e0d83bc04169f6d2fdec401f86f384ef4376e373c02a776b`
- `trace_zhurnal.py=fc4b95fc749f3d9b785ce69bfce2705b11ade95a560d6fbd901b50de1423d086`
- live schema: `cars_count=11`, UA-0001…UA-0011, UA-0009 ровно одна, `PRAGMA quick_check=ok`.

## Единый контракт описания

1. Каноническое маркетинговое описание автомобиля — `cars.condition_text`.
2. `cars.description` — legacy alias на входе: любая команда/кнопка «Описание» должна записывать в `condition_text`. Существующее legacy-значение не удалять; чтение использует `condition_text`, затем fallback `description`.
3. `diag_text` — только заключение комплексной диагностики. Маркетинговое описание никогда не писать в `diag_text`.
4. На каждой существующей и любой будущей карточке автоматически доступна одна кнопка `📝 Описание` с callback, привязанным к фактическому `card_id`; без списков `range(1, N)` и без ручной настройки новой карточки.
5. После кнопки бот принимает 1–12000 Unicode-символов, сохраняет переносы строк и внутреннее форматирование. Убираются только внешние пустые строки/NUL; текст не сокращается и не «улучшается» ИИ.
6. Дополнительный детерминированный путь: в открытой карточке `Описание: <текст>`, `Добавь описание: <текст>`, `Измени описание: <текст>`. Он обновляет только открытую карточку и не создаёт новую.
7. Без открытой карточки текст/фото/голос не создаёт карточку и не записывает описание: бот просит выбрать карточку.
8. Повтор одного Telegram `chat_id:message_id` идемпотентен.
9. Ответ `✅ Описание сохранено` допустим только после commit и точного read-back той же `card_id`. При очереди: `Принято, сохраняю`; финальное `✅ Описание сохранено` только после commit/ack.
10. При ошибке или временной блокировке `car_wait` не теряется. Пользователь может повторить без повторного входа в карточку.
11. Подтверждение не должно повторять более 900 символов текста, чтобы не превысить Telegram limit; в БД сохраняется полный текст.
12. Синхронный путь не перестраивает сайт, не отправляет медиа и не запускает публикацию.

## Корневое исправление записи

1. Построить реальный standalone module для `/home/Carix` (не import из `cloud/`), совместимый с Python 3 live.
2. Строгий allowlist таблиц/полей строится из подтверждённой live-схемы; свободная SQL-интерполяция запрещена. Обязательные поля: `cars.condition_text` и legacy input alias `description→condition_text`; сохранить совместимость остальных текущих scalar-полей.
3. Одна правка: SELECT current + UPDATE + INSERT в реальную таблицу `audit` с её реальными колонками в одной короткой транзакции, одном соединении и одном commit.
4. Прямой write budget ≤0.8 с. При locked/busy — durable process-safe FIFO sidecar SQLite с UNIQUE `operation_id`; не менять schema `crm.db`.
5. Очередь не должна позволять старому queued-описанию перезаписать более новое. Drain идемпотентен при crash после CRM commit до queue ack.
6. Диагностические обёртки только наблюдают и не увеличивают timeout/busy_timeout/journal mode вызывающей транзакции.
7. Сохранить публичные API `db.connect`, `db.update_card_field`, `cars_ui.set_field/apply_value/catch_message` и все текущие callback.
8. Все исключения преобразуются в короткий безопасный ответ; traceback, серверные пути и `database is locked` в Telegram запрещены.
9. Никаких LLM-вызовов для сохранения описания.

## Независимая Gate A на реальной локальной копии

Через PythonAnywhere API использовать только GET и скачать во временную папку runner полные live `db.py`, `cars_ui.py`, `trace_zhurnal.py`, необходимые schema modules и `crm.db`. Ничего из полных live-файлов/БД не коммитить и не выводить в лог.

Обязательно:
- свежие full SHA + AST anchors; при drift — fail closed, без слепого patch;
- патч реально применяется только к временным копиям, compile/import PASS;
- baseline test на старой копии воспроизводит потерю `car_wait`/lock; patched test PASS;
- stub Telegram call-path: кнопка «Описание» → длинный текст со строками, кириллицей, emoji, VIN и `500 $` → точный read-back `condition_text`, один audit, правильный `card_id`;
- прямые команды `Описание:`, `Добавь описание:`, `Измени описание:` PASS;
- пустой текст, 12001 символ, NUL, неизвестное поле безопасно отклоняются;
- под `BEGIN EXCLUSIVE`: acceptance ≤1 с, затем FIFO drain до 0 и ровно одно применение;
- replay одинакового `chat_id:message_id`, crash after enqueue, crash after CRM commit before ack, restart/multiprocess drain — без дублей;
- каждая из 11 существующих карточек на отдельной копии проходит save/read-back без cross-card;
- будущая `UA-9912` на отдельной копии автоматически получает тот же путь без изменения кода;
- `cars_count` production copy остаётся 11; UA-0009 hash отдельно PASS; прочие поля, `description`, `diag_text`, media/photo/video/diagnostics/container/site SHA не меняются;
- `PRAGMA quick_check=ok`;
- 100 последовательных и конкурентных описаний: last-intended-wins, без потерь/дублей;
- p95/p99, backup, code-only rollback с сохранением очереди;
- production/CRM/PythonAnywhere остаются read-only.

## Выход

Создать только under `cloud/task_072/`:
- live GET-only controller (полностью реализованный, без NOT_IMPLEMENTED);
- точечный SHA+AST transformer;
- standalone writer + durable queue;
- локальный installer dry-run/apply/rollback;
- call-path tests;
- redacted evidence;
- `GATE_A_REPORT.md`;
- production Gate B plan/installer, но НЕ запускать.

Обновить `cloud/latest_status.md` и `cloud/owner_reply.md`.

Запустить Gate A автоматически после создания workflow/controller. Не ждать владельца.

Только при полном реальном PASS записать:
`TASK_072_GATE_A: PASS_READY_FOR_OWNER_GATE_B`
`DESCRIPTION_SAVE_EXISTING_11: PASS`
`DESCRIPTION_SAVE_FUTURE_CARD: PASS`
`NO_NEW_CARD_CREATED: PASS`
`UA-0009_INTEGRITY: PASS`
`SAFE_TO_START_PRODUCTION_GATE_B: YES`

При любом пробеле — BLOCKED/FAIL с точной причиной. Production не менять до отдельного письменного Gate B владельца.


## Независимый Gate A V2 — итог

`TASK_072_GATE_A: PASS_READY_FOR_OWNER_GATE_B`
`DESCRIPTION_SAVE_EXISTING_11: PASS`
`DESCRIPTION_SAVE_FUTURE_CARD: PASS`
`NO_NEW_CARD_CREATED: PASS`
`UA-0009_INTEGRITY: PASS`
`SAFE_TO_START_PRODUCTION_GATE_B: YES`

Фактический Gate A завершён через GET-only PythonAnywhere API. Production не менялся.
Gate B подготовлен без push-trigger и может быть запущен только после отдельного
письменного подтверждения владельца `TASK_072_GATE_B_APPROVED`.
