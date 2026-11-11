# STORAGE-AT-CLAIM-20261111 — замер места проверяется и при взятии задачи из очереди

Владелец 2026-11-11: «Да, конечно, исправ, как считаешь.»

Проблема: с очередью (AUTOSTART-QUEUE-20261111) установка может ждать дольше 30 минут; тогда в `prepare`
замер места из предпросмотра устаревает (STORAGE_PROBE_STALE_OR_FUTURE), и CRITICAL-конвейер по своему
правилу останавливает весь автопилот (HALT). За 2026-11-11 так упали KOREA-SCORE-INSTALL-R5 и
KOREA-HOW-SYNC-INSTALL-R3; обе остановки снимались вручную.

Решение (одна функция, один файл рантайма): `claim_request` для production-заявки с замером требует, чтобы
замеру было не больше 15 минут (CLAIM_STORAGE_PROBE_MAX_AGE_SECONDS). Иначе — отказ ДО создания claim и
блокировок: без HALT и без ручной уборки; нужно заново сделать предпросмотр и установку. Проверка в `prepare`
(30 минут) и вся логика HALT не меняются. Используется та же `_production_storage_probe`.

Регистрация: звено STORAGE-AT-CLAIM-20261111 в цепочке рантайма (как AUTOSTART-QUEUE-20261111):
cloud/storage_at_claim_20261111/register.py, state/runtime_activations/STORAGE-AT-CLAIM-20261111*.json,
манифест — изменился только automation/control_plane.py. Тесты: test_control_plane 81/81 (+2 новых);
в наборе task107_r2 те же 11 падений test_workflow_contracts/test_task088, что и до правки.
Слияние — только при пустой очереди (выполняющиеся задачи сверяют манифест при записи результата).
