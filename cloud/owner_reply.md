# Ответ Claude владельцу
СТАТУС: PASS
ЗАДАЧА: Выполнить только ЭТАП 1 по Issue #88 — в CRM переименовать поле «Цена» в «Цена Украины» и добавить отдельное необязательное поле «Цена Грузии», не трогая сайт и Production.
ЧТО СДЕЛАНО: Подготовлен безопасный CRM-only патч и офлайн-проверка. Подтверждено: старый ключ `price_uah` сохраняется, новое поле `price_georgia` пишется и читается отдельно, две цены независимы, пустая цена Грузии работает.
СОЗДАННЫЕ ФАЙЛЫ: cloud/task_088_ge_price_crm_stage1/README.md, cloud/task_088_ge_price_crm_stage1/stage1_patch.diff, cloud/task_088_ge_price_crm_stage1/simulator.py, cloud/task_088_ge_price_crm_stage1/tests/test_stage1.py, cloud/task_088_ge_price_crm_stage1/evidence.json, cloud/task_088_ge_price_crm_stage1/report.md
ЧТО НУЖНО ОТ ВЛАДЕЛЬЦА: НИЧЕГО
БЕЗОПАСНОСТЬ: production/CRM/PythonAnywhere не менялись; публичный сайт, карточки, publisher, этапы, VIN, спецификация, медиа, контейнеры, счётчики, SEO, языки и CTA не тронуты.
