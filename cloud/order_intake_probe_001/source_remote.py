"""Read-only probe on the server: which modules receive, validate and store order page requests (/api/orders).

Reads only. Top-level server modules and the web app's WSGI files are searched for the order API markers;
matching lines (with a little context) are returned, credential-like lines redacted, foreign URLs and long numbers
masked. The modules that define the order routes or the request schema are returned in full, sanitized.
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
ROOTS = (HOME, Path('/var/www'))
# R2/R3: all source directories under the home directory, up to MAX_DEPTH levels, without libraries and copies.
APP_DIRS = (HOME,)
SKIP = ('site-packages', '__pycache__', '/.', '/runs/', 'backup', '/inbox')
MAX_DEPTH = 3
MAX_FILES = 4000
# R4: the live order package (found by R3), every module returned in full, sanitized.
PACKAGE = HOME/'ua_order'
MARKERS = ('/api/orders', 'api/orders', 'ua_order_request', 'orders/submit', 'consent_version', 'card_presets',
           'order_requests', 'handoff')
# Modules that define the order routes or validate the request are returned in full.
DEFINES = re.compile(r'''api/orders|ua_order_request''')
MAX_SOURCE = 400 * 1024
MAX_FULL = 8
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


def sources():
    for root in ROOTS:
        try:
            entries = sorted(root.iterdir())
        except OSError:
            continue
        for path in entries:
            if path.suffix == '.py' and path.is_file() and not path.is_symlink():
                yield path
    count = 0
    for root in APP_DIRS:
        for path in sorted(root.rglob('*.py')):
            depth = len(path.relative_to(root).parts) - 1
            if not 1 <= depth <= MAX_DEPTH or any(part in str(path) for part in SKIP):
                continue
            if path.is_file() and not path.is_symlink():
                count += 1
                if count > MAX_FILES:
                    return
                yield path


def report():
    hits, full = {}, {}
    for path in sources():
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_SOURCE:
            continue
        text = raw.decode('utf-8', 'replace')
        if not any(marker in text for marker in MARKERS):
            continue
        lines = text.splitlines()
        found = [{'line': number + 1, 'context': [sanitized_line(item) for item in lines[max(0, number - 1):number + 2]]}
                 for number, line in enumerate(lines) if any(marker in line for marker in MARKERS)]
        hits[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'matches': found[:60]}
        if DEFINES.search(text) and len(full) < MAX_FULL:
            full[str(path)] = '\n'.join(sanitized_line(item) for item in lines)
    package = {path.name: '\n'.join(sanitized_line(item) for item in path.read_text(encoding='utf-8', errors='replace').splitlines())
               for path in sorted(PACKAGE.glob('*.py')) if path.is_file() and not path.is_symlink()}
    return {'status': 'PASS', 'source_hits': hits, 'order_sources': full, 'package_sources': package}


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
