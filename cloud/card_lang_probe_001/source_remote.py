"""Read-only probe on the server: how car card pages are generated and which language Google gets (CARD-LANG-PROBE).

Reads only. The card page generator and the modules that touch card HTML, the sitemap and the language
script's loader are returned in full, sanitized (credential-like lines redacted, foreign URLs and long numbers
masked). R1 read the card generator and sample pages; R2 reads the language script and every
top-level module line that writes or rebuilds a card page. Each file's sha256 is kept for a later exact edit.
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
# R2: every top-level module line that writes or rebuilds a card page (with a little context).
WRITERS = re.compile(r'sobrat_kartochku|_zapisat_atomarno|_peresobrat|opublikovat\(|perestroit|rebuild|'
                     r'UA-[0-9{%].*\.html|kod\s*\+\s*["\']\.html|\.html["\']\s*%|write_text\(|os\.replace\(')
FULL = ('ua-site-languages.js', 'video/ua-site-languages.js')
PARTIAL = {}
MAX_SOURCE = 900 * 1024  # R2: ua-site-languages.js is ~700 KB
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
    writers = {}
    for path in sorted(HOME.glob('*.py')):
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
            continue
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
        found = [{'line': n + 1, 'context': [sanitized_line(x) for x in lines[max(0, n - 2):n + 3]]}
                 for n, line in enumerate(lines) if WRITERS.search(line)]
        if found:
            writers[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'matches': found[:80]}
    return {'status': 'PASS', 'files': files, 'writers': writers}


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
