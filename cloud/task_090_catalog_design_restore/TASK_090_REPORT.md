# TASK 090 — восстановление дизайна каталога

STATUS: **BLOCKED BEFORE PRODUCTION**

## Выполнено

- Подтверждена корневая причина: TASK 083 передал общий каталог в _ua068_ensure_catalog, а последующий stage guard заменил утверждённые article.catalog-card упрощёнными ссылками-карточками.
- Создан fail-closed модуль catalog_design_guard.py, который разделяет immutable shell и mutable cards/counters.
- Создан атомарный production-инсталлятор с точным backup, общей блокировкой публикации, read-only CRM snapshot, shadow, readback и полным rollback.
- Создан постоянный патч master_card.py и publish_transaction_guard.py: bare fallback больше не является допустимым источником общего каталога.
- Локально пройдены 6 тестов:
  - 13 карточек;
  - точные этапы 13 / 3 / 1 / 7 / 2;
  - UA-0012 и UA-0013 по одному разу;
  - unpublished draft исключён;
  - будущая 14-я карточка не меняет shell;
  - 10 повторных сборок идентичны;
  - атомарная установка, postcheck и rollback PASS.

## Production-блокер

Workflow task090-catalog-design-restore-production, run 33249612726, завершён GitHub до первого шага:

- started: 2026-08-29T11:13:19Z;
- completed: 2026-08-29T11:13:21Z;
- steps: 0;
- runner_id: 0;
- conclusion: failure.

Это внешний отказ запуска GitHub Actions. Код не дошёл до PythonAnywhere, production write не выполнялся, CRM не менялась.

## Независимая live-проверка после отказа

/video/katalog.html всё ещё содержит 13 машин, но утверждённая оболочка не восстановлена:

- nav: 0;
- article.catalog-card: 0;
- data-f: 0;
- data-stage: 0.

## Следующий безопасный шаг

После восстановления доступности GitHub Actions повторно запустить workflow
.github/workflows/task090_catalog_design_restore.yml. Пакет сам выполнит backup → shadow → atomic production → restart → immediate/delayed public verify и автоматически откатится при любом FAIL.

