# TASK 077 — CRM-CONTAINER-STAGE-SYNC-004 v1.0

OWNER_APPROVAL: `УТВЕРЖДАЮ CRM-CONTAINER-STAGE-SYNC-004 v1.0. В РАБОТУ.`

## Режим

`BACKUP → GET-only AUDIT → SANDBOX/CANARY`. Production запрещён до отдельной
письменной команды владельца. Не запускать и не подменять Gate B TASK 076.
Сначала прочитать результат TASK 076 и расширить его единую ETA-транзакцию,
не создавать второй конкурирующий writer.

## Подтверждённый дефект

Live-код хранит два статуса одного публичного этапа:
`sea_loaded / Загружено в контейнер` и `sea_transit / В пути`. Оба строятся в
меню из `S.STATUSES`. Обработчик срока записывает ETA отдельно и не обязан
менять `status`; поэтому CRM может показать сохранённый срок, но этап/категория
останутся несогласованными. На скриншоте UA-0012: 30 дней, 28.09.2026, при этом
контейнерные данные пусты и использован самостоятельный этап «В пути».

Дополнительное live-доказательство 29.08.2026 13:28: для UA-0012 CRM сначала
сообщила `SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0012` и «Публикация отменена», а
следующим сообщением ложно заявила «Машина видна клиентам в каталоге». Значит,
caller игнорирует publisher FAIL либо отправляет success из независимой ветки.

## Итоговый контракт владельца

1. Полностью удалить самостоятельную кнопку **«В пути»** из всех фактически
   активных renderers CRM, существующих и будущих карточек.
2. Оставить ровно одну рабочую кнопку **«Загружено в контейнер»** в маршруте
   `🚚 Доставка и этапы`; callback `car_setstage:<cid>:sea_loaded` сохраняется.
3. `Продано · в пути / sold_transit` не изменять.
4. Единственный канонический внутренний код обычного паромного этапа —
   `sea_loaded`. Legacy `sea_transit` после отдельного production approval
   мигрируется в `sea_loaded` одной bounded row-level транзакцией.
5. В CRM текущая подпись для `sea_loaded` и временно для legacy `sea_transit` —
   **«На пароме»**. Кнопка действия остаётся **«Загружено в контейнер»**.
6. На сайте badge и категория — **«На пароме» / `more`**. Публичного отдельного
   этапа «В пути» нет.

## Автоматическая транзакция

При фиксации количества дней внутри контейнерного flow для карточки этапа
Корея/Паром одна логическая транзакция обязана сохранить и проверить:

- `status=sea_loaded`;
- `days_to_kyiv=N`;
- `eta_manual=UTC_today+N days`;
- `updated_at`;
- staged bounded rebuild primary + diag/placeholder + два каталога;
- read-back БД и проверку обеих `/video` и `/site` canary.

Этапы Грузия/Киев и terminal/sold нельзя автоматически откатывать назад при
редактировании срока. Success-сообщение разрешено только после полного PASS.
При DB/read-back/publisher/queue/verify failure — понятная ошибка, отсутствие
ложного успеха и полный bounded rollback. Повтор той же команды идемпотентен.
Отсутствующая диагностика не является ошибкой публикации: до commit создаётся
каноническая страница-заглушка «Материалы диагностики ожидаются». Ошибка
`SEO068_DIAGNOSTIC_TARGET_MISSING` для новой карточки после патча недопустима.
На один запрос разрешено ровно одно итоговое сообщение: success только после
verified PASS, иначе только failure; поле `published` возвращается к preimage.

## Gate A — свежий GET-only аудит

Получить актуальные SHA/definitions после завершения TASK 076 для:
`cars_ui.py`, `konteyner.py`, `cars_schema.py`, `db.py`, активного ETA writer,
publisher/generators, `crm.db` + optional WAL, двух каталогов и карточек.
Определить реально активный handler order; не патчить архивы/неактивные дубли.
Зафиксировать counts callback `:sea_loaded`, `:sea_transit`, `:sold_transit`.
Production writes = 0; PythonAnywhere только GET.

## Sandbox/canary

На локальной копии CRM:

