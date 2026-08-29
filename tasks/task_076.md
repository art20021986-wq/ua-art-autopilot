# TASK 076 — CRM-ETA-SYNC-GUARD-004 v1.0

OWNER_REQUEST: «В CRM для UA-0009, UA-0010 и UA-0011 изменены статусы и срок прибытия на 30 дней, но дата на карточках обновилась не везде. Исправить существующие и все будущие карточки».

## Разрешённый режим

BACKUP → GET-only AUDIT → SANDBOX/CANARY. Production запрещён без отдельной точной команды владельца.

## Подтверждённый live-дефект 29.08.2026

- UA-0009: 30 дней, ориентировочно 28 сентября 2026; страница обновлена 06:12, но в описании осталась старая дата 9 сентября.
- UA-0010: 11 дней, ориентировочно 9 сентября 2026; страница обновлена 02:01 и не пересобралась после команды CRM.
- UA-0011: 30 дней, ориентировочно 28 сентября 2026; страница обновлена 06:12.
- Владелец задал 30 дней для всех трёх. Требуется доказать, на каком шаге потерялась UA-0010: CRM write, read-back, очередь, publisher или rebuild.

## Цель

1. Прочитать актуальные CRM и live-source только GET:
   `crm.db`, optional WAL, `cars_ui.py`, `db.py`, `konteyner.py`,
   `stranica.py`, `master_card.py`, `yadro.py`, `publikaciya.py`,
   два каталога и страницы UA-0009/0010/0011.
2. Зафиксировать для трёх строк `status`, `days_to_kyiv`, `eta_manual`,
   `updated_at` и сравнить с фактическим HTML: дни, дата, footer updated,
   дубли даты в описании. Секреты и персональные данные в evidence не писать.
3. Найти exact live call path: callback `eta_days` → validation →
   сохранение обоих ETA-полей → verified read-back → bounded rebuild/publish →
   оба `/video` и `/site` → public HTTP.
4. Создать один production-ready, но НЕ запускаемый release candidate,
   исправляющий причину для всех текущих и будущих карточек без списка ID.
5. В sandbox/canary показать UA-0009/0010/0011 как 30 дней с одной согласованной
   датой; удалить/нормализовать устаревшую календарную дату из свободного
   описания, чтобы описание не спорило с динамическим ETA-блоком.

## Обязательный контракт

- Один ввод N дней выполняет логическую транзакцию:
  `days_to_kyiv=N`, `eta_manual=UTC_today+N days`, `updated_at`.
- Success в CRM разрешён только после read-back обоих полей и PASS publisher.
- Частичная запись, stale row, busy/queue timeout или publisher FAIL:
  успех не показывать; вернуть понятную ошибку; сохранить повторяемую задачу или
  выполнить bounded rollback по доказанному live-механизму.
- Генераторы и publisher читают один нормализованный ETA object. Приоритет:
  подтверждённый ручной срок/дата → stage rule → neutral «уточняется».
- Значения `days_to_kyiv` и `eta_manual` обязаны быть взаимно согласованы.
  Конфликт блокирует публикацию; старый HTML не считается успехом.
- После сохранения одной карточки атомарно обновляются её primary page,
  обязательная diag/placeholder при необходимости и оба каталога. Чужие
  страницы, фото, видео, VIN, цена, описание (кроме устаревшей ETA-фразы),
  дизайн и этап не изменяются.
- Свободное описание не должно содержать независимую точную дату доставки.
  Единственный публичный источник даты — ETA-компонент.
- Для этапа 3 сохраняется правило TASK 075: 15 дней от фактической даты
  перехода, не от оплаты.
- Runtime LLM tokens = 0.

## Gate A — обязателен, только чтение

Создать secret-backed GET-only workflow и evidence:

- exact SHA/size до transform;
- SQLite `quick_check=ok`, 11 unique published rows, UA-0009 PASS;
- значения ETA трёх строк и parsed live HTML;
- exact definition/full-file SHA relevant functions;
- in-memory patch, compile, unit/integration tests;
- sandbox/canary, production writes=0;
- итог только `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` либо FAIL.

## Тесты

- UA-0009/0010/0011: expected N=30, one computed date, two locations, no stale description date.
- Future synthetic card without ID special case.
- N=0, 1, 30, 400; invalid/negative/>400 rejected.
- idempotent repeated submit.
- injected failure after first DB field, read-back mismatch, queue timeout,
  publisher failure, partial file write, delayed rebuild overwrite.
- two consecutive deterministic canary runs.
- protected UA-0001…UA-0008 and media hashes unchanged; UA-0009 separately PASS.

## Gate B — только подготовить, не запускать

Manual `workflow_dispatch` only, exact token:
`CRM-ETA-SYNC-GUARD-004-V1.0-PRODUCTION-APPROVED`.

Перед любой production write: exclusive window, persistent collision-safe backup,
full source SHA gates, DB row-level transaction (не full DB replace), atomic file
replace, restart exact active launcher, immediate + delayed >=60s public check,
automatic rollback and rollback verification on any failure.

## Выходы

Создать под `cloud/task_076_eta_sync/`:

- sanitized live audit;
- patcher/installer/controller/postcheck;
- tests;
- Gate A and manual Gate B workflows;
- canary evidence/report;
- `cloud/latest_status.md`;
- `cloud/owner_reply.md`.

Не заявлять, что production исправлен, пока Gate B реально не разрешён и не прошёл.
