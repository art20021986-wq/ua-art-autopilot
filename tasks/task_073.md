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

## Реальный live-аудит Codex и обязательная коррекция R3

После отклонённого офлайн-прототипа Codex выполнил отдельный реальный GET-only probe через защищённый GitHub runner. Использовать `cloud/task_073/evidence/live_probe.json`, generated `2026-08-29T02:33Z`. Evidence получен только GET-запросами; production не менялся.

Подтверждено:

- `crm.db sha256=5743702206898b09543d6f50fb8b76a0b04265140ac8d14d0c1430bb99bb6eb4`, `quick_check=ok`, 11 уникальных UA-0001…UA-0011;
- UA-0011: `id=18`, `published=1`, `publish_pending=0`, `status=sea_loaded`, диагностика отсутствует;
- public `UA-0011.html` и `UA-0011-diag.html` перенаправляются на `/video/index.html`; в `katalog.html` ровно UA-0001…UA-0010, UA-0011 нет;
- актуальные full SHA записаны в evidence для `cars_ui.py`, `konteyner.py`, `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py` и остальных файлов;
- реальный `konteyner.gde_mashina` и fallback `cars_ui.stage_menu` строят все `S.STATUSES`, включая внешние `sea_loaded / Загружено в контейнер` и `sea_transit / В пути`;
- реальный `konteyner._ekran` (`📦 Номер и дата контейнера`) пока содержит поля номера/даты/срока, но не содержит двух status-callback. Следовательно, нельзя просто удалить внешние кнопки: сначала перенести/добавить те же `car_setstage:<cid>:sea_loaded|sea_transit` внутрь `_ekran`, затем исключить их из обоих внешних renderers. Существующие handlers `cars_ui.stage_set` и `konteyner.posle_statusa` не менять;
- одинаковый `_ua_seo068_normalize` в `stranica.py`, `master_card.py`, `yadro.py` требует существующий live `<UA>-diag.html` ДО построения нового bundle и выбрасывает `SEO068_DIAGNOSTIC_TARGET_MISSING`; ниже уже существует `_ua068_ensure_diag_files`, поэтому текущий порядок делает failsafe недостижимым для новой карточки;
- `cars_ui.toggle_publish` сначала пишет `published=1`, затем получает `(ok, text)` от `publikaciya.opublikovat`, игнорирует `ok` и безусловно отправляет `Машина видна клиентам в каталоге.`;
- `publikaciya.opublikovat` пишет primary/diag, но общий `katalog.html` обновляется только отдельным hardcoded UA-0009 helper/background full rebuild. Это не единый commit публикации.

### Отклонить R1-прототипы

Текущие `tools/live_audit_controller.py`, `keyboard_transformer.py`, `publish_guard.py`, `installer.py`, `public_verifier.py` и `workflows/gate_b_manual_dispatch.yml` не являются release-кандидатом:

- live controller возвращает `NOT_IMPLEMENTED_WITHOUT_LIVE_CREDENTIALS`;
- keyboard transformer работает с вымышленным dict, не с live Python source;
- publish guard пишет только два файла последовательно, не строит каталог/счётчики и не откатывает уже заменённый первый файл;
- installer имеет неиспользуемый `target_paths`, collision backup по basename и неполный rollback;
- verifier проверяет одну страницу и вымышленный revision header;
- Gate B workflow содержит placeholder `echo` вместо действий.

Не удалять их ради маскировки истории, но пометить в отчёте `REJECTED_PROTOTYPE_DO_NOT_DEPLOY` и создать полностью реализованные файлы с суффиксом `_v2`.

### Обязательный live-кандидат V2

