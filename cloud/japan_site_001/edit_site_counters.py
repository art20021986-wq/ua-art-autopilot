"""ua_site_counters.py: the stage-1 catalog filter button is «Выкуплены · N» / «Викуплені · N» (JAPAN-STOCK-001 step 2).

The server catalog patch and its browser counter use the same labels; only the stage-1 label changes.
"""
from edits import replace_once

NAME = 'ua_site_counters.py'
PAIRS = (
    ("""              'korea':('В Корее','У Кореї')}
""", """              'korea':('Выкуплены','Викуплені')}
"""),
    ("""korea:[\\'В Корее\\',\\'У Кореї\\']};""", """korea:[\\'Выкуплены\\',\\'Викуплені\\']};"""),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
