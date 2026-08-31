# TASK 101 — UA-ORDER-GE-8COUNTRY-GUARD-016 v1.1 FINAL

## УТВЕРЖДЁННАЯ КОМАНДА ВЛАДЕЛЬЦА

31.08.2026 Артём Бровинский утвердил запуск словами:

> «Запускай в работу и ставь в очередь, загрузи файл».

CLAUDE: подготовить полный безопасный пакет реализации для сайта UA ART: добавить грузинский язык, расширить блок «Авто под заказ» до 8 стран в сетке 4 сверху + 4 снизу, обеспечить переход к 5 топовым моделям каждой страны и доказать сохранность всех карточек UA-0001…UA-0016.

**PRODUCTION WRITE: NO.**
**CRM WRITE: NO.**
**PUBLIC SITE WRITE: NO.**
**PYTHONANYWHERE WRITE/RELOAD: NO.**

Claude работает только в `cloud/`. Результат после независимого аудита ChatGPT/Codex может быть передан в отдельный контролируемый этап Sandbox/Canary. Никакого прямого внедрения в этой задаче.

## 1. Подтверждённый аудит входного состояния

По live GET-аудиту на 31.08.2026:

- каталог содержит 16 уникальных карточек: UA-0001…UA-0016;
- все 16 публичных URL карточек отвечают HTTP 200;
- актуальное распределение каталога: Киев 3, Грузия 1, На пароме 8, Корея 4, всего 16;
- исходный HTML главной страницы всё ещё содержит старый fallback: всего 13, этапы 3 / 1 / 7 / 2;
- браузерный JavaScript пытается исправлять старые цифры после загрузки, но серверный HTML и часть роботов получают устаревшее состояние;
- текущий переключатель основной части сайта: RU | UA;
- текущий `i18n.js` принимает только `ru` и `uk`;
- текущий блок `.countries-inline` содержит 5 декоративных `span`: Корея, Япония, Америка, Европа, Китай;
- названия стран на главной не являются полноценными ссылками;
- общая кнопка ведёт на `podbor.html` без выбранной страны;
- текущий `podbor.html` поддерживает только `korea`, `japan`, `usa`, `europe`, `china`;
- при отсутствии/ошибке параметра `strana` используется fallback `korea`;
- существующая заявка передаёт код страны в Telegram WebApp поле `s` и в deep-link `z_<country>`.

Эти факты использовать как baseline. Не заявлять о более свежем live-состоянии без приложенного machine evidence.

## 2. Цели

1. Добавить третий язык интерфейса: грузинский.
2. Отображать переключатель `RU | UA | GE`; визуальная метка `GE`, внутренний ISO-код `ka`, HTML `lang="ka"`.
3. Расширить «Авто под заказ» с 5 до 8 стран.
4. Сохранить существующую стилистику: флаг + название, золотые акценты, фон и CTA.
5. Разместить страны строго 4 + 4:
   - ряд 1: Корея, Япония, Америка, Европа;
   - ряд 2: Китай, Канада, ОАЭ, Грузия.
6. Каждая страна — доступная ссылка/кнопка с маршрутом `podbor.html?strana=<code>&lang=<current>`.
7. На странице подбора показывать 5 утверждённых моделей выбранной страны.
8. Сохранить все 16 карточек, CRM, бот, медиа, диагностику, VIN, цены, этапы, CTA и URL.
9. Устранить исторический fallback 13 на главной: сгенерированный HTML должен брать значения из одного источника с каталогом и содержать актуальные 16 / 3 / 1 / 8 / 4 ещё до JavaScript. Запрещён новый hardcode; решение обязано работать для UA-0017+.

## 3. Стабильные коды и названия стран

| code | RU | UA | GE/ka |
|---|---|---|---|
| korea | Корея | Корея | კორეა |
| japan | Япония | Японія | იაპონია |
| usa | Америка | Америка | აშშ |
| europe | Европа | Європа | ევროპა |
| china | Китай | Китай | ჩინეთი |
| canada | Канада | Канада | კანადა |
| uae | ОАЭ | ОАЕ | ემირატები |
| georgia | Грузия | Грузія | საქართველო |

`georgia` на `podbor.html` означает страну подбора и не должен конфликтовать с этапом доставки «В Грузии». Использовать раздельные namespaces/state для country и stage.

## 4. Утверждённые 40 моделей

### Корея
1. Kia K5
2. Hyundai Sonata
3. Hyundai Tucson
4. Kia Sportage
5. Hyundai Santa Fe

### Япония
1. Nissan Note
2. Toyota Aqua
3. Mercedes-Benz B-Class
4. Toyota Prius
5. Раритетные авто 1980–1990-х годов

