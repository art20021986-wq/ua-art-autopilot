"""Read-only probe on the server for PHOTO-ADD-001 (owner 2026-11-19: «I cannot add more photos» to the galleries).

Reads only:
- the bot photo journal (media_log.txt) and the CRM bot log lines about photos of the last 7 days (sanitized,
  Telegram file ids masked);
- the photo intake queue (.crm_media_spool.jsonl) and the photo receipt ledger (.crm_media_receipts.jsonl) as counts
  per card and section, with ages (no file ids);
- per car in crm.db (opened read-only): id, number, status, how many photos each section holds, and the media table
  counts per section and status (no texts, no client data);
- how many photo files each published card folder (video/foto/<number>) holds;
- the sanitized source of the photo intake modules (cars_ui.py, crm_online_guard.py, cars_schema.py).
R2 (the first run: UA-0011 got 22 photos saved at 02:08-02:19 UTC, the card shows 0 and changed at 02:33): for the
focus card only, its change history (field names, times, actor ids masked, value lengths only), the rows of every
crm.db table that reference it from the last 3 days (column names, times, value lengths only), the photo backup
folders (.otkat_media) and the published photo folder times; and the sanitized db.py source.
R3 (owner: it started when a video was sent into «Добавить фото» by accident): per card, the Telegram file kind of every
item in its photo lists (first 4 characters of the file id only: AgAC photo, BAAC video, BQAC document, DQAC video
note, CgAC animation), and for the focus card every media table row of any date (kind, mime, file extension, times).
Nothing is written outside this run's own receipt.
"""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import time

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
BOT_LOG = Path('/var/log/alwayson-log-266084.log')
TAIL = 4 * 1024 * 1024
DAYS = 7
MAX_LINES = 1500
SOURCES = ('cars_ui.py', 'crm_online_guard.py', 'cars_schema.py', 'db.py')
FOCUS = 'UA-0011'
FOCUS_DAYS = 3
CAR_REFERENCE = ('car_id', 'card_id', 'record_id', 'cid', 'auto_number', 'entity_id', 'row_id')
MAX_SOURCE = 900 * 1024
SECTIONS = ('photos', 'condition_photos', 'videos', 'condition_videos')
LOG_TOPIC = re.compile(r'(?i)photo|фото|media|spool|предел|limit|album|альбом|traceback|error|exception')
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
FILE_ID = re.compile(r'\b[A-Za-z0-9_-]{20,}\b')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')
CARD_NUMBER = re.compile(r'UA-[0-9]{4,}')


def sanitized_line(line, ids=True):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    if ids:
        line = FILE_ID.sub('[ID]', line)
    return LONG_NUMBER.sub('[N]', line)


def tail_lines(path):
    if not path.is_file():
        return None
    with path.open('rb') as handle:
        handle.seek(max(0, path.stat().st_size - TAIL))
        return handle.read().decode('utf-8', 'replace').splitlines()


def recent_marks(now):
    days = [time.gmtime(now - 86400 * n) for n in range(DAYS + 1)]
    return {mark for day in days for mark in (time.strftime('%Y-%m-%d', day), time.strftime('%b %d', day),
                                              time.strftime('%b ', day) + str(day.tm_mday).rjust(2))}


def journal(path, now, topic=None):
    lines = tail_lines(path)
    if lines is None:
        return None
    marks = recent_marks(now)
    picked = [sanitized_line(x)[:300] for x in lines
              if any(m in x for m in marks) and (topic is None or topic.search(x))]
    refusals = Counter(re.sub(r'\d+', 'N', x.split('  ', 1)[-1])[:120] for x in picked
                       if 'ОТКАЗ' in x or 'предел' in x.casefold() or 'Error' in x or 'Traceback' in x)
    return {'bytes': path.stat().st_size, 'mtime': round(path.stat().st_mtime), 'recent_lines': len(picked),
            'refusal_kinds': refusals.most_common(40), 'lines': picked[-MAX_LINES:]}


