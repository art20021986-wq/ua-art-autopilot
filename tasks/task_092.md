# TASK 092 — UA-WEB-RECOVERY-015 v1.0

## Команда владельца

**УТВЕРЖДАЮ UA-WEB-RECOVERY-015 v1.0. BACKUP → SANDBOX → CANARY. PRODUCTION — ТОЛЬКО ПО МОЕЙ ОТДЕЛЬНОЙ КОМАНДЕ. ОТЧЁТ КАЖДЫЕ 5%. ПРИСТУПИТЬ НЕМЕДЛЕННО.**

Источник команды и полный рабочий контекст: GitHub Issue #34.

## Приоритет и режим

- Приоритет: **P0 / CRITICAL**.
- Цель: вернуть сайт UA ART в единое рабочее состояние и восстановить утверждённый mobile/web design.
- Разрешено: read-only аудит, backup, локальный sandbox, canary, тесты, подготовка безопасного bounded-пакета и rollback.
- Запрещено без отдельной команды владельца: production write, CRM write, merge, deploy, Cloudflare purge, изменение live PythonAnywhere, изменение live БД/медиа.
- Не делать поверхностный CSS-патч. Сначала доказать первопричину, затем исправить архитектуру публикации.

## Наблюдаемые критические дефекты

1. Главная показывает 10 автомобилей: Киев 3 / Грузия 1 / паром 4 / Корея 2, тогда как публичный каталог содержит 13.
2. При неизменной CRM ожидаемый snapshot: Киев 3 / Грузия 1 / паром 7 / Корея 2 / total 13.
3. UA-0011, UA-0012 и UA-0013 есть в каталоге, но не учтены главной и этапными счётчиками.
4. UA-0009 показывает разные ETA/days в каталоге и полной карточке. UA-0009 — обязательный blocking release gate.
5. Mobile: WhatsApp перекрывает CTA, рамки, фото и зоны свайпа; фото обрезаются до фары/колеса/части кузова; отсутствует единая safe-zone/focal-point система; карточки имеют нестабильную геометрию.
6. Нарушена нормализация: смешанный язык/регистр и разные форматы топлива/названий.
7. UA-0012 содержит подозрительный пробег `342 км`; нельзя автоматически превращать его в другое значение без исходного доказательства.

## Главный архитектурный контракт

Единая цепочка:

`CRM/канонический реестр → schema validation → единая атомарная сборка → главная → каталог → фильтры этапов → карточки → cache → production`.

Один источник истины. Нельзя вручную дублировать в HTML или нескольких генераторах:

- counters;
- stage;
- ETA;
- days;
- container;
- media counts;
- публичную строку статуса;
- видимость этапных полей.

## Этап 0 — fail-closed preflight

До любой правки:

1. Зафиксировать publication lock в sandbox-модели.
2. Инвентаризировать всех writers/generators/tasks, включая `master_card.py`, `start_safe.py`, `fitfix.py`, `yadro.py`, cron и новые генераторы.
3. Для ключевых файлов получить SHA-256, mtime, size, owner и источник записи.
4. Подготовить backup/manifest для данных, generators/templates, production HTML/CSS/JS, media manifests, diagnostics и cache/Cloudflare configuration evidence.
5. Сформировать `PRE_RECOVERY_MANIFEST`.
6. Выполнить three-way diff: последняя подтверждённая рабочая версия дизайна ↔ текущий production ↔ актуальные данные 13 автомобилей.
7. Полный откат, который потеряет UA-0011/0012/0013, фото, VIN, описания или новый контент, запрещён.

## Root-cause audit

Для главной, каталога, filters, UA-0001…UA-0013, counters, ETA/days, containers и RU/UA установить:

- какой файл/функция создаёт объект;
- из какого источника берутся данные;
- какой триггер обновления;
- какой cache layer используется;
- существует ли второй конкурирующий writer.

Обязательно проверить:

1. multiple generators;
2. stale static homepage;
3. partial non-atomic publish;
4. browser/Cloudflare cache mismatch;
5. старые скрипты, перезаписывающие новый renderer.

