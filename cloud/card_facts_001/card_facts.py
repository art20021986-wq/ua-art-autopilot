"""Two owner-approved card facts (2026-11-17, SEO-AUDIT-20261116 answers 1 and 2).

UA-0021 Sonata: the manual arrival date has passed — clear it, so the card stops promising a past date.
UA-0023 Kia K5: the owner's year is 2021 — the description text that says «K5 2022» is brought to «K5 2021».
Cards are identified by VIN; every other field and row stays as it is.
"""
import datetime

SONATA_VIN = 'KMHL341DBNA241966'
K5_VIN = 'KNAG541BBNA169806'
ETA_FIELD = 'eta_manual'
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
