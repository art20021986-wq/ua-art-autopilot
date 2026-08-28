# CRM-ONLINE-GUARD-001 v1.3 — финальный отчёт

Статус: **FAIL**

- Атомарная установка и автоматический rollback: PASS
- Оба Telegram-бота и heartbeat: FAIL
- Критические callback-маршруты ≤5 с: FAIL
- RU/UA/EN golden: 0/0
- Медиа: 0 принято, 0 сохранено, очередь ?
- SQLite ≤2 с + durable field queue: — (очередь ?)
- 60-минутный soak: — (0 с)
- LLM-токены guard/детерминированных тестов: 0

Существующие карточки, сайт и медиа установщиком не изменялись.

Ошибки:

```
ControllerError:POSTCHECK_INITIAL_FAIL:["CheckError:SOURCE_CONTRACT:{\"marker_all_core\": true, \"callback_safety\": true, \"cas_no_overwrite\": true, \"voice_five_seconds\": true, \"voice_restore_semantic\": false, \"stt_last_known_good_ru\": true, \"media_receipts\": true, \"client_fast_tail\": true, \"updates_preserved\": true, \"delivery_route\": true, \"condition_route\": true, \"db_wait_bounded\": true, \"db_no_hot_journal_switch\": true, \"db_field_durable_queue\": true, \"guard_latency_percentiles\": true, \"event_loop_autore
```
