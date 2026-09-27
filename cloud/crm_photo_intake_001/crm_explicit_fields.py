"""Extract only explicitly labelled CRM facts; no database or network access."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

LABELS = {
    'vin': ('vin', 'chassis no', 'chassis number', 'вин', 'номер кузова'),
    'brand': ('brand', 'make', 'марка', 'бренд'),
    'model': ('model', 'модель'),
    'year': ('year', 'model year', 'year of manufacture', 'год', 'год выпуска', 'рік', 'рік випуску'),
    'mileage_km': ('mileage', 'odometer', 'пробег', 'пробіг'),
    'engine_cc': ('engine capacity', 'engine displacement', 'engine cc', 'объём двигателя', 'объем двигателя', 'двигатель', 'обʼєм двигуна', 'двигун'),
    'color': ('color', 'colour', 'цвет', 'колір'),
    'gearbox': ('transmission', 'gearbox', 'коробка передач', 'коробка', 'кпп'),
    'fuel': ('fuel type', 'fuel', 'топливо', 'паливо'),
    'drive': ('drive', 'drivetrain', 'привод'),
    'condition_text': ('condition', 'состояние', 'техсостояние', 'стан'),
}
# These labels terminate a previous row, but have no destination in this form.
IGNORED = ('registration date', 'дата регистрации', 'дата реєстрації',
           'auction venue', 'auction date', 'auction score', 'lot', 'lot no',
           'price', 'цена', 'ціна', 'дата аукциона', 'аукцион', 'лот')
ALIASES = {label: field for field, labels in LABELS.items() for label in labels}
ALIASES.update({label: None for label in IGNORED})
ROW = re.compile(r'^(' + '|'.join(re.escape(x) for x in sorted(ALIASES, key=len, reverse=True))
                 + r')(?:\.(?=\s|$))?(?:(?:\s*[:=]\s*|\s+)(.*)|$)', re.I)
VIN = re.compile(r'[A-HJ-NPR-Z0-9]{17}')
INTEGER = re.compile(r'(?:\d{1,7}|\d{1,3}(?:([ ,.])\d{3})(?:\1\d{3})*)')


def normalize_vin(value):
    value = re.sub(r'[\s-]', '', str(value or '').upper())
    return value if VIN.fullmatch(value) else None


def integer(value):
    value = value.strip()
    return int(re.sub(r'[ ,.]+', '', value)) if INTEGER.fullmatch(value) else None


def normalize(field, raw, dictionaries=None):
    value = unicodedata.normalize('NFKC', str(raw)).strip()
    if not value or value in {'-', '—', '?'}:
        return None
    if field == 'vin':
        return normalize_vin(value)
    if field == 'year':
        return int(value) if re.fullmatch(r'\d{4}', value) and 1980 <= int(value) <= date.today().year + 1 else None
    if field == 'mileage_km':
        match = re.fullmatch(r'([\d ,.]+)\s*(?:(km|км)|(?:тыс\.?|тис\.?|k)\s*(?:km|км)?)?', value, re.I)
        if not match:
            return None
        number = integer(match.group(1))
        if number is not None and re.search(r'тыс|тис|k(?!m)', value, re.I):
            number *= 1000
        return number if number is not None and 0 <= number <= 2_000_000 else None
    if field == 'engine_cc':
        match = re.fullmatch(r'([\d ,.]+)\s*(cc|cm3|cm³|см3|см³|куб\.?|л|l)?', value, re.I)
        if not match:
            return None
        number, unit = match.groups()
        try:
            result = Decimal(number.replace(',', '.').strip()) * 1000 if unit and unit.lower() in {'л', 'l'} else integer(number)
        except InvalidOperation:
            return None
        return int(result) if result is not None and result == int(result) and 500 <= result <= 8000 else None
    if field in {'fuel', 'gearbox', 'drive', 'color'}:
        mapping = (dictionaries or {}).get(field, {})
        canonical = {str(k).casefold(): v for k, v in mapping.items()}
        canonical.update({str(v).casefold(): v for v in mapping.values()})
        return canonical.get(value.casefold())
    if field in {'brand', 'model', 'condition_text'}:
        return value if len(value) <= (1000 if field == 'condition_text' else 80) and not re.search(r'[\x00-\x1f]', value) else None
    return None


def parse(text, allowed, dictionaries=None):
    """Return (facts, conflicting/invalid fields, matched labels).

    A label can be followed by its value on the next non-empty line. Conflicting
    duplicate rows are omitted, rather than selecting whichever OCR pass wins.
    """
    data, rejected, seen = {}, set(), set()
    pending = None
    for raw_line in unicodedata.normalize('NFKC', str(text or '')).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = ROW.fullmatch(line)
        if match:
            label, value = match.groups()
            field = ALIASES[label.casefold()]
            seen.add(label.casefold())
            pending = field
            if not value:
                continue
        elif pending:
            field, value, pending = pending, line, None
        elif normalize_vin(line):
            field, value = 'vin', line
            seen.add('vin')
        else:
            pending = None
            continue
        pending = None
        if field not in allowed:
            continue
        normalized = normalize(field, value, dictionaries)
        if normalized is None or (field in data and data[field] != normalized):
            data.pop(field, None)
            rejected.add(field)
        elif field not in rejected:
            data[field] = normalized
    return data, rejected, seen
