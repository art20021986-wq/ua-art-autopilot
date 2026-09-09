TASK_ID: UA-ART-SPEC-AUTO-10-RESTORE-001
ROUND: 3
CLAUDE_STATUS: BLOCKED
CURRENT_ACTION: Исправление из 10 модулей подготовлено; 169 локальных проверок PASS; Preview v3 размещён с одним VIN и годом UA-0016 2017. Серверный Python 3.10 subgate FAIL до тестов (errno 22 candidate_compile). Общий Gate B NOT_READY_FOR_PRODUCTION.
FILES_CREATED: cloud/spec_auto10_restore/; новые lifecycle, one-VIN, owner-year, server-gate и Preview доказательства; cloud/owner_reply.md
PRODUCTION_TOUCHED: NO
SERVER_STAGING_TOUCHED: YES — только отдельная папка /home/Carix/spec_gate_b_restore_20260909 и собственный временный каталог теста.
OWNER_ACTION_REQUIRED: NO
OWNER_QUESTION: NONE — год 2017 подтверждён; отдельная команда размещения уже получена. Повторное разрешение не запрашивать.
NEXT_FOR_CHATGPT: Продолжить с точного пакета и сохранённых протоколов: устранить несовместимость атомарной сборки RENAME_NOREPLACE на сервере (errno 22 также в /tmp), выполнить Python 3.10 / полный реальный publisher+rollback / 10 адаптеров+timings; подготовить CAS-правку года UA-0016 1999→2017; пройти существующий разрешённый recovery/release маршрут при EMERGENCY_HALT. Не повторять общий аудит и не обходить controls; tests169 относятся только к локальной среде. Draft PR79, ветка spec-auto-10-restore-001.
UPDATED_AT_UTC: 2026-09-09T05:25:53.110556+00:00
