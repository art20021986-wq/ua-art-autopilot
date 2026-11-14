# BOT-ORDER-STORAGE-001 — «⚠️ Ошибка в боте»: Order storage unavailable

Владелец 2026-11-14 прислал из бота: `ua_order.storage.StorageUnavailable: Order storage unavailable`
(bindings.py job → notifications.dispatch_once → mysql_repository.claim_notification).

## Разбор (по снимку кода cloud/order_intake_probe_001/20261026-R4.json)
- Каждые несколько секунд бот берёт из очереди уведомлений о заказах (MySQL `Carix$orders`,
  таблица order_outbox) следующее уведомление.
- `_run` открывает новое соединение (connect_timeout=3, read/write 5 с). Любая ошибка MySQL,
  кроме блокировок 1205/1213, превращается в StorageUnavailable; первопричина скрыта (`from None`).
- Значит, в этот момент база MySQL PythonAnywhere не ответила за 3–5 с (кратковременный сбой).
- Потери нет: уведомление не помечено как взятое, следующий запуск задания его заберёт;
  бот не падает. Такой же сбой уже был 2026-10-07 (cloud/crm_delete_probe_20261011/evidence.json).

## Проба ORDER-STORAGE-CHECK-20261114-R2 (2026-11-14, только чтение, FINISHED)
R1 отклонён на входе (слово в описании → CRITICAL), ничего не запускалось.
Журнал бота 266084 (13.11 10:19–16:24 UTC, 137 КБ): 7 сбоев, все claim_notification, 6 эпизодов,
самый длинный 46 с. Других строк ошибок MySQL нет (код скрыт `from None`). CPU 41%.
Вывод: короткие обрывы связи с MySQL примерно раз в час при ~720 подключениях/ч, длительного отказа нет.
В start_safe.py уже есть такой же фильтр для сетевых ошибок Telegram (patch_error_handlers).

## Исправление (владелец через координатора: «Дай задачу, убери ошибку»)
Пакет cloud/order_storage_guard_001 (README там): новый ua_order/outbox_guard.py; в bindings.py задание
глотает StorageUnavailable и сообщает один раз при отказе 5+ минут; в mysql_repository.py код ошибки MySQL
пишется в журнал. Тесты 7 + 25. Превью ORDER-GUARD-PREFLIGHT-20261114 → «да» владельца → установка
ORDER-GUARD-INSTALL-20261114 (в очереди координатора).

Production не менялся.

## Итог
УСТАНОВЛЕНО 2026-11-14 12:23 UTC: ORDER-GUARD-INSTALL-20261114-R2 FINISHED (run 43592798938), квитанция state/receipts/ORDER-GUARD-INSTALL-20261114-R2.json. Production: только 3 файла ua_order; сайт и CRM не менялись.
