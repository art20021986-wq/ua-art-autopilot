"""TASK088 source patcher and independently callable runtime helpers.

Patching never writes a file or opens a network/database connection. Runtime
helpers accept dependencies through their host module globals; importing this
module only reads its own helper source for inclusion in a candidate.

The caller supplies freshly read cars_ui.py and must separately control its
installation. Known structural anchors are required; drift fails closed.
Historical evidence is a regression fixture, never an assertion of live state.
"""
from __future__ import annotations

import ast
import hashlib
import re
import inspect


class PatchRefused(RuntimeError):
    pass


def _task088_price_rows(rows):
    """Keep the existing car_setf convention and put both prices together."""
    import re
    rows = [list(row) for row in rows]
    ua = [(ri, bi, button) for ri, row in enumerate(rows)
          for bi, button in enumerate(row)
          if re.fullmatch(r"car_setf:\d+:price_uah",
                          getattr(button, "callback_data", "") or "")]
    ge = [button for row in rows for button in row
          if re.fullmatch(r"car_setf:\d+:price_georgia",
                          getattr(button, "callback_data", "") or "")]
    if not ua and not ge:
        return rows
    if len(ua) != 1:
        raise RuntimeError("TASK088_PRICE_BUTTON_ANCHOR")
    _, _, button = ua[0]
    cid = button.callback_data.split(":")[1]
    if len(ge) > 1 or any(item.callback_data != "car_setf:%s:price_georgia" % cid for item in ge):
        raise RuntimeError("TASK088_GE_BUTTON_ANCHOR")
    result = []
    for row in rows:
        result_row = []
        for item in row:
            callback = getattr(item, "callback_data", "") or ""
            if callback == "car_setf:%s:price_georgia" % cid:
                continue
            if item is button:
                result_row.extend([
                    InlineKeyboardButton("Цена Украины", callback_data=callback),
                    InlineKeyboardButton("Цена Грузии", callback_data=
                                         "car_setf:%s:price_georgia" % cid),
                ])
            else:
                result_row.append(item)
        if result_row:
            result.append(result_row)
    return result


def _task088_ge_number(raw):
    """Reuse the current parser's amount, never its default price_uah target."""
    import re
    text = str(raw or "").strip()
    if not text or re.search(r"(?:₴|€|₾|\b(?:uah|gel|eur|грн|грив\w*|лари)\b)",
                             text, re.I):
        raise ValueError("Укажите цену Грузии в долларах, одним числом.")
    try:
        from price_parser import parse_sale_price_message
    except ModuleNotFoundError as exc:
        if exc.name != "price_parser":
            raise
        normalized = re.sub(r"\s+", " ", text.replace("\u00a0", " ")).lower()
        normalized = re.sub(
            r"^(?:(?:измени|изменить|поставь|запиши|зміни)\s+)?"
            r"(?:(?:цена|цену|ціна|ціну|стоимость|вартість|price)\s*)?"
            r"(?:(?:грузии|грузії|georgia|авто|автомобиля)\s*)?(?:на\s+)?", "", normalized)
        match = re.fullmatch(
            r"\$?\s*(\d{1,3}(?: \d{3})+|\d+)\s*"
            r"(?:\$|usd|доллар(?:ов|а)?|долар(?:ів|и)?)?", normalized)
        if match:
            value = int(match.group(1).replace(" ", ""))
        else:
            scaled = re.fullmatch(
                r"\$?\s*(\d+(?:[.,]\d{1,3})?)\s*(?:тысяч|тыс\.?|тис\.?|к)\s*"
                r"(?:\$|usd|доллар(?:ов|а)?|долар(?:ів|и)?)?", normalized)
            if not scaled:
                raise ValueError("Укажите одну цену Грузии, например 11 400 USD.")
            from decimal import Decimal
            value = int(Decimal(scaled.group(1).replace(",", ".")) * 1000)
    else:
        parsed = parse_sale_price_message(text, in_price_uah_wait=True)
        if not parsed.ok:
            raise ValueError("Не разобрал цену Грузии. Укажите одно число в долларах.")
        value = parsed.value
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value < 2**63:
        raise ValueError("Цена должна быть положительным целым числом.")
    return value


