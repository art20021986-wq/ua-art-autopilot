"""crm_online_guard.py (CRM bot), PHOTO-ADD-001: the photo receipt ledger keeps which photo (file id) each receipt saved.

media_saved_file(key) answers which photo a receipt saved ("" for receipts written before this release, None when the
photo was never saved); media_mark records a new receipt when the same photo is saved again after a removal.
media_seen is unchanged.
"""
from edits import replace_once

NAME = 'crm_online_guard.py'
MARK = '# PHOTO-ADD-001'
PAIRS = (
    ('''def media_mark(key: str, card_id, target) -> None:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            try:
                keys = _media_keys_locked()
                if str(key) in keys:
                    return
                row = {"key": str(key), "card_id": int(card_id),
                       "target": str(target), "saved_at": int(time.time())}
''', '''''' + MARK + ''': which photo each receipt saved, so a removed photo can be sent again.
def _media_files_locked() -> dict[str, str]:
    try:
        lines = MEDIA_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    result = {}
    for line in lines[-20000:]:
        try:
            value = json.loads(line)
            if value.get("key"):
                result[str(value["key"])] = str(value.get("file_id") or "")
        except Exception:
            pass
    return result


def media_saved_file(key: str) -> str | None:
    """File id the receipt saved; "" for an older receipt without it; None if never saved."""
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH)
            try:
                return _media_files_locked().get(str(key))
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        return None


def media_mark(key: str, card_id, target, file_id=None) -> None:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            try:
                files = _media_files_locked()
                if files.get(str(key)) == str(file_id or ""):
                    return
                row = {"key": str(key), "card_id": int(card_id),
                       "target": str(target), "saved_at": int(time.time())}
                if file_id:
                    row["file_id"] = str(file_id)
'''),
)


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('GUARD_ALREADY_INSTALLED')
    return replace_once(text, PAIRS, NAME).encode('utf-8')