Формулировка `скорее всего cache` без файла, функции, process/run или cache rule не принимается.

## Каноническая модель данных

Для каждой машины требуется единая запись с минимумом:

- id, vin, year, make, model, stage;
- price, mileage, engine_cc, fuel, transmission, drive, color;
- container_number, eta_kiev, stage_changed_at;
- photos, videos, diagnostic_assets;
- cover_photo, cover_focal_point;
- title_ru, title_ua, description_ru, description_ua;
- published, updated_at.

Вычисляемые значения не хранить вручную: stage number, days, total/stage counters, media counts, public status string, route text, tracking visibility.

## State machine

### Stage 1 — Korea

Публично: `В Корее — выкуплен и проверен`, фото, цена, VIN, характеристики.

Запрещено публично: container, ETA, days, tracking и stale payload предыдущего этапа.

### Stage 2 — Sea/Ferry

Публично: `На пароме: Корея → Грузия`; container/tracking/ETA/days только из canonical source и только при валидных данных.

### Stage 3 — Georgia

Публично: `В Грузии — финальный этап`; расчёт до Киева от фактического stage transition. Старое морское значение не переносить в публичный блок.

### Stage 4 — Kyiv

Публично: `В Киеве — можно посмотреть`; без container, морского маршрута, ETA и days.

Несовместимые поля должны исключаться renderer-ом автоматически при переходе этапа.

## Atomic build contract

`lock → canonical data → schema validation → validate VIN/ID/stage/media/dates → build temp dir → build-manifest.json → data tests → link tests → visual tests → canary`.

Production-фаза только после отдельной команды владельца.

Каждая сборка должна иметь один `build_id` для homepage/catalog/cards. Разные build_id = FAIL.

## Обязательные data invariants

- `total == количество unique published cards`;
- `total == Korea + Sea + Georgia + Kyiv`;
- каждая машина находится ровно в одном этапе;
- ID и VIN уникальны;
- stage homepage == catalog == card;
- ETA catalog == card;
- days catalog == card;
- photo/video counts соответствуют реально доступным ненулевым файлам;
- cover существует и имеет ненулевой размер;
- stage 1 и stage 4 не имеют публичных container/ETA/days;
- на странице ровно один public WhatsApp/Chat element.

Любое нарушение блокирует release.

## Mobile/UI recovery

Сохранить утверждённую систему UA ART: dark navy background, gold border/accent, green statuses, live car photos.

### Homepage stages

Порядок: Kyiv → Georgia → Sea → Korea.

- единая геометрия, width, radius, border;
- безопасная текстовая зона и затемняющий gradient;
- контраст текста не ниже 4.5:1;
- whole card clickable;
- tap target >= 44×44 CSS px;
- counters только динамические;
- no horizontal scroll на 320–430 px;
- WhatsApp не пересекает stage cards и `Открыть все автомобили`.

### Catalog cards

- единый layout для всех карточек: 50/50 либо единый 45/55 в пользу фото;
- одна внешняя рамка, без второй рамки на стыке;
- одинаковые padding и порядок элементов;
- слева информация, справа живое фото;
- title максимум 2 строки;
- VIN и CTA не обрезаются и не уходят под фото/WhatsApp;
- длинное название не меняет ширину карточки.

Порядок данных:

1. ID и stage;
2. price;
3. make/model/year;
4. public status;
5. mileage/engine/fuel/transmission;
6. VIN;
7. `VIN проверен`;
8. media counts;
9. CTA.

Внутренние технические пояснения не перегружают preview-карточку.

## Photo contract

1. Первое подтверждённое фото — default cover, но original не уничтожать.
2. Разрешён отдельный catalog thumbnail.
3. Использовать `object-fit: cover` вместе с сохранённым focal point/object-position.
4. Нельзя показывать только колесо, фару, капот или половину кузова.
5. Без black/grey/blur bars.
6. Если первое фото не даёт приемлемого preview, выбрать следующую подходящую фотографию для cover, сохранив первое в gallery.
7. Задать width/height/srcset/sizes; lazy load ниже первого экрана; исключить CLS.

