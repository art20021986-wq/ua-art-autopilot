# Excerpt of the live crm_online_guard.py (sha256 bcbde472, PHOTO-ADD-PROBE-20261119): photo receipt ledger.
def media_receipt_key(card_id, target, unique_id) -> str:
    raw = "%s\0%s\0%s" % (int(card_id), str(target), str(unique_id))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _media_keys_locked() -> set[str]:
    try:
        lines = MEDIA_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()
    result = set()
    for line in lines[-20000:]:
        try:
            value = json.loads(line)
            if value.get("key"):
                result.add(str(value["key"]))
        except Exception:
            pass
    return result


def media_seen(key: str) -> bool:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_SH)
            try:
                return str(key) in _media_keys_locked()
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        return False


def media_mark(key: str, card_id, target) -> None:
    try:
        with open(MEDIA_LEDGER_LOCK, "a+", encoding="utf-8") as guard:
            fcntl.flock(guard.fileno(), fcntl.LOCK_EX)
            try:
                keys = _media_keys_locked()
                if str(key) in keys:
                    return
                row = {"key": str(key), "card_id": int(card_id),
                       "target": str(target), "saved_at": int(time.time())}
                descriptor = os.open(
                    MEDIA_LEDGER_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
                try:
                    data = (json.dumps(row, separators=(",", ":")) + "\n").encode()
                    os.write(descriptor, data)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                fcntl.flock(guard.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass


