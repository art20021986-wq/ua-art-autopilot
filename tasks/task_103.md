TASK_ID: task_103
SPEC_CODE: UA-ORDER-GE-8COUNTRY-GUARD-016
SPEC_VERSION: 1.2 — FINAL
OWNER_APPROVED: YES
DEFAULT_LANGUAGE: uk
SANDBOX_PREVIEW_ONLY: YES
PRODUCTION_WRITE_AUTHORIZED: NO
OWNER: Артём Бровинский / UA ART COMPANY LLC
DATE: 2026-08-31
TARGET: подготовить к утру полный Sandbox/Preview-пакет и проверяемый отчёт
MAX_ROUNDS: 10

# TASK 103 — UA ART: грузинский язык, 8 стран «Авто под заказ» и защита 16 карточек

## Главная директива владельца

Начать автоматически и выполнить максимально автономно. Основной язык публичного сайта — украинский, технический код uk. Русский ru и грузинский ka — дополнительные. Работать только в Sandbox/Preview. Не писать в Production, CRM, бот или production paths PythonAnywhere. Не просить владельца о промежуточных решениях, если можно безопасно продолжить. Любой FAIL блокирует Production.

Нельзя заявлять, что Preview, live или визуальная проверка выполнены без машинного доказательства.

## 1. Цель

Без повреждения сайта, CRM, бота, медиа и 16 карточек:

1. Добавить грузинский язык.
2. Сделать украинский языком по умолчанию.
3. Расширить «Авто под заказ» с 5 до 8 стран: Канада, ОАЭ, Грузия.
4. Сделать 8 стран кликабельными и открывать подбор выбранной страны.
5. Показывать 5 утверждённых моделей каждой страны.
6. Сохранить UA-0001…UA-0016 без изменения данных, медиа, этапов, ссылок и CRM-связей.

## 2. Обязательный baseline

Ожидается:

- 16 уникальных карточек UA-0001…UA-0016;
- Киев 3;
- Грузия 1;
- На пароме 8;
- Корея 4;
- сумма 16;
- HTTP 200 для 16 из 16.

До правок определить source of truth главной, каталога, карточек, i18n, podbor, справочника автомобилей/этапов и обработчика заявок; сделать BEFORE-снимок; сформировать машинный манифест ID, VIN, этап, цена, числа фото/видео, диагностика, контейнер, SHA-256 медиа.

Если baseline не равен 16 и 3/1/8/4, прекратить модификации, оформить BLOCKED и ничего автоматически не исправлять.

## 3. Запреты

Запрещено:

- менять, удалять или переименовывать UA-0001…UA-0016;
- менять VIN, цену, пробег, двигатель, КПП, привод, этап, срок, контейнер, дату, описание, комплектацию;
- перемещать автомобили между этапами;
- менять количество, имена, кодек или содержимое фото, видео, OBD, диагностики;
- менять CTA карточек, WhatsApp, Telegram, диагностику, VIN-проверку, трекинг контейнера;
- вручную править 16 карточек в обход единого шаблона;
- менять структуру CRM, старые заявки и существующие коды;
- выполнять runtime-перевод внешними сервисами;
- выполнять Production write, deploy, restart или публикацию;
- использовать секреты в отчётах;
- заявлять визуальный PASS без доказательства.

Разрешены только Sandbox-копия и новые файлы под cloud/.

## 4. Языки UA / RU / GE

Переключатель интерфейса: UA | RU | GE.

- UA: код uk, html lang=uk;
- RU: код ru;
- GE: метка GE, код только ka, html lang=ka;
- ge как код языка запрещён;
- без lang, без localStorage и при неизвестном коде открывать uk;
- fallback отсутствующего перевода — украинский;
- whitelist языков: uk, ru, ka;
- разрешить параметры lang=uk, lang=ru, lang=ka и localStorage;
- сохранять язык при переходах;
- корректный aria-pressed;
- расширить data-uk, data-ru, data-ka и content, placeholder, aria, alt;
- не показывать undefined, ключи или пустые блоки;
- не выбирать язык по геолокации или браузеру.

Охват: главная, каталог/фильтры, 16 карточек, условия, подбор, диагностика, title, description, Open Graph, кнопки, статусы, ошибки, success, placeholders, aria-label, alt, счётчики, WhatsApp, Telegram и заявка.

Не переводить марки/модели, VIN, ID, контейнеры, телефон, URL, суммы, технические коды и CRM-значения.

Контрольные строки ka:

- Авто под заказ — ავტომობილი შეკვეთით
- Подберём автомобиль под ваш бюджет и пожелания — შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად
- Цена фиксируется в договоре и не меняется — ფასი ფიქსირდება ხელშეკრულებაში და არ იცვლება
- Подобрать авто — ავტომობილის შერჩევა

