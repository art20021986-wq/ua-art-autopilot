"""cars_ui.py (CRM bot), PHOTO-ORDER-001 (owner 2026-11-19: photos show in the order they were sent, the first is the main).

The photo queue saved photos in arrival order, which can mix the albums of one upload (UA-0011, PHOTO-ADD-PROBE-20261119-R5).
Telegram numbers the messages of a chat in sending order and the queue already keeps that number: after each queue run
every saved photo keeps its sender and message number, and the photos of one sender are put back in message order;
other photos keep their places.
"""
from edits import replace_once

NAME = 'cars_ui.py'
MARK = '# PHOTO-ORDER-001'
PAIRS = (
    ('''def _v166_drain_owned(max_items=100):
''', MARK + ''': photos keep the order they were sent in (Telegram message number), per sender.
def _photo_order_apply(rows):
    touched = {}
    for row in rows:
        if row.get("target") in ("photos", "condition_photos") and row.get("message_id"):
            touched.setdefault((row["card_id"], row["target"]), {})[str(row["file_id"])] = (
                int(row["actor_id"]), int(row["message_id"]))
    for (card_id, target), sent in touched.items():
        card = card_of(card_id)
        if not card:
            continue
        items = [dict(p) if isinstance(p, dict) else {"file_id": p, "tag": ""} for p in jload(card.get(target))]
        changed = False
        for item in items:
            mark = sent.get(str(item.get("file_id")))
            if mark and (item.get("by"), item.get("sent")) != mark:
                item["by"], item["sent"] = mark
                changed = True
        for actor in {item.get("by") for item in items if item.get("sent")}:
            slots = [i for i, item in enumerate(items) if item.get("sent") and item.get("by") == actor]
            ordered = sorted((items[i] for i in slots), key=lambda item: item["sent"])
            for i, item in zip(slots, ordered):
                if items[i] is not item:
                    items[i] = item
                    changed = True
        if changed:
            set_field(card_id, target, jdump(items), next(iter(sent.values()))[0])


def _v166_drain_owned(max_items=100):
'''),
    ('''    _v165_spool_remove(done)
    return {"processed": len(done), "remaining": len(_v165_read_rows()),
''', '''    try:
        _photo_order_apply([row for row in rows if row["key"] in set(done)])  ''' + MARK + '''
    except Exception as exc:
        log.warning("Порядок фото не обновлён: %s", exc)
    _v165_spool_remove(done)
    return {"processed": len(done), "remaining": len(_v165_read_rows()),
'''),
)


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    return replace_once(text, PAIRS, NAME).encode('utf-8')
