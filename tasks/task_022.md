# TASK 022 — CRM-SPEED-001: ускорение BOT CRM UA ART

## Owner authorization

Владелец явно поручил запустить в работу ТЗ CRM-SPEED-001 и вести онлайн-статус как в предыдущем проекте.

Выполни полное ТЗ из `tasks/task_020_crm_speed.md`. Этот файл является канонической задачей-продолжением и поднимает CRM-SPEED-001 выше завершённого TASK 021 в числовой очереди AUTOPILOT.

## Обязательные границы

- Создавай и изменяй только проверяемые артефакты под `cloud/` в соответствии с Deliverables из `tasks/task_020_crm_speed.md`.
- Не изменяй Production, CRM, `/home/Carix/crm.db`, живые Python-файлы, сайт, медиа, карточки, генераторы, WSGI, процессы и scheduled tasks.
- Не перезапускай bot/web/worker и не публикуй UA-0009.
- Gate A не выполнять: только подготовить fail-closed runner и доказательства готовности.
- Любая установка в Production — отдельный Gate B только после независимого аудита ChatGPT/Codex и нового явного разрешения владельца.
- Missing/ambiguous anchors или входы должны давать BLOCKED, без предположений и без частичного патча.
- Все implementation files из Deliverables должны быть полностью authored by Claude, взаимно согласованы, без TODO/placeholders и production-write capability.

## Требуемый результат этого запуска

1. Реализовать весь пакет `cloud/crm_speed_optimization/` из `tasks/task_020_crm_speed.md`.
2. Провести доступные статические/юнит-проверки в безопасном cloud-контуре, не импортируя и не выполняя production modules.
3. Обновить `cloud/latest_status.md`, `cloud/owner_reply.md` и подробный `cloud/crm_speed_optimization/cloud_report_020.md`.
4. Статус `READY_FOR_GATE_A` допустим только если все cloud-проверки прошли; иначе `BLOCKED` с точными причинами.
5. Всегда явно указать:
   - `PRODUCTION_TOUCHED: NO`
   - `CRM_TOUCHED: NO`
   - `GATE_A_EXECUTED: NO`
   - `UA_0009_PUBLISHED: NO`
6. Закоммитить полный результат в текущую task branch по протоколу AUTOPILOT.

## Перед завершением

Перечитай `tasks/task_020_crm_speed.md` целиком и проверь каждый Required validation и Deliverables. Не заявляй, что CRM уже ускорена в Production: результат этого этапа — только кандидат, готовый к независимому аудиту и затем к отдельно разрешённому Gate A.