До Production грузинские формулировки должны пройти ручную проверку носителем. В Sandbox это внешний gate, не выполненный PASS.

## 5. Сетка стран 4 на 2

Первая строка: Корея, Япония, Америка, Европа.
Вторая строка: Китай, Канада, ОАЭ, Грузия.

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

Маршруты:

- podbor.html?strana=korea
- podbor.html?strana=japan
- podbor.html?strana=usa
- podbor.html?strana=europe
- podbor.html?strana=china
- podbor.html?strana=canada
- podbor.html?strana=uae
- podbor.html?strana=georgia

Всегда добавлять текущий язык, например podbor.html?strana=canada&lang=ka.

Страна — настоящая ссылка или доступная кнопка. Требования: одинаковая высота; click target минимум 44 px; focus, hover, active; без horizontal scroll и наложения WhatsApp; сетка 4 на 2 сохраняется на 360, 375, 390, 430, 768, 1024, 1440 px.

На podbor.html показать 8 стран. Смена страны обновляет URL и модели без потери бюджета, типа и текста. Без strana использовать korea. strana=georgia и стадия «В Грузии» используют разные state/переменные.

## 6. Единый конфиг 8 стран по 5 моделей

| Страна | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| Корея | Kia K5 | Hyundai Sonata | Hyundai Tucson | Kia Sportage | Hyundai Santa Fe |
| Япония | Nissan Note | Toyota Aqua | Mercedes-Benz B-Class | Toyota Prius | Раритетные авто 1980–1990-х годов |
| Америка | Tesla Model Y | Tesla Model 3 | Ford Escape | Nissan Rogue | BMW X3 |
| Европа | Volkswagen Golf | Volkswagen Tiguan | Audi Q5 | Škoda Octavia | Renault Megane |
| Китай | BYD Song Plus | Volkswagen ID.4 | BYD Yuan Plus (Atto 3) | Zeekr 001 | BYD Seal |
| Канада | Lexus RX 350 | Lexus RX 500 | Lexus TX | Toyota Tacoma TRD Pro | Toyota Tacoma Trailhunter |
| ОАЭ | Tesla Model Y | Tesla Model 3 | Ford Escape | Nissan Rogue | BMW X3 |
| Грузия | Ford Fusion / Fusion Hybrid | Toyota Camry | Volkswagen Jetta | Toyota RAV4 / RAV4 Hybrid | Subaru Forester |

Один whitelist-конфиг. ОАЭ хранить отдельным массивом, не ссылкой на USA. Поле «Другая модель» сохранить. Модель попадает в заявку ровно один раз.

## 7. WhatsApp, Telegram, WebApp, CRM

Добавить только коды canada, uae, georgia.

Передавать country_code или существующее s, локализованное имя страны, модель, бюджет, тип, текст или ссылку, язык uk/ru/ka, source/URL если уже есть.

Сохранить старый контракт и start=z_country; добавить z_canada, z_uae, z_georgia.

Для каждой новой страны проверить:

1. Safari/Chrome → WhatsApp.
2. Telegram WebApp sendData.
3. fallback Telegram link.
4. одна CRM-заявка без дубля.
5. правильные страна и модель.
6. UTF-8 грузинского.

В Sandbox нельзя писать в живую CRM. Создать mock/fixture и контрактные тесты. Live CRM остаётся отдельным gate до разрешения владельца.

## 8. Статические счётчики

Исходный HTML главной сразу содержит: всего 16, Киев 3, Грузия 1, На пароме 8, Корея 4.

Не оставлять 13/3/1/7/2. Статические числа строятся из того же источника, что каталог. Клиентская синхронизация только дополнительная.

## 9. Защита карточек

После каждого шага и в финале проверить UA-0001…UA-0016; UA-0009 отдельной строкой.

Для каждой: HTTP 200, уникальный ID, тот же VIN, цена, этап, срок, контейнер, техданные, числа фото/видео; первая фотография главная; фото открываются; видео и poster; одна диагностика; OBD, VIN, контейнерные ссылки; без дублей; CTA этапа; язык меняет только интерфейс.

Общее: 16 уникальных, дублей 0, 3+1+8+4=16, одинаковые числа на главной/каталоге/фильтрах, числа до JS, язык не меняет фильтр и порядок, Back сохраняет язык и этап.

SHA-256 CRM-данных, медиа и диагностики BEFORE/AFTER совпадают. Неожиданный diff = FAIL и удаление только Sandbox-сборки.

## 10. Безопасная реализация

