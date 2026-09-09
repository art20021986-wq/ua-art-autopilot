# Запрос хостингу — подготовлен, не отправлен

Внешняя отправка требует отдельного разрешения владельца. Подготовлен технический вопрос в штатной форме Contact Support аккаунта Carix; действия с сервисами не запрашиваются. Ответ хостинга не подменяет фактическое завершение процессов в согласованном окне.

Требуется уточнить гарантию полного завершения старой группы WSGI-процессов после disable и способ её подтверждения. Вопрос не касается оплаты, дополнительных слотов или передачи токенов.

## Точный текст

Account: Carix. Site: www.uaart.com.ua (WSGI, Python 3.10).

We are preparing a controlled maintenance window to restore existing vehicle specifications. This is a technical question only; please do not stop, reload, delete, or modify any service or data in response to this request.

Please confirm the supported way to prove completion of a WSGI webapp disable:

1. Does POST /api/v0/user/Carix/webapps/www.uaart.com.ua/disable/ terminate the entire old WSGI process tree or PID namespace, including detached/reparented subprocesses, or only disable routing/worker startup?
2. What authenticated observable event or readback proves that termination has completed, so no old process can subsequently write to /home/Carix/video or /home/Carix/site? Does a 200/204 response plus enabled=false guarantee this, or is there a separate completion signal? Is restart prevented until an explicit enable?
3. If the API cannot provide this guarantee, can support coordinate and confirm the complete old WSGI process-tree termination during an agreed maintenance window?

Our current server.log shows master PID 1 with three workers in the generation started 2026-09-07 12:08:33 UTC; it also records non-worker subprocess exits, so old worker burial messages alone are not sufficient for our check. Tasks and Consoles process lists are checked separately. We need the WSGI completion boundary to hand control to one installer holding the existing file locks, while preserving the CRM, files, queue and rollback.

Please advise on the supported procedure and its completion guarantee. No credentials or customer data are included.
