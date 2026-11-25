"""Read-only probe on the server for PAGES-LAG-001 (owner's CRM bot, 2026-11-25 08:53 UTC: «CRM: страницы сайта отстали
от базы, и пересобрать их не получилось.»).

Reads only:
- the sanitized full source of the self-check (samokontrol.py) and of the modules that decide «pages behind» and rebuild
  them (ua_public_freshness.py, ua_crm_public_sync.py), and every server line that starts or imports the self-check;
- the self-check's state and log files and the CRM public sync state (sanitized; log lines of 24–25.11 and errors only);
- per CRM car: status, published flag, change-time columns, and the modification time of its published pages;
- the publication request ledger (counts by status) and the database file time.
Nothing is written outside this run's own receipt.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
MAX_SOURCE = 900 * 1024
FULL_SOURCES = ('samokontrol.py', 'ua_public_freshness.py', 'ua_crm_public_sync.py')
SKIP_DIRS = {'backups', 'autopilot_inbox', 'node_modules', 'video', 'site', '__pycache__'}
STATE_NAME = re.compile(r'(?i)samokontrol|sborka|soobsh|alert|public_sync|freshness|publish|\.log$')
LOG_LINE = re.compile(r'2026-11-2[45]|samokontrol|sborka|sobrat|отстал|stranic|Traceback|Error|Exception|FAIL|timed? ?out',
                      re.I)
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|api_hash|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|api\.telegram\.org)(?:[/\'"\s]|$)')
DATE_IN_NUMBER = re.compile(r'\s*20\d\d-\d\d-\d\d(?:[ T]\d\d)?\s*')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    line = EMAIL.sub('[EMAIL]', line)
    return LONG_NUMBER.sub(lambda m: m.group(0) if DATE_IN_NUMBER.fullmatch(m.group(0)) else '[N]', line)


def stamp(seconds):
    return datetime.datetime.fromtimestamp(seconds, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def text_of(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
        return None
    return path.read_bytes().decode('utf-8', 'replace')


def full_sources():
    found = {}
    for name in FULL_SOURCES:
        text = text_of(HOME / name)
        found[name] = None if text is None else {
            'sha256': hashlib.sha256(text.encode()).hexdigest()[:16], 'mtime': stamp((HOME / name).stat().st_mtime),
            'source': '\n'.join(sanitized_line(x) for x in text.splitlines())}
    return found


def callers():
    found = {}
    for path in sorted(list(HOME.glob('*.py')) + list(HOME.glob('*/*.py'))):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS for part in relative.parts[:-1]) or relative.name in FULL_SOURCES:
            continue
        text = text_of(path)
        if text is None or 'samokontrol' not in text:
            continue
        found[str(relative)] = [{'line': n + 1, 'text': sanitized_line(line)[:220]}
                                for n, line in enumerate(text.splitlines()) if 'samokontrol' in line][:20]
    return found


def tail_lines(path, limit=400 * 1024):
    size = path.stat().st_size
    with path.open('rb') as handle:
        handle.seek(max(0, size - limit))
        data = handle.read().decode('utf-8', 'replace')
    return data.splitlines()


def state_files():
    found = {}
    candidates = [p for p in HOME.iterdir() if p.is_file() and not p.is_symlink() and STATE_NAME.search(p.name)
                  and not p.name.endswith('.py')]
    for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[:40]:
        info = path.stat()
        item = {'bytes': info.st_size, 'mtime': stamp(info.st_mtime)}
        if path.suffix == '.json' and info.st_size <= 64 * 1024:
            item['content'] = [sanitized_line(x)[:300] for x in path.read_text('utf-8', 'replace').splitlines()][:200]
        elif path.suffix in ('.log', '.txt', '.jsonl') or path.name.endswith('.log'):
            lines = [sanitized_line(x)[:300] for x in tail_lines(path) if LOG_LINE.search(x)]
            item['matching_lines'] = lines[-150:]
        found[path.name] = item
    return found


def columns(connection, table):
    return [row[1] for row in connection.execute('PRAGMA table_info(%s)' % table)]


def crm_and_pages():
    database = HOME / 'crm.db'
    result = {'crm_db_mtime': stamp(database.stat().st_mtime)}
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
        names = columns(connection, 'cars')
        times = [n for n in names if re.search(r'updat|izmen|chang|modif|edited|_at$|sync|publish', n, re.I)]
        keep = ['id', 'auto_number', 'status', 'published'] + times
        keep = [n for n in keep if n in names]
        rows = connection.execute('SELECT %s FROM cars ORDER BY id' % ', '.join(keep)).fetchall()
        result['time_columns'] = times
        cars = []
        for row in rows:
            item = dict(zip(keep, row))
            code = str(item.get('auto_number') or '')
            pages = {}
            for folder in ('video', 'video/ru', 'video/ua', 'site'):
                page = HOME / folder / (code + '.html')
                if page.is_file():
                    pages[folder] = stamp(page.stat().st_mtime)
            item['pages'] = pages
            cars.append({k: (str(v)[:40] if v is not None else None) if k != 'pages' else v for k, v in item.items()})
        result['cars'] = cars
    ledger = HOME / '.crm_publish_requests' / 'requests.sqlite3'
    if ledger.is_file():
        with sqlite3.connect(ledger.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
            tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            counts = {}
            for table in tables:
                names = columns(connection, table)
                if 'status' in names:
                    counts[table] = dict(connection.execute('SELECT status, COUNT(*) FROM %s GROUP BY status' % table)
                                         .fetchall())
                    recent = [n for n in names if re.search(r'updat|creat|_at$', n)]
                    if recent:
                        counts[table + ':latest'] = [[str(x)[:60] for x in r] for r in connection.execute(
                            'SELECT status, %s FROM %s ORDER BY rowid DESC LIMIT 12' % (', '.join(recent[:2]), table))]
                else:
                    counts[table] = connection.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]
            result['publish_ledger'] = {'mtime': stamp(ledger.stat().st_mtime), 'tables': counts}
    return result


def report():
    value = {'status': 'PASS', 'now': stamp(datetime.datetime.now(datetime.timezone.utc).timestamp())}
    for key, call in (('full_sources', full_sources), ('callers', callers), ('state_files', state_files),
                      ('crm_and_pages', crm_and_pages)):
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
