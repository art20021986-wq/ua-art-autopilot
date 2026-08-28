# CRM-ONLINE-GUARD-001 v1.3 — финальный отчёт

Статус: **FAIL**

- Атомарная установка и автоматический rollback: PASS
- Оба Telegram-бота и heartbeat: PASS
- Критические callback-маршруты ≤5 с: PASS
- RU/UA/EN golden: 150/150
- Медиа: 100 принято, 100 сохранено, очередь 0
- SQLite ≤2 с + durable field queue: PASS (очередь 0)
- 60-минутный soak: FAIL (240.408 с)
- LLM-токены guard/детерминированных тестов: 0

Существующие карточки, сайт и медиа установщиком не изменялись.

Ошибки:

```
ControllerError:SOAK_FAIL:["stale_heartbeat:crm_bot:17.058", "guard_event_p0"]
```