### Америка
1. Tesla Model Y
2. Tesla Model 3
3. Ford Escape
4. Nissan Rogue
5. BMW X3

### Европа
1. Volkswagen Golf
2. Volkswagen Tiguan
3. Audi Q5
4. Škoda Octavia
5. Renault Megane

### Китай
1. BYD Song Plus
2. Volkswagen ID.4
3. BYD Yuan Plus (Atto 3)
4. Zeekr 001
5. BYD Seal

### Канада
1. Lexus RX 350
2. Lexus RX 500
3. Lexus TX
4. Toyota Tacoma TRD Pro
5. Toyota Tacoma Trailhunter

### ОАЭ
На запуске тот же набор, что у Америки, по прямому указанию владельца, но хранить отдельным массивом:
1. Tesla Model Y
2. Tesla Model 3
3. Ford Escape
4. Nissan Rogue
5. BMW X3

### Грузия
1. Ford Fusion / Fusion Hybrid
2. Toyota Camry
3. Volkswagen Jetta
4. Toyota RAV4 / RAV4 Hybrid
5. Subaru Forester

Поле «Другая модель» сохранить. Выбранная модель должна передаваться в заявку ровно один раз.

## 5. Требования к грузинской локализации

Расширить существующую модель `data-ru/data-uk`, не переписывая архитектуру без необходимости:

- добавить `data-ka`, `data-ka-content`, `data-ka-placeholder`, `data-ka-aria`, `data-ka-alt`;
- разрешить `ka` в query и localStorage;
- default оставить `ru`;
- не использовать `ge` как технический код языка;
- выбранный язык сохраняется между главной, каталогом, карточкой, условиями, подбором и диагностикой;
- локализовать title, description, Open Graph, кнопки, статусы, подсказки, ошибки, success-окна, placeholders, aria, alt, динамические счётчики и текст заявки;
- покрыть главную, каталог, 16 карточек, условия, подбор и интерфейсы диагностических страниц;
- не переводить марки/модели, VIN, ID, контейнеры, телефоны, URL, числа, суммы и значения CRM;
- runtime machine translation запрещён;
- fallback при пропущенном ключе — контролируемый русский, без `undefined` и пустых элементов;
- все грузинские формулировки перед Production требуют ручной проверки носителем.

Контрольные базовые строки, подлежащие native review:

- «Авто под заказ» → `ავტომობილი შეკვეთით`
- «Подберём автомобиль под ваш бюджет и пожелания» → `შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად`
- «Цена фиксируется в договоре и не меняется» → `ფასი ფიქსირდება ხელშეკრულებაში და არ იცვლება`
- «Подобрать авто» → `ავტომობილის შერჩევა`

## 6. UX и маршрутизация

Требуемые маршруты:

- `podbor.html?strana=korea`
- `podbor.html?strana=japan`
- `podbor.html?strana=usa`
- `podbor.html?strana=europe`
- `podbor.html?strana=china`
- `podbor.html?strana=canada`
- `podbor.html?strana=uae`
- `podbor.html?strana=georgia`

Правила:

- добавлять `lang=ru|uk|ka`;
- whitelist ровно восьми country-кодов;
- неизвестный код безопасно даёт `korea`;
- на `podbor.html` вывести видимый selector восьми стран;
- смена страны обновляет активное состояние, URL и пять моделей;
- уже выбранные бюджет, тип и свободный текст не теряются;
- общая CTA «Подобрать авто» сохраняется;
- элементы страны имеют focus/hover/active и минимум 44 px по высоте;
- сетка 4×2 без горизонтального скролла и без наложения WhatsApp;
- названия могут занимать 2 строки, но сетка остаётся 4×2;
- проверить 360/375/390/430/768/1024/1440 px и отдельно iPhone Safari;
- cache-busting CSS/JS обновлять только на будущем контролируемом install.

## 7. Заявка, бот и CRM

Добавить только новые значения: `canada`, `uae`, `georgia`.

Сохранить старый контракт Telegram WebApp и deep-link. Предложенный пакет должен предусмотреть:

- поле `s`/country_code;
- название страны в текущем языке;
- модель, бюджет, тип, описание;
- язык `ru|uk|ka`;
- распознавание `z_canada`, `z_uae`, `z_georgia`;
- одну заявку без дубля;
- UTF-8 грузинского текста без обрезания;
- полную обратную совместимость старых кодов.

В TASK 101 запрещено изменять рабочий бот или CRM. Нужны только безопасные patch proposals и тест-контракт.

## 8. Абсолютные запреты и защита карточек

Запрещено:

