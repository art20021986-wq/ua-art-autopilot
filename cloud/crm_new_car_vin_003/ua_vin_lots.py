"""VIN -> main CRM car fields from the Korean auction lots the server already collects (VIN-KOREA-001, owner 2026-11-15).

Korean domestic VINs (no check digit) are not decoded by NHTSA vPIC. The korea_auction job writes the week's lots,
each with its VIN and specs, to video/korea/lots.json on the same server. Only an exact VIN match is used: it is the
same car, not a similar one. Values are reduced to the codes of the CRM vocabulary; unknown ones are left out.
"""
import json
from pathlib import Path

LOTS = Path('/home/Carix/video/korea/lots.json')
FUEL = {'gasoline', 'diesel', 'hybrid', 'electric', 'lpg'}
GEARBOX = {'AT': 'at', 'MT': 'mt', 'CVT': 'cvt'}


def lot_of(vin, path=None):
    """The lot with exactly this VIN, or None."""
    with open(path or LOTS, encoding='utf-8') as handle:
        lots = json.load(handle).get('lots') or []
    return next((lot for lot in lots if str(lot.get('vin') or '').upper() == vin), None)


def raw_fields(lot):
    """Lot -> CRM fields in the codes of the CRM vocabulary (not yet normalised)."""
    data = {}
    maker, title = str(lot.get('maker') or ''), str(lot.get('title') or '')
    model = title[len(maker):].strip() if maker and title.startswith(maker) else ''
    if model:
        data['model'] = model
    for key, low, high in (('year', 1980, 2100), ('engine_cc', 500, 9000), ('mileage_km', 1, 2000000)):
        value = lot.get(key)
        if isinstance(value, int) and low <= value <= high:
            data[key] = value
    if lot.get('fuel') in FUEL:
        data['fuel'] = lot['fuel']
    if lot.get('transmission') in GEARBOX:
        data['gearbox'] = GEARBOX[lot['transmission']]
    return data
