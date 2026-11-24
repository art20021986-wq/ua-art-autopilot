"""Two owner-approved card facts (2026-11-17, SEO-AUDIT-20261116 answers 1 and 2).

UA-0021 Sonata: the manual arrival date has passed — clear it, so the card stops promising a past date.
UA-0023 Kia K5: the owner's year is 2021 — the description text that says «K5 2022» is brought to «K5 2021».
Cards are identified by VIN; every other field and row stays as it is.
The card language versions (ru/, ua/) are built only when every phrase has Ukrainian in the site script's
dictionary, so the K5 description entry there gets the same «K5 2022» → «K5 2021» (key and Ukrainian).
"""
import datetime
import json

SONATA_VIN = 'KMHL341DBNA241966'
K5_VIN = 'KNAG541BBNA169806'
ETA_FIELD = 'eta_manual'
SCRIPT = 'video/ua-site-languages.js'
DICTIONARIES = 'var dictionaries = '
OLD, NEW = 'K5 2022', 'K5 2021'
IDENTITY = ('id', 'auto_number', 'vin')
# Reported for review, not changed: what decides the Sonata arrival line once the manual date is gone.
SONATA_CONTEXT = ('status', 'eta_manual', 'sea_date_out', 'sea_container', 'ge_released', 'ge_to_kyiv_at')


def parse_date(value):
    text = str(value or '').strip()
    for form, size in (('%Y-%m-%d', 10), ('%d.%m.%Y', 10)):
        try:
            return datetime.datetime.strptime(text[:size], form).date()
        except ValueError:
            continue
    return None


def card(rows, vin):
    found = [row for row in rows if str(row.get('vin') or '').strip().upper() == vin]
    if len(found) != 1:
        raise ValueError('CARD_IDENTITY:%s:%d' % (vin, len(found)))
    return found[0]


def change(row, field, after):
    return {'id': row['id'], 'auto_number': row.get('auto_number'), 'vin': row['vin'], 'field': field,
            'before': row[field], 'after': after}


def sonata_changes(row, today):
    eta = parse_date(row.get(ETA_FIELD))
    return [change(row, ETA_FIELD, None)] if eta is not None and eta < today else []


def k5_changes(row):
    return [change(row, field, value.replace(OLD, NEW)) for field, value in sorted(row.items())
            if field not in IDENTITY and isinstance(value, str) and OLD in value]


def allowed(item):
    """The only edits this package may write: the Sonata date cleared, or «K5 2022» → «K5 2021» in K5 text."""
    if item['vin'] == SONATA_VIN:
        return item['field'] == ETA_FIELD and item['after'] is None and parse_date(item['before']) is not None
    if item['vin'] == K5_VIN:
        before = item['before']
        return (item['field'] not in IDENTITY and isinstance(before, str) and OLD in before
                and item['after'] == before.replace(OLD, NEW))
    return False


def plan_for(rows, today):
    sonata, k5 = card(rows, SONATA_VIN), card(rows, K5_VIN)
    changes = sonata_changes(sonata, today) + k5_changes(k5)
    return {'changes': changes,
            'sonata_context': {k: sonata.get(k) for k in SONATA_CONTEXT if k in sonata},
            # every other place «2022» still appears in the K5 row (reviewed by hand, never written)
            'k5_other_2022': sorted(f for f, v in k5.items()
                                    if f not in IDENTITY and '2022' in str(v) and OLD not in str(v)),
            'k5_year': k5.get('year')}


def uk_dictionary(script):
    start = script.index(DICTIONARIES) + len(DICTIONARIES)
    return json.JSONDecoder().raw_decode(script[start:])[0]['uk']


def script_edit(script):
    """The site script with «K5 2022» → «K5 2021» in the Ukrainian dictionary entry of the K5 description.

    Every «K5 2022» in the script must be inside that entry (its Russian key and Ukrainian value); nothing else
    changes. Already edited → the script as it is.
    """
    words = uk_dictionary(script)
    entries = {k: v for k, v in words.items() if OLD in k}
    if not entries:
        if any(NEW in k for k in words):
            return script
        raise ValueError('SCRIPT_ENTRY_MISSING')
    expected = sum(json.dumps(k, ensure_ascii=False).count(OLD) + json.dumps(v, ensure_ascii=False).count(OLD)
                   for k, v in entries.items())
    if script.count(OLD) != expected:
        raise ValueError('SCRIPT_OLD_OUTSIDE_ENTRY:%d:%d' % (script.count(OLD), expected))
    edited = script.replace(OLD, NEW)
    after = uk_dictionary(edited)
    wanted = {k: v for k, v in words.items() if k not in entries}
    wanted.update({k.replace(OLD, NEW): v.replace(OLD, NEW) for k, v in entries.items()})
    if after != wanted:
        raise ValueError('SCRIPT_DICTIONARY_DRIFT')
    return edited
