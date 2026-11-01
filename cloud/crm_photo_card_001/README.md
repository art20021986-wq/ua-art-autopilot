# CRM-PHOTO-AUTOFILL-001 — фото с VIN → новая карточка CRM

Задача и правила: `tasks/CRM-PHOTO-AUTOFILL-001.md`. Причина доказана пробой
`cloud/crm_photo_autofill_001/probe_20261101-R2.json`.

Модули (каждый — одна ответственность):
- `screen_fields.py` — пары «подпись ⏎ значение» со скриншотов → «подпись: значение».
- `vin_brand.py` — марка по WMI VIN.
- `photo_card.py` — распознать фото и применить правила (создать / уже есть / нет VIN).
- `candidate.py` — точные правки установленных `local_ocr.py` (2 строки) и `team_bot.py` (ветка фото).
- `candidate_builder.py`, `deployment_*`, `make_release.py` — установка по образцу `cloud/home_photo_001`
  (бэкап, пауза бота, блокировки, проверка, откат).

Тесты: `test_photo_card.py` (точные серверные модули, скриншот владельца, три правила),
`test_deployment.py` (бэкап/установка/откат на временных файлах).
