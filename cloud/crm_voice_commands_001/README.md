# CRM-VOICE-ALL-001 — карточка CRM голосом

Задача, причина и список полей: `tasks/CRM-VOICE-ALL-001.md`; факты — `cloud/crm_voice_probe_001/probe_20261101.json`.

Модули (каждый — одна ответственность):
- `voice_fields.py` — названные поля и их значения из фразы (чистый текст).
- `voice_stage.py` — этап доставки из фразы о местонахождении (чистый текст).
- `voice_commands.py` — запись через функции CRM в `cars_ui` и ответ в чат.
- `candidate.py` — точные правки установленного `cars_ui.py`.
- `candidate_builder.py`, `deployment_*`, `make_release.py` — установка по образцу `cloud/crm_photo_card_001`.

Тесты: `test_voice_commands.py`, `test_deployment.py`.