def _task088_apply_selected_price(card_id, field, raw, actor_id):
    """Commit the selected market price + audit; verify an independent DB read."""
    if field not in ("price_uah", "price_georgia"):
        return False, "Неизвестное поле цены."
    label = "Цена Украины" if field == "price_uah" else "Цена Грузии"
    other = "price_georgia" if field == "price_uah" else "price_uah"
    try:
        value = _task088_ge_number(raw)
    except ValueError as exc:
        return False, str(exc).replace("цену Грузии", label.lower())
    conn = None
    try:
        conn = db.connect()
        conn.execute("BEGIN IMMEDIATE")
        all_before = {item["id"]: dict(item) for item in conn.execute("SELECT * FROM cars")}
        row = conn.execute("SELECT * FROM cars WHERE id=?", (int(card_id),)).fetchone()
        if row is None:
            conn.rollback()
            return False, "Карточка не найдена. %s не записана." % label
        before = dict(row)
        if not {"price_uah", "price_georgia", "updated_at"} <= set(before):
            raise RuntimeError("TASK088_GE_SCHEMA_MISSING")
        changed_at = db.now()
        if field == "price_uah":
            history = price_history(before)
            history[str(S.stage_of(before.get("status")) or 1)] = value
            history_text = jdump(history)
            conn.execute("UPDATE cars SET price_uah=?,price_history=?,updated_at=? WHERE id=?",
                         (value, history_text, changed_at, int(card_id)))
        else:
            conn.execute("UPDATE cars SET price_georgia=?,updated_at=? WHERE id=?",
                         (value, changed_at, int(card_id)))
        after = dict(conn.execute("SELECT * FROM cars WHERE id=?",
                                  (int(card_id),)).fetchone())
        expected = dict(before, updated_at=changed_at)
        expected[field] = value
        if field == "price_uah":
            expected["price_history"] = history_text
        if after != expected:
            raise RuntimeError("TASK088_GE_CROSS_WRITE")
        conn.execute(
            "INSERT INTO audit (actor_id,action,entity_type,entity_id,field,"
            "old_value,new_value,created_at) VALUES (?,?,?,?,?,?,?,?)",
            (actor_id, "card_edit", "cars", int(card_id), field,
             str(before[field]) if before[field] is not None else None,
             str(value), changed_at))
        checked = dict(conn.execute("SELECT * FROM cars WHERE id=?",
                                    (int(card_id),)).fetchone())
        if checked != expected:
            raise RuntimeError("TASK088_AUDIT_CROSS_WRITE")
        all_expected = dict(all_before)
        all_expected[int(card_id)] = expected
        all_after = {item["id"]: dict(item) for item in conn.execute("SELECT * FROM cars")}
        if all_after != all_expected:
            raise RuntimeError("TASK088_OTHER_CAR_CROSS_WRITE")
        conn.commit()
        conn.close()
        conn = db.connect()
        saved = conn.execute("SELECT price_uah,price_georgia FROM cars WHERE id=?",
                             (int(card_id),)).fetchone()
        saved = dict(saved) if saved is not None else None
        if saved is None or saved[field] != value or saved[other] != before[other]:
            return False, ("Не удалось подтвердить сохранение: %s. "
                           "Откройте карточку повторно и проверьте значение.") % label
        return True, "%s сохранена: %s USD." % (label, S.num(saved[field]))
    except Exception:
        if conn is not None:
            conn.rollback()
        return False, "%s не подтверждена. Откройте карточку и повторите." % label
    finally:
        if conn is not None:
            conn.close()

GE_RUNTIME_SOURCE = ("# TASK088_UI_V1_BEGIN\n" + "\n\n".join(
    inspect.getsource(function).rstrip()
    for function in (_task088_price_rows, _task088_ge_number, _task088_apply_selected_price)
) + "\n# TASK088_UI_V1_END\n")


GE_APPLY_BRANCH = '''    if field == "price_georgia":
        return _task088_apply_selected_price(card_id, field, raw, actor_id)
'''
GE_AUTO_BRANCH = '''    if (context.user_data.get("car_wait") or {}).get("field") in ("price_uah", "price_georgia"):
        return False
'''
GE_CATCH_BRANCH = '''    # TASK088_GE_EXPLICIT_WAIT: after existing text/voice input decoding.
    if wait and not wait.get("client") and wait.get("field") in ("price_uah", "price_georgia") and input_text:
        ok, answer = _task088_apply_selected_price(
            wait["card_id"], wait["field"], input_text, user_id)
        if ok:
            context.user_data.pop("car_wait", None)
        rows = [[InlineKeyboardButton("← Вернуться к карточке",
                                     callback_data="car_open:%d" % wait["card_id"])]]
        if thinking:
            await thinking.edit_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        else:
            await msg.reply_text(answer, reply_markup=InlineKeyboardMarkup(rows))
        raise ApplicationHandlerStop

'''


