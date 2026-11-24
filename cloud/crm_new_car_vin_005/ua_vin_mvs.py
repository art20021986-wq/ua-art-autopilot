"""VIN -> main CRM car fields from the Ukrainian MVS open register of vehicles (owner 2026-11-17: cars of all
countries, refreshed every month).

Source: data.gov.ua, Ministry of Internal Affairs open data with VIN — the yearly registers «Відомості про
транспортні засоби та їх власників» (VIN since 2021) and the current «Інформація про зареєстровані транспортні
засоби (включаючи VIN)». Every car registered in Ukraine is there, imported ones from the US, Europe, Korea, China
included. The server keeps its own index with the vehicle fields only (VIN, brand, model, year, colour, fuel,
engine size, body); owner data, addresses and plates are never stored. Only an exact VIN match is used. The index is
rebuilt in a separate low-priority process once it is older than 30 days; the bot only reads it.

Usage on the server: python3.10 ua_vin_mvs.py refresh
"""
import csv
import fcntl
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile

INDEX = Path('/home/Carix/ua_vin_mvs.sqlite3')
LOCK = Path('/home/Carix/.ua_vin_mvs.lock')
CKAN = 'https://data.gov.ua/api/3/action/package_show?id='
YEARLY = '06779371-308f-42d7-895e-5a39833375f0'  # «Відомості про транспортні засоби та їх власників»
CURRENT = '00a6c5c6-ff57-406c-a6e5-795acbaca5c3'  # «Інформація про зареєстровані ТЗ (включаючи VIN)»
FROM_YEAR = 2021  # the registers carry the VIN from 2021
MAX_AGE = 30 * 86400
TIMEOUT = 120
HEADERS = {'User-Agent': 'uaart-crm-vin/1'}  # data.gov.ua refuses the default urllib client name
KEEP = ('vin', 'brand', 'model', 'year', 'color', 'fuel', 'capacity', 'body')
# Register words -> codes of the CRM vocabulary (ai_filter); ambiguous ones («БЕНЗИН АБО ГАЗ») are left out.
FUEL = {'БЕНЗИН': 'gasoline', 'ДИЗЕЛЬНЕ ПАЛИВО': 'diesel', 'ЕЛЕКТРО': 'electric', 'ГАЗ': 'lpg',
        'ЕЛЕКТРО АБО БЕНЗИН': 'hybrid', 'ЕЛЕКТРО АБО ДИЗЕЛЬНЕ ПАЛИВО': 'hybrid'}
COLOR = {'БІЛИЙ': 'білий', 'ЧОРНИЙ': 'чорний', 'СІРИЙ': 'сірий', 'СИНІЙ': 'синій', 'ЧЕРВОНИЙ': 'червоний',
         'ЗЕЛЕНИЙ': 'зелений', 'КОРИЧНЕВИЙ': 'brown', 'БЕЖЕВИЙ': 'beige', 'СРІБЛЯСТИЙ': 'silver'}
# Column names of the two layouts (2021-2025 archives: upper case; current file: camelCase).
COLUMNS = {'VIN': 'vin', 'BRAND': 'brand', 'MODEL': 'model', 'MAKE_YEAR': 'year', 'MAKEYEAR': 'year',
           'COLOR': 'color', 'FUEL': 'fuel', 'CAPACITY': 'capacity', 'BODY': 'body'}


def lookup(vin, index=None):
    """The register row of exactly this VIN, or None (no index yet: None)."""
    target = index or INDEX
    if not Path(target).exists():
        return None
    with sqlite3.connect('file:%s?mode=ro' % target, uri=True, timeout=10) as connection:
        row = connection.execute('SELECT %s FROM cars WHERE vin=?' % ','.join(KEEP), (vin,)).fetchone()
    return dict(zip(KEEP, row)) if row else None


def raw_fields(row):
    """Register row -> CRM fields in the codes of the CRM vocabulary (not yet normalised)."""
    data = {}
    if row.get('model'):
        data['model'] = row['model']
    for key, target, low, high in (('year', 'year', 1950, 2100), ('capacity', 'engine_cc', 50, 9000)):
        try:
            value = int(float(row.get(key) or 0))
        except ValueError:
            value = 0
        if low <= value <= high:
            data[target] = value
    if row.get('fuel') in FUEL:
        data['fuel'] = FUEL[row['fuel']]
    if row.get('color') in COLOR:
        data['color'] = COLOR[row['color']]
    return data


