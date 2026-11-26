"""konteyner.py: the backup «Где машина?» menu marks the choice of the car's country (JAPAN-STOCK-001).

Its buttons come from ua_delivery_status.CHOICES (now with «В Японии» and «Паром Япония») and save through the
common stage handler, as before.
"""
from edits import replace_once

NAME = 'konteyner.py'
PAIRS = (
    ('''    from ua_delivery_status import CHOICES, public_status
    q = update.callback_query
''', '''    from ua_delivery_status import CHOICES, choice_code
    import ua_car_country
    q = update.callback_query
'''),
    ('''    rows = []
    try:
        for nomer_etapa, _nazv in S.STAGES:
''', '''    rows = []
    try:
        country = ua_car_country.country_of(cid)
        for nomer_etapa, _nazv in S.STAGES:
'''),
    ('''                ("• " if public_status(card.get("status")) == code else "") + label,
''', '''                ("• " if choice_code(card.get("status"), country) == code else "") + label,
'''),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
