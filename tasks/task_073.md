# TASK 073 — CRM-UNIFIED-CATALOG-001 v1.0

STATUS: OWNER_APPROVED_IN_WORK
PRIORITY: P0
MODE: ROOT-CAUSE REPAIR / GATE A + MANUAL GATE B RELEASE
OWNER_DIRECTIVE: «УТВЕРЖДАЮ CRM-UNIFIED-CATALOG-001 v1.0. В РАБОТУ.»
OWNER_GATE_B_APPROVAL_RECEIVED: YES
OWNER_APPROVAL_TOKEN: CRM-UNIFIED-CATALOG-001-V1.0-APPROVED
RUNTIME_LLM_TOKENS_TARGET: 0

## Цель

Сделать CRM визуально единой и недублирующей, не нарушив существующие рабочие процессы, и устранить корневую причину, по которой объявление UA-0011 не выходит в публичный каталог.

Контракт состоит из двух связанных, но строго ограниченных изменений:

1. Убрать только две дублирующие кнопки верхнего уровня карточки CRM: `Загружено в контейнер` и `В пути`.
2. Исправить публикацию UA-0011 и общий путь будущих публикаций так, чтобы отсутствие диагностических материалов не блокировало карточку и никогда не приводило к ложному сообщению об успехе.

Не устанавливать и не смешивать с этой задачей ожидающие production-патчи TASK 069, TASK 070/071 или TASK 072. Не менять сохранение описания, общий writer CRM, контейнерные значения либо другие поля, если это не требуется непосредственно данным контрактом.

## Подтверждённые симптомы

- Внешние кнопки `Загружено в контейнер` и `В пути` визуально дублируют рабочие действия внутри раздела владельца `Номер и дата контейнера` (фактическое live-название раздела определить аудитом; ранее использовалось `📦 Контейнер, даты и сроки`).
- Внутренние кнопки сейчас используются в рабочем процессе и должны остаться с теми же callback, переходами статуса и записью в те же поля.
- В CRM существуют 11 карточек UA-0001…UA-0011.
- В публичном каталоге видны только 10 карточек; UA-0011 отсутствует.
- При `Показать в каталоге` для UA-0011 CRM сообщает:
  `Публикация отменена: сборщик не смог собрать UA-0011 (SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0011). Старая страница цела.`
- После ошибки CRM противоречиво сообщает: `Машина видна клиентам в каталоге.`
- Публичные `/video/UA-0011.html` и `/video/UA-0011-diag.html` не открывают карточку UA-0011, а возвращают/перенаправляют на главную.
- Для существующей UA-0010 диагностический маршрут работает даже без материалов и показывает безопасный placeholder `Материалы диагностики пока не добавлены.` Это допустимый контракт для UA-0011 и будущих карточек.

Перед реализацией повторить GET-only аудит live production и записать свежие SHA, AST anchors, схему, маршруты и фактический call path. При любом drift — fail closed; никаких слепых замен полных файлов.

## Контракт интерфейса CRM

1. В основном/верхнем меню открытой карточки не должно быть кнопок `Загружено в контейнер` и `В пути`.
2. Внутри единственного контейнерного раздела обе рабочие операции остаются доступны ровно по одному разу.
3. Сохранить без изменения callback data, handler, переходы статуса, запись контейнера/дат/сроков и возможность вернуться в карточку.
4. Не удалять сами статусы из бизнес-логики, БД, каталога, фильтров, журналов или карточек клиентов. Изменяется только размещение двух кнопок верхнего уровня.
5. Все остальные кнопки, порядок разделов и права доступа сохраняются, если аудит не докажет обязательную техническую коррекцию.
6. Правило применяется динамически ко всем 11 существующим и будущим карточкам; запрещены списки `range(1, N)` и ручная привязка UA-номеров.
7. Структурная проверка обязательна: outer occurrence = 0; inner occurrence = 1 для каждого действия. Простой глобальный подсчёт текста недостаточен.

## Корневой контракт публикации