1. `patcher_v2.py` скачивает/принимает полные live preimage только во временной среде и применяет точечные SHA+AST transforms:
   - `konteyner._ekran`: добавить ровно по одному рабочему `car_setstage:%d:sea_loaded` и `car_setstage:%d:sea_transit` внутри контейнерного раздела;
   - `konteyner.gde_mashina` и `cars_ui.stage_menu`: исключить только эти два code из внешних списков; остальные статусы/порядок/callback неизменны;
   - `cars_ui.toggle_publish`: учитывать `ok`; success только после publish PASS; при publish fail вернуть `published` к точному preimage с read-back и отправить одно failure-сообщение; исключения также fail+rollback; скрытие сохранить;
   - в трёх `_ua_seo068_normalize` убрать только ошибочный precondition на **старый live diagnostic file**. Оставить fail-closed проверки canonical, robots, exact diagnostic href, CTA и insertion point. Наличие/валидность diagnostics теперь проверяется в staged bundle до commit;
   - `publikaciya.py`: добавить generic unified publisher для любого UA, не hardcoded UA-0009. Он до write строит primary+diag/placeholder+catalog для VIDEO и SITE, валидирует 11 уникальных карточек и exact href, готовит все temp files + fsync + manifest, делает уникальный backup каждого target, заменяет bounded set, read-back проверяет SHA и protected cards, при любой ошибке откатывает весь write set и проверяет восстановление. `proba=True` = строго zero production writes.
2. Не менять `crm.db` в publisher. Единственная разрешённая DB-операция остаётся существующий field `published` выбранной карточки через `toggle_publish` с точным rollback при fail.
3. Interactive publication должна проверить exact UA primary, diagnostics и catalog через реальный public HTTP без redirect-to-home до финального success; не требовать несуществующий revision header. Gate B дополнительно делает delayed verify >=60 секунд.
4. Background `stranica.main()` после изменения DB тоже обязан проходить для UA-0011 без старого diag target и генерировать placeholder+catalog; Gate A запускает его только на temp copy/tree.
5. Gate A V2 реально использует `PYTHONANYWHERE_API_TOKEN` GET-only, повторно проверяет свежие SHA, скачивает source+DB во временную папку, применяет V2 candidate, compile/import/tests на копии и не пишет production.
6. Gate A V2 обязан доказать baseline FAIL → candidate PASS для UA-0011, UI outer=0/inner=2, false-success rollback, unified catalog=11, idempotent repeat, future UA-9913, fault injection + full rollback, UA-0009 и existing 10 protected.
7. Создать реально исполнимые `gate_a_v2.py`, `gate_b_installer_v2.py`, `gate_b_controller_v2.py`, `postcheck_v2.py`, `GATE_A_V2_REPORT.md` generator и два workflow-файла under `cloud/task_073/workflows/`. Никаких `placeholder`, `TODO`, `NOT_IMPLEMENTED` или `echo`-шагов.
8. Gate A workflow использует secret только для GET и может иметь push-trigger только на собственный путь после копирования Codex в `.github/workflows/`. Gate B — только manual `workflow_dispatch` с exact approval token.
9. Для PythonAnywhere API/controller использовать проверенные production patterns из `cloud/task_069/gate_a.py`, `cloud/task_069/gate_b_controller.py`, `cloud/task_069/gate_b_installer.py`, `cloud/task_072/gate_a_v2.py` и `cloud/task_072/gate_b_controller_v2.py`; не создавать очередной API shell.
10. Все Python-файлы compile + unit/integration tests внутри автопилота. Отчёт не может заявлять Gate A PASS, пока реальный secret-backed workflow не выполнен; допустимый результат генерации — `READY_TO_RUN_REAL_GATE_A_V2`.

После этой коррекции production по-прежнему не трогать: Claude создаёт V2 release tooling, Codex копирует/запускает реальный Gate A, аудитирует evidence и только при PASS запускает уже одобренный Gate B.


---

## ROUND 4 — ОБЯЗАТЕЛЬНАЯ КОРРЕКЦИЯ ПО РЕЗУЛЬТАТАМ НЕЗАВИСИМОГО LIVE-АУДИТА CODEX

