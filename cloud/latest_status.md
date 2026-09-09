TASK_ID: UA-ART-SPEC-REBUILD-10-001
SPEC_VERSION: 1.0
CLAUDE_STATUS: SERVER_STAGE_PASS_PRODUCTION_BLOCKED
CURRENT_ACTION: Реализованы data installer, реальные runtime providers, автоматическая spec-only синхронизация и reviewed-source provisioning. Сервер Python3.10.12:197/197 PASS,0 ошибок/пропусков; реальный copy install/readback/rollback32HTML+18CRM PASS;28 runtime Python sources compiled.
TARGET_RECEIPT: cloud/spec_rebuild10/evidence/target-stage-r2.json; SHA12926614cba520b3b2914ab1d7d9fdcf549952579864d533c09e0e20be4fabac; завершение15:20:26 UTC2026-09-09
FIX_FOUND_ON_TARGET: set_authorizer(None) поддерживается сPython3.11. На3.10 первый прогон195 дал13 ошибокnot authorized; callback теперь остаётся ограничивающим до закрытия соединения, добавлены2 регрессионных теста. Не выдавать это за доказанное исправление всякой старой errno22.
DATA:557 сохранены,550 видимы,7 скрыты.32копии: одинVIN,видимаяссылка,оболочка сохранена. UA0016год2017 только в кандидатах/копиях; liveгод пока1999.
RUNTIME_PACKAGE:29files,version20260909-r2,manifest2605ca1a08207e94a77747b984930c07947bce8b3ee271a6454d06c9a702de40,archive46a20d282cd3114eb49364a4a6b662a09a2074f58ee837c3c1982f46c416933f. Частный архив на сервере в stage R2; код не установлен/не импортирован. Старыйv4 допускает только прежний17-filemanifest и корректно отказывает новому.
LIVE_OBSERVATION:34HTML/DB-файла и18CRMстрок совпали со снимком14:56UTC;16published,17/18draft.32code-target/dependency preconditions проверены15:20:26UTC;3 зависимости оболочки совпали. Это readonly observation,не global atomic snapshot и не exclusive window.
PREVIEW_URL: https://ua-art-spec-preview.art20021986.chatgpt.site
PRODUCTION_UAART_TOUCHED: NO
SERVER_STAGING_TOUCHED: YES — изолированные stageR1/R2,fixtures и read-only кодовые preconditions; никакой установки в applicationroot
CRM_RUNTIME_INSTALLED: NO
FULL_GATE_B: PENDING
EXACT_REMAINING_WORK: Подтверждённое завершение всего старого WSGI/process-tree и передача lease; отдельная reviewed code-admission/installation для29filepackage с new-directory journal и combined code/data recovery; реальный controller/bootstrap startup/loaded runtime; затем public readback16. Holder-death recovery и runtime authority не создаются тестовым callback.
LIVE_TEN_SOURCE_PASS: NO — reviewed local-document collector готов; Kia2023LPI8-fact model candidate подготовлен; все18CRM market missing,UA17Audi несколько вариантов.10-source selection не заменяет access grants и точную vehicle identity. Исторические значения не объявлены свежепроверенными.
OWNER_ACTION_REQUIRED: NO — повторное утверждение ТЗ не требуется. Кнопки17/18 покаNOT_READY; сначала реальные16 и исправленнаяCRM, затем владелец нажимает17, проверка, затем18.
NEXT_FOR_CHATGPT: Продолжить новый29-filecode-admission/combinedcontroller по RUNTIME-PACKAGE.md; использовать фактические32codepreconditions из target receipt и заново валидировать их перед записью. Подтверждение exactplan получить лишь после готового проверяемого плана,если маршрут требует. Не сниматьHALT,не обходитьEXTERNAL_WRITER_VERIFICATION_REQUIRED,не повторятьTASK120,не создаватьproductionдубликат. Ранее согласованный запросSupport уже отправлен09Sep12:32:50UTC; не дублировать и не считать ответ полученным.
DETAILS: cloud/spec_rebuild10/GATE-B.md; cloud/spec_rebuild10/RUNTIME-PACKAGE.md; cloud/spec_rebuild10/DATA-INSTALL.md; cloud/spec_rebuild10/SYNC.md
BRANCH_ONLY_STATUS: YES — main и production не менялись
UPDATED_AT_UTC: 2026-09-09T15:20:26.143870+00:00
