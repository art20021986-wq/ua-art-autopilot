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


def _key(value):
    return re.sub(r'[^a-z0-9]', '', (value or '').lower())


def popular(make, model):
    """The make's model word, spelled any way IAAI writes it («MODEL 3», «MODEL-3», «Model3»); a word of up to 2
    characters («3», «es») matches only exactly, a longer one also a longer name («RAV4 HYBRID», «X5 M»)."""
    words = POPULAR.get((make or '').strip().lower())
    name, raw = _key(model), (model or '').strip().lower()
    return bool(words) and any(name == _key(w) or (len(_key(w)) > 2 and name.startswith(_key(w)))
                               or raw.startswith(w + ' ') for w in words)


def candidate(lot):
    """USA-LOTS-FIX-002 (live 27.11: the listing does not show the start code): what the listing can tell —
    popular model, from MIN_YEAR, a minimal primary damage, nothing ruinous anywhere."""
    damage = ' '.join((lot.get('damage', ''), lot.get('secondary_damage', ''), lot.get('title_type', '')))
    return (popular(lot.get('make'), lot.get('model')) and lot.get('year', 0) >= MIN_YEAR
            and any(w in lot.get('damage', '').lower() for w in MINIMAL_DAMAGE) and not NEVER.search(damage))


def keep(lot):
    """A candidate that also runs and drives (the lot page's start code)."""
    return candidate(lot) and bool(lot.get('runs'))


def choose(lots, size=SIZE, rule=keep):
    """The lots `rule` keeps, at most `size`, at most 3 of one model (variety). USA-LOTS-FIX-006 (owner 28.11: the whole
    week, not only the nearest sale): one lot of each model in turn (soonest auction first within a model), so the
    choice does not lean on the lot numbers (the listing has no auction date)."""
    per_model = {}
    for lot in sorted((l for l in lots if rule(l)), key=lambda l: (l.get('auction_start') or '9', l['id'])):
        per_model.setdefault((lot['make'].lower(), lot['model'].lower()), []).append(lot)
    queues = [found[:3] for found in per_model.values()]
    out = []
    for turn in range(3):
        out += [found[turn] for found in queues if len(found) > turn]
    return out[:size]


def spread(lots, size=SIZE):
    """USA-LOTS-FIX-006: the shown lots spread over the auction days: one of each day in turn (soonest day first, soonest
    lot first), up to `size` — no day has more than one lot over another day that still has lots."""
    days = {}
    for lot in sorted(lots, key=lambda l: (l.get('auction_start') or '9', l['id'])):
        days.setdefault((lot.get('auction_start') or '')[:10], []).append(lot)
    queues = [days[day] for day in sorted(days)]
    out = []
    for turn in range(max(map(len, queues), default=0)):
        out += [found[turn] for found in queues if len(found) > turn]
    return out[:size]