- whitelist стран: korea, japan, usa, europe, china, canada, uae, georgia;
- неизвестная страна → korea;
- whitelist языков: uk, ru, ka; неизвестный → uk;
- не вставлять пользовательский текст через небезопасный innerHTML;
- не менять URL существующих страниц;
- обновить cache-busting CSS/JS;
- атомарная Sandbox-сборка;
- rollback-пакет;
- запрет Production paths;
- не импортировать UA ART модули с возможными side effects;
- идемпотентность;
- секреты только env и не в вывод.

## 11. UI / QA

Языки UA/RU/GE. Страны 8. Экраны 360, 375, 390, 430, 768, 1024, 1440. Браузеры iPhone Safari, Android Chrome, desktop Chrome и Safari. Страницы: главная, каталог, одна карточка каждого этапа, UA-0009, UA-0016, подбор, условия, диагностика.

Проверить 4+4, флаги и названия, отсутствие горизонтального скролла и наложения WhatsApp, Georgian/Mkhedruli, активный язык и страну, 5 моделей, клавиатуру и submit, сохранение данных.

Если браузер/Preview недоступен, подготовить исполняемые тесты и честно пометить реальные проверки NOT_RUN/BLOCKED. Не ставить PASS по статическому анализу.

## 12. Definition of Done

1. UA/RU/GE.
2. Default uk.
3. 8 стран, 4 на 2.
4. 8 из 8 маршрутов.
5. 40 из 40 моделей.
6. Canada PASS.
7. UAE PASS.
8. Georgia owner-approved list.
9. WhatsApp/Telegram/WebApp contract.
10. CRM one request/no duplicate только после разрешённого live gate.
11. 16 unique cards.
12. 3+1+8+4=16.
13. static counters 16/3/1/8/4.
14. HTTP 200 16/16.
15. UA-0009 SAFE CHECK.
16. card data changes 0.
17. media hash changes 0.
18. unexpected changes 0.
19. mobile Safari visual.
20. rollback test.
21. отдельное разрешение владельца до Production.

Любой FAIL или NOT_RUN блокирует Production.

## Deliverables

Создать:

1. cloud/ua_order_ge_8country_guard_016/README.md
2. cloud/ua_order_ge_8country_guard_016/IMPLEMENTATION_PLAN.md
3. cloud/ua_order_ge_8country_guard_016/sandbox_executor.py
4. cloud/ua_order_ge_8country_guard_016/test_sandbox_executor.py
5. cloud/ua_order_ge_8country_guard_016/country_models.json
6. cloud/ua_order_ge_8country_guard_016/i18n_dictionary_uk_ru_ka.json
7. cloud/ua_order_ge_8country_guard_016/BEFORE_AFTER_MANIFEST_SCHEMA.json
8. cloud/ua_order_ge_8country_guard_016/VALIDATION_REPORT.md
9. cloud/ua_order_ge_8country_guard_016/CHANGED_FILES.md
10. cloud/ua_order_ge_8country_guard_016/ROLLBACK_POINT.md
11. cloud/latest_status.md
12. cloud/owner_reply.md

sandbox_executor.py: Python 3.10+, stdlib-only where practical, fail-closed, режимы --self-test, --discover, --build-sandbox, --validate, --report; по умолчанию без записи. Запись только в явно переданный изолированный sandbox root после проверки, что он не равен production root и не находится внутри него. Не содержать секреты или выдуманные production paths.

Тесты: whitelist языков и стран, default uk, 40 моделей, независимость UAE от USA, маршруты, UTF-8 ka, запрет небезопасного innerHTML, счётчики, production deny, sandbox path guard, manifest equality и rollback.

## Финальный отчёт

VALIDATION_REPORT должен содержать:

- подготовленные файлы и назначение;
- Preview-ссылки UA/RU/GE либо честный NOT_AVAILABLE;
- 8 Preview-ссылок стран либо NOT_AVAILABLE;
- таблицу 40 моделей;
- screenshots/evidence либо NOT_RUN;
- 16/16 и UA-0009 либо NOT_RUN;
- BEFORE/AFTER счётчики;
- SHA-256 либо NOT_RUN;
- WhatsApp, Telegram, WebApp, CRM;
- ограничения;
- rollback point.

Финальная строка только при доказанном полном Sandbox PASS:

SANDBOX PASS · 16/16 CARDS SAFE · 8/8 COUNTRIES · UA/RU/GE PASS · PRODUCTION WRITE: NO

Если доказательств не хватает:

SANDBOX PACKAGE READY · LIVE/PREVIEW CHECKS PENDING · PRODUCTION WRITE: NO

Production остаётся запрещён до отдельной письменной команды владельца.
