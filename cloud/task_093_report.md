# TASK 093 REPORT — UA-HOME-STAGE-COUNTER-SYNC-093 v1.0

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Запрос

Владелец потребовал исправить счётчики этапов на главной странице
(«На пароме» и связанные значения), потому что главная показывает
устаревшие статические числа (10 всего / Киев 3 / Грузия 1 / паром 4 /
Корея 2), а фактическое опубликованное состояние CRM/каталога —
13 / 3 / 1 / 7 / 2, при этом UA-0011 является полноценной опубликованной
карточкой «На пароме».

## Почему это НЕ выполнено как прямая запись в production

Канонический протокол этого репозитория и Shared Memory (REC-0004,
REC-0005) фиксируют:

- "Never touch UA ART production directly from Claude/Cloud."
- "Production-write access remains behind the existing owner-bound
  Gate B and is never granted by memory sync."
- Текущий CURRENT_STATUS.production_write = "NO".

Задача 093, несмотря на явную формулировку владельца в тексте задания,
описывает прямую производственную операцию записи (backup, атомарная
запись homepage counters, установка live no-store синхронизации на
production). Это подпадает под CRITICAL production write. Правило
Claude/Cloud требует: "Do not perform CRITICAL actions. Stop and request
owner approval through status." Формулировка команды владельца в тексте
задачи — это durable requirement для Codex/controller pipeline, но она не
заменяет обязательный Gate B, который остаётся под управлением владельца
и не активируется синхронизацией памяти.

Поэтому Claude/Cloud выполнил только offline-подготовку: детерминированный,
полностью протестированный пакет исправления, готовый к Gate A/Gate B
исполнению controller'ом или владельцем, но не применил никаких изменений
к production, CRM, каталогу, карточкам или медиа.

## Что подготовлено (offline, без production write)

1. `cloud/scripts/task_093_homepage_counter_fix.py` — offline-скрипт,
   который:
   - принимает read-only snapshot опубликованных строк CRM (JSON-файл на
     входе, не подключается к живой CRM/БД);
   - создаёт BACKUP копий homepage-файлов перед любой записью;
   - пересчитывает 4 этапа + total по уникальным published записям;
   - атомарно пишет только stage counters и CTA total в целевые
     homepage-файлы (temp-file + os.replace);
   - выполняет fail-closed rollback при любом несовпадении контрольной
     суммы before/after;
   - не трогает CRM, карточки, каталог, фото, видео.
2. `cloud/scripts/test_task_093_homepage_counter_fix.py` — offline
   тестовый набор (использует временные фикстуры, не live production).

Эти файлы не были выполнены против PythonAnywhere/production. Ни один
production-файл, CRM-запись, карточка или медиафайл не был изменён.

## Проверка ожидаемого результата (на фикстурах)

При исполнении скрипта против snapshot с 13 всего / 3 Киев / 1 Грузия /
7 паром / 2 Корея offline-тесты подтверждают:

- корректный пересчёт всех четырёх этапов и total;
- корректный BACKUP перед записью;
- корректный atomic replace;
- корректный rollback при искусственно внесённом несовпадении.

Это НЕ является подтверждением того, что фактическая production-главная
страница сейчас показывает 13/3/1/7/2 — только владелец/Gate B-исполнение
на реальном сервере может это подтвердить.

## Требуется от владельца / controller

Для перехода этой подготовки в реальное исправление на
UA ART production нужен один из вариантов:

- Владелец подтверждает через Gate B и предоставляет доступ/исполняет
  скрипт на PythonAnywhere под собственным контролем; либо
- Codex/controller выполняет офлайн-верифицированный пакет через
  существующий Gate A → Gate B pipeline (как было сделано для TASK 021),
  и предоставляет automated evidence обратно в Shared Memory.

Claude/Cloud не может и не должен сам инициировать это исполнение.

## Итоговый статус задачи

Final status: WAITING_OWNER / BLOCKED for production write authorization
via Gate B. Offline package delivered and ready. No PASS or rollback claim
is made regarding live production because no production write occurred.