- UA-0012 привести к `sea_loaded`, 30 дней, 28.09.2026, подпись «На пароме»;
- найти все legacy `sea_transit` и показать план миграции без live write;
- проверить все текущие строки динамически, без hardcoded общего количества;
- отдельно UA-0009 PASS;
- синтетическая будущая карточка проходит тот же путь;
- фото, видео, диагностика, VIN, цена, описание и чужие карточки byte/hash
  unchanged;
- два последовательных deterministic canary PASS.

## Обязательные тесты

- кнопка/callback `sea_transit` = 0 во всех активных меню;
- `sea_loaded` = ровно 1 на экране; `sold_transit` сохранён;
- N=0,1,30,400; invalid/negative/>400;
- legacy normalization; restart persistence; repeated submit;
- never regress Georgia/Kyiv/sold/archive;
- injected DB partial failure, read-back mismatch, publisher fail, timeout,
  partial file install, delayed overwrite → no success + rollback PASS;
- UA-0012 без диагностики: placeholder создаётся в staging, primary+catalog
  проходят; сценарий publisher FAIL никогда не выдаёт success-текст;
- CRM status, DB, public badge and catalog category identical;
- runtime LLM tokens = 0.

## Выходы

Создать `cloud/task_077_container_stage_sync/` с sanitized evidence,
production-ready but not executed patcher/installer/controller/postcheck,
tests, Gate A workflow и manual Gate B workflow. Gate B должен требовать
точный новый production token, подготовить backup/auto-rollback и оставаться
не запущенным. Обновить `cloud/latest_status.md` и `cloud/owner_reply.md`.

Итог Gate A: только `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` либо FAIL.
Не заявлять об исправлении live CRM/UA-0012 до отдельного разрешения production.

## ROUND 2 — обязательная интеграция с завершённым TASK 076

Первый push TASK 077 пересёкся по времени с завершением TASK 076. Канонический
`main` теперь содержит commit `d05ebf0376f2779d2c36c29b80570f30adbfca57`
с реальными выходами `cloud/task_076_eta_sync/`, однако первый worker TASK 077
стартовал от более раннего SHA и не мог их прочитать. Этот continuation обязан:

1. Прочитать все исходники, тесты и отчёт `cloud/task_076_eta_sync/`.
2. Расширить существующие `eta_engine`/`eta_transaction`; не создавать второй
   конкурирующий ETA writer и не дублировать очередь/publisher.
3. Запустить объединённые offline tests TASK 076 + TASK 077 и записать точные
   counts PASS/FAIL.
4. Подготовить исполнимый Gate A candidate с GET-only/backup/sandbox режимом.
   Фраза «нет live-доступа» не является PASS: без controller-verified evidence
   итог остаётся `WAITING_GATE_A`, а не `DONE` и не «исправлено».
5. В отчёте явно доказать: publisher FAIL даёт только одно failure-сообщение;
   сообщение «Машина видна клиентам в каталоге» возможно только после verified
   PASS primary + diag/placeholder + оба каталога.


## ROUND 3 — отклонение прототипа и обязательный live-anchored release candidate

Controller 29.08.2026 выполнил реальные GET-only Gate A для TASK 076 и TASK 077.
Канонические доказательства:
- `cloud/task_076_eta_sync/evidence/gate_a_live.json` = PASS;
- `cloud/task_077_container_stage_sync/evidence/live_audit.json` =
  `PASS_AUDIT_DEFECT_REPRODUCED`;
- production/CRM/site writes = 0, `PRAGMA quick_check=ok`.

### Точная причина, уже доказанная live-кодом

Активный `konteyner.sprosit_dni` ставит wait field `eta_manual`.
`konteyner.prinyat` для числового N вычисляет дату и вызывает только
`_pisat(cid, "eta_manual", date, actor)`; `days_to_kyiv` не записывает.
Затем fire-and-forget `_peresobrat()` делает `subprocess.Popen(stranica.main)`
без ожидания/результата, а handler всегда отвечает «Страница обновляется».
Отдельный `cars_ui.apply_value("eta_days")` пишет два поля двумя независимыми
`set_field`/транзакциями и также не проверяет publisher.

Live preimage:
- UA-0009: `days_to_kyiv=13`, `eta_manual=2026-09-28`,
  `condition_text` содержит устаревшее «прибуття — 9 вересня 2026»;