- менять/удалять ID UA-0001…UA-0016;
- менять VIN, цену, пробег, двигатель, этап, сроки, контейнер, описание, комплектацию;
- менять число/порядок фото и видео;
- перекодировать/перезагружать media;
- менять CTA карточек, диагностику, VIN/container links;
- перемещать авто между этапами;
- писать в CRM/public/PythonAnywhere;
- перезапускать сервисы;
- выполнять deploy/reload;
- создавать патч, который массово правит generated cards вместо source-of-truth template/generator;
- утверждать visual/live PASS без machine evidence.

Перед будущим install обязательны: backup, manifest 16 карточек, SHA-256 данных/media, sandbox, canary, all-16 gate, atomic replace, rollback.

Отдельный обязательный gate: `UA-0009 SAFE CHECK — PASS`.

## 9. Требуемые deliverables

Создать ровно под `cloud/task_101_ge_8_countries/`:

1. `cloud/task_101_ge_8_countries/README.md`
   - границы задачи, owner authorization, краткая карта пакета.

2. `cloud/task_101_ge_8_countries/baseline_audit.md`
   - сверка известных live-фактов;
   - список недостающих canonical source-файлов/evidence;
   - никаких вымышленных результатов.

3. `cloud/task_101_ge_8_countries/countries_models.json`
   - валидный UTF-8 JSON;
   - 8 стабильных кодов;
   - названия ru/uk/ka;
   - флаги;
   - ровно 5 моделей в каждом массиве;
   - отдельные массивы USA и UAE.

4. `cloud/task_101_ge_8_countries/localization_dictionary.json`
   - валидный JSON-каркас ru/uk/ka для всего public cycle;
   - обязательные ключи и fallback contract;
   - значения ka, требующие native review, явно маркировать metadata, не вставляя метки в отображаемый текст.

5. `cloud/task_101_ge_8_countries/implementation.patch`
   - fail-closed patch proposal только для canonical source/template/config;
   - не патчить 16 generated cards по отдельности;
   - если canonical source отсутствует в evidence, не выдумывать exact context lines: сформировать явно помеченный integration patch template и перечислить, какие SHA/source нужны для применимого патча.

6. `cloud/task_101_ge_8_countries/form_bot_contract.md`
   - country/query/lang/state/payload/deep-link contract;
   - backward compatibility и duplicate prevention.

7. `cloud/task_101_ge_8_countries/card_guard_manifest.schema.json`
   - JSON Schema для BEFORE/AFTER: 16 IDs, VIN, stage, price, media counts/hashes, links, CTA, HTTP status.

8. `cloud/task_101_ge_8_countries/test_matrix.md`
   - RU/UA/GE × 8 стран × mobile/desktop;
   - 16-card integrity;
   - counters source-of-truth;
   - WhatsApp/Telegram/WebApp/CRM contract;
   - accessibility, Safari, overflow, UTF-8.

9. `cloud/task_101_ge_8_countries/evidence.json`
   - factual statuses VERIFIED/PENDING;
   - all safety booleans false;
   - no fabricated checks.

10. `cloud/task_101_ge_8_countries/report.md`
    - результат;
    - найденные риски;
    - точный безопасный следующий шаг для ChatGPT/Codex;
    - список prerequisites для отдельного Sandbox install task.

Также обновить:

11. `cloud/latest_status.md`
12. `cloud/owner_reply.md`

## 10. Acceptance criteria

PASS только если:

- 12 deliverables существуют и непустые;
- JSON-файлы синтаксически валидны;
- 8 стран и ровно 40 моделей;
- Canada/UAE/Georgia совпадают с owner list;
- внутренний язык `ka`, UI-метка `GE`;
- сетка 4×2 специфицирована;
- country/stage Georgia разделены;
- старые country-коды не меняются;
- новый Telegram/CRM contract обратимо совместим;
- implementation patch не выдумывает отсутствующие source lines;
- card guard охватывает UA-0001…UA-0016 и отдельно UA-0009;
- static homepage counters берутся из source-of-truth, hardcode 13 запрещён;
- `production_touched=false`;
- `crm_touched=false`;
- `public_files_touched=false`;
- `pythonanywhere_touched=false`;
- `services_reloaded=false`;
- `PRODUCTION_TOUCHED: NO`.

Финальный статус:

`TASK 101 PACKAGE PASS · 16/16 CARD GUARD SPECIFIED · 8/8 COUNTRIES · 40/40 MODELS · RU/UA/GE · PRODUCTION_TOUCHED: NO`

## 11. Следующий этап

После завершения Claude:

1. ChatGPT/Codex независимо проверяет все 12 файлов.
2. При PASS формируется отдельная задача Sandbox install с точными canonical source SHA.
3. Затем canary + all-16 regression.
4. Production возможен только после отдельной письменной команды владельца.