1. Сохранить SEO068 fail-closed guard. Нельзя отключать проверку обязательных целей, подменять ошибку успехом или публиковать битую ссылку.
2. Если у автомобиля ещё нет диагностических материалов, сборщик атомарно создаёт каноническую диагностическую placeholder-страницу по действующему шаблону UA-0010. Отсутствие материалов не является причиной отмены основной публикации.
3. Одна публикация формирует согласованный staged bundle: основная карточка, диагностический маршрут/placeholder, необходимые индексы каталога, счётчики/фильтры и только те sitemap/manifest-файлы, которые реально требуются текущей архитектурой.
4. До публикации весь bundle собирается во временном каталоге, компилируется/валидируется и получает manifest с SHA. В production файлы заменяются атомарно только после полного PASS.
5. Существующие UA-0001…UA-0010, их медиа, диагностика, тексты, VIN, этапы и маршруты не перегенерировать без необходимости. Разрешены изменения только UA-0011 и общих индексов/счётчиков/manifest, подтверждённые отчётом.
6. Публикация идемпотентна: повторный запрос не создаёт дубль карточки, ссылки, счётчика или диагностики и не меняет уже корректное содержимое.
7. Для любой будущей UA-XXXX без диагностики действует тот же placeholder-путь без изменения кода.
8. Сообщение `Машина видна клиентам в каталоге` допустимо только после успешного commit публикации и фактической публичной HTTP-проверки этой же ревизии. При любой ошибке — одно честное сообщение об ошибке, без последующего success.
9. Проверка success должна быть привязана к точному `card_id/auto_number` и publish revision; чужая или старая страница не засчитывается.
10. Синхронный Telegram handler не должен выполнять полный rebuild всего сайта и не должен блокироваться на минуты. Использовать минимальный bundle/существующий безопасный фоновой механизм; мгновенный ответ о начале не считать финальным успехом.

## Целостность и скорость

- `crm.db` остаётся с 11 карточками, UA-0001…UA-0011 ровно по одной; `PRAGMA quick_check=ok`.
- UA-0009 — отдельный protected canary: row hash, карточка, медиа и диагностический маршрут неизменны.
- Не менять `condition_text`, `description`, `diag_text`, фото, видео, цены, VIN, контейнер, даты и статусы существующих карточек.
- Если текущий publish path меняет только publication flag UA-0011, разрешена исключительно эта доказанная field-level операция с preimage/read-back и compare-and-swap rollback. Полный rollback живой БД запрещён.
- Навигация по карточке и открытие контейнерного раздела: не добавлять DB/HTTP/LLM вызовов; измерить baseline/patched p95 и не допустить ухудшения более 10%.
- Runtime LLM tokens для CRM, publisher, canary и watchdog: 0.
- Ошибки, traceback и серверные пути не показывать владельцу в Telegram.

## Gate A — независимый и production read-only

Через PythonAnywhere API использовать только GET и скачать во временную папку runner актуальные live source, необходимые шаблоны/страницы и согласованную копию `crm.db`. Полные live-файлы, БД, токены, персональные данные и временные download URL не коммитить и не выводить в лог.

Обязательно:

1. Зафиксировать свежие full SHA + AST/call-path anchors всех затрагиваемых файлов; сравнить с последними TASK 068/069/072 и fail closed при несовместимости.
2. Воспроизвести на baseline-копии:
   - две внешние дублирующие кнопки;
   - сохранённые рабочие inner callbacks;
   - `SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0011`;
   - отсутствие UA-0011 в каталоге;
   - ошибочный error → success control flow.
3. Применить только точечный deterministic transform к временным копиям; полная замена live source запрещена. Compile/import PASS.
4. UI matrix для каждой из 11 карточек и синтетической UA-9913:
   outer duplicates = 0; inner actions = 2; callbacks/handlers/state transitions совпадают с baseline; другие кнопки без изменений.
5. Publication matrix на отдельной копии:
   UA-0011 без диагностики → primary + placeholder diag + catalog exactly once; повторная публикация → тот же логический результат без дублей.
6. Будущая UA-9913 без диагностики → тот же PASS; карточка с диагностикой → реальные материалы не заменяются placeholder.
7. Fault injection на каждом шаге staging/install/public verify: до commit production tree неизменен; после частичного отказа автоматический rollback восстанавливает точные preimage SHA.
8. False-success tests: builder fail, diagnostics fail, catalog index fail, stale revision, redirect на главную, HTTP не-200 и delayed verify fail никогда не порождают финальный success.
9. Сверить каталожную матрицу с CRM: все 11 UA ровно один раз; категории/счётчики вычислены из фактических данных; ссылки primary/diagnostics открывают именно нужный UA.
10. Protected regression: UA-0001…UA-0010 page/media/diag SHA неизменны, кроме ожидаемых общих index files; UA-0009 отдельно PASS; `quick_check=ok`.
11. Измерить baseline/patched UI latency и publish build latency; записать число прочитанных/изменённых файлов и доказать отсутствие полного rebuild в Telegram request path.
12. Backup, bounded installer, manual Gate B workflow, immediate + delayed public verifier и автоматический rollback обязательны.
13. Production, CRM и PythonAnywhere во время Gate A остаются read-only.

