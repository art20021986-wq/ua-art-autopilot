# Patch notes for /home/Carix/team_bot.py (TASK 061)

Claude/Cloud did not read or modify the live `/home/Carix/team_bot.py`
(production access is out of scope for Claude/Cloud). This document is the
exact additive integration the owner-approved installer must apply, plus the
safety/rollback procedure.

## Goal

When the owner sends a photo, screenshot, image-document, text, or voice
message (not from staff/manager flow), the bot must:

1. Get raw text:
   - Photo/screenshot/image-document → existing local OCR extraction call.
   - Text/caption → the message text/caption directly.
   - Voice → the EXISTING single transcription call already used elsewhere
     in team_bot.py (do not add a second call, do not add any new model call).
2. Call `local_ocr.recognize_card_fields(raw_text, allowed_keys=ai_filter.ALLOWED)`
   (import `ai_filter` if not already imported; read `ai_filter.ALLOWED` live,
   never a cached/hardcoded copy).
3. If the returned dict is non-empty:
   - Open a NEW CRM draft in memory with those fields (do NOT write crm.db;
     drafting stays in the existing in-memory/session draft mechanism already
     used by team_bot.py for card creation).
   - Send message starting with exactly: `✅ Новая карточка открыта`
   - Offer inline button `✅ Сохранить карточку` per the existing save-draft
     flow already implemented for manual card creation.
   - Do NOT call any staff/manager routing function for this owner intake
     path. Do NOT send any staff/manager handoff message.
4. If the dict is empty (nothing recognized at all), keep current fallback
   behavior only for the "nothing readable" case — this must still not route
   to staff for owner intake; ask the owner for one more detail instead.

## Explicit prohibitions during integration

- Do not remove the staff/manager flow entirely from the file — only ensure
  it is never triggered on this owner-intake path.
- Do not add any new outbound model/API call for photo or text recognition.
- Do not add a second transcription call for voice; reuse the existing one.
- Do not write to `crm.db` as part of this change.
- Do not touch UA-0009 / UA-0010 site publication code paths.

## Suggested minimal integration point (illustrative, adapt to actual code)

```python
import ai_filter  # already present in team_bot.py in production
from local_ocr import recognize_card_fields

def handle_owner_media_or_text(raw_text):
    fields = recognize_card_fields(raw_text, allowed_keys=set(ai_filter.ALLOWED))
    if fields:
        draft = open_new_crm_draft(fields)  # existing draft-open helper
        send_message(
            "✅ Новая карточка открыта\n" + format_draft_summary(draft),
            reply_markup=save_card_keyboard(),  # existing keyboard with
                                                  # "✅ Сохранить карточку"
        )
        return
    ask_for_more_detail()  # never route_to_staff() here
```

## Backup / rollback requirement for the installer

1. `cp /home/Carix/team_bot.py /home/Carix/team_bot.py.bak_task061`
2. Apply the additive integration above at the correct existing owner-intake
   handler(s) for photo, screenshot, image-document, text, caption, voice.
3. Run `python3 -m py_compile /home/Carix/team_bot.py`.
4. Run the read-only CRM integrity / UA-0009 presence check (existing check
   script; must remain read-only, no writes).
5. If compile or the read-only check fails, restore:
   `cp /home/Carix/team_bot.py.bak_task061 /home/Carix/team_bot.py` and abort.
6. Only after both checks pass, restart the single production bot task
   (the one Always-On/Task entry that runs team_bot.py) — no other
   PythonAnywhere task, web app, or site file may be touched or reloaded.
7. Keep `.bak_task061` files in place for atomic rollback until the owner
   confirms the acceptance case passes in production.
