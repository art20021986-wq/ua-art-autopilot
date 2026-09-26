Продолжение 14.09.2026 — повторная проверка сохранённого состояния через подключённый GitHub.

Текущий head: e146c2ea8c28033050b49ccbebb33aa5276c8788; main: 0c85a6561d80c4d8789b3a482ae41cdaf9d0f667. PR open/draft, не merged. Новых программных/браузерных PASS в этом продолжении нет. Сохранённые 443/443 software PASS и 108/120 браузерных наблюдений не объявляются полным Gate; 90% относится только к числу наблюдённых браузерных случаев, не к готовности проекта.

В текущем наборе инструментов отсутствуют shell/runtime, управляемый браузер и прямая консоль PythonAnywhere. Чтение Preview/production через web завершилось non-retryable ошибкой инструмента; это не доказательство недоступности сайта для пользователей. Прежние raw-файлы из /workspace/scratch/bb84e57911cb/qa не прочитаны в этой сессии, свежие серверные read-backs не выполнены.

Проверен возможный путь через существующие Actions. Единственный check-run на текущем head — успешная Cloudflare Workers сборка ua-art-seo-watch; она не является Preview PASS цен и не доказывает публикацию uaart.com.ua. Отдельного callable Preview QA запуска в текущем подключении не найдено. Новый отдельный workflow в этой ветке нарушит exact active-workflow set; изменение событий существующего — event policy. Политики не менялись.

Свежая проверка уже завершённых Actions на main:
- Maintenance run 34826661805: 180 тестов, 7 FAIL workflow-contract (известный baseline, не включён в 443 целевых PASS): https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34826661805
- Watchdog run 34847065870: discover success, recovery_canary failure RECOVERY_CANARY_RECEIPT_BINDING: https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34847065870
Эти результаты нельзя считать успешной финальной эксплуатационной проверкой. Повторный запуск production/recovery jobs не выполнялся.

Продолжать по checkpoint CONTINUATION_20260914_108_BROWSER_CASES.json: UA-0015/0016 × RU/UA/GE × два размера; сверка raw и полный evaluator; оставшиеся gallery/visual проверки; свежие CRM/DB/source/HTML/hosting read-backs; реальное исключение конкурирующих записей и полный backup; каноническая регистрация; публикация и post-deploy; постоянный authenticated reader и реальный Stage 4 цикл. Отсутствие github-read.token известно только по прежнему stat и сейчас повторно не проверено. Подключённый GitHub не выпускает и не экспортирует этот credential.

Авторизация владельца на публикацию после 100% PASS сохранена, нового разрешения не требуется. Для Киева — только UA на сайте, GE сохраняется в CRM. Stage 1/2 не переустанавливать. В этом продолжении обновлено только описание PR; исходники, main, Preview, CRM и production не изменялись. Stage 3/4 остаются открытыми.

---

Продолжение 14.09.2026: рабочая среда и браузер восстановились, код локального checkout проверен на полное совпадение дерева с PR114. Выполнен свежий программный прогон: 348 публичных + 95 приватных = 443/443 PASS. Доведены до фактического наблюдения 108/120 браузерных случаев (90%): прежние 48 + новые 60; новые наблюдения — complete, правильный язык/размер, без горизонтального переполнения. Остаются только UA-0015 и UA-0016 × RU/UA/GE × два размера = 12 случаев. Полный Preview Gate ещё NOT_PASSED.

Открыты все 18 карточек, 18 диагностик, условия и подбор; загрузились 18 фотографий каталога. На всех карточках проверены ссылки диагностики, дополнительные спецификации и целевые CTA; 5 киевских карточек показывают только UA, остальные 13 — UA+GE. Визуально проверены Киев и числовая GE. Отправки сообщений/заявок не было.

Серверный stat подтвердил: /home/Carix/.config/uaart-price-control/github-read.token отсутствует. Значение секрета не читалось. Подготовлен read-only checker для свежей CRM/DB/HTML/исходников/679 ресурсов, но он не загружен и не запущен.

Перед последними 12 случаями exec-server снова отключился. Повторное соединение exec и браузера завершилось recovery timeout 25s. Свежий live readback, writer fence, backup, canonical install и post-deploy не выполнены. Production/Preview/CRM в этом продолжении не изменялись. Публикация остаётся авторизованной после 100% PASS, повторное разрешение не требуется.

Новый checkpoint: cloud/task088_v5_acceptance/CONTINUATION_20260914_108_BROWSER_CASES.json. Полные новые raw-файлы сохранены в /workspace/scratch/bb84e57911cb/qa до разрыва соединения и пока не перенесены в GitHub; checkpoint не заменяет доказательства полного Gate. Следующий исполнитель продолжает с оставшихся 12 случаев, сверяет raw evidence и свежие серверные данные.

---
Предыдущий handoff (история):

Команда владельца «Публикуй» получена 14.09.2026 после проверки Kyiv Preview. Публикация авторизована; повторное подтверждение не требуется. В этой сессии среда выполнения не запустилась (exec-server initialization timeout), инструменты браузера и серверной консоли отсутствуют. Подключённый GitHub доступен, PR остаётся draft на 93515742d3ff70c7d57ffeb5e0b1a8e421f6e131. 443 программные проверки и 48/120 браузерных случаев подтверждены ранее; оставшиеся 72 случая, полный Preview Gate, свежие данные/backup/каноническое развёртывание и post-deploy не выполнены. Production в этой попытке не изменялся. Команда публикации не заменяет фактический полный PASS.

