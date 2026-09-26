TASK_ID: UA-ART-CRM-SITE-CONSISTENCY-001
STATUS: IN_PROGRESS_PARTIAL_DIAGNOSTICS
OWNER_INSTRUCTION: Запускай в работу — 2026-09-26 22:04 Asia/Ho_Chi_Minh
CURRENT_ACTION: Подтверждён прямой read-only доступ к рабочей CRM; 21 карточка, 23/23 обычных публичных URL совпали с серверными файлами. Кандидат расширенной проверки характеристик подготовлен, не установлен. Исправлен контракт новой read-only диагностики без изменения валидаторов.
PRODUCTION_TOUCHED: NO
GATE_B: NOT_READY
FULL_ACCEPTANCE: NO
REPORT: cloud/crm_site_consistency_001/REPORT.md
CHECKPOINT: cloud/crm_site_consistency_001/CHECKPOINT.json
NEXT: Запустить ограниченный read-only probe через штатный marker-only автопилот; затем закончить реестр полей, deletion/media, статусы бота, SLA и browser tests. Уточнить политику archive для UA-0020/UA-0021. Production — только после готового Gate B и отдельной команды по ТЗ.

DIAGNOSTIC_RUN: 36251435028 — completed/success; read-only only; Ukrainian price mismatches=0; full_consistency_accepted=false.
DIAGNOSTIC_RECEIPT: state/receipts/CRM-SITE-CONSISTENCY-PROBE-20260926.json
BACKGROUND_REPAIR_RUNNING: NO — this diagnostic run has finished; production candidate is not installed.