- UA-0010: `days_to_kyiv=NULL`, `eta_manual=2026-09-28`;
- UA-0011: `days_to_kyiv=NULL`, `eta_manual=2026-09-28`;
- public `/video/UA-0009..0011.html` уже показывает динамические
  30 дней / 28 сентября 2026, но UA-0009 всё ещё содержит старую дату в
  свободном тексте;
- UA-0012 legacy `sea_transit`, страница отсутствует, publisher ранее дал
  `SEO068_DIAGNOSTIC_TARGET_MISSING`, после чего caller ложно показал success.

### Прототип Round 2 запрещено переносить в Gate B без исправления

`patcher/eta_transaction_controller.py` и
`patcher/stage_sync_patch.py` сейчас НЕ production-ready, потому что:
1. создан второй конкурирующий ETA writer вместо реального расширения TASK 076;
2. SQLite transaction/savepoint удерживается во время rebuild/publisher/canary,
   что блокирует отдельные reader/writer connections и скрывает uncommitted ETA;
3. реальный `cars.id` — integer, но прототип вызывает `car_id.replace`;
4. protected statuses выдуманы (`georgia/kyiv/sold`) вместо реальных
   `ge_waiting/ge_to_kyiv/ua_arrived/sold_*`;
5. success всегда делает `published=1`, а обязан вернуть точный preimage;
6. transforms generic, без literal live source/full-SHA anchors;
7. README и `gate_a_findings.md` ошибочно остались
   `NOT_EXECUTED_PLACEHOLDER` после реального PASS.

### Обязательный Round 3

1. Использовать точные full SHA из двух live evidence и literal function
   definitions. Подготовить AST/function-SHA anchored transforms минимум для
   `db.py:update_card_field`, `cars_ui.apply_value`,
   `cars_ui.stage_menu/toggle_publish`, `konteyner.prinyat/_peresobrat`,
   активного `stranica.sobrat_kartochku`, publisher.
2. Одна короткая DB transaction выполняет только row-level write:
   optional safe status normalization (только Korea/ferry →
   `sea_loaded`), `days_to_kyiv=N`, `eta_manual=UTC_today+N`,
   `updated_at` и обе audit rows. Затем COMMIT и отдельный verified read-back.
   Нельзя держать DB transaction открытой при file/publisher/public HTTP.
3. До write зафиксировать preimage DB и точный bounded file set. Publisher
   строит staging primary + diag/placeholder + оба каталога, валидирует,
   атомарно устанавливает и читает обратно. При любом FAIL выполнить
   compensating DB transaction + file rollback и проверить восстановление.
   `published` на PASS и rollback равен preimage, не принудительно 1.
4. `konteyner.prinyat` и `cars_ui.apply_value` обязаны вызывать один и тот
   же writer. Только после DB read-back + publisher PASS разрешено ровно одно
   success-сообщение. Fire-and-forget success удалить.
5. `toggle_publish`: при publisher FAIL восстановить preimage
   `published` и выдать только failure. Текст «Машина видна клиентам…»
   допустим только после verified PASS.
6. Stale-text guard должен удалять/заменять только предложение о
   прибытии/доставке/выдаче, содержащее независимую дату. Нельзя удалять даты
   сервиса, аукциона, ремонта или регистрации. UA-0009 canary обязан убрать
   «9 вересня 2026», сохранив остальное описание byte-semantic.
7. На local copy canary привести UA-0009/0010/0011 к
   `days=30, eta=2026-09-28, status=sea_loaded`; UA-0012 к
   `sea_loaded, days=30, eta=2026-09-28` с diag placeholder. Проверить
   `/video`, `/site`, оба каталога, UA-0009 отдельно и все чужие
   фото/видео/VIN/price/status/description hashes.
8. Tests: N=0/1/30/400, invalid; idempotence; int IDs; реальные protected
   statuses; preimage published=0 и =1; DB commit before publisher;
   injected publisher/readback/partial install/delayed overwrite;
   compensating rollback; narrow stale-date sanitation; exact one message.
9. Исправить canonical reports: live Gate A реально выполнен. Итог только
   `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` либо FAIL.
10. Gate B подготовить, но НЕ запускать. Exact token остаётся отдельной
    owner-командой. Production writes = 0.
11. Уже установлен `.github/workflows/safe_workflow_watchdog.yml`:
    не создавать второй watchdog; лишь проверить совместимость workflow name.
