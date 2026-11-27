"""Which IAAI lots the site shows (owner 2026-11-27): models popular in Ukraine, runs and drives, minimal damage.

Pure functions of a parsed lot (lot_page.parse): no network. One responsibility: the choice.
"""
import re

# Models most bought from the USA for Ukraine (make: model words as IAAI writes them, lower case)
POPULAR = {
    'tesla': ('model 3', 'model y', 'model s', 'model x'),
    'toyota': ('camry', 'rav4', 'corolla', 'highlander', 'prius'),
    'volkswagen': ('tiguan', 'jetta', 'passat', 'atlas', 'golf', 'id.4'),
    'ford': ('escape', 'fusion', 'edge', 'explorer', 'mustang mach-e'),
    'nissan': ('rogue', 'leaf', 'sentra', 'altima', 'murano'),
    'hyundai': ('tucson', 'sonata', 'santa fe', 'elantra', 'ioniq'),
    'kia': ('sportage', 'k5', 'optima', 'sorento', 'niro', 'soul'),
    'chevrolet': ('malibu', 'bolt', 'equinox', 'volt'),
    'jeep': ('compass', 'cherokee', 'grand cherokee', 'renegade', 'wrangler'),
    'audi': ('q5', 'q7', 'a4', 'a6', 'q3', 'e-tron'),
    'bmw': ('x5', 'x3', '330', '530', 'i3', 'x1'),
    'mercedes-benz': ('glc', 'gle', 'c 300', 'e 350', 'gla'),
    'honda': ('cr-v', 'accord', 'civic', 'hr-v'),
    'mazda': ('cx-5', 'cx-30', 'mazda3', '3'),
    'subaru': ('forester', 'outback', 'crosstrek'),
    'lexus': ('rx', 'nx', 'es'),
    'porsche': ('macan', 'cayenne'),
    'volvo': ('xc60', 'xc90'),
}
MINIMAL_DAMAGE = ('minor dent', 'scratch', 'normal wear', 'hail')  # IAAI «Primary Damage» words
NEVER = re.compile(r'(?i)water|flood|fire|burn|biohazard|rollover|undercarriage|frame|all over|stripped|junk|parts only')
MIN_YEAR = 2015
SIZE = 30  # as the Japan ticker cards: the countries in equal numbers (owner 2026-11-27)


def popular(make, model):
    words = POPULAR.get((make or '').strip().lower())
    name = (model or '').strip().lower()
    return bool(words) and any(name == w or name.startswith(w + ' ') for w in words)


def keep(lot):
    """Popular model, from MIN_YEAR, runs and drives, a minimal primary damage, nothing ruinous anywhere, photos."""
    damage = ' '.join((lot.get('damage', ''), lot.get('secondary_damage', ''), lot.get('title_type', '')))
    return (popular(lot.get('make'), lot.get('model')) and lot.get('year', 0) >= MIN_YEAR and lot.get('runs')
            and any(w in lot.get('damage', '').lower() for w in MINIMAL_DAMAGE) and not NEVER.search(damage)
            and bool(lot.get('photos')))


def choose(lots, size=SIZE):
    """The kept lots, soonest auction first, at most `size`, at most 3 of one model (variety)."""
    out, per_model = [], {}
    for lot in sorted((l for l in lots if keep(l)), key=lambda l: (l.get('auction_start') or '9', l['id'])):
        key = (lot['make'].lower(), lot['model'].lower())
        if per_model.get(key, 0) >= 3:
            continue
        per_model[key] = per_model.get(key, 0) + 1
        out.append(lot)
        if len(out) == size:
            break
    return out
