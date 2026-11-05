"""Read-only probe on the server for CARD-DIAG-001 (tasks/CARD-DIAG-001.md).

Owner 2026-11-05: the «complex diagnostics» link disappeared from the Mercedes-Benz B-Class card in stock.
Reads only:
- per car in crm.db (opened read-only): identity and stage columns, and for the diagnostics/media fields only
  whether they are filled and their length (no texts, no client data);
- per published card page (video/, video/ua/, video/ru/): whether it carries the diagnostics link, its target,
  size and modification time; per diagnostics page: size, time, video count;
- the server lines (sanitized, with context and file sha256) that write or remove the diagnostics link;
- the full sanitized HTML of the Mercedes-Benz B-Class card pages, for comparison.
Nothing is written outside this run's own receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
MAX_SOURCE = 900 * 1024
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')
CARD = re.compile(r'UA-[0-9]{4,}\.html')
DIAG_PAGE = re.compile(r'UA-[0-9]{4,}-diag\.html')
DIAG_HREF = re.compile(r'''<a\b[^>]*href=["']([^"']*UA-[0-9]{4,}-diag\.html)["'][^>]*>''', re.I)
MARKERS = ('ua-art-diagnostics-permanent-v1', 'mcf-diag-cta')
# Server code that writes or strips the link, or decides when a card shows it.
SOURCE_NEEDLE = re.compile(r'ua-art-diagnostics-permanent|mcf-diag-cta|-diag\.html|комплексн|diag_cta|has_diag')
SKIP_DIRS = {'backups', 'autopilot_inbox', 'node_modules', 'video', 'site', '__pycache__'}
DIRECT = {'id', 'auto_number', 'published', 'publish_pending', 'status', 'stage', 'brand', 'model', 'year',
          'marka', 'god', 'updated_at', 'created_at'}
FILLED = ('diag_report', 'diag_link', 'diag_text', 'condition_text', 'condition_photos', 'condition_videos',
          'description', 'photos', 'videos')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def sanitized(text):
    return '\n'.join(sanitized_line(line) for line in text.splitlines())


def text_of(path):
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    return raw.decode('utf-8', 'replace') if len(raw) <= MAX_SOURCE else None


def cars():
    import sqlite3
    from contextlib import closing
    database = HOME / 'crm.db'
    if not database.is_file():
        return None
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        columns = [row[1] for row in connection.execute('PRAGMA table_info(cars)')]
        rows = connection.execute('SELECT * FROM cars').fetchall()
    result = []
    for row in rows:
        item = {key: row[key] for key in columns if key in DIRECT}
        for key in FILLED:
            if key in columns:
                value = row[key]
                item[key + '_length'] = len(str(value or ''))
        result.append(item)
    return {'columns': columns, 'rows': result}


def page(path):
    text = text_of(path)
    if text is None:
        return None
    title = re.search(r'<title>(.*?)</title>', text, re.S)
    return {'bytes': len(text.encode()), 'mtime': round(path.stat().st_mtime),
            'title': sanitized_line(title.group(1).strip())[:160] if title else None,
            'markers': {m: text.count(m) for m in MARKERS}, 'diag_hrefs': DIAG_HREF.findall(text)[:4],
            'mercedes_b': bool(re.search(r'(?i)Mercedes[^<]{0,40}(?:B-Class|B-Klasse|Б-КЛАСС|B ?1[68]0|B ?200)', text))}


def pages():
    video = HOME / 'video'
    result = {}
    for folder in ('', 'ua/', 'ru/'):
        base = video / folder
        if base.is_dir():
            for path in sorted(base.iterdir()):
                if CARD.fullmatch(path.name):
                    result[folder + path.name] = page(path)
    diag = {}
    if video.is_dir():
        for path in sorted(video.iterdir()):
            if DIAG_PAGE.fullmatch(path.name):
                text = text_of(path) or ''
                diag[path.name] = {'bytes': len(text.encode()), 'mtime': round(path.stat().st_mtime),
                                   'videos': len(re.findall(r'<video\b', text, re.I)),
                                   'images': len(re.findall(r'<img\b', text, re.I))}
    catalog = text_of(video / 'katalog.html') or ''
    return {'cards': result, 'diag_pages': diag,
            'catalog_cards': sorted(set(re.findall(r'href=["\'](?:[^"\']*/)?(UA-[0-9]{4,})\.html', catalog)))}


def sources():
    found = {}
    for path in sorted(list(HOME.glob('*.py')) + list(HOME.glob('*/*.py'))):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        text = text_of(path)
        if text is None or not SOURCE_NEEDLE.search(text):
            continue
        lines = text.splitlines()
        hits = sorted({i for n, line in enumerate(lines) if SOURCE_NEEDLE.search(line)
                       for i in range(max(0, n - 12), min(len(lines), n + 13))})
        found[str(relative)] = {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'mtime': round(path.stat().st_mtime),
                                'lines': [{'line': n + 1, 'text': sanitized_line(lines[n])[:400]} for n in hits][:400]}
        if len(found) >= 60:
            break
    return found


def mercedes_pages(found):
    video = HOME / 'video'
    return {name: sanitized(text_of(video / name) or '') for name, value in found.items()
            if value and value['mercedes_b']}


def report(home=None):
    global HOME
    if home is not None:
        HOME = home
    published = pages()
    return {'status': 'PASS', 'cars': cars(), 'pages': published, 'sources': sources(),
            'mercedes_pages': mercedes_pages(published['cards'])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
