"""Catalog status of stage 1 without «проверен» (BOUGHT-WORD-001): «В Корее · выкуплен» / «У Кореї · викуплений»,
for a Japanese car «В Японии · выкуплен» / «У Японії · викуплений»."""
from edits import replace_once

GUARD = ('catalog_design_guard.py', (
    ('''    1: ("В Корее · выкуплен и проверен", "У Кореї · викуплений і перевірений"),
''', '''    1: ("В Корее · выкуплен", "У Кореї · викуплений"),
'''),))
COUNTRY = ('ua_country_site.py', (
    ("""CATALOG_JAPAN_LABEL = ('В Японии · выкуплен и проверен', 'У Японії · викуплений і перевірений')""",
     """CATALOG_JAPAN_LABEL = ('В Японии · выкуплен', 'У Японії · викуплений')"""),))
EDITS = (GUARD, COUNTRY)


def build(name, source):
    pairs = dict(EDITS)[name]
    text = replace_once(source.decode('utf-8'), pairs, name)
    compile(text, name, 'exec')
    return text.encode('utf-8')
