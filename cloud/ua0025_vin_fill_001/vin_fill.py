"""UA-0025: fill only the empty main fields from the VIN (owner «да» 2026-11-13).

The values come from the installed ua_vin_decode (NHTSA vPIC, clean decode only, CRM vocabulary) — the same module
that fills a new card. A field that already has a value is never touched.
"""
CARD = 'UA-0025'
VIN = 'WDDZF4KB1KA596783'
FIELDS = ('model', 'year', 'engine_cc', 'fuel', 'gearbox', 'drive')


def empty(value):
    return value is None or (isinstance(value, str) and not value.strip()) or value == 0


def changes_for(row, decoded):
    """[{id, auto_number, published, field, before, after}] for the empty fields the decode fills."""
    if row.get('auto_number') != CARD or str(row.get('vin') or '').upper() != VIN:
        raise ValueError('CARD_IDENTITY')
    return [{'id': row['id'], 'auto_number': CARD, 'published': row.get('published'), 'field': field,
             'before': row.get(field), 'after': decoded[field]}
            for field in FIELDS if field in decoded and field in row and empty(row.get(field))]
