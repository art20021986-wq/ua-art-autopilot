TASK_ID: UA-ART-SPEC-REBUILD-10-001
SPEC_VERSION: 1.0
ROUND: 12
CLAUDE_STATUS: BLOCKED
CURRENT_ACTION: Завершён отдельный установщик 29 файлов и общий координатор установки кода/данных. На серверном Python 3.10.12: 56/56 тестов PASS, без ошибок/пропусков; общий install/readback/rollback на точных копиях 29 исходников, 32 HTML и 18 CRM-строк PASS.
FILES_CREATED: cloud/spec_rebuild10/code_install.py, cloud/spec_rebuild10/tests/test_code_install.py, cloud/spec_rebuild10/CODE-INSTALL.md, cloud/spec_rebuild10/AVAILABILITY.md, cloud/spec_rebuild10/evidence/target-stage-r3.json
TARGET_RECEIPT: cloud/spec_rebuild10/evidence/target-stage-r3.json; SHA256 b455185a96e8d0f48c0f3fc0a758acf34bfe02775f3f6429250fc71c7b61b3d2; 2026-09-09T16:09:58.969937+00:00
TEST_SCOPE: 31 новых теста кода/координатора плюс 25 повторных регрессий данных. Прежние 197/197 R2 остаются отдельным результатом. Это изолированные тесты, не реальная публикация.
EXACT_CODE: a9ec4a2db16293a69aee7f78e65a1fde18bdd9d06cef2c9ca6f336c90aeb69c0; старый complete17 и data_install не менялись
DATA: 557 исторических значений сохранены, 550 видимы, 7 скрыты. Спецификация, один VIN и сохранённая оболочка проверены на 32 копиях для 16 карточек. UA-0016 год 2017 только в кандидатах. UA-0017/18 защищены как черновики.
PREVIEW_URL: https://ua-art-spec-preview.art20021986.chatgpt.site
PRODUCTION_TOUCHED: NO
SERVER_STAGING_TOUCHED: YES — только отдельная папка R3 и временные тестовые копии; процесс проверки завершился
SITE_AVAILABILITY: www главная, каталог с 16 карточками и переход UA-0001 открылись. После теста главная также открылась. Webapp включён; Disable/Reload/DNS/WSGI настройки не менялись. Причина прежнего сбоя не установлена.
OWNER_AVAILABILITY_CONSTRAINT: Старый план с DISABLE и временной недоступностью исключён. Текущий проверенный маршрут не содержит доказанного способа изолировать всех старых писателей с сохранением доступности сайта.
FULL_GATE_B: PENDING
EXACT_BLOCKER: EXTERNAL_WRITER_VERIFICATION_REQUIRED — отсутствует подтверждённая процедура и реальный контроллер, исключающие записи всего прежнего WSGI/process-tree без отключения сайта. Нужны связанное с точной операцией доказательство завершения, передача lease, восстановление после смерти holder и проверка реально загруженного runtime.
SUPPORT: Согласованный информационный запрос отправлен 2026-09-09T12:32:50Z. Технический ответ не подтверждён; не отправлять дубликат и не считать общий ответ доказательством реального завершения процессов.
LIVE_TEN_SOURCE_PASS: NO — выбор 10 источников утверждён; реальные права доступа и точное сопоставление новых источников ещё требуются. Все 18 captured CRM market отсутствуют. Историческое восстановление не выдаётся за свежую проверку 10 источников.
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE
MANUAL_PUBLISH: UA-0017 NOT_READY; UA-0018 NOT_READY. Сначала реальное восстановление 16 карточек и readback, затем владелец нажимает 17; после подтверждения 17 — 18.
NEXT_FOR_CHATGPT: Получить поддерживаемую процедуру исключения старых писателей при сохранении доступности. Подключить настоящий контроллер к завершённому CombinedInstall; сформировать свежий точный план и получить отдельную команду лишь если проверенный маршрут её требует. Не снимать HALT, не обходить external writer gate, не повторять TASK120 и не создавать production-дубликат.
DETAILS: cloud/spec_rebuild10/GATE-B.md; cloud/spec_rebuild10/CODE-INSTALL.md; cloud/spec_rebuild10/AVAILABILITY.md
BRANCH_ONLY_STATUS: YES — main и production не менялись
UPDATED_AT_UTC: 2026-09-09T16:16:00.671595+00:00
