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

PHOTO_AUDIT: 2026-09-26T15:32:08Z — 21 galleries compared by count; UA-0017 40 vs 39 allowed; UA-0019 32 vs 31 allowed. Matching counts for other 19 do not prove image identity.
PHOTO_CANDIDATE: structural guard added to hash-pinned freshness adapter; 24 field/photo tests passed; not installed. Do not deploy guard alone before fixing gallery source.
PHOTO_REPORT: cloud/crm_site_consistency_001/PHOTO_REPORT.md
CURRENT_NEXT: Reconstruct verified CRM file_id-to-asset mapping, fix gallery source/filter/order/cover and related-table revision tracking; complete public field and browser acceptance before Gate B. No production writes performed.
