TASK_ID: UA-ART-SPEC-AUTO-10-RESTORE-001
ROUND: 5
CLAUDE_STATUS: BLOCKED
CURRENT_ACTION: После исправления errno22 подготовлены автоповторы v8, сохранение оболочки нового publisher, согласованный единственный VIN и постоянная нумерация. Сервер Python3.10: worker 50/50 PASS; полный publisher v2 PASS с возвратом 5 изменённых HTML; allocator 26/26 PASS. Единый15модульный пакет собран,12 локальных проверок assembler PASS. Исполнение всего состава ещё не проверено; общий Gate B не закрыт.
FILES_CREATED: cloud/spec_auto10_restore/ — код, воспроизводимые пакеты, фактические серверные JSON, Gate-B.md, INTEGRATION-15-CHECKLIST.md; существующий draft PR79.
PRODUCTION_TOUCHED: NO
SERVER_STAGING_TOUCHED: YES — только отдельные spec_gate_b_restore/spec_retry_v8/spec_publisher_gate/spec_allocator_gate каталоги; рабочие источники сохранены.
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE
NEXT_FOR_CHATGPT: Читать текущий main и PR79. Recovery route уже подключён PR81, run34323968311 canary PASS, main8866d83e52197703a2f148ec882d560090ed62c9; DONE в main относится только к подключению. Не повторять старый запрос утверждения recovery-ТЗ. Закончить проверку единого15модульного состава и фактического создания/удаления/публикации, затем verified external-writer mechanism,10 разрешённых source checks, loaded worker/timings. EXTERNAL_WRITER_VERIFICATION_REQUIRED не обходить; отдельная команда точного плана остаётся требованием маршрута. HALT/очередь не менять напрямую, TASK120 не повторять. UA0017/UA0018 ещё draft; UA0016 год1999→2017 уже утверждён, пока не применён. Автопилот не активирован. Все новые пакеты — подготовка, не разрешение установки.
CONDITIONAL_RECHECK: PAUSED — рабочее включение требует отсутствующего проверенного external-writer механизма и отдельной команды точного плана; существующие серверные задачи не менялись.
UPDATED_AT_UTC: 2026-09-09T08:30:42.492227+00:00