Уточнение владельца 14.09: когда автомобиль в Киеве, грузинская цена не нужна. Реализовано в общем renderer, price sync и штатном stage sync; сохранённая GE не меняется. В 10:54 UTC обновлён только отдельный Preview. Проверены пять киевских карточек и каталог: UA без GE; остальные стадии показывают обе цены. 348 публичных + 95 приватных проверок = 443 PASS. 48 актуальных браузерных CSS/ценовых случаев PASS (RU/UA/GE, 390×844 и 1280×900); полный Stage 3 Gate ещё не пройден. Все live CRM/HTML/исходники/маршруты сохранены, 679 ресурсов Preview PASS, rollback предыдущего Preview готов.

Текущие доказательства: cloud/task088_v5_acceptance/KYIV_VISIBILITY_PREVIEW_RECEIPT.json, SERVER_KYIV_PREVIEW_REFRESHED.json и KYIV_PREVIEW_BROWSER_OBSERVATIONS.json; cloud/ua_ge_price_protection/SOFTWARE_GATE_KYIV_VISIBILITY_V5.json.
Текущий manifest Preview: 7c5335f921487734c5af8a94df49d1ba04ba6f5bf97492d346ab619b7205fb28. Source manifest: 18fc3c2ffb16df204cdd7318f550fbffa0a2169da3be57ff0d2bc88b1855b5c7.

Исторический отчёт предыдущего кандидата (его числа не относятся к текущему):

UA-ART-GE-UA-MARKET-PRICE-001 FINAL v5.0: кандидат независимых UA/GE цен подготовлен; отдельный Preview установлен и открыт без пароля по прямому разрешению владельца. Production не изменён, Stage 1/2 повторно не устанавливались. Stage 3/4 остаются открытыми.

Preview: https://carix.pythonanywhere.com/video/katalog.html

Изменение включает независимые nullable UA/GE представления RU/UA/GE в штатных генераторах, durable intents, FIFO внутри автомобиля, параллельность разных автомобилей, separate DB read-back, подтверждение аномальных сумм, restart recovery, постоянный audit, защищённые данные и receipt после полной проверки. Подготовлены backup/rollback системной установки, canonical activation и UA/GE PRICE PROTECTION.

Фактические проверки 14.09.2026:
- 340 публичных + 88 приватных программных проверок = 428 PASS, без ошибок и пропусков. Приватные тесты используют ранее снятые исходники и не являются реальным контрольным циклом CRM.
- Серверный кандидат: 18 автомобилей, 39 исходных страниц, 38 преобразований только ценовых участков. Действующая главная с четырьмя плитками этапов сохранена побайтно.
- 20 обслуживаемых ценовых страниц, 20 связанных страниц, 638 ресурсов и viewport harness: 679 закреплённых ресурсов проверены in-process; недостающих ресурсов 0. Ещё 19 не обслуживаемых /site/ копий сохраняются под offline-проверками.
- Серверные read-backs сборки 08:36: все 17 таблиц БД, схема, 880 HTML, рабочие исходники и маршруты Production — без изменений.
- В 10:05 UTC записан только новый Preview WSGI, сохранён backup; Production WSGI не изменён. Force HTTPS включён, static mappings отсутствуют. После Reload отдельного app в браузере открываются кандидат, каталог и карточки без пароля.
- Владелец прямо разрешил публичный read-only Preview. Открыты только закреплённые страницы/ресурсы; приватные маршруты запрещены. Production Gates не изменены.
- 42 из 120 запланированных CSS/языковых случаев фактически измерены и независимо проверены: главная, каталог и карточки UA-0001/0002/0003/0005/0008, RU/UA/GE, 390×844 и 1280×900. Цены соответствуют ранее снятым CRM-значениям, второй рынок виден, переводы корректны, горизонтального переполнения нет, шрифты не менее 14 px.
- Ошибки преждевременного измерения ещё загружающихся страниц сохранены отдельно и не засчитаны. Это не native iPhone/Safari и не полный визуальный Gate.

Полный Stage 3 Preview Gate НЕ ПРОЙДЕН. Остаются остальные браузерные случаи, фото/кнопки/ссылки и связанные страницы, свежий CRM/DB read-back, final writer exclusion и полный backup, canonical registration, разрешённая автоматическая Production-публикация только после полного Preview PASS, post-deploy и реальный Stage 4 цикл. GitHub Contents: read credential для постоянного runtime ещё не предоставлен; Preview пароль больше не требуется. Семь прежних baseline FAIL workflow-contract не включены в 428 целевых проверок.

Актуальные свидетельства:
- cloud/task088_v5_acceptance/PREVIEW_GATE_RU.md
- cloud/task088_v5_acceptance/OWNER_PUBLIC_PREVIEW_CHANGE.json
- cloud/task088_v5_acceptance/SERVER_PUBLIC_PREVIEW_PROVISIONED.json
- cloud/task088_v5_acceptance/PUBLIC_PREVIEW_ACCESS_RECEIPT.json
- cloud/task088_v5_acceptance/PUBLIC_PREVIEW_BROWSER_OBSERVATIONS_PARTIAL.json
- cloud/ua_ge_price_protection/SOFTWARE_GATE_PUBLIC_PREVIEW_V5.json
- cloud/task088_v5_acceptance/PRIVATE_SOURCE_VALIDATION_PUBLIC_PREVIEW_V5.json

Source manifest SHA256: e87c4d7a7b213ea94f466106ed6613bb566bc077145b71d1d774f2024d9db3e3.
Server candidate manifest SHA256: 083cd2de139f2f9e695f76c4e9873252c3291b4adb90af488c069315b37abdd6.
Candidate tree with current receipts: 083cb3642cc92f69958be69bd6bf84a7803fb2c7.

PR остаётся draft. Stage 3/4 PASS и включение автопилота не объявлены.
