"""Read-only probe on the server for JAPAN-STOCK-001 (owner 2026-11-26: cars bought in Japan and the Japan ferry).

Reads only:
- which server .py files (home folder and one level down) and top-level template files contain the delivery stage,
  catalog filter, home tile and card stage markers: per file size, time, short hash and per-marker line numbers;
- the sanitized full source of the most relevant files (by marker score, bounded in count and size);
- the cars table column names and the number of cars per status and published flag (no rows, no personal data).
R3 (after JAPAN-BOT-INSTALL): bot/log files of the last 2 hours (tail and error lines) and bot process ages.
R2 (JAPAN-STOCK-001 package): also the full source and exact hash of the modules in ALWAYS.
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
MAX_TOTAL = 7 * 1024 * 1024
MAX_FULL = 40
# R2: always read these in full (they import ua_delivery_status or write the public pages).
ALWAYS = ('ua_delivery_status.py', 'db.py', 'publikaciya.py', 'publish_transaction_guard.py', 'ua_crm_public_sync.py',
          'card_render.py', 'publication_fence.py', 'ua_crm_catalog_folders.py', 'cars_ui.py', 'konteyner.py',
          'cars_schema.py', 'stranica.py', 'master_card.py', 'ua_stage_catalog_sync.py', 'ua_site_counters.py',
          'catalog_design_guard.py')
SKIP_DIRS = {'backups', 'backup', 'autopilot_inbox', 'node_modules', 'video', 'site', '__pycache__'}
TEMPLATE = re.compile(r'\.(?:html|txt|tpl|js|css|json)$')
# Marker -> weight. Strong markers name the stage policy, the CRM menu and the generated page parts.
MARKERS = {
    'kr_bought': 3, 'sea_loaded': 3, 'ge_waiting': 1, 'ua_arrived': 1,
    'ua_delivery_status': 3, 'CHOICES': 1, 'stage_menu': 3, 'car_setstage': 3, 'status_label': 1,
    'filter-row': 3, 'data-f=': 2, 'stage-card': 3, 'data-stage': 2, 'ua-stage-v1': 3, 'ua-delivery-v1': 3,
    'стоянка в Корее': 3, 'стоянка в Кореї': 3, 'Викуплені та перевірені': 3, 'Выкуплены и проверены': 3,
    'На поромі': 2, 'На пароме': 2, 'У Кореї': 1, 'В Корее': 1, 'UA-CIFRY': 3, 'catalog-card': 2,
    'Путь автомобиля': 2, 'Шлях автомобіля': 2, '🇰🇷': 1, 'chip': 1,
}
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


def candidates():
    paths = list(HOME.glob('*.py')) + list(HOME.glob('*/*.py'))
    paths += [p for p in HOME.iterdir() if p.is_file() and TEMPLATE.search(p.name)]
    for path in sorted(set(paths)):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        yield relative, path


def scan():
    found = {}
    for relative, path in candidates():
        text = text_of(path)
        if text is None:
            continue
        lines = text.splitlines()
        hits = {}
        for marker in MARKERS:
            if marker in text:
                hits[marker] = [n + 1 for n, line in enumerate(lines) if marker in line][:40]
        if not hits:
            continue
        score = sum(MARKERS[m] * min(len(v), 5) for m, v in hits.items())
        found[str(relative)] = {'bytes': path.stat().st_size, 'mtime': stamp(path.stat().st_mtime),
                                'sha256': hashlib.sha256(text.encode()).hexdigest()[:16], 'score': score, 'hits': hits,
                                '_text': text}
    return found


def full_sources(found):
    chosen, total = {}, 0
    for name in ALWAYS:
        text = text_of(HOME / name)
        if text is not None:
            found.setdefault(name, {'bytes': len(text.encode()), 'mtime': stamp((HOME / name).stat().st_mtime),
                                    'sha256': hashlib.sha256(text.encode()).hexdigest()[:16], 'score': 0, 'hits': {},
                                    '_text': text})
            found[name]['score'] += 10000
            found[name]['sha256_full'] = hashlib.sha256(text.encode()).hexdigest()
    ranked = sorted(found.items(), key=lambda item: (-item[1]['score'], item[0]))
    for name, item in ranked:
        if len(chosen) >= MAX_FULL:
            break
        source = '\n'.join(sanitized_line(x) for x in item['_text'].splitlines())
        if total + len(source.encode()) > MAX_TOTAL:
            continue
        total += len(source.encode())
        chosen[name] = source
    return chosen


def crm_schema():
    database = HOME / 'crm.db'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=10) as connection:
        names = [row[1] for row in connection.execute('PRAGMA table_info(cars)')]
        counts = [list(r) for r in connection.execute(
            'SELECT status, published, COUNT(*) FROM cars GROUP BY status, published ORDER BY status')]
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {'cars_columns': names, 'status_published_counts': counts, 'tables': tables}


def recent_logs():
    """R3 (after JAPAN-BOT-INSTALL): bot/log files changed in the last 2 hours — last lines and error lines."""
    import time as _time
    found = {}
    limit = _time.time() - 7200
    for path in sorted(HOME.iterdir()):
        if not path.is_file() or path.is_symlink() or path.suffix in ('.py', '.db', '.json', '.html', '.lock', '.zip'):
            continue
        if not re.search(r'(?i)log|zhurnal', path.name) or path.stat().st_mtime < limit:
            continue
        with path.open('rb') as handle:
            handle.seek(max(0, path.stat().st_size - 200 * 1024))
            lines = handle.read().decode('utf-8', 'replace').splitlines()
        errors = [sanitized_line(x)[:260] for x in lines if re.search(r'Traceback|Error|Exception|JAPAN-STOCK', x)]
        found[path.name] = {'mtime': stamp(path.stat().st_mtime), 'tail': [sanitized_line(x)[:260] for x in lines[-25:]],
                            'errors': errors[-40:]}
    return found


def processes():
    rows = []
    uptime = float(Path('/proc/uptime').read_text().split()[0])
    clock = os.sysconf('SC_CLK_TCK')
    for item in Path('/proc').glob('[0-9]*'):
        try:
            if item.stat().st_uid != os.getuid():
                continue
            args = [Path(a).name for a in (item / 'cmdline').read_bytes().decode('utf-8', 'replace').split('\0') if a][:3]
            age = uptime - int((item / 'stat').read_text().rsplit(')', 1)[1].split()[19]) / clock
            if any(a in ('start_safe.py', 'run_all.py', 'team_bot.py') for a in args):
                rows.append({'program': args, 'age_seconds': int(age)})
        except Exception:
            continue
    return rows


def report():
    value = {'status': 'PASS', 'now': stamp(datetime.datetime.now(datetime.timezone.utc).timestamp())}
    try:
        found = scan()
        value['full_sources'] = full_sources(found)
        found = {k: v for k, v in found.items() if v['hits'] or k in ALWAYS}
        value['files'] = {k: {x: y for x, y in v.items() if x != '_text'} for k, v in found.items()}
    except Exception as error:
        value['files'] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    for key, call in (('recent_logs', recent_logs), ('bot_processes', processes)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__}
    try:
        value['crm_schema'] = crm_schema()
    except Exception as error:
        value['crm_schema'] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
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
