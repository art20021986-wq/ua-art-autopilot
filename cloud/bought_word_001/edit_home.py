"""video/index.html: the «выкуплено» tile title without «проверенные» (BOUGHT-WORD-001, owner 2026-11-26).

The page is a static file; the counters change only each tile's <em> count, so the new title stays.
"""
from edits import replace_once

NAME = 'video/index.html'
PAIRS = (
    ('<b data-ru="Выкуплены и проверены в Корее и Японии" data-uk="Викуплені та перевірені в Кореї та Японії" '
     'data-ka="კორეასა და იაპონიაში შეძენილი და შემოწმებული">Викуплені та перевірені в Кореї та Японії</b>',
     '<b data-ru="Выкуплены в Корее и Японии" data-uk="Викуплені в Кореї та Японії" '
     'data-ka="კორეასა და იაპონიაში შეძენილი">Викуплені в Кореї та Японії</b>'),
)


def build(source):
    return replace_once(source.decode('utf-8'), PAIRS, NAME).encode('utf-8')
