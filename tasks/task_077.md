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
