"""cars_ui.py: «Доставка и этапы» with Japan (JAPAN-STOCK-001, owner «Да» 2026-11-26).

- the menu marks the choice of the car's country («• В Японии», «• Паром Япония») and shows its label;
- a press on «В Корее» / «В Японии» / «Паром Корея» / «Паром Япония» also saves the country (ua_car_country);
  «В Грузии» / «В Киеве» keep it;
- the card and the car lists show the stage label of the car's country.
The menu rows come from ua_delivery_status.CHOICES (one row per stage, two buttons in a row), as before.
"""
from edits import replace_once

NAME = 'cars_ui.py'
HELPER = '''

def _ua_jp_label(card):
    """JAPAN-STOCK-001: the stage label of the car's country («В Японии», «Паром Корея», ...)."""
    status = card.get("status")
    try:
        import ua_car_country
        from ua_delivery_status import choice_label
        return choice_label(status, ua_car_country.country_of(card["id"])) or S.status_label(status)
    except Exception:
        log.exception("JAPAN-STOCK-001: страна машины не прочитана, card=%s", card.get("id"))
        return S.status_label(status)
'''
PAIRS = (
    # helper next to card_of()
    ('''        if not card.get(new) and card.get(old):
            card[new] = card[old]
    return card
''', '''        if not card.get(new) and card.get(old):
            card[new] = card[old]
    return card
''' + HELPER),
    # stage_menu
    ('''    from ua_delivery_status import CHOICES, public_status
    import asyncio as _v168_asyncio
''', '''    from ua_delivery_status import CHOICES, choice_code
    import asyncio as _v168_asyncio
'''),
    ('''        stage = S.stage_of(card.get("status"))
        lines = ["🚚 Доставка и этапы", card.get("auto_number") or "#%d" % cid, "",
                 "Сейчас: %s" % S.status_label(card.get("status")),
                 ("Этап %d из 4: %s" % (stage, dict(S.STAGES).get(stage, "—")) if stage else "Скрыт из каталога")]
''', '''        import ua_car_country
        country = ua_car_country.country_of(cid)
        stage = S.stage_of(card.get("status"))
        lines = ["🚚 Доставка и этапы", card.get("auto_number") or "#%d" % cid, "",
                 "Сейчас: %s" % _ua_jp_label(card),
                 ("Этап %d из 4: %s" % (stage, _ua_jp_label(card)) if stage else "Скрыт из каталога")]
'''),
    ('''                ("• " if public_status(card.get("status")) == code else "") + label,
''', '''                ("• " if choice_code(card.get("status"), country) == code else "") + label,
'''),
    # stage_set: the country of the pressed choice is saved before the stage
    ('''    set_field(cid, "status", code, q.from_user.id)

    if code == "ge_waiting" and not card_before.get("ge_arrived"):
''', '''    from ua_delivery_status import CHOICE_COUNTRY
    if code != "hidden" and requested in CHOICE_COUNTRY:
        import ua_car_country
        ua_car_country.set_country(cid, CHOICE_COUNTRY[requested], q.from_user.id)
    set_field(cid, "status", code, q.from_user.id)

    if code == "ge_waiting" and not card_before.get("ge_arrived"):
'''),
    ('''        "Этап сохранён: %s" % S.status_label(saved),
''', '''        "Этап сохранён: %s" % _ua_jp_label(card),
'''),
    # card text and lists
    ('''    if card.get("status"):
        L.append("Статус: %s" % S.status_label(card.get("status")))
''', '''    if card.get("status"):
        L.append("Статус: %s" % _ua_jp_label(card))
'''),
    ('''    else:
        L.append("Статус: %s" % S.status_label(card.get("status")))
''', '''    else:
        L.append("Статус: %s" % _ua_jp_label(card))
'''),
    ('''        etap = S.status_label(card.get("status")) if card.get("status") else "этап не задан"
''', '''        etap = _ua_jp_label(card) if card.get("status") else "этап не задан"
'''),
    ('''        etap = S.status_label(c.get("status")) if c.get("status") else "этап не задан"
''', '''        etap = _ua_jp_label(c) if c.get("status") else "этап не задан"
'''),
    ('''                card.get("auto_number") or "", S.status_label(card.get("status")),
''', '''                card.get("auto_number") or "", _ua_jp_label(card),
'''),
    ('''            stage = S.status_label(card.get('status')) if card.get('status') else 'этап не задан'
''', '''            stage = _ua_jp_label(card) if card.get('status') else 'этап не задан'
'''),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
