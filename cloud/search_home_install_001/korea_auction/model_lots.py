"""This week's auction lots for the order page model carousels (KOREA-MODEL-LOTS-001, owner 2026-11-12).

Country-neutral: select() takes the auction lots, the country's model rules and the copied photos and returns
{"models": {model key: [lot, ...]}} for /video/<country>/model-lots.json, which the order page reads
(video/order/order.js). Korea is the first country (KOREA); another country's job passes its own rules.
Per model: up to PER_MODEL lots of the card's generation that have not started yet and have a copied photo,
best grade first (AA, then AB/BA, then BB, ...), then lower mileage, then newer year; lots with a start price
before lots without one. Pure function: no network, no account data.
"""
import re

PER_MODEL = 6
GRADES = 'ABCDEF'
# Korea order models (video/podbor.html?strana=korea): maker, model word and the generation's full years. The auction
# writes no generation (its «Model Code» column is empty, LOT-PROBE-20261112-R3) and a plain model name, so the
# generation is told by the year: only the years when the card's generation alone was sold in Korea (a change-over
# year sold both): K5 DL3 from Dec 2019, Sonata DN8 from Mar 2019, Tucson NX4 from Sep 2020, Sportage NQ5 from Jul
# 2021, Santa Fe TM Feb 2018 – Aug 2023.
KOREA = {
    'kia-k5': {'maker': 'KIA', 'word': 'K5', 'years': (2020, None)},
    'hyundai-sonata': {'maker': 'HYUNDAI', 'word': 'SONATA', 'years': (2020, None)},
    'hyundai-tucson': {'maker': 'HYUNDAI', 'word': 'TUCSON', 'years': (2021, None)},
    'kia-sportage': {'maker': 'KIA', 'word': 'SPORTAGE', 'years': (2022, None)},
    'hyundai-santa-fe': {'maker': 'HYUNDAI', 'word': 'SANTA FE', 'years': (2019, 2022)},
}


def grade_rank(score):
    """Owner's order: 'AA' 0, 'AB'/'BA' 1, 'BB' 2 ... (sum of the two letters, A best). A letter and a number ('A2',
    the other houses' form) comes after the letter pairs of the same first letter ('A2' 1.5: after AB, before BB);
    no grade comes last."""
    score = (score or '').strip().upper()
    if len(score) == 2 and score[0] in GRADES:
        if score[1] in GRADES:
            return GRADES.index(score[0]) + GRADES.index(score[1])
        if score[1].isdigit():
            return GRADES.index(score[0]) * 2 + 1.5
    return 99


def matches(lot, rule):
    """The lot is the card's model and generation: maker, model word and the generation's years."""
    year_from, year_to = rule['years']
    return (lot['maker'].upper().startswith(rule['maker'])
            and re.search(r'(?<![A-Z0-9])%s(?![A-Z0-9])' % re.escape(rule['word']), lot['model'].upper()) is not None
            and lot['year'] >= year_from and (year_to is None or lot['year'] <= year_to))


def view(lot, photos, page):
    day = lot['auction_start'][:10].split('/')
    return {'id': lot['id'], 'href': '%s#lot-%s' % (page, lot['id']), 'photo': photos[0],
            'date': '%s.%s' % (day[2], day[1]), 'start': lot['auction_start'], 'score': lot['score'],
            'year': lot['year'], 'km': lot['mileage_km'], 'usd': lot.get('start_usd', 0)}


def select(lots, rules, photos, now, page):
    """{'models': {key: [lot view, ...]}}: `lots` carry 'start_usd' (0 if unknown); `photos` are the site
    addresses of each lot's copied photos; `now` is 'YYYY/MM/DD HH:MM' in the auction's time."""
    chosen = {}
    for key, rule in rules.items():
        found = [lot for lot in lots if photos.get(lot['id']) and lot['auction_start'] > now and matches(lot, rule)]
        found.sort(key=lambda l: (not l.get('start_usd'), grade_rank(l['score']), l['mileage_km'], -l['year']))
        if found:
            chosen[key] = [view(lot, photos[lot['id']], page) for lot in found[:PER_MODEL]]
    return {'models': chosen}
