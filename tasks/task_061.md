# TASK 061 — CRM-AI-CARD-001

OWNER APPROVAL: «УТВЕРЖДАЮ CRM-AI-CARD-001. В РАБОТУ»
MODE: IMPLEMENT_AND_INSTALL
PRIORITY: P0

## Required result

1. Owner sends photo, screenshot, image-document, text, voice, or a captioned image.
2. Recognize and keep only keys present in the live `ai_filter.ALLOWED` CRM schema.
3. Open the new CRM draft immediately when at least one field is readable.
4. Never route owner intake to staff and never show a staff/manager handoff message.
5. Photo and text complete within 15 seconds.
6. Photo/text use local deterministic recognition with zero model tokens. Voice uses at most the existing single transcription call.
7. Partial recognition succeeds; unknown values are ignored and nothing is invented.

## Acceptance case

The supplied screenshot must yield: Kia, K5, 2018, VIN KNAGU416BKA324445,
198000 km, LPG, 2000 cc, automatic. The bot message starts with
`✅ Новая карточка открыта` and offers `✅ Сохранить карточку`.

## Safety

- Patch only `/home/Carix/team_bot.py` and `/home/Carix/local_ocr.py`.
- Backup and atomic rollback are mandatory.
- Do not write `crm.db`; do not rebuild or change site files.
- Do not publish UA-0009 or UA-0010 during installation.
- Run read-only CRM integrity/UA-0009 presence check and restart only the single production bot task.