## WhatsApp contract

Ровно один public WhatsApp/Chat element.

Он не должен перекрывать CTA, VIN, текст, arrows, car image или swipe-zone; обязан учитывать `safe-area-inset-bottom`; tap target >= 44×44 px.

Простое увеличение z-index не считается исправлением. При необходимости применить collision-aware positioning/collapse, например через IntersectionObserver.

## Language/normalization

- Только активный RU либо UA, без одновременного отображения.
- Единый регистр и формат names/fuel/numbers.
- Выбранный язык сохраняется при переходе catalog/filter/card/back.
- Не исправлять сомнительные значения догадкой.

## UA-0009 blocking release gate

Проверить:

- ID, VIN, stage, price, mileage;
- 20 photos и cover;
- container/tracking;
- ETA/days;
- diagnostics;
- catalog/filter/home counter;
- RU/UA;
- mobile layout;
- отсутствие регрессии UA-0001…UA-0008.

Catalog и full card обязаны показывать одинаковые ETA/days. Текущий verdict до доказанного исправления: **FAIL**.

## Visual test matrix

Playwright или эквивалент:

- 320×568;
- 360×800;
- 375×812;
- 390×844;
- 393×852;
- 430×932;
- 768×1024;
- 1366×768;
- 1440×900.

Проверить homepage, full catalog, каждый stage, UA-0001, UA-0002, UA-0003, UA-0009, UA-0011, UA-0012, UA-0013.

Обязательные screenshots: stages, open-all CTA, catalog start, long title, ETA card, no-video card, WhatsApp collision case, RU→UA, UA-0009, UA-0013.

## Functional/regression tests

- stage navigation/filtering;
- возврат в общий catalog;
- открытие card через CTA и photo;
- gallery swipe/fullscreen;
- diagnostics;
- container tracking;
- WhatsApp/phone/map;
- RU/UA/back;
- no double firing;
- no click interception;
- no JS errors, 404/500 или mixed content.

Сохранить без регрессии все UA-0001…UA-0013 media, diagnostics/posters/OBD, CarHistory, tracking, deposit 500 $ CTA, forms, phone/map/share, canonical/robots/sitemap, descriptions, VIN, prices и analytics.

## Performance targets

- CLS <= 0.10;
- LCP <= 2.5 s на нормальном mobile connection;
- INP <= 200 ms;
- image dimensions mandatory;
- не загружать весь catalog eagerly;
- не дублировать CSS/JS versions;
- никаких infinite workers/CPU tarpit;
- HTML revalidation/no-cache, hashed assets immutable, targeted purge только после отдельного production approval.

## Canary deliverables

До любого production approval предоставить:

1. доказанную root cause;
2. PRE_RECOVERY_MANIFEST и backup plan;
3. canary URL или полностью воспроизводимый локальный canary package;
4. mobile screenshots;
5. таблицу 13 автомобилей;
6. stage/counter table;
7. отдельный UA-0009 verdict;
8. changed files;
9. SHA before/after;
10. data/link/visual validator results;
11. rollback instructions;
12. явное `PRODUCTION_TOUCHED: NO`.

## Auto-rollback conditions будущего production gate

Counter mismatch, missing card, missing cover, ETA mismatch, build_id mismatch, JS error, 404 или failed visual smoke.

## Отчётность

Каждые 5% фиксировать:

- подтверждённый процент;
- что реально выполнено;
- files touched;
- PASS/FAIL;
- blocker;
- следующий шаг;
- `PRODUCTION_TOUCHED: NO`.

Не придумывать прогресс. При зависании продолжать с checkpoint. После трёх неудачных retries — STOP с точной command/file/error.

## Definition of Done для sandbox/canary

Задача не считается готовой, пока не доказаны все invariants, не открываются все 13 cards, не синхронизированы counters/stages, UA-0009 не имеет PASS, WhatsApp не перестал перекрывать UI, mobile Safari не прошёл проверку, а media/diagnostics/SEO и rollback не подтверждены.

Production остаётся запрещённым до отдельной команды владельца.
