"""Read-only probe on the server: who serves /ua/a.js and who puts it into the public pages.

Reads only. Top-level server modules and the web app's WSGI files are searched for the site analytics markers;
matching lines (with a little context) are returned, credential-like lines redacted, foreign URLs and long numbers
masked. The modules that serve /ua/a.js are returned in full, sanitized. Public HTML files are counted by whether
they already load /ua/a.js or a Google tag. Nothing is written outside this run's own receipt.
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
PUBLIC = HOME/'video'
MARKERS = ('UA-ANALIT', '/ua/a.js', '/ua/a/e', 'mcf-izmer', 'googletagmanager', 'gtag(', 'Content-Security-Policy')
# R2: which modules build or write which public pages.
WRITERS = ('ua_seo_metadata', 'ua_seo_index', 'obrabotat_obshuyu', '_install_catalog', 'index.html', 'podbor.html',
           'info.html', 'sravnenie.html')
MODULES = ('ua_seo_metadata.py', 'ua_seo_index.py', 'ua_seo_landings.py', 'publish_transaction_guard.py',
           'publikaciya.py', 'master_card.py', 'stranica.py', 'ua_crm_public_sync.py', 'analitika_wsgi.py',
           'analitika_yadro.py', 'ua_site_counters.py')
SERVES = re.compile(r'''['"]/ua/a\.js|/ua/a/e['"]|route\(\s*['"]/ua''')
MAX_SOURCE = 400 * 1024  # larger files are searched only when listed in MODULES
MAX_FULL = 6
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org|www\.googletagmanager\.com'
                          r'|www\.google-analytics\.com)(?:[/\'"\s]|$)')


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


def search():
    hits, full = {}, {}
    for path in sources():
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_SOURCE and path.name not in MODULES:
            continue
        text = raw.decode('utf-8', 'replace')
        if not any(marker in text for marker in MARKERS + WRITERS):
            continue
        lines = text.splitlines()
        found = []
        for number, line in enumerate(lines):
            if any(marker in line for marker in MARKERS + WRITERS):
                found.append({'line': number + 1, 'context': [sanitized_line(item)
                                                            for item in lines[max(0, number - 1):number + 2]]})
        hits[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'matches': found[:60]}
        if SERVES.search(text) and len(full) < MAX_FULL:
            full[str(path)] = '\n'.join(sanitized_line(item) for item in lines)
    return hits, full


def pages():
    counts = {'html': 0, 'with_a_js': 0, 'with_marker': 0, 'with_google_tag': 0}
    without = []
    for path in sorted(PUBLIC.rglob('*.html')):
        if path.is_symlink() or not path.is_file():
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        counts['html'] += 1
        counts['with_a_js'] += '/ua/a.js' in text
        counts['with_marker'] += 'UA-ANALIT' in text
        counts['with_google_tag'] += 'googletagmanager' in text
        if '/ua/a.js' not in text:
            without.append(str(path.relative_to(HOME)))
    return {**counts, 'without_a_js': without[:300]}


def modules():
    found = {}
    for name in MODULES:
        path = HOME/name
        found[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return found


def report():
    hits, full = search()
    return {'status': 'PASS', 'source_hits': hits, 'serving_sources': full, 'public_pages': pages(),
            'module_sha256': modules()}


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
