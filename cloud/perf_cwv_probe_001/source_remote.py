"""Read-only probe on the server for PERF-CWV-001 (owner 2026-11-26: page speed, layout shifts, phone comfort).

Reads only:
- which server .py and template files (home folder, two levels down, and the user site-packages usercustomize.py)
  contain the markers of the home Korea ticker, the card header "← На головну" style, the language switcher,
  the card stage labels, catalog photo tags and image optimisation: per file size, time, hash, marker line numbers;
- the sanitized full source of the most relevant files (by marker score, bounded in count and size);
- whether Pillow on this Python can write WebP, and whether ffmpeg is installed;
- the size of the existing light-image folder video/opt (count, bytes, a few names).
R2: also the writers of the blocks appended at the end of the cards (UA-BRAND-HOME, UA-CHAT-GLASS, UA-SOCIAL,
UA-AUTORIA-BADGE), the photo gallery (um-gallery) and the callers of ua_korea_home / the ticker; archive, sandbox
and spec_* copies are skipped; files up to 2 MB.
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
import shutil

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
USERCUSTOMIZE = '.local/lib/python3.10/site-packages/usercustomize.py'
MAX_SOURCE = 2 * 1024 * 1024
MAX_TOTAL = 7 * 1024 * 1024
MAX_FULL = 40
# Always read in full: the page writers and the catalog renderer.
ALWAYS = ('catalog_design_guard.py', 'catalog_stage_guard_core.py', 'master_card.py', 'stranica.py', 'yadro.py',
          'publish_transaction_guard.py', 'publikaciya.py', USERCUSTOMIZE)
SKIP_DIRS = {'backups', 'backup', 'autopilot_inbox', 'node_modules', 'staroe', '__pycache__', 'opt', 'foto', 'archive',
             'sandbox'}
SKIP_PREFIX = ('spec_',)
TEMPLATE = re.compile(r'\.(?:html|txt|tpl|js|css|json)$')
# Marker -> weight.
MARKERS = {
    'not(.znak)::after': 6, 'ua-korea-ticker': 6, 'korea/ticker.html': 6, 'korea-ticker': 4, 'kt-arrow': 4,
    'UA-KOREA-AUCTION': 4, 'UA-HOME-ORDER': 3, 'lang-toggle': 3, 'ua-site-languages': 2, 'header-phone': 3,
    'ЕТАП': 2, 'ЗАРАЗ': 2, 'ПОТОЧНИЙ': 2, 'um-gallery': 4, 'um-stage': 3, 'quick-lead.css': 2,
    'telegram-web-app': 2, 'fetchpriority': 2, 'loading="lazy"': 1, 'oblegchit': 2, '/video/opt': 2,
    'srcset': 2, 'ua-v203.css': 2, 'mcf-chat': 2, 'shapka': 1,
    'UA-BRAND-HOME': 8, 'ua-brand-home': 8, 'UA-CHAT-GLASS': 5, 'UA-SOCIAL-V1': 5, 'UA-AUTORIA-BADGE': 5,
    'um-thumbs': 5, 'ua_korea_home': 6, 'ticker.html': 3,
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
    paths = list(HOME.glob('*.py')) + list(HOME.glob('*/*.py')) + list(HOME.glob('*/*/*.py'))
    paths += [p for p in HOME.iterdir() if p.is_file() and TEMPLATE.search(p.name)]
    for path in sorted(set(paths)):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS or part.startswith(SKIP_PREFIX) for part in relative.parts[:-1]):
            continue
        yield relative, path
    extra = HOME / USERCUSTOMIZE
    if extra.is_file():
        yield Path(USERCUSTOMIZE), extra


def entry(path, text):
    return {'bytes': path.stat().st_size, 'mtime': stamp(path.stat().st_mtime),
            'sha256_full': hashlib.sha256(text.encode()).hexdigest(), 'score': 0, 'hits': {}, '_text': text}


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
        if not hits and str(relative) not in ALWAYS:
            continue
        item = entry(path, text)
        item['hits'] = hits
        item['score'] = sum(MARKERS[m] * min(len(v), 5) for m, v in hits.items())
        found[str(relative)] = item
    return found


def full_sources(found):
    for name in ALWAYS:
        if name not in found:
            text = text_of(HOME / name)
            if text is not None:
                found[name] = entry(HOME / name, text)
        if name in found:
            found[name]['score'] += 10000
    chosen, total = {}, 0
    for name, item in sorted(found.items(), key=lambda pair: (-pair[1]['score'], pair[0])):
        if len(chosen) >= MAX_FULL:
            break
        source = '\n'.join(sanitized_line(x) for x in item['_text'].splitlines())
        if total + len(source.encode()) > MAX_TOTAL:
            continue
        total += len(source.encode())
        chosen[name] = source
    return chosen


def image_tools():
    value = {'ffmpeg': bool(shutil.which('ffmpeg'))}
    try:
        import PIL
        from PIL import features
        value.update(pillow=PIL.__version__, webp=bool(features.check('webp')), avif=bool(features.check('avif')))
    except Exception as error:
        value['pillow_error'] = type(error).__name__
    return value


def light_images():
    folder = HOME / 'video' / 'opt'
    if not folder.is_dir():
        return {'exists': False}
    files = [p for p in folder.iterdir() if p.is_file()]
    return {'exists': True, 'count': len(files), 'bytes': sum(p.stat().st_size for p in files),
            'sample': sorted(p.name for p in files)[:15]}


def report():
    value = {'status': 'PASS', 'now': stamp(datetime.datetime.now(datetime.timezone.utc).timestamp())}
    try:
        found = scan()
        value['full_sources'] = full_sources(found)
        value['files'] = {k: {x: y for x, y in v.items() if x != '_text'} for k, v in found.items()}
    except Exception as error:
        value['files'] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    for key, call in (('image_tools', image_tools), ('light_images', light_images)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__}
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