def jsonl(path):
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except FileNotFoundError:
        return None, 0
    rows, bad = [], 0
    for line in lines:
        try:
            row = json.loads(line)
            rows.append(row if isinstance(row, dict) else {})
        except Exception:
            bad += 1
    return rows, bad


def grouped(path, stamp, now):
    rows, bad = jsonl(path)
    if rows is None:
        return None
    groups = defaultdict(list)
    for row in rows:
        groups['%s:%s' % (row.get('card_id'), row.get('target'))].append(int(row.get(stamp) or 0))
    return {'rows': len(rows), 'invalid_lines': bad, 'bytes': path.stat().st_size,
            'per_card_section': {key: {'count': len(ages), 'oldest_age_s': now - min(ages), 'newest_age_s': now - max(ages)}
                                 for key, ages in sorted(groups.items())}}


def count_of(value):
    try:
        items = json.loads(value or '[]')
    except Exception:
        return 'invalid'
    return len(items) if isinstance(items, list) else 'not_list'


def crm():
    database = HOME / 'crm.db'
    if not database.is_file():
        return None
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        columns = [row[1] for row in connection.execute('PRAGMA table_info(cars)')]
        cars = []
        for row in connection.execute('SELECT * FROM cars'):
            item = {key: row[key] for key in ('id', 'auto_number', 'status', 'published', 'updated_at') if key in columns}
            item.update({key: count_of(row[key]) for key in SECTIONS if key in columns})
            cars.append(item)
        media = None
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='media'").fetchone():
            media = [dict(row) for row in connection.execute(
                'SELECT car_id, vid, status, COUNT(*) AS n, MAX(kogda) AS last FROM media GROUP BY car_id, vid, status')]
    return {'cars_columns': columns, 'cars': cars, 'media': media}


def published():
    base = HOME / 'video' / 'foto'
    if not base.is_dir():
        return None
    return {path.name: len(list(path.glob('*.jpg'))) for path in sorted(base.iterdir())
            if path.is_dir() and CARD_NUMBER.fullmatch(path.name)}


def sources():
    found = {}
    for name in SOURCES:
        path = HOME / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
            found[name] = None
            continue
        text = path.read_bytes().decode('utf-8', 'replace')
        found[name] = {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'mtime': round(path.stat().st_mtime),
                       'source': '\n'.join(sanitized_line(x, ids=False) for x in text.splitlines())}
    return found


