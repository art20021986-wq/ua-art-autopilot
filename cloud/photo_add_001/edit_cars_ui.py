"""cars_ui.py (CRM bot), PHOTO-ADD-001 (owner 2026-11-19: «I cannot add more photos»).

The photo intake treated a photo as a duplicate when the receipt ledger had ever seen it for the card, even after the
photo was removed from the card, so a removed photo could not be sent again. Now a receipt counts as a duplicate only
while the photo it saved is still in the card, and the drain records which photo each receipt saved.
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
    ('''                _v168_guard.media_mark(row["key"], row["card_id"], row["target"])
''', '''                _v168_guard.media_mark(row["key"], row["card_id"], row["target"], row["file_id"])  # PHOTO-ADD-001
'''),
)


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    return replace_once(text, PAIRS, NAME).encode('utf-8')
