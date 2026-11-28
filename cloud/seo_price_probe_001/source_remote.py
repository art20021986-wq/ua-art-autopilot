"""Read-only probe on the server for SEO-PRICE-001 (coordinator «можно» 2026-11-28).

Since 2026-11-27 ~07:19Z the card pages carry no price in <title>, the description and the JSON-LD Product, while the
page itself still shows it. ua_seo_metadata.card_facts takes the price from the market price block when normalize runs,
so the question is which writer now runs normalize before that block exists. Reads only:
- the sanitized full source of ua_seo_metadata.py, site_ge_inject.py and the card writers (stranica, yadro, publikaciya,
  publish_transaction_guard, master_card, ua_card_lang, ua_card_lang_job) and every server .py that mentions the
  market price block;
- every server .py (home folder, two levels down) changed since 2026-11-26: size, time, hash;
- line numbers of the markers (normalize, inject_html, market prices) per file;
- for the UA-0017 card files: modification time, title, description, JSON-LD price;
- the title the installed normalize gives that card in memory, in a child process that may not write any file.
No CRM read, nothing written outside this run's own receipt.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import subprocess
import sys

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
MAX_SOURCE = 2 * 1024 * 1024
MAX_TOTAL = 6 * 1024 * 1024
SINCE = datetime.datetime(2026, 11, 26, tzinfo=datetime.timezone.utc).timestamp()
ALWAYS = ('ua_seo_metadata.py', 'site_ge_inject.py', 'stranica.py', 'yadro.py', 'publikaciya.py',
          'publish_transaction_guard.py', 'master_card.py', 'ua_card_lang.py', 'ua_card_lang_job.py')
MARKERS = ('normalize(', 'inject_html', 'UA-ART-MARKET-PRICES', 'data-ua-market', 'karta_html', 'zapisat_atomarno')
CARDS = ('video/UA-0017.html', 'video/ua/UA-0017.html', 'video/ru/UA-0017.html')
SKIP_DIRS = {'backups', 'backup', 'autopilot_inbox', 'node_modules', 'staroe', '__pycache__', 'opt', 'foto', 'archive',
             'sandbox', 'video', 'site'}
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|api_hash|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')
DATE_IN_NUMBER = re.compile(r'\s*20\d\d-\d\d-\d\d(?:[ T]\d\d)?\s*')
# Run by a child process that may not write any file (RLIMIT_FSIZE 0): the installed normalize on the card, in memory.
NORMALIZE_CHECK = r'''
import builtins, io, json, os, re, sys
source = open(sys.argv[2], encoding='utf-8').read()
_open, _os_open = builtins.open, os.open
def _read_only(file, mode='r', *args, **kwargs):
    if any(flag in mode for flag in 'wax+'):
        raise PermissionError('READ_ONLY_PROBE')
    return _open(file, mode, *args, **kwargs)
def _os_read_only(path, flags, *args, **kwargs):
    if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC):
        raise PermissionError('READ_ONLY_PROBE')
    return _os_open(path, flags, *args, **kwargs)
def _refuse(*args, **kwargs):
    raise PermissionError('READ_ONLY_PROBE')
builtins.open = io.open = _read_only
os.open = _os_read_only
for _name in ('remove', 'unlink', 'rename', 'replace', 'rmdir', 'mkdir', 'makedirs', 'chmod', 'symlink', 'link'):
    setattr(os, _name, _refuse)
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import ua_seo_metadata
result = ua_seo_metadata.normalize(source, sys.argv[3])
title = re.search(r'<title[^>]*>(.*?)</title>', result, re.S)
print(json.dumps({'title': title.group(1).strip() if title else None,
                  'price_in_source': bool(re.search(r'data-ua-market=["\']ukraine["\'][^>]*?data-ua-value=["\']([0-9]+)', source)),
                  'ld_price': '"price"' in result}, ensure_ascii=False))
'''


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


def python_files():
    paths = list(HOME.glob('*.py')) + list(HOME.glob('*/*.py')) + list(HOME.glob('*/*/*.py'))
    for path in sorted(set(paths)):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS or part.startswith('spec_') for part in relative.parts[:-1]):
            continue
        yield str(relative), path


def scan():
    files, sources, total = {}, {}, 0
    for name, path in python_files():
        text = text_of(path)
        if text is None:
            continue
        lines = text.splitlines()
        hits = {m: [n + 1 for n, line in enumerate(lines) if m in line][:60] for m in MARKERS if m in text}
        changed = path.stat().st_mtime >= SINCE
        if not changed and name not in ALWAYS and 'UA-ART-MARKET-PRICES' not in text:
            continue
        files[name] = {'bytes': path.stat().st_size, 'mtime': stamp(path.stat().st_mtime), 'changed_since_26_11': changed,
                       'sha256': hashlib.sha256(text.encode()).hexdigest(), 'hits': hits}
        if name in ALWAYS or 'UA-ART-MARKET-PRICES' in text:
            source = '\n'.join(sanitized_line(x) for x in lines)
            if total + len(source.encode()) <= MAX_TOTAL:
                total += len(source.encode())
                sources[name] = source
    return files, sources


def card(relative):
    path = HOME / relative
    text = text_of(path)
    if text is None:
        return {'exists': False}
    title = re.search(r'<title[^>]*>(.*?)</title>', text, re.S)
    description = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', text)
    return {'exists': True, 'mtime': stamp(path.stat().st_mtime), 'title': title.group(1).strip() if title else None,
            'description': description.group(1) if description else None, 'ld_price': '"price"' in text,
            'market_block': 'UA-ART-MARKET-PRICES' in text}


def no_write_limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 35))


def normalize_check():
    source = HOME / 'video/UA-0017.html'
    if not source.is_file():
        return {'error': 'CARD_MISSING'}
    result = subprocess.run([sys.executable, '-B', '-c', NORMALIZE_CHECK, str(HOME), str(source), 'UA-0017.html'],
                            cwd=str(HERE), capture_output=True, text=True, timeout=60, preexec_fn=no_write_limits)
    if result.returncode != 0:
        return {'error': sanitized_line(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'EXIT')[:200]}
    return json.loads(result.stdout)


def report():
    value = {'status': 'PASS', 'now': stamp(datetime.datetime.now(datetime.timezone.utc).timestamp())}
    for key, call in (('scan', scan), ('cards', lambda: {c: card(c) for c in CARDS}),
                      ('normalize_check', normalize_check)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    if isinstance(value['scan'], tuple):
        value['files'], value['full_sources'] = value.pop('scan')
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
