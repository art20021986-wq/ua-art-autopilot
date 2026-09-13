"""Pure, source-pinned CRM hook builder. Does not read/write production files."""
import ast
import hashlib

SOURCE_SHA256 = "4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde"


HELPERS = '''# TASK088_PRICE_SYNC_HOOK_V1: explicit committed publication intent.
def _task088_sync_identity(update):
    message = update.effective_message
    chat = update.effective_chat
    return (getattr(chat, "id", None), getattr(message, "message_id", None),
            getattr(update, "update_id", None))


def _task088_sync_amount(value, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or not 0 <= value < 2**63:
        raise RuntimeError("TASK088_CANONICAL_STORED_PRICE_REQUIRED")
    return "%d.00" % value


def _task088_sync_precheck(conn, before, field, value, actor_id, sync_identity):
    if before.get("published") not in (None, 0, 1):
        raise RuntimeError("TASK088_PUBLISHED_FLAG_INVALID")
    if before.get("published") != 1:
        return None, False  # Initial publication still needs the owner's button.
    if (type(sync_identity) is not tuple or len(sync_identity) != 3
            or any(type(v) is not int for v in sync_identity)
            or sync_identity[0] == 0 or sync_identity[1] <= 0 or sync_identity[2] < 0
            or type(actor_id) is not int or actor_id <= 0):
        raise RuntimeError("TASK088_STABLE_TELEGRAM_IDENTITY_REQUIRED")
    import hashlib
    import json
    import uaart_price_sync_outbox as outbox
    identity = ("TASK088_PRICE_SYNC_V1", *sync_identity, actor_id, before["id"], field)
    key = hashlib.sha256(json.dumps(identity, separators=(",", ":")).encode()).hexdigest()
    existing = outbox.get(conn, key)
    if existing is None:
        return key, False
    latest = conn.execute("SELECT MAX(revision) FROM " + outbox.TABLE + " WHERE car_id=?",
                          (before["id"],)).fetchone()[0]
    selected = "ukraine_usd" if field == "price_uah" else "georgia_usd"
    if (existing["revision"] != latest
            or existing[selected] != _task088_sync_amount(value, field == "price_georgia")
            or existing["ukraine_usd"] != _task088_sync_amount(before.get("price_uah"))
            or existing["georgia_usd"] != _task088_sync_amount(before.get("price_georgia"), True)):
        raise RuntimeError("TASK088_STALE_OR_CONFLICTING_PRICE_REPLAY")
    return key, existing


def _task088_sync_enqueue(conn, after, key):
    if key is None:
        return None
    import time
    import uaart_price_sync_outbox as outbox
    return outbox.enqueue(conn, event_key=key, car_id=after["id"],
        ukraine_usd=_task088_sync_amount(after.get("price_uah")),
        georgia_usd=_task088_sync_amount(after.get("price_georgia"), True),
        now_ms=time.time_ns() // 1000000)


def _task088_sync_readback(conn, expected):
    if expected is None:
        return
    import uaart_price_sync_outbox as outbox
    saved = outbox.get(conn, expected["event_key"])
    keys = ("event_key", "car_id", "revision", "ukraine_usd", "georgia_usd", "created_ms")
    if saved is None or any(saved[key] != expected[key] for key in keys):
        raise RuntimeError("TASK088_COMMITTED_OUTBOX_READBACK_MISMATCH")


'''


def _once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("SOURCE_ANCHOR_COUNT: " + old[:80])
    return source.replace(old, new, 1)


