"""Candidate price helpers derived from the historical TASK088 helper.

Not installed and not live-accepted. Integration awaits current handler review.
Host bindings required: db.connect/db.now, price_history, jdump, S.stage_of/S.num.
No database connection or live source import occurs when this module is loaded.
Historical candidate history/audit intent is retained; live parity is unverified.
There is no installer in this package.
One cleanup fix clears the closed connection before opening fresh read-back.
"""

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
    except Exception:
        # A broken optional parser must not escape the Telegram callback or
        # proceed to the DB. Keep exception details out of the user response.
        return False, "%s не записана: не удалось проверить ввод. Повторите позже." % label
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
        conn = None
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
