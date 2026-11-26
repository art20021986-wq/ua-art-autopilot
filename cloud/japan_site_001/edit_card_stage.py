"""stranica.py and master_card.py: the card page in the car's country (JAPAN-STOCK-001 step 2).

Both build the «Путь автомобиля» block (stranica on the full rebuild, master_card on publication) with the same code;
the same three edits go into each: the country of the car, the visible name of step 1, the «ТЕКУЩИЙ ЭТАП» line.
stranica also gets the card chips: «Автомобиль из Кореи/Японии» and the stage chip in the car's country.
Korean cards keep every existing text; data-ua-stage-label stays «Корея» for the publication check.
"""
from edits import replace_once

ANCHOR = (
    ('''    details = list(_UA_STAGE_DETAILS)
''', '''    details = list(_UA_STAGE_DETAILS)
    import ua_country_site as _ua_cs  # JAPAN-STOCK-001
    _ua_country = _ua_cs.country(m)
'''),
    ('''            state, number, state[3:], current, icon, label, label,
''', '''            state, number, state[3:], current, icon, label, _ua_cs.stage_name(label, _ua_country),
'''),
    ('''% (("🇰🇷", "🚢", "📋", "📍")[stage - 1], details[stage - 1]))
''', '''% _ua_cs.current_stage(stage, details[stage - 1], _ua_country))
'''),
)
CHIPS = (
    ('''    c.append("<div class='chip'>%s</div>" % ekran(etap_tekst))
''', '''    import ua_country_site as _ua_cs  # JAPAN-STOCK-001
    c.append(_ua_cs.country_chip(m))
    c.append(_ua_cs.stage_chip(m, etap_tekst))
'''),
)
PAIRS = {'stranica.py': ANCHOR + CHIPS, 'master_card.py': ANCHOR}


def build(name, source):
    text = replace_once(source.decode('utf-8'), PAIRS[name], name)
    compile(text, name, 'exec')
    return text.encode('utf-8')