def _sha(source):
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _one(nodes, label):
    if len(nodes) != 1:
        raise PatchRefused("ANCHOR_COUNT_%d:%s" % (len(nodes), label))
    return nodes[0]


def _function(source, name):
    return _one([n for n in ast.parse(source).body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name], name)


def _text(source, node):
    return ast.get_source_segment(source, node)


def _replace_node(source, node, replacement):
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[:node.lineno - 1])
    # AST columns count UTF-8 bytes, not Unicode characters.
    start += len(lines[node.lineno - 1].encode("utf-8")[:node.col_offset].decode("utf-8"))
    end = sum(len(line) for line in lines[:node.end_lineno - 1])
    end += len(lines[node.end_lineno - 1].encode("utf-8")[:node.end_col_offset].decode("utf-8"))
    return source[:start] + replacement + source[end:]


def _insert_function_start(source, name, branch):
    node = _function(source, name)
    first = node.body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
        first = node.body[1]
    lines = source.splitlines(keepends=True)
    lines.insert(first.lineno - 1, branch)
    return "".join(lines)


def _assignment(source, name):
    return _one([n for n in ast.parse(source).body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)], name)


def patch_text(source):
    """Return (source, JSON-safe metadata); unknown or partial installs refuse."""
    compile(source, "cars_ui.py", "exec")
    original = source
    if "TASK088_UI_V1_BEGIN" in source or "price_georgia" in source:
        raise PatchRefused("ALREADY_OR_PARTIALLY_PATCHED_REQUIRES_FRESH_REVIEW")
    apply = _function(source, "apply_value")
    if [a.arg for a in apply.args.args][:4] != ["card_id", "field", "raw", "actor_id"]:
        raise PatchRefused("APPLY_SIGNATURE_DRIFT")
    _function(source, "auto_catch")
    catch = _function(source, "catch_message")
    before_hashes = {name: _sha(_text(source, _function(source, name)))
                     for name in ("apply_value", "auto_catch", "catch_message", "edit_menu")}
    no_wait = _one([n for n in catch.body if isinstance(n, ast.If)
                   and isinstance(n.test, ast.UnaryOp) and isinstance(n.test.op, ast.Not)
                   and isinstance(n.test.operand, ast.Name) and n.test.operand.id == "wait"],
                  "catch_message_not_wait")
    prefix = "\n".join(source.splitlines()[catch.lineno - 1:no_wait.lineno - 1])
    for anchor in ('input_text =', 'thinking =', 'wait = context.user_data.get("car_wait")'):
        if anchor not in prefix:
            raise PatchRefused("CATCH_INPUT_ANCHOR:" + anchor)
    # Dedicated branch precedes every free-form parser and legacy UA reroute.
    lines = source.splitlines(keepends=True)
    lines.insert(no_wait.lineno - 1, GE_CATCH_BRANCH)
    source = "".join(lines)
    source = _insert_function_start(source, "apply_value", GE_APPLY_BRANCH)
    source = _insert_function_start(source, "auto_catch", GE_AUTO_BRANCH)

    labels = _assignment(source, "LABELS_ALL")
    values = ast.literal_eval(labels.value)
    if values.get("price_uah") not in ("цена", "цена Украины", "Цена Украины"):
        raise PatchRefused("UA_LABEL_DRIFT")
    key = _one([k for k in labels.value.keys if isinstance(k, ast.Constant) and k.value == "price_uah"], "UA_LABEL_KEY")
    value = labels.value.values[labels.value.keys.index(key)]
    source = _replace_node(source, value, '"цена Украины", "price_georgia": "цена Грузии"')

    editable = _assignment(source, "EDITABLE")
    items = ast.literal_eval(editable.value)
    ua_index = _one([i for i, item in enumerate(items) if item[0] == "price_uah"], "EDITABLE_UA")
    if items[ua_index][1] not in ("Цена продажи", "Цена Украины"):
        raise PatchRefused("EDITABLE_LABEL_DRIFT")
    source = _replace_node(source, editable.value.elts[ua_index],
                           '("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")')
    for name in ("MONEY", "NUMERIC"):
        node = _assignment(source, name)
        if not isinstance(node.value, ast.Set) or "price_uah" not in ast.literal_eval(node.value):
            raise PatchRefused("SET_DRIFT:" + name)
        ua = _one([n for n in node.value.elts if isinstance(n, ast.Constant) and n.value == "price_uah"], name)
        source = _replace_node(source, ua, '"price_uah", "price_georgia"')

    # Find the field prompt by its observed price hint; do not guess its name.
    prompt = _one([n for n in ast.parse(source).body
                   if isinstance(n, ast.AsyncFunctionDef) and "Только число, в долларах." in _text(source, n)],
                  "PRICE_PROMPT")
    comparison = _one([n for n in ast.walk(prompt) if isinstance(n, ast.Compare)
                       and ast.dump(n) == ast.dump(ast.parse('field == "price_uah"', mode="eval").body)],
                      "PRICE_PROMPT_COMPARE")
    source = _replace_node(source, comparison, 'field in ("price_uah", "price_georgia")')

    menu = _function(source, "edit_menu")
    menu_source = _text(source, menu)
    if "EDITABLE" not in menu_source or "car_setf:" not in menu_source:
        raise PatchRefused("EDIT_MENU_CALLBACK_CONVENTION")
    markup = _one([n for n in ast.walk(menu) if isinstance(n, ast.Call)
                   and isinstance(n.func, ast.Name) and n.func.id == "InlineKeyboardMarkup"],
                  "EDIT_MENU_MARKUP")
    if len(markup.args) != 1 or markup.keywords:
        raise PatchRefused("EDIT_MENU_MARKUP_SIGNATURE")
    source = _replace_node(source, markup.args[0],
                           "_task088_price_rows(%s)" % _text(source, markup.args[0]))

    # Helpers must be defined before any application setup at end of module.
    first_function = next(n for n in ast.parse(source).body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    insert_line = min([first_function.lineno] + [n.lineno for n in first_function.decorator_list])
    lines = source.splitlines(keepends=True)
    lines.insert(insert_line - 1, GE_RUNTIME_SOURCE + "\n")
    source = "".join(lines)
    compile(source, "cars_ui.py", "exec")
    return source, {
        "changed": True,
        "before_sha256": _sha(original), "after_sha256": _sha(source),
        "before_functions_sha256": before_hashes,
        "ge_explicit_wait_before_auto_parser": True,
        "ge_fresh_db_readback": True,
        "adjacent_price_buttons": True,
        "ua_body_preserved": True,
        "site_changes": 0,
    }


def verify_candidate_runtime(source):
    """Return static candidate evidence; executing supplied source is forbidden.

    This API cannot establish that the running Telegram process loaded the
    change. It deliberately never returns runtime PASS. The deployment caller
    must stop until an approved runtime verification path provides that proof.
    """
    result = {"status": "NOT_VERIFIED", "proof": "static_source_shape_only",
              "live_bot_verified": False, "external_messages": 0,
              "reason": "RUNTIME_PROOF_UNAVAILABLE_NO_DYNAMIC_SOURCE_EXECUTION"}
    try:
        tree = ast.parse(source)
        editable = ast.literal_eval(_assignment(source, "EDITABLE").value)
        prices = [item for item in editable if item[0] in ("price_uah", "price_georgia")]
        if prices != [("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")]:
            raise PatchRefused("STATIC_PRICE_LABELS")
        ua_index = editable.index(("price_uah", "Цена Украины"))
        if editable[ua_index + 1] != ("price_georgia", "Цена Грузии"):
            raise PatchRefused("STATIC_EDITABLE_ORDER")
        for name in ("_task088_price_rows", "_task088_ge_number", "_task088_apply_selected_price"):
            node = _function(source, name)
            expected = ast.parse(inspect.getsource(globals()[name])).body[0]
            if ast.dump(node, include_attributes=False) != ast.dump(expected, include_attributes=False):
                raise PatchRefused("STATIC_HELPER_DRIFT:" + name)
        menu = _function(source, "edit_menu")
        calls = [node for node in ast.walk(menu) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name) and node.func.id == "_task088_price_rows"]
        _one(calls, "STATIC_MENU_HELPER_CALL")
        catch = _text(source, _function(source, "catch_message"))
        if GE_CATCH_BRANCH not in catch or GE_CATCH_BRANCH not in source:
            raise PatchRefused("STATIC_SELECTED_PRICE_ROUTE")
        prompt = _one([n for n in tree.body if isinstance(n, ast.AsyncFunctionDef)
                       and "Только число, в долларах." in _text(source, n)], "PRICE_PROMPT")
        if 'field in ("price_uah", "price_georgia")' not in _text(source, prompt):
            raise PatchRefused("STATIC_PRICE_PROMPT")
        result["static_evidence"] = {
            "helper_sources_match": True, "ordered_editable_fields": True,
            "menu_helper_present": True, "explicit_price_route_present": True,
            "price_prompt_shape_present": True,
        }
    except Exception as exc:
        result["reason"] = type(exc).__name__ + ":" + str(exc)
    return result
