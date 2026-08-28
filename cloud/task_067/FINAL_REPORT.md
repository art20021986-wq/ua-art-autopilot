# CRM-ONLINE-GUARD-001 v1.3 — финальный отчёт

Статус: **FAIL**

- Атомарная установка и автоматический rollback: PASS
- Оба Telegram-бота и heartbeat: FAIL
- Критические callback-маршруты ≤5 с: PASS
- RU/UA/EN golden: 200/200
- Медиа: 100 принято, 100 сохранено, очередь 0
- SQLite ≤2 с + durable field queue: — (очередь ?)
- 60-минутный soak: — (0 с)
- LLM-токены guard/детерминированных тестов: 0

Существующие карточки, сайт и медиа установщиком не изменялись.

Ошибки:

```
ControllerError:POSTCHECK_INITIAL_FAIL:["CheckError:TEXT_GEARBOX"]
```
