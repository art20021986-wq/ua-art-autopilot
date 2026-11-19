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
SOURCES = ('cars_ui.py', 'crm_online_guard.py', 'cars_schema.py')
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


def report(now=None):
    now = int(time.time()) if now is None else now
    value = {'status': 'PASS', 'now': now}
    for key, call in (('media_log', lambda: journal(HOME / 'media_log.txt', now)),
                      ('bot_log', lambda: journal(BOT_LOG, now, LOG_TOPIC)),
                      ('spool', lambda: grouped(HOME / '.crm_media_spool.jsonl', 'accepted_at', now)),
                      ('ledger', lambda: grouped(HOME / '.crm_media_receipts.jsonl', 'saved_at', now)),
                      ('crm', crm), ('published', published), ('sources', sources)):
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
