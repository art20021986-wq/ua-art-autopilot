"""Read-only probe on the server before the enquiry deadlines in the CRM bot (ORDER-PROCESS-001).

Reads only: the order package storage/service/runtime/contract, ua_site_leads.py and db.py, returned in full,
sanitized (credential-like lines redacted, foreign URLs and long numbers masked), each with its sha256; and whether
the Europe/Kyiv zone loads with the standard library. No data rows are read. Nothing is written outside this
run's own receipt.
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
FULL = ()
PARTIAL = {}
MAX_SOURCE = 900 * 1024
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def read(name):
    path = HOME/name
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    return raw if len(raw) <= MAX_SOURCE else None


def report(home=None):
    global HOME
    if home is not None:
        HOME = home
    files = {}
    for name in FULL:
        raw = read(name)
        files[name] = None if raw is None else {
            'sha256': hashlib.sha256(raw).hexdigest(),
            'source': '\n'.join(sanitized_line(line) for line in raw.decode('utf-8', 'replace').splitlines())}
    for name, pattern in PARTIAL.items():
        raw = read(name)
        if raw is None:
            files[name] = None
            continue
        lines = raw.decode('utf-8', 'replace').splitlines()
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest(),
                       'lines': [{'line': n + 1, 'text': sanitized_line(l)} for n, l in enumerate(lines) if pattern.search(l)][:200]}
    try:
        import sys
        from zoneinfo import ZoneInfo
        ZoneInfo('Europe/Kyiv')
        zone = 'OK'
    except Exception as error:
        zone = type(error).__name__
    desk = None
    database = HOME/'crm.db'
    if database.is_file():
        import sqlite3
        from contextlib import closing
        # Read-only: only the names of the desk tables and when deadlines started to count; no rows of clients.
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
            tables = sorted(r[0] for r in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'lead_desk%'"))
            track = connection.execute("SELECT value FROM lead_desk_meta WHERE key='track_from'").fetchone() \
                if 'lead_desk_meta' in tables else None
        desk = {'tables': tables, 'track_from': track[0] if track else None}
    return {'status': 'PASS', 'files': files, 'python': '%d.%d' % sys.version_info[:2], 'zone_kyiv': zone,
            'lead_desk': desk, 'staff': staff(), 'invites': invites(), 'reply_source': reply_source()}


def staff():
    """Read-only: active staff per role and whether the manager @Beetle204 is active (no names or ids returned)."""
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect((HOME/'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        rows = connection.execute('SELECT role, active, lower(coalesce(username, \'\')) FROM staff').fetchall()
    roles = {}
    for role, active, _ in rows:
        if active:
            roles[role] = roles.get(role, 0) + 1
    beetle = [(role, bool(active)) for role, active, name in rows if name.lstrip('@') == 'beetle204']
    return {'active_by_role': roles, 'beetle204': beetle}


def invites():
    """Read-only: the invite table's columns and, for the two codes the owner sent, whether each exists and is used."""
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect((HOME/'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        columns = [row[1] for row in connection.execute('PRAGMA table_info(invites)')]
        result = {'columns': columns, 'codes': {}}
        for code in ('7030AC', '812DFF'):
            row = connection.execute('SELECT * FROM invites WHERE upper(code)=?', (code,)).fetchone()
            if row is None:
                result['codes'][code] = None
            else:
                item = dict(zip(columns, row))
                result['codes'][code] = {k: item.get(k) for k in ('role', 'used_by', 'used_at', 'created_at', 'expires_at')
                                         if k in item and k != 'used_by'} | {'used': bool(item.get('used_by'))}
    return result


def reply_source():
    """Read-only: which Python files on the server contain the reply the employee got."""
    needle = 'Доступ по приглашению'
    found = []
    for path in sorted(HOME.rglob('*.py')):
        if any(part.startswith('.') or part in ('backups', 'autopilot_inbox', 'node_modules') for part in path.parts):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace')
        except OSError:
            continue
        if needle in text:
            lines = [n + 1 for n, line in enumerate(text.splitlines()) if needle in line]
            found.append({'file': str(path.relative_to(HOME)), 'lines': lines[:5]})
        if len(found) >= 20:
            break
    return found


# Read-only public view: what each entry address serves now, as a phone browser asks for it.
PUBLIC_URLS = ('https://uaart.com.ua/', 'http://uaart.com.ua/', 'https://www.uaart.com.ua/',
               'https://www.uaart.com.ua/video/index.html', 'https://www.uaart.com.ua/video/podbor.html')
MARKERS = ('Безкоштовна консультація', 'podbor.html#zayavka', 'id="zayavka"', 'Розкажіть бюджет і побажання')


def public():
    import urllib.request
    result = {}
    for url in PUBLIC_URLS:
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) '
                                                       'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(2 * 1024 * 1024).decode('utf-8', 'replace')
                result[url] = {'status': response.status, 'final_url': response.url, 'bytes': len(body),
                               'server': response.headers.get('Server'), 'cache_control': response.headers.get('Cache-Control'),
                               'last_modified': response.headers.get('Last-Modified'),
                               'markers': {m: m in body for m in MARKERS}}
        except Exception as error:
            result[url] = {'error': type(error).__name__ + ':' + str(error)[:160]}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
    work = HERE/'runs'/args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work/'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work/'.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
