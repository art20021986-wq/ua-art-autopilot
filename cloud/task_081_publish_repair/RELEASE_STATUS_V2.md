# UA-0013-PUBLISH-REPAIR-001 v1.0 — актуальный статус

Статус: **Gate A PASS; production ожидает отдельного точного разрешения владельца.**

## Подтверждённая причина

1. `cars_ui.toggle_publish` записывает `published=1`, получает отрицательный
   результат `publikaciya.opublikovat`, но не проверяет его и затем безусловно
   отправляет «Машина видна клиентам в каталоге.»
2. Одинаковая `_ua_seo068_normalize` в `stranica.py`, `master_card.py` и
   `yadro.py` требует уже существующий live-файл `<UA>-diag.html` до того, как
   новая карточка может собрать диагностическую заглушку. Получается замкнутый
   круг `SEO068_DIAGNOSTIC_TARGET_MISSING`.

## Свежие live-факты

- `UA-0013`: Mercedes-Benz Б-КЛАССА 2015, `id=20`, `published=1`,
  `review_status=approved_owner`.
- Правильный этап уже записан в CRM: `status=sea_loaded` → **«На пароме»**,
  категория `more`; контейнер `ONEYSELGF1046602`. Изменять этап на другой нельзя.
- SQLite `PRAGMA quick_check=ok`.
- В CRM опубликовано 13 автомобилей. На публичном сайте отсутствуют ровно
  `UA-0012` и `UA-0013`; их URL перенаправляются на главную. `UA-0011` уже
  открывается как точная карточка.
- Live Gate A: GitHub Actions run `33241443249`, статус success.

## Готовое исправление V2

- удаляет только ошибочную проверку существования старого live diag-файла во
  всех трёх SEO-модулях, сохраняя проверку ссылки на чужую диагностику;
- строит placeholder внутри staged bundle без преждевременной записи;
- публикует единым bounded-набором primary + diagnostics + оба каталога;
- откатывает новые файлы удалением, существующие — из byte-exact backup;
- восстанавливает preimage `published/status/publish_pending` при любом FAIL;
- отправляет ровно одно финальное сообщение и никогда не сообщает успех при
  отрицательном/исключительном результате;
- действует для любого `UA-[0-9]{4,}`, включая тестовую будущую `UA-9999`;
- production Gate B автоматически чинит только реально отсутствующие
  опубликованные карточки (сейчас `UA-0012`, `UA-0013`), максимум пять.

Проверено на точных копиях live-файлов: компиляция 5 кандидатов, 11 тестов
publisher/UI/SEO и 5 тестов внешнего backup/rollback/границ ремонта.

## Production Gate B

Workflow: `.github/workflows/task081_publish_repair_gate_b_v2.yml`.

Он запускается только вручную и до чтения секретов сравнивает точный token:

`UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED`

Затем заново выполняет свежий GET-only Gate A, real-master shadow с нулевыми
production-write, полный backup, установку, публикацию `UA-0012`/`UA-0013`,
перезапуск единственного bot launcher, immediate public postcheck и delayed
postcheck через 65 секунд. Любая ошибка после установки запускает внешний
полный rollback и повторный restart.

Production, CRM, сайт и bot process этим Gate A не изменялись.
