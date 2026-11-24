"""VIN -> main CRM car fields (NEW-CAR-VIN-SPEC, owner 2026-11-13; Korean auction lots: VIN-KOREA-001, 2026-11-15;
similar cars: owner «да» 2026-11-17).

Sources, in this order: the Korean auction lot with exactly this VIN (ua_vin_lots: the same car, Korean domestic
VINs included), then NHTSA vPIC, the free official decoder of the US Department of Transportation
(https://vpic.nhtsa.dot.gov/api/, DecodeVinValues, no key), for the fields still missing, and — only when no lot has
this exact VIN — the fields every similar archived lot agrees on (ua_vin_pattern). From vPIC only a clean
decode (ErrorCode 0) is used: for VINs vPIC does not know it may return a wrong model year. Values are reduced to the
codes of the CRM vocabulary (ai_filter: gasoline, automatic, awd, ...) and normalised by the installed ai_fast_schema,
so the CRM keeps one vocabulary. Unknown values are left out. The brand is not taken from here: the installed
vin_brand names it. A source that fails is skipped; with none the card is created as before.
"""
import json
import re
import urllib.parse
import urllib.request

URL = 'https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/%s?format=json'
TIMEOUT = 8.0
FUEL = {'gasoline': 'gasoline', 'diesel': 'diesel', 'electric': 'electric',
        'liquefied petroleum gas': 'lpg'}
GEARBOX = (('continuously variable', 'cvt'), ('dual-clutch', 'dct'), ('automated manual', 'dct'),
           ('automatic', 'automatic'), ('manual', 'manual'))
DRIVE = (('awd', 'awd'), ('4wd', 'awd'), ('4x4', 'awd'), ('fwd', 'fwd'), ('rwd', 'rwd'))


def _text(row, key):
    value = str(row.get(key) or '').strip()
    return '' if value.lower() in ('', 'not applicable', 'null') else value


def _first(table, value):
    value = value.lower()
    return next((code for word, code in table if value.startswith(word)), None)


def raw_fields(row):
    """vPIC result row -> CRM fields in the codes of the CRM vocabulary (not yet normalised)."""
    if any(part.strip() != '0' for part in _text(row, 'ErrorCode').split(',')):
        return {}
    data = {}
    if _text(row, 'Model'):
        data['model'] = _text(row, 'Model')
    if re.fullmatch(r'(19[89]|20\d)\d', _text(row, 'ModelYear')):
        data['year'] = int(_text(row, 'ModelYear'))
    try:
        cc = float(_text(row, 'DisplacementCC') or 0) or float(_text(row, 'DisplacementL') or 0) * 1000
    except ValueError:
        cc = 0
    if 500 <= cc <= 9000:
        data['engine_cc'] = int(round(cc))
    level = _text(row, 'ElectrificationLevel').lower()
    fuel = FUEL.get(_text(row, 'FuelTypePrimary').lower())
    if 'hev' in level or (fuel in ('gasoline', 'diesel') and _text(row, 'FuelTypeSecondary').lower() == 'electric'):
        fuel = 'hybrid'
    if fuel:
        data['fuel'] = fuel
    gearbox = _first(GEARBOX, _text(row, 'TransmissionStyle'))
    if gearbox:
        data['gearbox'] = gearbox
    drive = _first(DRIVE, _text(row, 'DriveType'))
    if drive:
        data['drive'] = drive
    return data


def fetch(vin, opener=urllib.request.urlopen):
    """The vPIC result row of a VIN."""
    with opener(URL % urllib.parse.quote(vin, safe=''), timeout=TIMEOUT) as response:
        rows = json.loads(response.read().decode('utf-8')).get('Results') or [{}]
    return rows[0]


def lot_fields(vin):
    """Fields of the auction lot with this VIN (this week or the archive); {} when there is none."""
    import ua_vin_lots
    try:
        lot = ua_vin_lots.find(vin)
    except (OSError, ValueError):
        return {}
    return ua_vin_lots.raw_fields(lot) if lot else {}


def vpic_fields(vin, opener):
    """Fields of a clean vPIC decode; {} when vPIC does not answer or does not know the VIN."""
    try:
        return raw_fields(fetch(vin, opener))
    except (OSError, ValueError):
        return {}


def pattern_fields(vin):
    """Fields every similar archived lot agrees on; {} when the archive cannot be read."""
    import sqlite3
    import ua_vin_lots
    import ua_vin_pattern
    try:
        return ua_vin_pattern.agreed(ua_vin_pattern.similar(vin, ua_vin_lots.ARCHIVE), ua_vin_lots.raw_fields)
    except (OSError, ValueError, sqlite3.Error):
        return {}


def fields(vin, opener=urllib.request.urlopen):
    """Main CRM fields from the VIN, normalised to the CRM vocabulary; {} when nothing reliable."""
    import ai_fast_schema as fast
    import ai_filter
    raw = lot_fields(vin)
    exact = bool(raw)
    raw.update({key: value for key, value in vpic_fields(vin, opener).items() if key not in raw})
    if not exact:
        raw.update({key: value for key, value in pattern_fields(vin).items() if key not in raw})
    if not raw:
        return {}
    clean = fast.clean_car(fast.parsed_from_data(dict(raw, vin=vin)), ai_filter, '')
    return {key: value for key, value in clean.items() if key in raw}
