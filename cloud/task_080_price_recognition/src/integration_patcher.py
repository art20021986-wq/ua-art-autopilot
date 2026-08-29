"""Fail-closed TASK 080 integration candidate builder.

The module only transforms source strings supplied by a controller.  It never
opens production files, a database, or a network connection.  Every complete
live file and every changed active block must match the GET-only Gate A hashes
before any candidate text is returned.
"""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from textwrap import dedent
from typing import Dict, Iterable, Tuple


class PatchRefused(RuntimeError):
    pass


@dataclass(frozen=True)
class BlockAnchor:
    kind: str
    name: str
    sha256: str


@dataclass(frozen=True)
class FileAnchor:
    sha256: str
    blocks: Tuple[BlockAnchor, ...] = ()


LIVE_MANIFEST = {
    "cars_ui.py": FileAnchor(
        "50f1cb15b6e1ec3a35878a3021beb362a87f3607ac46abf3eb44566023b14306",
        (
            BlockAnchor("function", "apply_value", "2d6db7d9b36cbff2635e2012f95d232dfd9be3b757f82540e0df43bfa9a77133"),
            BlockAnchor("function", "auto_catch", "eb285e823ad69e55ec1a5d3995450c45ee767de0316e50ac9fad80850b16287b"),
            BlockAnchor("function", "_v168_cas_write", "1c6b4a285cb821847621ed16ac215cbbff9130006babfc01f739880eca04bf8a"),
            BlockAnchor("function", "voice_undo", "77910d3484d0892231988260b6a3905daab78bc87daed336533eb01b85e97f5e"),
            BlockAnchor("function", "catch_message", "152d00158bcd097f61fad4e795340f45113724217b481d56ab32f358549a4fd5"),
        ),
    ),
    "local_ocr.py": FileAnchor(
        "7eb4de0597fb6064c8e5f7b56c00d673e8d964630481b3fe5511bb20363770b5",
        (BlockAnchor("function", "fields_from_text", "184038c604061417baea19d45333f3737b42de02111645f93e682b065f58cda3"),),
    ),
    "ai_fast_schema.py": FileAnchor(
        "d2ac2104b2293e3c5cb38930fac6f4de87b9d1d3f35783b1b4e892433fcfd64e",
        (
            BlockAnchor("function", "labeled_text_data", "093cd70b35b5e58f996e709a8f1914de9ecddca8074d3e7fbbe2a7815fdc75e6"),
            BlockAnchor("function", "fast_text_data", "e7a7f9e22afb53051ee680d9d9dd175c696b8e2a9546448017cebf2970b55d11"),
        ),
    ),
    "ai_filter.py": FileAnchor(
        "7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6",
        (BlockAnchor("assignment", "ALLOWED", "fb25dfaf70cb44887a9e720cbac5059385b5069fa772a977b1907233ab799b54"),),
    ),
    # Dependency contract for the supplied connection factory and clock.
    "db.py": FileAnchor(
        "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
        (
            BlockAnchor("function", "connect", "da9b6d2d26eaa1ebc82cecf6036a276c8951da8f2314156519705ba5d67ed374"),
            BlockAnchor("function", "now", "08c460137950477a288ce91ad002f0a9d0b5797c7ff8a484cded7def346d4bd3"),
            BlockAnchor("class", "Soedinenie", "edfd3fd7709aaaee60d013f266481a2cfc7cd03d0d318683f8e245f4aa816b66"),
        ),
    ),
}


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _node_kind(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return "function"
    if isinstance(node, ast.ClassDef):
        return "class"
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        return "assignment"
    return None


def _assignment_names(node: ast.AST) -> Iterable[str]:
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return ()
    return tuple(target.id for target in targets if isinstance(target, ast.Name))


def _named_nodes(source: str, kind: str, name: str):
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if _node_kind(node) != kind:
            continue
        if kind == "assignment":
            if name in _assignment_names(node):
                found.append(node)
        elif getattr(node, "name", None) == name:
            found.append(node)
    return found


def _node_source(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def verify_live_sources(files: Dict[str, str]) -> None:
    missing = sorted(set(LIVE_MANIFEST) - set(files))
    if missing:
        raise PatchRefused("TARGET_FILE_NOT_PROVIDED:" + ",".join(missing))
    for path, anchor in LIVE_MANIFEST.items():
        source = files[path]
        if _sha(source) != anchor.sha256:
            raise PatchRefused("WHOLE_FILE_HASH_MISMATCH:" + path)
        compile(source, path, "exec")
        for block in anchor.blocks:
            nodes = _named_nodes(source, block.kind, block.name)
            if len(nodes) != 1:
                raise PatchRefused(
                    "%s_%s:%s" % (
                        "BLOCK_NOT_FOUND" if not nodes else "DUPLICATE_ACTIVE_BLOCK",
                        block.name,
                        path,
                    )
                )
            if _sha(_node_source(source, nodes[0])) != block.sha256:
                raise PatchRefused("BLOCK_HASH_MISMATCH:%s:%s" % (path, block.name))


def _replace_once(value: str, old: str, new: str, label: str) -> str:
    count = value.count(old)
    if count != 1:
        raise PatchRefused("ANCHOR_COUNT_%d:%s" % (count, label))
    return value.replace(old, new, 1)


def _replace_block(source: str, kind: str, name: str, replacement: str) -> str:
    nodes = _named_nodes(source, kind, name)
    if len(nodes) != 1:
        raise PatchRefused("PATCH_BLOCK_COUNT_%d:%s" % (len(nodes), name))
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    replacement = replacement.rstrip("\n") + "\n"
    lines[node.lineno - 1 : node.end_lineno] = [replacement]
    return "".join(lines)


APPLY_VALUE = dedent(r'''
def apply_value(card_id, field, raw, actor_id, correction=False,
                in_price_uah_wait=False, expected_auto_number=None):
    """Validate one value; sale price uses the atomic TASK 080 writer."""
    value = (raw or "").strip()
    if not value:
        return False, "Пустое значение не записываю."

    if field == "price_uah":
        from price_parser import parse_sale_price_message
        from crm_price_atomic import write_price

        parsed = parse_sale_price_message(value, in_price_uah_wait=in_price_uah_wait)
        if not parsed.ok:
            retry = {
                "MULTIPLE_COMPETING_AMOUNTS": "Укажите одну цену продажи.",
                "AMBIGUOUS_CURRENCY": "Укажите цену в одной валюте.",
                "AMBIGUOUS_CONTEXT_BLOCKED": "Уточните именно цену продажи автомобиля.",
                "NEGATIVE_AMOUNT": "Цена должна быть положительным числом.",
                "OUT_OF_RANGE": "Цена вне допустимого диапазона.",
            }.get(parsed.reason, "Не разобрал цену продажи.")
            return False, retry + " Например: «цена авто 11 400 USD». Карточка не изменена."
        card = card_of(int(card_id))
        if not card:
            return False, "Карточка не найдена. Цена не записана."
        number = card.get("auto_number")
        if not number:
            return False, "У карточки нет постоянного номера. Цена не записана."
        result = write_price(
            connect=db.connect,
            now=db.now,
            card_id=int(card_id),
            expected_auto_number=expected_auto_number or number,
            expected_status=card.get("status"),
            expected_old=card.get("price_uah"),
            new_value=parsed.value,
            actor_id=actor_id,
            stage_key=S.stage_of(card.get("status")) or 1,
            correction=bool(correction or in_price_uah_wait or
                            parsed.is_explicit_change_intent),
        )
        if result.ok:
            return True, "Записано: %s" % S.num(parsed.value)
        if result.reason == "filled":
            return False, ("Цена уже заполнена. Для замены напишите: "
                           "«измени цену на 11 400». Карточка не изменена.")
        if result.reason == "same":
            return False, "Такая цена уже указана. Карточка не изменена."
        if result.reason in ("conflict", "identity_conflict", "stage_conflict"):
            return False, "Карточка изменилась параллельно. Откройте её снова; цена не записана."
        return False, "Цена не записана из-за технической ошибки. Повторите позже."

    if field == "eta_days":
        digits = "".join(ch for ch in value if ch.isdigit())
        if not digits:
            return False, "Пришлите число дней, например 45."
        n = int(digits)
        if n > 400:
            return False, "Слишком большой срок. Пришлите число дней."
        eta = _date.today() + _td(days=n)
        set_field(card_id, "eta_manual", eta.isoformat(), actor_id)
        set_field(card_id, "days_to_kyiv", n, actor_id)
        return True, "До прибытия %d дней · %s" % (n, eta.strftime("%d.%m.%Y"))

    if field in NUMERIC:
        digits = value.lower().replace(" ", "").replace("\u00a0", "")
        for lishnee in ("цена", "стоимость", "$", "usd", "долларов", "долл"):
            digits = digits.replace(lishnee, "")
        for word, mult in (("тысяч", 1000), ("тыс", 1000), ("к", 1000)):
            if word in digits.lower():
                digits = digits.lower().split(word)[0]
                try:
                    num = int(float(digits.replace(",", ".")) * mult)
                except ValueError:
                    return False, "Не разобрал число. Пришлите цифрами."
                break
        else:
            digits = "".join(ch for ch in digits if ch.isdigit())
            if not digits:
                return False, "Не разобрал число. Пришлите цифрами."
            num = int(digits)
        if field == "engine_cc" and num < 100:
            return False, ("Похоже, это литры. Объём нужен в кубических сантиметрах — "
                           "например, 1598.")
        set_field(card_id, field, num, actor_id)
        return True, "Записано: %s" % S.num(num)

    if field == "vin":
        vin = value.upper().replace(" ", "")
        ok, msg = S.check_vin(vin)
        if not ok:
            return False, "VIN не принят: %s" % msg
        set_field(card_id, field, vin, actor_id)
        return True, "Записано: %s" % vin

    set_field(card_id, field, value, actor_id)
    return True, "Записано."
''').lstrip()


V168_CAS_WRITE = dedent(r'''
def _v168_cas_write(card_id, field, expected_old, new_value, actor_id,
                    correction=False, expected_auto_number=None):
    import re as _v168_re
    if not _v168_re.fullmatch(r"[a-z_][a-z0-9_]*", str(field or "")):
        return False, "invalid"
    if _v168_empty(new_value):
        return False, "empty"
    if field == "price_uah":
        from crm_price_atomic import write_price
        card = card_of(int(card_id))
        if not card:
            return False, "missing_card"
        number = card.get("auto_number")
        if not number:
            return False, "identity_conflict"
        result = write_price(
            connect=db.connect,
            now=db.now,
            card_id=int(card_id),
            expected_auto_number=expected_auto_number or number,
            expected_status=card.get("status"),
            expected_old=expected_old,
            new_value=new_value,
            actor_id=actor_id,
            stage_key=S.stage_of(card.get("status")) or 1,
            correction=correction,
        )
        return result.ok, result.reason
    with db.connect() as _v168_con:
        columns = {row[1] for row in _v168_con.execute("PRAGMA table_info(cars)")}
        if field not in columns:
            return False, "unknown"
        row = _v168_con.execute(
            "SELECT %s FROM cars WHERE id=?" % field, (int(card_id),)).fetchone()
        if row is None:
            return False, "missing_card"
        current = row[0]
        if str(current or "") == str(new_value):
            return False, "same"
        if correction:
            if str(current or "") != str(expected_old or ""):
                return False, "conflict"
        elif not _v168_empty(current):
            return False, "filled"
        cursor = _v168_con.execute(
            "UPDATE cars SET %s=?,updated_at=? WHERE id=? AND %s IS ?" % (field, field),
            (new_value, db.now(), int(card_id), current))
        if cursor.rowcount != 1:
            return False, "conflict"
    try:
        db.log_action(actor_id, "card_edit", "cars", int(card_id),
                      field, current, new_value)
    except Exception as _v168_exc:
        log.warning("CRM CAS audit failed card=%s field=%s error=%s",
                    card_id, field, _v168_exc)
    return True, "applied"
''').lstrip()


FAST_TEXT_DATA = dedent(r'''
def fast_text_data(text, ai_filter):
    labeled = labeled_text_data(text, ai_filter)
    fallback = clean_car(parsed_from_data({}), ai_filter, text or "")
    merged = dict(fallback)
    merged.update(labeled)
    if "price_uah" in car_fields(ai_filter):
        from price_parser import parse_sale_price_message
        price = parse_sale_price_message(text or "")
        if price.ok:
            merged["price_uah"] = price.value
    return merged
''').lstrip()


def _patch_local_ocr(block: str) -> str:
    return _replace_once(
        block,
        "    return data\n",
        "    if \"price_uah\" in allowed:\n"
        "        from price_parser import parse_sale_price_message\n"
        "        price = parse_sale_price_message(raw)\n"
        "        if price.ok:\n"
        "            data[\"price_uah\"] = price.value\n"
        "    return data\n",
        "local_ocr:return",
    )


def _patch_labeled(block: str) -> str:
    old = (
        '        "цена": _choose(allowed, "price_total", "price_buy"),\n'
        '        "ціна": _choose(allowed, "price_total", "price_buy"),\n'
        '        "цена usd": _choose(allowed, "price_total", "price_buy"),\n'
    )
    new = (
        '        "цена": _choose(allowed, "price_uah"),\n'
        '        "ціна": _choose(allowed, "price_uah"),\n'
        '        "цена usd": _choose(allowed, "price_uah"),\n'
    )
    return _replace_once(block, old, new, "ai_fast:labeled-price-target")


def _patch_allowed(block: str) -> str:
    anchor = '    "condition_text": ("condition_text", "condition", "состояние",\n'
    addition = (
        '    "price_uah": ("price_uah", "sale_price", "selling_price", "цена", "цену",\n'
        '                  "стоимость", "ціна", "ціну", "вартість", "price"),\n'
    )
    return _replace_once(block, anchor, addition + anchor, "ai_filter:allowed-price")


def _patch_auto_catch(block: str) -> str:
    old_start = '''    cid = card["id"]
    number = card.get("auto_number") or "#%d" % cid

    # ── фото, видео, документы: только по кнопке ──
    # Что нельзя опознать наверняка, бот сам в карточку не кладёт.
    # Нажмите «Фото и видео» или «Тех. состояние» и пришлите файлы туда.
    if msg.photo or msg.video or msg.video_note or msg.document:
        return False

    # ── текст ──
    text = (msg.text or "").strip()
    if not text:
        return False
    if VIN_RE.search(text):
'''
    new_start = '''    cid = card["id"]
    number = card.get("auto_number") or "#%d" % cid

    # Text and a media caption share the same deterministic price parser.
    text = (msg.text or getattr(msg, "caption", None) or "").strip()
    if text:
        from price_parser import parse_sale_price_message
        price = parse_sale_price_message(text)
        price_intent = price.ok or price.reason not in (
            "NO_SALE_PRICE_INTENT", "EMPTY_INPUT")
        if price_intent:
            marker = "%s:%s" % (getattr(msg, "chat_id", ""), msg.message_id)
            seen = context.chat_data.get("crm_price_seen")
            if not isinstance(seen, list):
                seen = []
                context.chat_data["crm_price_seen"] = seen
            if marker in seen:
                return True
            seen.append(marker)
            del seen[:-50]
            if not price.ok:
                await msg.reply_text(
                    "Не разобрал цену продажи. Укажите одну сумму и одну валюту, "
                    "например: «цена авто 11 400 USD». Карточка не изменена.")
                return True
            ok, answer = apply_value(
                cid, "price_uah", text, actor_id,
                correction=price.is_explicit_change_intent,
                expected_auto_number=card.get("auto_number"))
            if ok:
                answer = "%s · цена: %s" % (
                    number, answer.replace("Записано: ", ""))
            else:
                answer = "%s · %s" % (number, answer)
            await msg.reply_text(
                answer,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Вернуться к карточке",
                                         callback_data="car_open:%d" % cid)]]))
            return True

    # Non-price media still follows the existing explicit media-button path.
    if msg.photo or msg.video or msg.video_note or msg.document:
        return False
    if not text:
        return False
    if VIN_RE.search(text):
'''
    block = _replace_once(block, old_start, new_start, "auto_catch:start")
    old_bare = r'''    golo = _re.fullmatch(r"[\d\s]{3,12}\s*[$₴]?", text)
    if golo:
        ok, answer = apply_value(cid, "price_uah", text, actor_id)
        if ok:
            await msg.reply_text(
                "%s · цена: %s" % (number, answer.replace("Записано: ", "")),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("← Вернуться к карточке",
                                         callback_data="car_open:%d" % cid)]]))
            return True

'''
    block = _replace_once(block, old_bare, "", "auto_catch:bare-number")
    block = _replace_once(
        block,
        '''            for field, value in (polya or {}).items():
                if field not in dict(EDITABLE) and field not in (
''',
        '''            for field, value in (polya or {}).items():
                if field == "price_uah":
                    continue  # sale price is accepted only by the shared parser above
                if field not in dict(EDITABLE) and field not in (
''',
        "auto_catch:assistant-price-skip",
    )
    block = _replace_once(
        block,
        '''    for rx, field in PHRASES:
        m = rx.search(text)
''',
        '''    for rx, field in PHRASES:
        if field == "price_uah":
            continue  # legacy narrow price regex is intentionally disabled
        m = rx.search(text)
''',
        "auto_catch:legacy-price-skip",
    )
    return block


def _patch_voice_undo(block: str) -> str:
    old = '''        db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)
        restored.append(LABELS_ALL.get(field, field))
'''
    new = '''        if field == "price_uah":
            from crm_price_atomic import write_price
            result = write_price(
                connect=db.connect,
                now=db.now,
                card_id=cid,
                expected_auto_number=card.get("auto_number"),
                expected_status=card.get("status"),
                expected_old=current,
                new_value=change.get("old"),
                actor_id=q.from_user.id,
                stage_key=S.stage_of(card.get("status")) or 1,
                correction=True,
                allow_clear=True,
            )
            if not result.ok:
                continue
        else:
            db.update_card_field("cars", cid, field, change.get("old"), q.from_user.id)
        restored.append(LABELS_ALL.get(field, field))
'''
    return _replace_once(block, old, new, "voice_undo:atomic-price")


def _patch_catch_message(block: str) -> str:
    block = _replace_once(
        block,
        '    input_text = (msg.text or "").strip()\n',
        '    input_text = (msg.text or getattr(msg, "caption", None) or "").strip()\n',
        "catch_message:caption",
    )
    block = _replace_once(
        block,
        '''        if marker in seen:
            await msg.reply_text("Это голосовое уже обработано.")
            raise ApplicationHandlerStop
''',
        '''        if marker in seen:
            # Telegram retry: the first handling already produced the response.
            raise ApplicationHandlerStop
''',
        "catch_message:voice-duplicate-silent",
    )
    old_card = '''        card = card_of(cid) if cid else None
        if card and voice_object:
'''
    new_card = '''        card = card_of(cid) if cid else None
        if not card and not voice_object and input_text:
            from price_parser import parse_sale_price_message
            price_probe = parse_sale_price_message(input_text)
            if price_probe.ok or price_probe.reason not in (
                    "NO_SALE_PRICE_INTENT", "EMPTY_INPUT"):
                await msg.reply_text(
                    "Откройте нужную карточку автомобиля и повторите цену. "
                    "Новая карточка автоматически не создаётся.")
                raise ApplicationHandlerStop
        if card and voice_object:
'''
    block = _replace_once(block, old_card, new_card, "catch_message:no-active-card")

    old_voice = '''            schema_allowed = set(fast.car_fields(ai_filter))
            card = card_of(card["id"]) or card
            correction = _v168_is_correction(input_text)
            if correction:
                allowed = _v168_named_fields(input_text, schema_allowed)
            else:
                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}
            data = {}
            if allowed:
                data.update(local_ocr.fields_from_text(input_text, allowed))
                data.update(fast.fast_text_data(input_text, ai_filter))
                if data:
                    data = fast.clean_car(fast.parsed_from_data(data), ai_filter, "")
                data = {key: value for key, value in (data or {}).items()
                        if key in allowed and value not in (None, "", [])}
                data.update(_v167_voice_explicit_fields(input_text, allowed))
            changes, skipped = voice_change_plan(card, data, allowed, correction)
'''
    new_voice = '''            from price_parser import parse_sale_price_message
            price = parse_sale_price_message(input_text)
            price_intent = price.ok or price.reason not in (
                "NO_SALE_PRICE_INTENT", "EMPTY_INPUT")
            if price_intent and not price.ok:
                await thinking.edit_text(
                    "Не разобрал цену продажи. Укажите одну сумму и одну валюту, "
                    "например: «цена авто 11 400 USD». Карточка не изменена.")
                raise ApplicationHandlerStop
            schema_allowed = set(fast.car_fields(ai_filter))
            card = card_of(card["id"]) or card
            correction = _v168_is_correction(input_text)
            if correction:
                allowed = _v168_named_fields(input_text, schema_allowed)
            else:
                allowed = {field for field in schema_allowed if _v168_empty(card.get(field))}
            if price.ok:
                allowed.add("price_uah")
            data = {}
            if allowed:
                data.update(local_ocr.fields_from_text(input_text, allowed))
                data.update(fast.fast_text_data(input_text, ai_filter))
                if data:
                    data = fast.clean_car(fast.parsed_from_data(data), ai_filter, "")
                data = {key: value for key, value in (data or {}).items()
                        if key in allowed and value not in (None, "", [])}
                data.update(_v167_voice_explicit_fields(input_text, allowed))
                if price.ok:
                    data["price_uah"] = price.value
            changes, skipped = voice_change_plan(card, data, allowed, correction)
'''
    block = _replace_once(block, old_voice, new_voice, "catch_message:voice-parse")
    block = _replace_once(
        block,
        '''                    ok, reason = _v168_cas_write(
                        card["id"], field, old, new, user_id, correction)
''',
        '''                    ok, reason = _v168_cas_write(
                        card["id"], field, old, new, user_id, correction,
                        expected_auto_number=card.get("auto_number"))
''',
        "catch_message:voice-cas-identity",
    )
    block = _replace_once(
        block,
        "            elif data and skipped and not override:\n",
        "            elif data and skipped and not correction:\n",
        "catch_message:undefined-override",
    )
    old_wait = '''        field = wait["field"]
        nizhny = input_text.lower()
        if field not in ("price_uah", "condition_text", "diag_text", "diag_link") \\
                and ("$" in nizhny or "цена" in nizhny or "стоимость" in nizhny):
            field = "price_uah"
        elif field == "eta_days" and _re.search(r"\\d{4,}", nizhny):
            field = "price_uah"
        ok, answer = apply_value(wait["card_id"], field, input_text, user_id)
        card = card_of(wait["card_id"])
        if ok and field == "price_uah" and card:
            remember_price(card, user_id)
            answer = "%s · цена этапа «%s»: %s" % (
'''
    new_wait = '''        original_field = wait["field"]
        field = original_field
        from price_parser import parse_sale_price_message
        in_price_wait = original_field == "price_uah"
        price = parse_sale_price_message(
            input_text, in_price_uah_wait=in_price_wait)
        price_intent = price.ok or price.reason not in (
            "NO_SALE_PRICE_INTENT", "EMPTY_INPUT")
        if original_field not in ("price_uah", "condition_text", "diag_text", "diag_link") \\
                and price_intent:
            field = "price_uah"
        before = card_of(wait["card_id"])
        if field == "price_uah":
            ok, answer = apply_value(
                wait["card_id"], field, input_text, user_id,
                correction=bool(in_price_wait or price.is_explicit_change_intent),
                in_price_uah_wait=in_price_wait,
                expected_auto_number=before.get("auto_number") if before else None)
        else:
            ok, answer = apply_value(wait["card_id"], field, input_text, user_id)
        card = card_of(wait["card_id"])
        if ok and field == "price_uah" and card:
            answer = "%s · цена этапа «%s»: %s" % (
'''
    block = _replace_once(block, old_wait, new_wait, "catch_message:wait-price")
    return block


def _transform_block(path: str, kind: str, name: str, block: str) -> str:
    if (path, kind, name) == ("local_ocr.py", "function", "fields_from_text"):
        return _patch_local_ocr(block)
    if (path, kind, name) == ("ai_fast_schema.py", "function", "labeled_text_data"):
        return _patch_labeled(block)
    if (path, kind, name) == ("ai_fast_schema.py", "function", "fast_text_data"):
        return FAST_TEXT_DATA
    if (path, kind, name) == ("ai_filter.py", "assignment", "ALLOWED"):
        return _patch_allowed(block)
    if (path, kind, name) == ("cars_ui.py", "function", "apply_value"):
        return APPLY_VALUE
    if (path, kind, name) == ("cars_ui.py", "function", "auto_catch"):
        return _patch_auto_catch(block)
    if (path, kind, name) == ("cars_ui.py", "function", "_v168_cas_write"):
        return V168_CAS_WRITE
    if (path, kind, name) == ("cars_ui.py", "function", "voice_undo"):
        return _patch_voice_undo(block)
    if (path, kind, name) == ("cars_ui.py", "function", "catch_message"):
        return _patch_catch_message(block)
    raise PatchRefused("NO_TRANSFORM:%s:%s" % (path, name))


def build_candidate(files: Dict[str, str]) -> tuple[Dict[str, str], dict]:
    """Return compiled candidate sources only after the complete Gate A match."""
    verify_live_sources(files)
    output = dict(files)
    changed = []
    for path, anchor in LIVE_MANIFEST.items():
        source = output[path]
        for block in anchor.blocks:
            if path == "db.py":
                continue
            node = _named_nodes(source, block.kind, block.name)[0]
            old = _node_source(source, node)
            new = _transform_block(path, block.kind, block.name, old)
            if old == new:
                raise PatchRefused("NO_CHANGE:%s:%s" % (path, block.name))
            source = _replace_block(source, block.kind, block.name, new)
            changed.append("%s:%s" % (path, block.name))
        output[path] = source
    for path, source in output.items():
        compile(source, path, "exec")
    report = {
        "status": "PASS_IN_MEMORY_CANDIDATE",
        "changed_blocks": changed,
        "input_sha256": {path: _sha(files[path]) for path in sorted(files)},
        "candidate_sha256": {path: _sha(output[path]) for path in sorted(output)},
        "production_write": False,
        "database_write": False,
        "process_restart": False,
    }
    return output, report


def transform_audited_block(path: str, kind: str, name: str, block: str, sha256: str) -> str:
    """Test helper: transform one evidence block only after its exact hash matches."""
    if _sha(block) != sha256:
        raise PatchRefused("BLOCK_HASH_MISMATCH:%s:%s" % (path, name))
    result = _transform_block(path, kind, name, block)
    compile(result, "%s:%s" % (path, name), "exec")
    return result
