# CRM-VOICE-STAGE-001 — этап доставки голосом

Задача и причина: `tasks/CRM-VOICE-STAGE-001.md`; факты — `cloud/crm_voice_probe_001/probe_20261101.json`.

- `voice_stage.py` — фраза → код этапа (только однозначные фразы о местонахождении) и ответ в чате.
- `candidate.py` — точные правки установленного `cars_ui.py`: `save_stage()` для кнопок и голоса,
  голосовой вызов voice_stage, имя поля коробки `gearbox`.
- `candidate_builder.py`, `deployment_*`, `make_release.py` — установка по образцу `cloud/crm_photo_card_001`.

Тесты: `test_voice_stage.py` (фразы, ответ, правки, кнопки этапа как раньше, коробка),
`test_deployment.py` (бэкап/установка/откат).
