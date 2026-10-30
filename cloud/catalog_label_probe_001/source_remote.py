"""Read-only probe on the server: where the Japan rare-car card label lives (owner 2026-10-30, label without years).

Reads only. The order settings give the catalogue path (only that key is read); the catalogue is returned with its
hash, version and the lines around the rare-car card. Server sources and pages (up to MAX_DEPTH levels under the
home directory) are searched for the card's current labels; matching lines are returned sanitized. Nothing is written
outside this run's own receipt.
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
SETTINGS = HOME/'order_requests'/'settings.json'
KEY = 'classics-1980-1990'
# The card's current labels and alt texts (public order bootstrap 2026-10-25).
MARKERS = ('Раритетні авто 1980', 'Раритетные авто 1980', '1980–1990-იანი', 'Mercedes-Benz 230E, 1988', KEY)
SUFFIXES = ('.py', '.json', '.html', '.js', '.txt')
SKIP = ('site-packages', '__pycache__', '/.', '/runs/', 'backup', '/inbox', '/media/')
MAX_DEPTH = 3
MAX_FILES = 6000
MAX_SOURCE = 2 * 1024 * 1024
CONTEXT = 3
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org|commons\.wikimedia\.org|'
                          r'creativecommons\.org)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)[:400]


def around(lines, wanted):
    return [{'line': n + 1, 'context': [sanitized_line(item) for item in lines[max(0, n - CONTEXT):n + CONTEXT + 1]]}
            for n, line in enumerate(lines) if any(marker in line for marker in wanted)]


def catalog():
    path = Path(json.loads(SETTINGS.read_text(encoding='utf-8'))['catalog_path'])
    raw = path.read_bytes()
    text = raw.decode('utf-8')
    data = json.loads(text)
    card = [m for m in data['countries']['japan']['models'] if m['key'] == KEY]
    stat = path.stat()
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'mode': oct(stat.st_mode & 0o777),
            'version': data.get('version'), 'card': card, 'counts': {m: text.count(m) for m in MARKERS},
            'lines': around(text.splitlines(), MARKERS)[:40], 'newline_at_end': text.endswith('\n'),
            'ensure_ascii': '\\u04' in text}


def files():
    count = 0
    for path in sorted(HOME.rglob('*')):
        depth = len(path.relative_to(HOME).parts) - 1
        if depth > MAX_DEPTH or path.suffix not in SUFFIXES or any(part in str(path) for part in SKIP):
            continue
        if path.is_file() and not path.is_symlink():
            count += 1
            if count > MAX_FILES:
                return
            yield path


def hits():
    found = {}
    for path in files():
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_SOURCE:
            continue
        text = raw.decode('utf-8', 'replace')
        if any(marker in text for marker in MARKERS):
            found[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                                'counts': {m: text.count(m) for m in MARKERS if m in text},
                                'matches': around(text.splitlines(), MARKERS)[:12]}
    return found


def report():
    return {'status': 'PASS', 'catalog': catalog(), 'label_hits': hits()}


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