def resources(opener=urllib.request.urlopen):
    """[(label, url)] in time order: yearly registers from FROM_YEAR, then the current register."""
    found = []
    for dataset in (YEARLY, CURRENT):
        with opener(urllib.request.Request(CKAN + dataset, headers=HEADERS), timeout=TIMEOUT) as response:
            items = json.load(response)['result']['resources']
        for item in items:
            name = str(item.get('name') or '')
            digits = ''.join(ch for ch in name if ch.isdigit())[:4]
            if dataset == CURRENT or (len(digits) == 4 and int(digits) >= FROM_YEAR):
                found.append((dataset == CURRENT, name, item.get('last_modified') or '', item['url']))
    return [(name, url) for _, name, _, url in sorted(found)]


def records(text_lines):
    """Rows of one register file (either layout) -> dicts with the KEEP fields; VIN of 17 characters only."""
    lines = iter(text_lines)
    head = next(lines, '')
    delimiter = ';' if head.count(';') > head.count(',') else ','
    names = [COLUMNS.get(name.strip().strip('"').upper()) for name in next(csv.reader([head], delimiter=delimiter))]
    for values in csv.reader(lines, delimiter=delimiter):
        row = {name: value.strip() for name, value in zip(names, values) if name}
        vin = row.get('vin', '').upper()
        if len(vin) == 17:
            row['vin'] = vin
            yield row


def _lines(path):
    """Text lines of a downloaded register: a zip with one CSV inside, or the CSV itself."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            member = next(info for info in archive.infolist() if info.filename.lower().endswith('.csv'))
            with archive.open(member) as raw:
                yield from io.TextIOWrapper(raw, encoding='utf-8-sig', errors='replace')
    else:
        with open(path, encoding='utf-8-sig', errors='replace') as handle:
            yield from handle


def build(target=None, opener=urllib.request.urlopen):
    """Rebuild the index from all registers into a new file, then replace the old one. -> VINs stored"""
    target = Path(target or INDEX)
    fresh = target.with_suffix('.new')
    fresh.unlink(missing_ok=True)
    with sqlite3.connect(fresh) as connection:
        connection.execute('PRAGMA journal_mode=OFF')
        connection.execute('PRAGMA synchronous=OFF')
        connection.execute('CREATE TABLE cars(%s, PRIMARY KEY(vin)) WITHOUT ROWID' % ','.join(KEEP))
        insert = 'INSERT OR REPLACE INTO cars VALUES(%s)' % ','.join('?' * len(KEEP))
        for _, url in resources(opener):
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.ua_vin_mvs-', delete=False) as part:
                with opener(urllib.request.Request(url, headers=HEADERS), timeout=TIMEOUT) as response:
                    while chunk := response.read(1 << 20):
                        part.write(chunk)
            try:
                batch = []
                for row in records(_lines(part.name)):  # later files win: the newest registration
                    batch.append(tuple(row.get(key) for key in KEEP))
                    if len(batch) >= 20000:
                        connection.executemany(insert, batch)
                        batch.clear()
                connection.executemany(insert, batch)
                connection.commit()
            finally:
                os.unlink(part.name)
        stored = connection.execute('SELECT COUNT(*) FROM cars').fetchone()[0]
    if not stored:
        fresh.unlink(missing_ok=True)
        raise ValueError('EMPTY_REGISTER')
    os.replace(fresh, target)
    return stored


def stale(index=None, now=None):
    target = Path(index or INDEX)
    return not target.exists() or (now or time.time()) - target.stat().st_mtime > MAX_AGE


def refresh():
    """One rebuild at a time (lock file); nothing when the index is fresh."""
    with open(LOCK, 'a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'BUSY'
        if not stale():
            return 'FRESH'
        return 'STORED %d' % build()


JOB = 'vin-mvs-refresh'


async def _refresh_job(context):
    """Start the rebuild in its own low-priority process when the index is stale; the bot does not wait."""
    import logging
    import subprocess
    try:
        if stale():
            subprocess.Popen(['nice', '-n', '19', 'python3.10', str(Path(__file__).resolve()), 'refresh'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        logging.getLogger(__name__).exception('vin mvs refresh not started')


def schedule(app):
    """Check the index once a day in the bot's job queue (first check ten minutes after start)."""
    if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(_refresh_job, interval=86400, first=600, name=JOB)


if __name__ == '__main__' and sys.argv[1:] == ['refresh']:
    print(refresh())
