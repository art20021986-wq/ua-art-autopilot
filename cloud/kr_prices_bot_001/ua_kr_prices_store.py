"""Korea logistics prices per month for the home page «5 кроків» (ORDER-PROCESS-001, owner 2026-11-11).

One public JSON file the home page reads (cloud/home_steps_001/kr_prices.py):
    {"version": 1, "months": {"2026-11": {"fob": 600, "container": 4800, "port": 250, "truck": 1100,
                                         "broker": 150, "cert": 150}, ...}}
The site shows the latest month not after the current one, so the coming months can be entered in advance. Prices are
whole US dollars; the container price is per container, one car carries container / CARS_PER_CONTAINER.
No Telegram here: only reading, checking and writing the file (atomically, readable by the web server).
"""
import datetime
import json
import os
from pathlib import Path
import re
import tempfile

PATH = Path(__file__).resolve().parent / 'video' / 'korea' / 'logistics.json'
KEYS = ('fob', 'container', 'port', 'truck', 'broker', 'cert')
LABELS = {'fob': 'FOB', 'container': 'Контейнер', 'port': 'Порт Грузия', 'truck': 'Автовоз Грузия — Киев',
          'broker': 'Брокер', 'cert': 'Сертификация'}
# What the page shows while the file has no month yet (the same numbers as written in the page).
DEFAULTS = {'fob': 600, 'container': 4800, 'port': 250, 'truck': 1100, 'broker': 150, 'cert': 150}
CARS_PER_CONTAINER = 4
LIMIT = 100000
MONTH = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


class PriceError(ValueError):
    pass


def per_car(prices):
    return prices['container'] // CARS_PER_CONTAINER


def total(prices):
    return sum(prices[k] for k in KEYS if k != 'container') + per_car(prices)


def parse(text):
    """Six whole numbers in KEYS order, separated by spaces, commas or new lines."""
    parts = [p for p in re.split(r'[\s,;]+', text.strip()) if p]
    if len(parts) != len(KEYS) or not all(re.fullmatch(r'\d{1,6}', p) for p in parts):
        raise PriceError('format')
    values = dict(zip(KEYS, (int(p) for p in parts)))
    if any(v > LIMIT for v in values.values()):
        raise PriceError('limit')
    return values


def months_ahead(today, count=3):
    """'YYYY-MM' of this month and the next ones."""
    year, month = today.year, today.month
    result = []
    for _ in range(count):
        result.append('%04d-%02d' % (year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return result


def live_month(months, today):
    """The month the site shows today, or None (the page's own numbers)."""
    current = '%04d-%02d' % (today.year, today.month)
    past = [m for m in months if m <= current]
    return max(past) if past else None


def load(path=PATH):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}
    months = data.get('months') if isinstance(data, dict) and data.get('version') == 1 else None
    if not isinstance(months, dict):
        raise PriceError('file')
    return {m: p for m, p in months.items()
            if MONTH.match(m) and isinstance(p, dict) and all(isinstance(p.get(k), int) for k in KEYS)}


def save_month(month, prices, path=PATH):
    if not MONTH.match(month) or set(prices) != set(KEYS):
        raise PriceError('month')
    months = load(path)
    months[month] = {k: prices[k] for k in KEYS}
    payload = json.dumps({'version': 1, 'months': dict(sorted(months.items()))}, ensure_ascii=False,
                         sort_keys=True, indent=1).encode('utf-8')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix='.logistics-')
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o644)  # a public file: the web server reads it
        os.replace(name, path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return months


def today_kyiv():
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo('Europe/Kyiv')).date()
