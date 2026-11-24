"""VIN -> main CRM fields from similar auction cars, when no source knows this exact VIN (owner «да» 2026-11-17).

Similar cars: archived auction lots with the same VIN characters 1-8 (maker, line, body, engine) and the same
10th character (model year). A field is filled only when every similar lot agrees (engine 1999 and 2000 cc count as
one size); the fuel only from lots of the same group. At least two lots are needed. Session 29 measured 90% agreement
with the main answer (VIN-KOREA-PROBE-20261115). The archive is the one ua_vin_lots keeps; nothing is fetched.
"""
import json
import sqlite3
from pathlib import Path

MIN_LOTS = 2


def similar(vin, db):
    """Archived lots of the same VIN group (characters 1-8 and 10), the car itself excluded."""
    if len(vin) != 17 or not Path(db).exists():
        return []
    with sqlite3.connect('file:%s?mode=ro' % db, uri=True, timeout=10) as connection:
        rows = connection.execute('SELECT lot FROM lots WHERE substr(vin, 1, 8)=? AND substr(vin, 10, 1)=? AND vin<>?',
                                  (vin[:8], vin[9], vin)).fetchall()
    return [json.loads(row[0]) for row in rows]


def _size(cc):
    """Engine size class: 1999 and 2000 cc are the same engine."""
    return round(cc / 100) if isinstance(cc, int) and cc > 0 else None


def agreed(lots, raw_fields):
    """The CRM fields (codes, via ua_vin_lots.raw_fields) on which every lot agrees; {} with fewer than MIN_LOTS."""
    if len(lots) < MIN_LOTS:
        return {}
    each = [raw_fields(lot) for lot in lots]
    result = {}
    for key in ('model', 'year', 'fuel', 'gearbox'):
        values = {fields.get(key) for fields in each}
        if len(values) == 1 and None not in values:
            result[key] = values.pop()
    sizes = {_size(fields.get('engine_cc')) for fields in each}
    if len(sizes) == 1 and None not in sizes:
        result['engine_cc'] = max(fields['engine_cc'] for fields in each)
    return result
