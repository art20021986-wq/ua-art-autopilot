"""Pure, source-pinned CRM hook builder. Does not read/write production files."""
import ast
import hashlib

SOURCE_SHA256 = "4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde"


HELPERS = '''# TASK088_PRICE_SYNC_HOOK_V5: durable operator intents precede price mutations.
def _task088_sync_identity(update):
    message = update.effective_message
    chat = update.effective_chat
    return (getattr(chat, "id", None), getattr(message, "message_id", None),
            getattr(update, "update_id", None))


def _task088_sync_provenance(update, context):
    return {"source": "TELEGRAM_UPDATE", "update_id": update.update_id,
            "message_id": update.effective_message.message_id,
            "chat_id": update.effective_chat.id, "chat_type": update.effective_chat.type,
            "actor_id": update.effective_user.id, "bot_id": context.bot.id}


def _task088_sync_authorize(conn, actor_id, card):
    # Live team_bot.who rejects inactive staff; existing editor has no extra
    # per-car ownership restriction. Read current membership under our write
    # transaction so role revocation cannot race accepted input/confirmation.
    row = conn.execute("SELECT * FROM staff WHERE user_id=?", (actor_id,)).fetchone()
    staff = dict(row) if row is not None else None
    if (not staff or not staff.get("active") or staff.get("role") not in
            (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER)):
        raise RuntimeError("TASK088_CAR_EDIT_PERMISSION_DENIED")


def _task088_sync_key(identity, actor_id, car_id, field):
    if (type(identity) is not tuple or len(identity) != 3
            or any(type(v) is not int for v in identity)
            or identity[0] == 0 or identity[1] <= 0 or identity[2] < 0
            or type(actor_id) is not int or actor_id <= 0):
        raise RuntimeError("TASK088_STABLE_TELEGRAM_IDENTITY_REQUIRED")
    import hashlib
    import json
    parts = ("TASK088_PRICE_SYNC_V5", *identity, actor_id, car_id, field)
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def _task088_sync_amount(value, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not int or not 0 < value < 2**63:
        raise RuntimeError("TASK088_CANONICAL_STORED_PRICE_REQUIRED")
    return "%d.00" % value


def _task088_sync_rows(answer, rows):
    token = getattr(answer, "confirmation", None)
    if token:
        return [[InlineKeyboardButton("Подтвердить сумму", callback_data="price5:yes:" + token),
                 InlineKeyboardButton("Отмена", callback_data="price5:no:" + token)]] + rows
    return rows


def _task088_sync_proposal_reply(proposal, label):
    import uaart_price_sync_confirmation as confirmations
    if proposal["state"] == "CANCELLED":
        return confirmations.PriceReply("Изменение отменено. Для новой операции отправьте цену ещё раз.")
    amount = format(proposal["payload"]["value"], ",").replace(",", " ")
    return confirmations.PriceReply(
        "%s — %s $. Сумма выглядит необычной. Подтвердите именно эту сумму перед сохранением."
        % (label, amount), confirmation=proposal["token"])


def _task088_sync_readback(conn, expected):
    import uaart_price_sync_outbox as outbox
    saved = outbox.get_operation(conn, expected["event_key"])
    keys = ("event_key", "car_id", "car_code", "vin", "field", "value", "actor_id",
            "chat_id", "provenance_json", "expected_old_json", "sequence", "created_ms")
    if saved is None or any(saved[key] != expected[key] for key in keys):
        raise RuntimeError("TASK088_COMMITTED_OUTBOX_READBACK_MISMATCH")


def _task088_sync_snapshot(conn):
    return ({item["id"]: dict(item) for item in conn.execute("SELECT * FROM cars")},
            [tuple(item) for item in conn.execute("SELECT rowid,* FROM audit ORDER BY rowid")])


def _task088_sync_prepare(conn, before, field, value, actor_id, sync_identity,
                          sync_provenance, expected_price, only_if_empty, restore_price,
                          confirmation_token, causal_price=False):
    import time
    import uaart_price_sync_outbox as outbox
    import uaart_price_sync_confirmation as confirmations
    _task088_sync_authorize(conn, actor_id, before)
    if before.get("published") not in (None, 0, 1):
        raise RuntimeError("TASK088_PUBLISHED_FLAG_INVALID")
    key = _task088_sync_key(sync_identity, actor_id, before["id"], field)
    provenance = dict(sync_provenance or {})
    if (provenance.get("source") != "TELEGRAM_UPDATE"
            or (provenance.get("chat_id"), provenance.get("message_id"), provenance.get("update_id")) != sync_identity
            or provenance.get("actor_id") != actor_id or type(provenance.get("bot_id")) is not int
            or provenance["bot_id"] <= 0 or provenance.get("chat_type") not in ("private", "group", "supergroup")
            or (provenance.get("chat_type") == "private" and sync_identity[0] != actor_id)
            or (provenance.get("chat_type") in ("group", "supergroup") and sync_identity[0] >= 0)):
        raise RuntimeError("TASK088_AUTHENTICATED_TELEGRAM_PROVENANCE_REQUIRED")
    provenance.update(authorized_car_id=before["id"], permission="EDIT_CAR")
    payload = dict(car_id=before["id"], field=field, value=value, actor_id=actor_id,
                   chat_id=sync_identity[0], identity=list(sync_identity), provenance=provenance,
                   expected_price=expected_price, only_if_empty=only_if_empty,
                   restore_price=restore_price, causal_price=causal_price)
    now_ms = time.time_ns() // 1000000
    snapshot = _task088_sync_snapshot(conn)
    if confirmation_token:
        proposal = confirmations.get(conn, confirmation_token)
        accepted = confirmations.check_identity(proposal, actor_id=actor_id,
                                                chat_id=sync_identity[0], car_id=before["id"])
        import json
        if json.dumps(payload, sort_keys=True) != json.dumps(accepted, sort_keys=True):
            raise RuntimeError("TASK088_CONFIRMATION_PAYLOAD_MISMATCH")
        if proposal["event_key"] != key:
            raise RuntimeError("TASK088_CONFIRMATION_OPERATION_MISMATCH")
        if proposal["state"] == "CANCELLED":
            return "reply", (False, _task088_sync_proposal_reply(proposal, "Цена"))
        if proposal["state"] == "CONFIRMED":
            return "duplicate", proposal
    elif confirmations.suspicious(value) or confirmations.get_for_event(conn, key) is not None:
        proposal = confirmations.propose(conn, event_key=key, payload=payload, now_ms=now_ms)
        if _task088_sync_snapshot(conn) != snapshot:
            raise RuntimeError("TASK088_CONFIRMATION_CROSS_WRITE")
        if proposal["state"] == "CONFIRMED":
            return "duplicate", proposal
        return "proposal", proposal
    existing = outbox.get_operation(conn, key)
    if existing is not None and before.get("published") != 1:
        raise RuntimeError("TASK088_REPLAY_CAR_PUBLICATION_CHANGED")
    if expected_price is not None and existing is None:
        if type(expected_price) is not tuple or len(expected_price) != 1:
            raise RuntimeError("TASK088_EXPECTED_PRICE_REQUIRED")
        if str(before[field] or "") != str(expected_price[0] or ""):
            return "reply", (False, "conflict")
        if only_if_empty and not _v168_empty(before[field]):
            return "reply", (False, "filled")
    if before.get("published") != 1:
        # Retain the existing Stage 2 write/audit routine, with a durable dedupe
        # marker so technical replay cannot apply an unpublished edit twice.
        proposal = confirmations.propose(conn, event_key=key, payload=payload, now_ms=now_ms)
        if _task088_sync_snapshot(conn) != snapshot:
            raise RuntimeError("TASK088_DRAFT_INTENT_CROSS_WRITE")
        if proposal["state"] == "CONFIRMED":
            return "duplicate", proposal
        if proposal["state"] == "CANCELLED":
            return "reply", (False, _task088_sync_proposal_reply(proposal, "Цена"))
        return "legacy", proposal
    worker_expected = expected_price
    if existing is not None:
        import json
        worker_expected = (tuple(json.loads(existing["expected_old_json"]))
                           if existing["expected_old_json"] is not None else None)
    elif causal_price and expected_price is not None:
        # Our current-row admission check above still detects external drift.
        # A preceding accepted correction is the legitimate future old value:
        # per-car FIFO guarantees it completes before this intent can commit.
        predecessor = conn.execute("SELECT value FROM " + outbox.V5_TABLE +
            " WHERE car_id=? AND field=? AND state!='COMPLETED' ORDER BY sequence DESC LIMIT 1",
            (before["id"], field)).fetchone()
        if predecessor is not None:
            from decimal import Decimal
            amount = None if predecessor[0] is None else Decimal(predecessor[0])
            if amount is not None and amount != amount.to_integral_value():
                raise RuntimeError("TASK088_PREDECESSOR_INTEGER_PRICE_REQUIRED")
            worker_expected = (None if amount is None else int(amount),)
    event = outbox.submit(conn, event_key=key, car_id=before["id"], field=field,
        value=_task088_sync_amount(value, field == "price_georgia"), actor_id=actor_id,
        chat_id=sync_identity[0], now_ms=now_ms, expected_old=worker_expected,
        provenance=provenance)
    if confirmation_token:
        confirmations.decide(conn, confirmation_token, state="CONFIRMED", now_ms=now_ms)
    if _task088_sync_snapshot(conn) != snapshot:
        raise RuntimeError("TASK088_OUTBOX_CROSS_WRITE")
    return "queued", event


async def _task088_price_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import time
    import uaart_price_sync_confirmation as confirmations
    query = update.callback_query
    answer = "Подтверждение не выполнено. Откройте карточку и проверьте цену."
    conn = None
    try:
        _, decision, token = query.data.split(":")
        if decision not in ("yes", "no"):
            raise RuntimeError("INVALID_PRICE_CONFIRMATION_ACTION")
        conn = db.connect()
        conn.execute("BEGIN IMMEDIATE")
        proposal = confirmations.get(conn, token)
        payload = confirmations.check_identity(proposal, actor_id=update.effective_user.id,
                                                chat_id=update.effective_chat.id)
        row = conn.execute("SELECT * FROM cars WHERE id=?", (payload["car_id"],)).fetchone()
        if row is None:
            raise RuntimeError("PRICE_CONFIRMATION_CARD_MISSING")
        _task088_sync_authorize(conn, update.effective_user.id, dict(row))
        if decision == "no":
            snapshot = _task088_sync_snapshot(conn)
            decided = confirmations.decide(conn, token, state="CANCELLED", now_ms=time.time_ns() // 1000000)
            if _task088_sync_snapshot(conn) != snapshot:
                raise RuntimeError("PRICE_CONFIRMATION_CANCEL_CROSS_WRITE")
            conn.commit()
            conn.close()
            conn = db.connect()
            if confirmations.get(conn, token) != decided:
                raise RuntimeError("PRICE_CONFIRMATION_CANCEL_READBACK")
            answer = "Изменение цены отменено. Можно отправить новую сумму."
        else:
            conn.rollback()
            conn.close()
            conn = None
            # Recheck current rights inside the transaction that accepts the intent.
            # Identity belongs to the original operator message, never callback replay.
            options = {key: tuple(payload[key]) if payload[key] is not None else None
                       for key in ("expected_price", "restore_price")}
            ok, answer = _task088_apply_selected_price(payload["car_id"], payload["field"],
                str(payload["value"]), update.effective_user.id,
                sync_identity=tuple(payload["identity"]), sync_provenance=payload["provenance"],
                only_if_empty=payload["only_if_empty"], causal_price=payload["causal_price"],
                confirmation_token=token, **options)
        context.user_data.pop("car_wait", None)
    except Exception:
        if conn is not None:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()
    await _v168_ack(query)
    await query.message.reply_text(str(answer))
    raise ApplicationHandlerStop


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
        "        sync_provenance=None, expected_price=None, only_if_empty=False, restore_price=None,\n"
        "        confirmation_token=None, causal_price=False):")
    source = _once(source, "        value = _task088_ge_number(raw)",
        "        if restore_price is None:\n"
        "            value = _task088_ge_number(raw)\n"
        "        else:\n"
        "            if (type(restore_price) is not tuple or len(restore_price) != 1\n"
        "                    or type(expected_price) is not tuple or len(expected_price) != 1):\n"
        "                raise RuntimeError('TASK088_GUARDED_RESTORE_REQUIRED')\n"
        "            value = restore_price[0]\n"
        "            _task088_sync_amount(value, field == 'price_georgia')")
    source = _once(source, '{"price_uah", "price_georgia", "updated_at"}',
                   '{"price_uah", "price_georgia", "updated_at", "published"}')
    source = _once(source, "        changed_at = db.now()",
        "        kind, result = _task088_sync_prepare(conn, before, field, value, actor_id,\n"
        "            sync_identity, sync_provenance, expected_price, only_if_empty, restore_price, confirmation_token, causal_price)\n"
        "        if kind == 'reply':\n"
        "            conn.rollback()\n"
        "            return result\n"
        "        if kind == 'duplicate':\n"
        "            conn.rollback()\n"
        "            conn.close()\n"
        "            conn = None\n"
        "            conn = db.connect()\n"
        "            import uaart_price_sync_confirmation as confirmations\n"
        "            if confirmations.get(conn, result['token']) != result:\n"
        "                raise RuntimeError('TASK088_DUPLICATE_CONFIRMATION_READBACK')\n"
        "            return True, confirmations.PriceReply('Эта операция уже принята; результат проверяется отдельно.', queued=True)\n"
        "        if kind in ('proposal', 'queued'):\n"
        "            conn.commit()\n"
        "            conn.close()\n"
        "            conn = None\n"
        "            conn = db.connect()\n"
        "            import uaart_price_sync_confirmation as confirmations\n"
        "            if kind == 'proposal':\n"
        "                if confirmations.get(conn, result['token']) != result:\n"
        "                    raise RuntimeError('TASK088_PROPOSAL_READBACK_MISMATCH')\n"
        "                return False, _task088_sync_proposal_reply(result, label)\n"
        "            _task088_sync_readback(conn, result)\n"
        "            if confirmation_token and confirmations.get(conn, confirmation_token)['state'] != 'CONFIRMED':\n"
        "                raise RuntimeError('TASK088_CONFIRMATION_READBACK_MISMATCH')\n"
        "            return True, confirmations.PriceReply('%s принята: %s $. Ожидайте проверку сайта.'\n"
        "                % (label, format(value, ',').replace(',', ' ') if value is not None else 'Цена уточняется'), queued=True)\n"
        "        if kind == 'legacy':\n"
        "            confirmation_token = result['token']\n"
        "        changed_at = db.now()")
    # The first commit now belongs to proposal/queue; amend only Stage 2 commit.
    source = _once(source, "        if all_after != all_expected:\n            raise RuntimeError(\"TASK088_OTHER_CAR_CROSS_WRITE\")\n        conn.commit()",
        "        if all_after != all_expected:\n            raise RuntimeError(\"TASK088_OTHER_CAR_CROSS_WRITE\")\n"
        "        if confirmation_token:\n"
        "            import time\n"
        "            import uaart_price_sync_confirmation as confirmations\n"
        "            _confirm_before = _task088_sync_snapshot(conn)\n"
        "            confirmations.decide(conn, confirmation_token, state='CONFIRMED', now_ms=time.time_ns() // 1000000)\n"
        "            if _task088_sync_snapshot(conn) != _confirm_before:\n"
        "                raise RuntimeError('TASK088_CONFIRMATION_FINISH_CROSS_WRITE')\n"
        "        conn.commit()")
    source = _once(source, '        return True, "%s сохранена: %s USD." % (label, S.num(saved[field]))',
        "        if confirmation_token and confirmations.get(conn, confirmation_token)['state'] != 'CONFIRMED':\n"
        "            raise RuntimeError('TASK088_DRAFT_CONFIRMATION_READBACK')\n"
        "        if saved[field] is None:\n"
        "            return True, '%s очищена.' % label\n"
        '        return True, "%s сохранена: %s USD." % (label, S.num(saved[field]))')
    return source


def patch_source(source):
    if type(source) is not str or hashlib.sha256(source.encode()).hexdigest() != SOURCE_SHA256:
        raise ValueError("CURRENT_CARS_UI_SOURCE_SHA256_MISMATCH")
    source = _function(source, "_task088_apply_selected_price", _price_helper)
    source = _once(source, "def _task088_apply_selected_price(", HELPERS + "def _task088_apply_selected_price(")
    passed = "sync_identity=sync_identity, sync_provenance=sync_provenance"
    actual = "sync_identity=_task088_sync_identity(update), sync_provenance=_task088_sync_provenance(update, context)"
    source = _function(source, "apply_value", lambda s: _once(_once(s,
        "def apply_value(card_id, field, raw, actor_id):",
        "def apply_value(card_id, field, raw, actor_id, *, sync_identity=None, sync_provenance=None):"),
        '    if field == "price_georgia":\n        return _task088_apply_selected_price(card_id, field, raw, actor_id)',
        '    if field in ("price_uah", "price_georgia"):\n'
        '        return _task088_apply_selected_price(card_id, field, raw, actor_id, ' + passed + ')'))

    def auto_catch(s):
        s = _once(s, "async def auto_catch(msg, card, actor_id, context):",
                  "async def auto_catch(msg, card, actor_id, context, *, sync_identity=None, sync_provenance=None):")
        for args in ('cid, "price_uah", text, actor_id', 'cid, field, str(value), actor_id',
                     'cid, field, raw, actor_id'):
            s = _once(s, "apply_value(" + args + ")", "apply_value(" + args + ", " + passed + ")")
        # Every price path sends the actual validation/proposal/queue result.
        s = _once(s, '        if ok:\n            await msg.reply_text(\n                "%s · цена: %s"',
                  '        if True:\n            await msg.reply_text(\n                "%s · цена: %s"')
        price_rows = 'reply_markup=InlineKeyboardMarkup([[\n                    InlineKeyboardButton("← Вернуться к карточке",\n                                         callback_data="car_open:%d" % cid)]]))'
        price_new = 'reply_markup=InlineKeyboardMarkup(_task088_sync_rows(answer, [[\n                    InlineKeyboardButton("← Вернуться к карточке",\n                                         callback_data="car_open:%d" % cid)]])))'
        if s.count(price_rows) != 2:
            raise ValueError("EXACT_AUTO_CATCH_PRICE_ROWS_REQUIRED")
        s = s.replace(price_rows, price_new)
        s = _once(s, '            zapisano = []\n', '            zapisano = []\n            price_handled = False\n')
        s = _once(s, '            if zapisano:\n', '            if price_handled and not zapisano:\n                return True\n            if zapisano:\n')
        s = _once(s, '                ok, _ = apply_value(', '                ok, answer = apply_value(')
        s = _once(s, '                if ok:\n                    zapisano.append(',
            '                if field in ("price_uah", "price_georgia"):\n'
            '                    price_handled = True\n'
            '                    await msg.reply_text(str(answer), reply_markup=InlineKeyboardMarkup(_task088_sync_rows(answer, [])))\n'
            '                    continue\n'
            '                if ok:\n                    zapisano.append(')
        s = _once(s, '        if ok:\n            await msg.reply_text(\n                "%s · %s"',
                  '        if ok or field in ("price_uah", "price_georgia"):\n            await msg.reply_text(\n                "%s · %s"')
        start = s.index("        if True:\n")
        end = s.index('\n    # «запиши', start)
        block = s[start + len("        if True:\n"):end]
        s = s[:start] + "".join(line[4:] if line.startswith("    ") else line
                               for line in block.splitlines(keepends=True)) + s[end:]
        return s
    source = _function(source, "auto_catch", auto_catch)

    def cas(s):
        s = _once(s, "def _v168_cas_write(card_id, field, expected_old, new_value, actor_id, correction=False):",
                  "def _v168_cas_write(card_id, field, expected_old, new_value, actor_id, correction=False, *, sync_identity=None, sync_provenance=None):")
        return _once(s, "    import re as _v168_re",
            '    if field in ("price_uah", "price_georgia"):\n'
            '        return _task088_apply_selected_price(card_id, field, str(new_value), actor_id,\n'
            '            ' + passed + ', expected_price=(expected_old,), only_if_empty=not correction, causal_price=correction)\n'
            '    import re as _v168_re')
    source = _function(source, "_v168_cas_write", cas)

    def catch(s):
        s = _once(s, 'input_text, user_id)\n        if ok:',
                  'input_text, user_id, ' + actual + ')\n        if ok:')
        s = _once(s, 'card["id"], field, old, new, user_id, explicit_override)',
                  'card["id"], field, old, new, user_id, explicit_override,\n'
                  '                        ' + actual + ')')
        s = _once(s, 'auto_catch(msg, card, user_id, context)',
                  'auto_catch(msg, card, user_id, context, ' + actual + ')')
        s = _once(s, 'apply_value(wait["card_id"], field, input_text, user_id)',
                  'apply_value(wait["card_id"], field, input_text, user_id, ' + actual + ')')
        s = _once(s, '        if ok and field == "price_uah" and card:\n            remember_price(card, user_id)\n'
            '            answer = "%s · цена этапа «%s»: %s" % (\n'
            '                card.get("auto_number") or "", S.status_label(card.get("status")),\n'
            '                S.money(_int(card.get("price_uah"))))\n', '')
        # Proposals survive restart in SQLite; in-memory wait is convenience only.
        s = _once(s, '        rows = [[InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % wait["card_id"])]]',
                  '        rows = _task088_sync_rows(answer, [[InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % wait["card_id"])]])')
        s = _once(s, '        if ok and field in ("condition_text", "diag_text"):',
                  '        rows = _task088_sync_rows(answer, rows)\n        if ok and field in ("condition_text", "diag_text"):')
        s = _once(s, '            applied = []\n', '            applied = []\n            price_results = []\n')
        s = _once(s, '                    if ok:\n                        applied.append((field, old, new))',
            '                    if field in ("price_uah", "price_georgia"):\n'
            '                        price_results.append(reason)\n'
            '                        await msg.reply_text(str(reason), reply_markup=InlineKeyboardMarkup(_task088_sync_rows(reason, [])))\n'
            '                    elif ok:\n                        applied.append((field, old, new))')
        s = _once(s, '            elif data and skipped and not explicit_override:',
                  '            elif price_results:\n                await thinking.edit_text("Результат ввода цены отправлен отдельным сообщением.")\n'
                  '            elif data and skipped and not explicit_override:')
        return s
    source = _function(source, "catch_message", catch)
    source = _function(source, "voice_change_plan", lambda s: _once(s,
        '        if str(old or "") != str(value):',
        '        if str(old or "") != str(value) or (override and field in ("price_uah", "price_georgia")):'))

    def undo(s):
        s = _once(s, '    restored = []\n', '    restored = []\n    price_results = []\n')
        s = _once(s, '        db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)',
            '        if field in ("price_uah", "price_georgia"):\n'
            '            ok, answer = _task088_apply_selected_price(cid, field, "", q.from_user.id,\n'
            '                ' + actual + ',\n'
            '                expected_price=(change.get("new"),), restore_price=(change.get("old"),))\n'
            '            price_results.append(answer)\n'
            '            await q.message.reply_text(str(answer), reply_markup=InlineKeyboardMarkup(_task088_sync_rows(answer, [])))\n'
            '            continue\n'
            '        db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)')
        return _once(s, '    else:\n        await _v168_ack(q,"Поля уже менялись позже',
            '    elif price_results:\n        await _v168_ack(q,"Запрос цены обработан")\n'
            '    else:\n        await _v168_ack(q,"Поля уже менялись позже')
    source = _function(source, "voice_undo", undo)
    source += '''

# TASK088_PRICE_SYNC_REGISTER_V5: retain all existing handlers and stage job.
_TASK088_PRICE_SYNC_BASE_REGISTER = register

def register(app):
    _TASK088_PRICE_SYNC_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(_task088_price_confirmation,
        pattern=r"^price5:(?:yes|no):[0-9a-f]{32}$"), group=-2)
    from pathlib import Path as _task088_Path
    import uaart_price_sync_binding
    uaart_price_sync_binding.bootstrap(app, anchor_path=_task088_Path("/home/Carix/.uaart_price_sync_anchor.json"))
    import uaart_price_sync_runtime
    uaart_price_sync_runtime.register(app)
'''
    ast.parse(source)
    return source