## Production Gate B — уже одобрен владельцем, но запускается только Codex

CLAUDE/Cloud не выполняет CRITICAL действия. Подготовить workflow только с `workflow_dispatch`, без `push`, `schedule` или другого автоматического trigger. Input `approval` обязан точно равняться `CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`; иначе fail before secrets/write.

После полного Gate A PASS Codex вправе запустить Gate B на основании уже полученного письменного утверждения владельца, без повторного вопроса.

Безопасная последовательность Gate B:

1. exclusive production window относительно TASK 067/068/069/072 и других writers;
2. свежий GET-only preflight и точное совпадение SHA/AST/schema;
3. shadow/dry-run на свежей копии;
4. backup всех затрагиваемых source/content и field-level preimage, если он нужен;
5. code/content install атомарно;
6. restart/reload только фактически затронутого сервиса;
7. canary UA-0011;
8. immediate public verify;
9. delayed verify не ранее 60 секунд;
10. при любой ошибке — автоматический rollback всего write set, повторная availability/integrity проверка и статус FAIL;
11. только после полного PASS — финальный Telegram success и evidence receipt.

## Критерии production PASS

- `CRM_OUTER_DUPLICATE_BUTTONS: 0`
- `CRM_INNER_CONTAINER_ACTIONS: PASS`
- `UA_0011_PRIMARY_PUBLIC: PASS`
- `UA_0011_DIAGNOSTICS_ROUTE: PASS`
- `CATALOG_11_UNIQUE_CARDS: PASS`
- `NO_FALSE_PUBLICATION_SUCCESS: PASS`
- `FUTURE_CARD_WITHOUT_DIAGNOSTICS: PASS`
- `UA_0009_INTEGRITY: PASS`
- `EXISTING_10_REGRESSION: PASS`
- `CRM_QUICK_CHECK: ok`
- `RUNTIME_LLM_TOKENS: 0`
- `ROLLBACK: NOT_NEEDED` (либо Gate B = FAIL с доказанным успешным rollback)

## Выход

Создать только under `cloud/task_073/`:

- GET-only live audit/controller;
- redacted evidence;
- точечный SHA+AST transformer;
- isolated candidate and tests;
- atomic installer + rollback;
- immediate/delayed public verifier;
- manual-only Gate B controller/workflow;
- `GATE_A_REPORT.md` и после запуска `GATE_B_REPORT.md`.

Обновить `cloud/latest_status.md` и `cloud/owner_reply.md`.

Запустить Gate A автоматически после создания контроллера/workflow. Не ждать владельца. Только при полном реальном PASS записать:

`TASK_073_GATE_A: PASS_READY_FOR_APPROVED_GATE_B`
`SAFE_TO_START_PRODUCTION_GATE_B: YES`
`OWNER_APPROVAL_TOKEN: CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`

При любом пробеле — BLOCKED/FAIL с точной причиной. Не заявлять о production fix до успешного Gate B и публичной проверки.

## Retry correction R2

Первый запуск Claude Autopilot `33228502519` завершился до commit и до любых production-действий: встроенный `python -m py_compile` отклонил сгенерированный `cloud/task_073/tests/test_installer.py` на строке 66, offset 0. Ни один из 15 временно сгенерированных файлов не был сохранён в репозиторий.

Повторить формирование полного комплекта. Перед выдачей каждого Python-файла локально проверить закрытие всех строк/скобок и выполнить эквивалент `python3 -m py_compile` для **всех** `cloud/task_073/**/*.py`, включая `tests/test_installer.py`. Не сокращать и не оставлять незавершённые test literals. После compile обязательно запустить unit tests. При любой ошибке исправить кандидат внутри текущего запуска; не выдавать синтаксически невалидный файл и не переходить к Gate A/production.
