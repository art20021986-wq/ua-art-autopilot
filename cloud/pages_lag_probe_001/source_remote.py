"""Read-only probe on the server for PAGES-LAG-001 (owner's CRM bot, 2026-11-25 08:53 UTC: «CRM: страницы сайта отстали
от базы, и пересобрать их не получилось.»).

Reads only:
- the sanitized full source of the self-check (samokontrol.py) and of the modules that decide «pages behind» and rebuild
  them (ua_public_freshness.py, ua_crm_public_sync.py), and every server line that starts or imports the self-check;
- the self-check's state and log files and the CRM public sync state (sanitized; log lines of 24–25.11 and errors only);
- per CRM car: status, published flag, change-time columns, and the modification time of its published pages;
- the publication request ledger (counts by status) and the database file time.
R2 (coordinator 2026-11-25: the bot restarted about 40 times 06:06–08:09 UTC): who restarts it — the sanitized source of
the start files and the restart lines of the bot modules, the bot/guard log files and the hosting's always-on task log
(lines of 24–25.11 and error lines), and the self-check start count per hour.
R3 (coordinator 2026-11-25): where the self-check gets started — the user's usercustomize/sitecustomize and .pth files
for each Python version (and their saved copies), zapusk.py, every server line that imports zapusk or samokontrol, and
the account's running processes (age, thread count and program name only) to count how many self-checks live at once.
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


RESTART_SOURCES = ('start_safe.py', 'run_all.py')
RESTART_NEEDLE = re.compile(r'os\._exit|sys\.exit|execv|restart|перезапуск|getMe|get_me|kill|SIGTERM|Conflict|'
                            r'always_on|alwayson|watchdog|stop\(|shutdown', re.I)
RESTART_FILES = re.compile(r'(?i)start_safe|run_all|bot|guard|online|crash|restart|watchdog|alwayson|zapusk')
RESTART_LINE = re.compile(r'restart|перезап|запущ|start|stop|exit|Traceback|Error|Exception|getMe|kill|SIGTERM|'
                          r'Conflict|timed? ?out|memory|Killed', re.I)
DAY = re.compile(r'2026-11-2[45]')


def restart_sources():
    found = {}
    for name in RESTART_SOURCES:
        text = text_of(HOME / name)
        found[name] = None if text is None else {
            'sha256': hashlib.sha256(text.encode()).hexdigest()[:16], 'mtime': stamp((HOME / name).stat().st_mtime),
            'source': '\n'.join(sanitized_line(x) for x in text.splitlines())[:60000]}
    lines = {}
    for name in ('crm_online_guard.py', 'team_bot.py', 'cars_ui.py', 'lead_bot.py'):
        text = text_of(HOME / name)
        if text:
            lines[name] = [{'line': n + 1, 'text': sanitized_line(line)[:220]}
                           for n, line in enumerate(text.splitlines()) if RESTART_NEEDLE.search(line)][:80]
    found['restart_lines'] = lines
    return found


def restart_logs():
    found = {}
    places = [p for p in HOME.iterdir() if p.is_file() and not p.is_symlink() and RESTART_FILES.search(p.name)
              and not p.name.endswith(('.py', '.json', '.db', '.sqlite3', '.lock', '.zip'))]
    var = Path('/var/log')
    try:
        places += [p for p in var.iterdir() if p.is_file() and ('alwayson' in p.name or 'Carix' in p.name.lower()
                                                                  or 'carix' in p.name)]
    except Exception as error:
        found['/var/log'] = {'error': type(error).__name__}
    for path in sorted(places, key=lambda p: p.stat().st_mtime, reverse=True)[:25]:
        try:
            info = path.stat()
            lines = tail_lines(path, 1200 * 1024)
            day = [x for x in lines if DAY.search(x)]
            chosen = [x for x in (day or lines) if RESTART_LINE.search(x)] or (day or lines)[-40:]
            found[str(path)] = {'bytes': info.st_size, 'mtime': stamp(info.st_mtime),
                                'lines': [sanitized_line(x)[:260] for x in chosen][-200:]}
        except Exception as error:
            found[str(path)] = {'error': type(error).__name__}
    return found


def watchman_starts():
    path = HOME / 'samokontrol_log.txt'
    counts = {}
    for line in tail_lines(path, 3 * 1024 * 1024):
        if 'сторож запущен' in line and DAY.match(line):
            counts[line[:13]] = counts.get(line[:13], 0) + 1
    return counts


IMPORT_NEEDLE = re.compile(r'zapusk|samokontrol|usercustomize|sitecustomize')


def startup_files():
    found = {}
    base = HOME / '.local' / 'lib'
    for site in sorted(base.glob('python*/site-packages')) if base.is_dir() else []:
        for path in sorted(site.iterdir()):
            if not path.is_file() or path.is_symlink():
                continue
            name = path.name
            if not (name.startswith(('usercustomize', 'sitecustomize')) or name.endswith('.pth')):
                continue
            info = path.stat()
            item = {'bytes': info.st_size, 'mtime': stamp(info.st_mtime)}
            text = text_of(path)
            if text is not None and info.st_size <= 200 * 1024:
                item['source'] = [sanitized_line(x)[:240] for x in text.splitlines()][:400]
            found[str(path.relative_to(HOME))] = item
    for name in ('zapusk.py', 'sitecustomize.py', 'usercustomize.py'):
        text = text_of(HOME / name)
        if text is not None:
            found[name] = {'mtime': stamp((HOME / name).stat().st_mtime),
                           'source': [sanitized_line(x)[:240] for x in text.splitlines()][:600]}
    return found


def importers():
    found = {}
    for path in sorted(list(HOME.glob('*.py')) + list(HOME.glob('*/*.py'))):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        text = text_of(path)
        if text is None or not IMPORT_NEEDLE.search(text):
            continue
        hits = [{'line': n + 1, 'text': sanitized_line(line)[:200]} for n, line in enumerate(text.splitlines())
                if IMPORT_NEEDLE.search(line) and re.search(r'import|start\(|exec|run', line)]
        if hits:
            found[str(relative)] = hits[:15]
    return found


def processes():
    rows = []
    uid = os.getuid()
    clock = os.sysconf('SC_CLK_TCK')
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    for item in Path('/proc').glob('[0-9]*'):
        try:
            if item.stat().st_uid != uid:
                continue
            args = (item / 'cmdline').read_bytes().decode('utf-8', 'replace').split('\0')
            fields = (item / 'stat').read_text().rsplit(')', 1)[1].split()
            age = uptime - int(fields[19]) / clock
            threads = [x for x in (item / 'status').read_text().splitlines() if x.startswith('Threads:')]
            names = [Path(a).name for a in args if a][:4]
            rows.append({'pid': int(item.name), 'age_seconds': int(age), 'threads': threads[0].split()[1] if threads else '?',
                         'program': [sanitized_line(n)[:60] for n in names]})
        except Exception:
            continue
    rows.sort(key=lambda r: -r['age_seconds'])
    python = [r for r in rows if r['program'] and 'python' in r['program'][0]]
    return {'count': len(rows), 'python': len(python),
            'python_older_than_90s': sum(r['age_seconds'] > 90 for r in python), 'rows': rows[:60]}


def report():
    value = {'status': 'PASS', 'now': stamp(datetime.datetime.now(datetime.timezone.utc).timestamp())}
    for key, call in (('full_sources', full_sources), ('callers', callers), ('state_files', state_files),
                      ('crm_and_pages', crm_and_pages), ('restart_sources', restart_sources),
                      ('restart_logs', restart_logs), ('watchman_starts', watchman_starts),
                      ('startup_files', startup_files), ('importers', importers), ('processes', processes)):
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