Текущие V2-файлы из commit 5e65396 являются НЕВЫПУСКАЕМЫМ кандидатом. Их нельзя копировать в .github и нельзя запускать против production. Причины подтверждены exact live definitions в `cloud/task_073/evidence/live_probe.json`:

1. `transform_gde_mashina_remove_outer` и `transform_stage_menu_remove_outer` ищут прямые строки `InlineKeyboardButton(...sea_loaded...)`, но live-функции строят кнопки comprehension из `S.STATUSES.items()`. Exact anchors:
   - `konteyner.gde_mashina` definition SHA256 `d49710dbe1831353432c084439afc1ece9203eee116db9c42b0b00fcb7ca964c`; фильтр: `if stage_no == nomer_etapa`.
   - `cars_ui.stage_menu` definition SHA256 `edf960e645680f758dd3cbfd071410067f6b4be2a94ec4c4ca97793fc9d8d795`; фильтр: `if stage_no == number`.
   Корректная точечная семантика: добавить к каждому фильтру исключение `code not in ("sea_loaded", "sea_transit")`; не удалять статусы из `S.STATUSES` и не менять handler `car_setstage`.

2. `konteyner._ekran` exact definition SHA256 `5e970dcedd8e29da0562dc2653c1b6173fd8d3007e0203fffc5e9f36bd196e6b`. Внутрь его `rows`, после controls номера/даты/дней и до очистки/навигации, добавить ровно две однострочные кнопки:
   - `Загружено в контейнер` -> `car_setstage:%d:sea_loaded`
   - `В пути` -> `car_setstage:%d:sea_transit`
   Они обязаны использовать существующий рабочий handler; никаких новых status values/DB migrations.

3. `transform_seo068_drop_stale_precondition` ищет `os.path.exists(...diag...)`, но live-код во всех трёх модулях одинаков и имеет definition SHA256 `30b706b49cbd0895631a8fd1dbe6908055016f0ef03fd30dd7338a7be0887566`:
   `if not any(_ua_seo068_os.path.isfile(_ua_seo068_os.path.join(root, target)) for root in ('/home/Carix/video', '/home/Carix/site')):`
   `    raise RuntimeError('SEO068_DIAGNOSTIC_TARGET_MISSING:' + identifier)`
   Удалить только этот exact stale precondition в `stranica.py`, `master_card.py`, `yadro.py`; canonical/robots/exact href/CTA/insertion guards оставить.

4. `transform_toggle_publish_respect_ok` ищет `ok, text = publikaciya.opublikovat(...)`, но live `cars_ui.toggle_publish` definition SHA256 `21c3f452813122f18247359259432bed2a23f12163ac36859bac0ffd594d8682` использует async `_ok_rem2, _txt_rem2 = await _aio_rem2.to_thread(_pub_rem2.opublikovat, ...)` и сейчас игнорирует `_ok_rem2`. Исправить exact live shape:
   - сохранить `preimage_published` до update;
   - при `_ok_rem2 is not True` либо exception вернуть published только если read-back всё ещё равен записанному `novoe`, проверить read-back;
   - отправить реальную причину отказа;
   - не отправлять `Машина видна клиентам в каталоге.`;
   - success разрешён только после publisher `ok=True` и его bounded verification.
   Скрытие (`novoe=0`) не ломать.

5. Live `publikaciya.opublikovat` definition SHA256 `93f130c2542124b820eae2416984705ecbbc80019a298d2b3c40fdf58d93033f` пишет primary/diag, но не `katalog.html`. Исправить существующий publisher, а не создавать параллельную кнопку:
   - перед любой записью собрать primary + mandatory diag/placeholder + полный catalog через существующий `_ua9_sobrat_katalog()`;
   - добавить оба `katalog.html` (VIDEO/SITE) в тот же bounded backup/write-set;
   - исправить `_otkat`: восстановить pre-existing target из backup, а newly-created target без preimage удалить;
   - staged validation до commit: primary содержит только UA-0011 как card identity, exact CTA `UA-0011-diag.html`, diag существует, catalog содержит exact `href=UA-0011.html` ровно один раз;
   - на любой записи/read-back/validation/regression ошибке откатить ВЕСЬ set primary+diag+catalog;
   - не запускать полный `stranica.main()` и не пересобирать чужие карточки.
   Итог: bounded per-card publish + один catalog, без LLM и без DB migration.

