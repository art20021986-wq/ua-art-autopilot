# Excerpt of the live cars_ui.py (sha256 c927ff01, PHOTO-ADD-PROBE-20261119): photo intake queue and drain.
# CRM-PHOTO-FASTPATH-001: durable, non-blocking photo intake.
_V165_SPOOL = "/home/Carix/.crm_media_spool.jsonl"
_V165_SPOOL_LOCK = "/home/Carix/.crm_media_spool.lock"
_V165_DRAIN_LOCK = "/home/Carix/.crm_media_drain.lock"
# CRM-PHOTO-COUNTER-002: one drain and session/total counters.
_V165_PROGRESS = {}


def _v165_key(card_id, target, unique_id):
    try:
        import crm_online_guard as _v168_guard
        return _v168_guard.media_receipt_key(card_id, target, unique_id)
    except Exception:
        import hashlib as _v165_hashlib
        raw = "%s\0%s\0%s" % (int(card_id), str(target), str(unique_id))
        return _v165_hashlib.sha256(raw.encode("utf-8")).hexdigest()



def _v165_limit(target):
    return {"photos": S.PHOTO_LIMIT,
            "condition_photos": S.CONDITION_PHOTO_LIMIT}.get(target, 100)


def _v165_read_rows():
    import fcntl as _v165_fcntl
    import json as _v165_json
    import os as _v165_os
    _v165_os.makedirs(_v165_os.path.dirname(_V165_SPOOL), exist_ok=True)
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as _v165_guard:
        _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                with open(_V165_SPOOL, "r", encoding="utf-8") as _v165_file:
                    _v165_lines = _v165_file.readlines()
            except FileNotFoundError:
                _v165_lines = []
        finally:
            _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_UN)
    _v165_rows = []
    for _v165_line in _v165_lines:
        try:
            _v165_row = _v165_json.loads(_v165_line)
            if isinstance(_v165_row, dict) and _v165_row.get("key"):
                _v165_rows.append(_v165_row)
        except Exception:
            continue
    return _v165_rows