def _function(source, name, transform):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise ValueError("EXACT_FUNCTION_REQUIRED: " + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    original = "".join(lines[node.lineno - 1:node.end_lineno])
    replacement = transform(original)
    return "".join(lines[:node.lineno - 1]) + replacement + "".join(lines[node.end_lineno:])


def _price_helper(source):
    source = _once(source, "def _task088_apply_selected_price(card_id, field, raw, actor_id):",
        "def _task088_apply_selected_price(card_id, field, raw, actor_id, *, sync_identity=None,\n"
        "                                  expected_price=None, only_if_empty=False, restore_price=None):")
    source = _once(source, "        value = _task088_ge_number(raw)",
        "        if restore_price is None:\n"
        "            value = _task088_ge_number(raw)\n"
        "        else:\n"
        "            if (type(restore_price) is not tuple or len(restore_price) != 1\n"
        "                    or type(expected_price) is not tuple or len(expected_price) != 1):\n"
        "                raise RuntimeError('TASK088_GUARDED_RESTORE_REQUIRED')\n"
        "            value = restore_price[0]\n"
        "            if value is not None and (type(value) is not int or not 0 <= value < 2**63):\n"
        "                raise RuntimeError('TASK088_RESTORE_VALUE_INVALID')")
    source = _once(source, '{"price_uah", "price_georgia", "updated_at"}',
                   '{"price_uah", "price_georgia", "updated_at", "published"}')
    source = _once(source, "        changed_at = db.now()",
        "        sync_key, duplicate = _task088_sync_precheck(\n"
        "            conn, before, field, value, actor_id, sync_identity)\n"
        "        if duplicate:\n"
        "            conn.rollback()\n"
        "            conn.close()\n"
        "            conn = None\n"
        "            conn = db.connect()\n"
        "            current = conn.execute('SELECT * FROM cars WHERE id=?', (int(card_id),)).fetchone()\n"
        "            if current is None or dict(current) != before:\n"
        "                raise RuntimeError('TASK088_DUPLICATE_FRESH_READBACK_MISMATCH')\n"
        "            _task088_sync_readback(conn, duplicate)\n"
        "            return True, '%s уже сохранена. Публикация проверяется отдельно.' % label\n"
        "        if expected_price is not None:\n"
        "            if type(expected_price) is not tuple or len(expected_price) != 1:\n"
        "                raise RuntimeError('TASK088_EXPECTED_PRICE_REQUIRED')\n"
        "            if str(before[field] or '') != str(expected_price[0] or ''):\n"
        "                conn.rollback()\n"
        "                return False, 'conflict'\n"
        "            if only_if_empty and not _v168_empty(before[field]):\n"
        "                conn.rollback()\n"
        "                return False, 'filled'\n"
        "            if before[field] == value:\n"
        "                conn.rollback()\n"
        "                return False, 'same'\n"
        "        changed_at = db.now()")
    source = _once(source, "        conn.commit()",
        "        sync_event = _task088_sync_enqueue(conn, checked, sync_key)\n"
        "        if sync_event is not None:\n"
        "            sync_cars = {item['id']: dict(item) for item in conn.execute('SELECT * FROM cars')}\n"
        "            if sync_cars != all_expected:\n"
        "                raise RuntimeError('TASK088_OUTBOX_CAR_CROSS_WRITE')\n"
        "            for audit_id, audit_value in audit_rows:\n"
        "                recorded = conn.execute(audit_sql, (audit_id,)).fetchone()\n"
        "                if recorded is None or tuple(recorded) != audit_value:\n"
        "                    raise RuntimeError('TASK088_OUTBOX_AUDIT_CROSS_WRITE')\n"
        "        conn.commit()")
    source = _once(source, '        return True, "%s сохранена: %s USD." % (label, S.num(saved[field]))',
        "        _task088_sync_readback(conn, sync_event)\n"
        "        if saved[field] is None:\n"
        "            return True, '%s очищена.' % label\n"
        '        return True, "%s сохранена: %s USD." % (label, S.num(saved[field]))')
    return source


def patch_source(source):
    if type(source) is not str or hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("CURRENT_CARS_UI_SOURCE_SHA256_MISMATCH")
    source = _function(source, "_task088_apply_selected_price", _price_helper)
    source = _once(source, "def _task088_apply_selected_price(", HELPERS + "def _task088_apply_selected_price(")
    source = _function(source, "apply_value", lambda s: _once(_once(s,
        "def apply_value(card_id, field, raw, actor_id):",
        "def apply_value(card_id, field, raw, actor_id, *, sync_identity=None):"),
        '    if field == "price_georgia":\n        return _task088_apply_selected_price(card_id, field, raw, actor_id)',
        '    if field in ("price_uah", "price_georgia"):\n'
        '        return _task088_apply_selected_price(card_id, field, raw, actor_id, sync_identity=sync_identity)'))
    def auto_catch(s):
        s = _once(s, "async def auto_catch(msg, card, actor_id, context):",
                  "async def auto_catch(msg, card, actor_id, context, *, sync_identity=None):")
        for args in ('cid, "price_uah", text, actor_id', 'cid, field, str(value), actor_id',
                     'cid, field, raw, actor_id'):
            s = _once(s, "apply_value(" + args + ")", "apply_value(" + args + ", sync_identity=sync_identity)")
        return s
    source = _function(source, "auto_catch", auto_catch)
    def cas(s):
        s = _once(s, "def _v168_cas_write(card_id, field, expected_old, new_value, actor_id, correction=False):",
                  "def _v168_cas_write(card_id, field, expected_old, new_value, actor_id, correction=False, *, sync_identity=None):")
        return _once(s, "    import re as _v168_re",
            '    if field in ("price_uah", "price_georgia"):\n'
            '        return _task088_apply_selected_price(card_id, field, str(new_value), actor_id,\n'
            '            sync_identity=sync_identity, expected_price=(expected_old,), only_if_empty=not correction)\n'
            '    import re as _v168_re')
    source = _function(source, "_v168_cas_write", cas)
    def catch(s):
        s = _once(s, 'input_text, user_id)\n        if ok:',
                  'input_text, user_id,\n            sync_identity=_task088_sync_identity(update))\n        if ok:')
        s = _once(s, 'card["id"], field, old, new, user_id, explicit_override)',
                  'card["id"], field, old, new, user_id, explicit_override,\n'
                  '                        sync_identity=_task088_sync_identity(update))')
        s = _once(s, 'auto_catch(msg, card, user_id, context)',
                  'auto_catch(msg, card, user_id, context, sync_identity=_task088_sync_identity(update))')
        s = _once(s, 'apply_value(wait["card_id"], field, input_text, user_id)',
                  'apply_value(wait["card_id"], field, input_text, user_id, sync_identity=_task088_sync_identity(update))')
        # Price history is now part of the helper's atomic price/audit transaction.
        return _once(s, '            remember_price(card, user_id)\n', '')
    source = _function(source, "catch_message", catch)
    source = _function(source, "voice_undo", lambda s: _once(s,
        '        db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)',
        '        if field in ("price_uah", "price_georgia"):\n'
        '            ok, _ = _task088_apply_selected_price(cid, field, "", q.from_user.id,\n'
        '                sync_identity=_task088_sync_identity(update),\n'
        '                expected_price=(change.get("new"),), restore_price=(change.get("old"),))\n'
        '            if not ok:\n'
        '                continue\n'
        '        else:\n'
        '            db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)'))
    source += '''

# TASK088_PRICE_SYNC_REGISTER_V1: retain all existing handlers and stage job.
_TASK088_PRICE_SYNC_BASE_REGISTER = register

def register(app):
    _TASK088_PRICE_SYNC_BASE_REGISTER(app)
    from pathlib import Path as _task088_Path
    import uaart_price_sync_binding
    uaart_price_sync_binding.bootstrap(app, anchor_path=_task088_Path("/home/Carix/.uaart_price_sync_anchor.json"))
    import uaart_price_sync_runtime
    uaart_price_sync_runtime.register(app)
'''
    ast.parse(source)
    return source