6. `postcheck_v2.verify_card` сейчас игнорирует `revision_marker`, не проверяет body и controller не проверяет diagnostics overall. Исправить:
   - exact requested URL == final URL, HTTP 200, без redirect;
   - primary body содержит UA-0011 и expected semantic marker/CTA;
   - diag URL exact 200 и содержит UA-0011/approved placeholder;
   - catalog exact 200 и exact href UA-0011 ровно 1;
   - immediate и delayed >=60s должны пройти все три страницы;
   - protected UA-0001..UA-0010 primary/diag hashes не меняются (catalog — ожидаемое изменение);
   - UA-0009 DB row SHA остаётся `b31572a4d321e40a8f8d07b7b127db4751f1cdaa8a1aa2369e27754f178dfbf7`; SQLite quick_check=ok; 11 unique cards.

7. Gate B сейчас не исполним: workflow требует отсутствующий `gate_b_production_entrypoint.py` и незаданные repo vars. Создать ПОЛНОСТЬЮ ИСПОЛНИМЫЙ production комплект, используя реальный trigger/receipt/API/restart pattern из `cloud/task_069/gate_b_controller.py` и installer pattern из task069/task072:
   - verified username/root: `Carix`, `/home/Carix`;
   - safe remote: `/home/Carix/autopilot_inbox/cloud/task_073`;
   - controller загружает reviewed patcher/installer/postcheck, GET read-back, запускает remote shadow через temporary always_on/schedule trigger, затем install/publish, restart exact active launcher `python3.10 /home/Carix/start_safe.py`, immediate+delayed postcheck;
   - exclusive GitHub production-window guard;
   - backup всех 6 code files (`konteyner.py`, `cars_ui.py`, `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py`) и всех bounded public targets before write;
   - source full-file SHA anchors из live_probe; fail closed on drift;
   - DB не писать в Gate B (UA-0011 already published=1); DB full-file rollback запрещён;
   - при любой ошибке после install выполнить explicit rollback code+public targets, restart и read-only verification;
   - no `TASK073_PA_DOMAIN` / `TASK073_PA_REMOTE_DIR` variables; no placeholder entrypoint, no TODO, no NOT_IMPLEMENTED, no echo-only production step.

8. Создать новую reviewable серию `patcher_v3.py`, `gate_a_v3.py`, `gate_b_installer_v3.py`, `gate_b_controller_v3.py`, `postcheck_v3.py`, exact unit/integration tests и два workflow-файла under `cloud/task_073/workflows/`. Не перезаписывать V2 так, чтобы было трудно сравнить.

9. Gate A V3 должен реально GET-fetch все live source, проверять полные file SHA из `live_probe.json`, применять все transforms in memory, compile, semantic assertions и dry-run publisher bundle on a temporary filesystem/database copy. Production writes=0. Только live secret-backed run может дать PASS.

10. Gate B workflow остаётся manual `workflow_dispatch` с exact token `CRM-UNIFIED-CATALOG-001-V1.0-APPROVED`. Claude НЕ запускает production. Codex после независимого аудита копирует Gate A V3 workflow в `.github/workflows`, запускает; при PASS запускает уже утверждённый Gate B.

ROUND 4 результат считается готовым только если entrypoint реально существует, workflow не содержит условной заглушки, все tests проходят, а отчёт честно имеет `READY_TO_RUN_REAL_GATE_A_V3`. Production не трогать.