def shape(value):
    """Value kind and length only: never the text itself (no client data)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value if abs(value) < 10 ** 6 else '[N]'
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return {'list': len(parsed)}
        if isinstance(parsed, dict):
            return {'dict_keys': sorted(parsed)[:20]}
    except Exception:
        pass
    return {'text_len': len(text)}


def is_time(column):
    name = str(column).casefold()
    return name in ('at', 'ts', 'dt', 'when', 'kogda') or name.endswith('_at') or any(
        word in name for word in ('time', 'date', 'kogda'))


def focus_history(entries):
    if not isinstance(entries, list):
        return shape(entries)
    result = []
    for entry in entries[-120:]:
        if isinstance(entry, dict):
            result.append({key: (entry[key] if is_time(key) or key in ('field', 'pole', 'action', 'kind', 'role')
                                 else shape(entry[key])) for key in entry})
        else:
            result.append(shape(entry))
    return result


def focus(now):
    database = HOME / 'crm.db'
    since = time.strftime('%Y-%m-%d', time.gmtime(now - 86400 * FOCUS_DAYS))
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        car = connection.execute('SELECT * FROM cars WHERE auto_number=?', (FOCUS,)).fetchone()
        if car is None:
            return None
        car = dict(car)
        history = None
        try:
            history = focus_history(json.loads(car.get('history') or '[]'))
        except Exception:
            history = shape(car.get('history'))
        tables = {}
        for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            columns = [row[1] for row in connection.execute('PRAGMA table_info("%s")' % name.replace('"', ''))]
            refs = [c for c in columns if c in CAR_REFERENCE]
            times = [c for c in columns if is_time(c)]
            if not refs or name == 'cars':
                continue
            where = ' OR '.join('"%s" IN (?, ?)' % c for c in refs)
            rows = connection.execute('SELECT * FROM "%s" WHERE (%s) %s LIMIT 400' % (
                name, where, ('AND (' + ' OR '.join('(typeof("%s")=\'text\' AND "%s" >= ?) OR (typeof("%s") IN (\'integer\', \'real\') AND "%s" >= ?)'
                                          % (c, c, c, c) for c in times) + ')') if times else ''),
                [v for _ in refs for v in (car['id'], FOCUS)] + [v for _ in times for v in (since, now - 86400 * FOCUS_DAYS)]
            ).fetchall()
            tables[name] = {'columns': columns, 'rows': [
                {k: (row[k] if is_time(k) or k in refs or k in ('field', 'pole', 'vid', 'status', 'action', 'kind')
                     else shape(row[k])) for k in columns} for row in rows]}
    backups = HOME / '.otkat_media'
    folder = HOME / 'video' / 'foto' / FOCUS
    return {'card': {k: (car[k] if is_time(k) or k in ('id', 'auto_number', 'status', 'published') else shape(car[k]))
                     for k in car if k != 'history'},
            'history': history, 'tables': tables,
            'backups': [{'name': p.name, 'files': len(list(p.iterdir())), 'mtime': round(p.stat().st_mtime)}
                        for p in sorted(backups.glob(FOCUS + '_*'))] if backups.is_dir() else None,
            'published_folder': {'exists': folder.is_dir(), 'mtime': round(folder.stat().st_mtime) if folder.is_dir() else None,
                                 'files': sorted(p.name for p in folder.iterdir())[:200] if folder.is_dir() else None}}


def kinds():
    """Per card and photo section: how many items of each Telegram file kind (file id prefix only)."""
    database = HOME / 'crm.db'
    result = {}
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        for row in connection.execute('SELECT id, auto_number, photos, condition_photos FROM cars'):
            for section in ('photos', 'condition_photos'):
                try:
                    items = json.loads(row[section] or '[]')
                except Exception:
                    continue
                ids = [str(i.get('file_id') if isinstance(i, dict) else i) for i in items if i]
                if ids:
                    result['%s:%s' % (row['auto_number'], section)] = dict(Counter(i[:4] for i in ids))
        media = []
        car = connection.execute('SELECT id FROM cars WHERE auto_number=?', (FOCUS,)).fetchone()
        if car is not None:
            for row in connection.execute('SELECT * FROM media WHERE car_id=? ORDER BY id', (car['id'],)):
                row = dict(row)
                media.append({'vid': row.get('vid'), 'status': row.get('status'), 'kind': str(row.get('file_id') or '')[:4],
                              'mime': row.get('mime'), 'ext': Path(str(row.get('put') or '')).suffix[:8],
                              'kogda': row.get('kogda'), 'poryadok': row.get('poryadok')})
    return {'photo_kinds': result, 'focus_media': media}


def report(now=None):
    now = int(time.time()) if now is None else now
    value = {'status': 'PASS', 'now': now}
    for key, call in (('media_log', lambda: journal(HOME / 'media_log.txt', now)),
                      ('bot_log', lambda: journal(BOT_LOG, now, LOG_TOPIC)),
                      ('spool', lambda: grouped(HOME / '.crm_media_spool.jsonl', 'accepted_at', now)),
                      ('ledger', lambda: grouped(HOME / '.crm_media_receipts.jsonl', 'saved_at', now)),
                      ('crm', crm), ('published', published), ('sources', sources),
                      ('focus', lambda: focus(now)), ('kinds', kinds)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