def _v165_spool_enqueue(card_id, target, file_id, actor_id, tag="", unique_id=None, message_id=None):
    """Durable, idempotent acceptance; no SQLite write and no getFile wait."""
    import fcntl as _v165_fcntl
    import hashlib as _v165_hashlib
    import json as _v165_json
    import os as _v165_os
    import time as _v165_time
    identity = str(unique_id or file_id)
    event_key = _v165_key(card_id, target, identity)
    try:
        import crm_online_guard as _v168_guard
        if _v168_guard.media_seen(event_key):
            return {"state": "duplicate_saved", "queued": 0}
    except Exception:
        pass
    try:
        if str(file_id) in set(_v165_media_ids(card_of(card_id), target)):
            return {"state": "duplicate_saved", "queued": 0}
    except Exception:
        pass
    _v165_os.makedirs(_v165_os.path.dirname(_V165_SPOOL), exist_ok=True)
    event = {
        "key": event_key, "card_id": int(card_id), "target": str(target),
        "file_id": str(file_id), "actor_id": int(actor_id), "tag": str(tag or ""),
        "unique_id_sha256": _v165_hashlib.sha256(identity.encode()).hexdigest(),
        "message_id": int(message_id) if message_id is not None else None,
        "accepted_at": int(_v165_time.time()),
    }
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as guard:
        _v165_fcntl.flock(guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                lines = open(_V165_SPOOL, "r", encoding="utf-8").readlines()
            except FileNotFoundError:
                lines = []
            keys, same = set(), 0
            for line in lines:
                try:
                    row = _v165_json.loads(line)
                except Exception:
                    continue
                keys.add(row.get("key"))
                if row.get("card_id") == int(card_id) and row.get("target") == str(target):
                    same += 1
            if event_key in keys:
                return {"state": "duplicate_queued", "queued": same}
            try:
                saved_count = len(set(_v165_media_ids(card_of(card_id), target)))
            except Exception:
                saved_count = 0
            if saved_count + same >= _v165_limit(target):
                return {"state": "limit", "queued": same}
            payload = (_v165_json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            descriptor = _v165_os.open(_V165_SPOOL, _v165_os.O_WRONLY | _v165_os.O_CREAT | _v165_os.O_APPEND, 0o600)
            try:
                _v165_os.write(descriptor, payload)
                _v165_os.fsync(descriptor)
            finally:
                _v165_os.close(descriptor)
            return {"state": "accepted", "queued": same + 1, "key": event_key}
        finally:
            _v165_fcntl.flock(guard.fileno(), _v165_fcntl.LOCK_UN)



def _v165_spool_remove(keys):
    import fcntl as _v165_fcntl
    import json as _v165_json
    import os as _v165_os
    import tempfile as _v165_tempfile
    _v165_keys = set(keys)
    if not _v165_keys:
        return
    with open(_V165_SPOOL_LOCK, "a+", encoding="utf-8") as _v165_guard:
        _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_EX)
        try:
            try:
                with open(_V165_SPOOL, "r", encoding="utf-8") as _v165_file:
                    _v165_lines = _v165_file.readlines()
            except FileNotFoundError:
                return
            _v165_keep = []
            for _v165_line in _v165_lines:
                try:
                    if _v165_json.loads(_v165_line).get("key") in _v165_keys:
                        continue
                except Exception:
                    pass
                _v165_keep.append(_v165_line)
            _v165_dir = _v165_os.path.dirname(_V165_SPOOL)
            _v165_fd, _v165_tmp = _v165_tempfile.mkstemp(prefix=".media-spool-", dir=_v165_dir)
            try:
                with _v165_os.fdopen(_v165_fd, "w", encoding="utf-8") as _v165_file:
                    _v165_file.writelines(_v165_keep)
                    _v165_file.flush()
                    _v165_os.fsync(_v165_file.fileno())
                _v165_os.replace(_v165_tmp, _V165_SPOOL)
            finally:
                try:
                    _v165_os.unlink(_v165_tmp)
                except FileNotFoundError:
                    pass
        finally:
            _v165_fcntl.flock(_v165_guard.fileno(), _v165_fcntl.LOCK_UN)


def _v166_drain_owned(max_items=100):
    """Drain once; mark a durable receipt only after successful CRM save."""
    rows = _v165_read_rows()[:max(1, int(max_items))]
    done, error = [], ""
    for row in rows:
        try:
            card = card_of(row["card_id"])
            if not card:
                error = "card unavailable"
                continue
            answer = save_media(card, row["target"], row["file_id"],
                                row["actor_id"], row.get("tag", ""))
            if answer and any(word in str(answer).casefold() for word in ("не принят", "не проверен")):
                error = str(answer)[:160]
                continue
            done.append(row["key"])
            try:
                import crm_online_guard as _v168_guard
                _v168_guard.media_mark(row["key"], row["card_id"], row["target"])
            except Exception:
                pass
        except Exception as exc:
            error = "%s: %s" % (type(exc).__name__, exc)
            if "locked" in str(exc).casefold() or "busy" in str(exc).casefold():
                break
    _v165_spool_remove(done)
    return {"processed": len(done), "remaining": len(_v165_read_rows()),
            "error": error, "busy": False}



def _v165_spool_drain(max_items=100):
    """Exactly one worker may mutate card media at a time."""
    import fcntl as _v166_fcntl
    with open(_V165_DRAIN_LOCK, "a+", encoding="utf-8") as _v166_guard:
        try:
            _v166_fcntl.flock(
                _v166_guard.fileno(), _v166_fcntl.LOCK_EX | _v166_fcntl.LOCK_NB)
        except BlockingIOError:
            return {"processed": 0, "remaining": len(_v165_read_rows()),
                    "error": "", "busy": True}
        try:
            return _v166_drain_owned(max_items)
        finally:
            _v166_fcntl.flock(_v166_guard.fileno(), _v166_fcntl.LOCK_UN)



def _v165_media_ids(card, target):
    if not card:
        return []
    try:
        _v165_items = jload(card.get(target))
    except Exception:
        _v165_items = []
    _v165_result = []
    for _v165_item in _v165_items:
        _v165_value = (_v165_item.get("file_id") if isinstance(_v165_item, dict)
                       else _v165_item)
        if _v165_value and _v165_value not in _v165_result:
            _v165_result.append(_v165_value)
    return _v165_result


def _v165_status(card_id, target, session_ids=None):
    rows = [row for row in _v165_read_rows()
            if row.get("card_id") == int(card_id) and row.get("target") == str(target)]
    session = {str(value) for value in (session_ids or []) if value}
    try:
        saved_set = set(_v165_media_ids(card_of(card_id), target))
        saved_count = len(saved_set)
        session_saved = len(saved_set & session)
    except Exception:
        saved_set, saved_count, session_saved = set(), None, None
    queued_ids = {str(row.get("file_id")) for row in rows if row.get("file_id")}
    return {"accepted": len(session), "saved": saved_count, "queued": len(rows),
            "limit": _v165_limit(target), "session_saved": session_saved,
            "session_queued": len(queued_ids & session)}




