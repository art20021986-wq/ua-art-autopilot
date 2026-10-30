"""Japan rare-car card label in the order catalogue (CATALOG-LABEL, owner 2026-10-30).

Owner: the card is «Раритетное авто», without years (it shows left-hand-drive cars of 2000–2003 since
MODEL-GALLERY-CLASSICS). In the server catalogue (order settings catalog_path, read by CATALOG-LABEL-PROBE-20261030)
only the card's name, labels and photo alt texts change; its key, the catalogue version (open forms and bot drafts
stay valid) and every other entry stay as they are. Each original fragment must occur exactly once and an applied
fragment is refused.
"""
import json

CATALOG = 'order_requests/country_models.json'
KEY = 'classics-1980-1990'
LABELS = {'uk': 'Раритетне авто', 'ru': 'Раритетное авто', 'ka': 'რარიტეტული ავტომობილები'}
ALT = {'uk': 'Раритетне авто з лівим кермом', 'ru': 'Раритетное авто с левым рулём',
       'ka': 'რარიტეტული ავტომობილი მარცხენა საჭით'}
EDITS = (
    ('"name": "Раритетні авто 1980-1990-х років"', '"name": "%s"' % LABELS['uk']),
    ('"uk": "Раритетні авто 1980-1990-х років"', '"uk": "%s"' % LABELS['uk']),
    ('"ru": "Раритетные авто 1980–1990-х годов"', '"ru": "%s"' % LABELS['ru']),
    ('"ka": "1980–1990-იანი წლების კლასიკური ავტომობილები"', '"ka": "%s"' % LABELS['ka']),
    ('"uk": "Приклад категорії: Mercedes-Benz 230E, 1988"', '"uk": "%s"' % ALT['uk']),
    ('"ru": "Пример категории: Mercedes-Benz 230E, 1988"', '"ru": "%s"' % ALT['ru']),
    ('"ka": "კატეგორიის მაგალითი: Mercedes-Benz 230E, 1988"', '"ka": "%s"' % ALT['ka']),
)


def card(value):
    return next(m for m in value['countries']['japan']['models'] if m['key'] == KEY)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('CATALOG_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    before, after = json.loads(source), json.loads(text)
    expected = card(before)
    expected = {**expected, 'name': LABELS['uk'], 'labels': LABELS, 'media': {**expected['media'], 'alt': ALT}}
    if card(after) != expected:
        raise ValueError('CATALOG_CARD_SHAPE')
    card(after).clear()
    card(before).clear()
    if after != before:
        raise ValueError('CATALOG_OTHER_CHANGES')
    return text.encode('utf-8')
