"""cars_ui.py (CRM bot), PHOTO-ADD-001 (owner 2026-11-19: «I cannot add more photos»).

The photo intake treated a photo as a duplicate when the receipt ledger had ever seen it for the card, even after the
photo was removed from the card, so a removed photo could not be sent again. Now a receipt counts as a duplicate only
while the photo it saved is still in the card, and the drain records which photo each receipt saved.
It began with a video sent into «Добавить фото» (UA-0011, PHOTO-ADD-PROBE-20261119-R3): a photo section saved any file,
and one video among the photos breaks the bot gallery album. Now a photo section takes only photos; anything else gets
the bot's existing «другой тип файла» answer and is not saved (owner: a video sent there is simply not uploaded).
"""
from edits import replace_once

NAME = 'cars_ui.py'
MARK = '# PHOTO-ADD-001'
PAIRS = (
    ('''        import crm_online_guard as _v168_guard
        if _v168_guard.media_seen(event_key):
            return {"state": "duplicate_saved", "queued": 0}
''', '''        import crm_online_guard as _v168_guard
        ''' + MARK + ''': a duplicate only while the saved photo is still in the card (a removed photo may come back).
        _photo_add_saved = _v168_guard.media_saved_file(event_key)
        if _photo_add_saved and _photo_add_saved in set(_v165_media_ids(card_of(card_id), target)):
            return {"state": "duplicate_saved", "queued": 0}
'''),
    ('''        elif msg.document:
            file_id = msg.document.file_id
        card = card_of(wait["card_id"])
''', '''        elif msg.document:
            file_id = msg.document.file_id
        if file_id and target in ("photos", "condition_photos"):  # PHOTO-ADD-001: a photo section takes photos only
            await msg.reply_text("В этот раздел нужен другой тип файла.\\n\\n"
                                 "Для видео нажмите «Добавить видео», для фотографий — «Добавить фото».")
            raise ApplicationHandlerStop
        card = card_of(wait["card_id"])
'''),
    ('''                _v168_guard.media_mark(row["key"], row["card_id"], row["target"])
''', '''                _v168_guard.media_mark(row["key"], row["card_id"], row["target"], row["file_id"])  # PHOTO-ADD-001
'''),
)


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    return replace_once(text, PAIRS, NAME).encode('utf-8')
