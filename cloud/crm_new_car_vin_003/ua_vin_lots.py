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


# Archive of past lots (owner 2026-11-15, «да»): lots.json holds one week; a car bought earlier must still be found.
ARCHIVE = Path('/home/Carix/ua_vin_lots_archive.sqlite3')
KEEP = ('vin', 'title', 'maker', 'year', 'engine_cc', 'mileage_km', 'fuel', 'transmission')
JOB = 'vin-lots-archive'
EVERY = 6 * 3600


def archive(path=None, db=None):
    """Copy the vehicle fields of the current lots into the archive (newest values win). -> lots stored"""
    import sqlite3
    with open(path or LOTS, encoding='utf-8') as handle:
        lots = [lot for lot in json.load(handle).get('lots') or [] if lot.get('vin')]
    rows = [(str(lot['vin']).upper(), json.dumps({k: lot.get(k) for k in KEEP}, ensure_ascii=False)) for lot in lots]
    with sqlite3.connect(db or ARCHIVE, timeout=10) as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS lots(vin TEXT PRIMARY KEY, lot TEXT NOT NULL, '
                           'seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
        connection.executemany('INSERT INTO lots(vin, lot) VALUES(?, ?) ON CONFLICT(vin) DO UPDATE SET '
                               'lot=excluded.lot, seen_at=CURRENT_TIMESTAMP', rows)
    return len(rows)


def archived(vin, db=None):
    """The archived lot with exactly this VIN, or None (no archive yet: None)."""
    import sqlite3
    target = db or ARCHIVE
    if not Path(target).exists():
        return None
    with sqlite3.connect('file:%s?mode=ro' % target, uri=True, timeout=10) as connection:
        row = connection.execute('SELECT lot FROM lots WHERE vin=?', (vin,)).fetchone()
    return json.loads(row[0]) if row else None


def find(vin):
    """This week's lot, else the archived one."""
    lot = None
    try:
        lot = lot_of(vin)
    except (OSError, ValueError):
        pass
    return lot or archived(vin)


async def _archive_job(context):
    import asyncio
    import logging
    try:
        await asyncio.to_thread(archive)
    except Exception:
        logging.getLogger(__name__).exception('vin lots archive failed')


def schedule(app):
    """Archive the lots every 6 hours in the bot's own job queue (first run a minute after start)."""
    if app.job_queue is not None and not app.job_queue.get_jobs_by_name(JOB):
        app.job_queue.run_repeating(_archive_job, interval=EVERY, first=60, name=JOB)
