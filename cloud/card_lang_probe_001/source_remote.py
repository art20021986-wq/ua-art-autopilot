"""Read-only probe on the server: how car card pages are generated and which language Google gets (CARD-LANG-PROBE).

Reads only. The card page generator and the modules that touch card HTML, the sitemap and the language
script's loader are returned in full, sanitized (credential-like lines redacted, foreign URLs and long numbers
masked). R1 read the card generator and sample pages; R2 read the language script and the card
writers; R3 lists every Google Maps link in the top-level modules and public pages; R4 reads the files and image sizes for the speed work; R5 the routing, sitemap, home and order page sources; R6 the catalogue readers and page writers; R7 the landing and sitemap sources for SEO-KOREA-001. Each file's sha256 is kept for a later exact edit.
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
# R7 (20261111): landing writer, hub texts, order models, sitemap and metadata modules, korea.html, for SEO-KOREA-001.
FULL = ('ua_seo_landings.py', 'ua_seo_hub_texts.py', 'ua_seo_order_models.py', 'ua_seo_sitemap.py', 'ua_seo_metadata.py',
        'ua_seo_index.py', 'video/korea.html', 'video/seo/ua/kia-sportage-koreya-kyiv.html')
# R3 (MAPS): every Google Maps link in the top-level modules and public pages (public URLs, not masked).
MAPS = re.compile(r'https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)[^\s\'"<>)\\]*')
PARTIAL = {name: re.compile(r'web_app|WebAppInfo|telegram-web-app') for name in
           ('client_ui.py', 'lead_bot.py', 'team_bot.py', 'cars_ui.py', 'yadro.py', 'card_html.py')}
MEDIA = ('video/stage/*.webp', 'video/opt/*.webp')
# R5: which top-level modules write the home stage images or link the order page styles.
# R6: modules that read card links from pages, or write the home page or the order page.
SCAN = re.compile(r'UA-\[0-9\]|UA-\\d|katalog\.html|index\.html|podbor\.html')
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
    maps = {}
    for path in sorted(list(HOME.glob('*.py')) + list((HOME/'video').glob('*.html')) + list((HOME/'site').glob('*.html'))):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SOURCE:
            found = MAPS.findall(path.read_text(encoding='utf-8', errors='replace'))
            if found:
                maps[str(path.relative_to(HOME))] = {url: found.count(url) for url in sorted(set(found))}
    scan = {}
    for path in sorted(HOME.glob('*.py')):
        if path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_SOURCE:
            lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
            found = [{'line': n + 1, 'text': sanitized_line(l)[:240]} for n, l in enumerate(lines) if SCAN.search(l)]
            if found:
                scan[path.name] = found[:60]
    return {'status': 'PASS', 'files': files, 'maps': maps, 'media': media(), 'scan': scan}


def media():
    """R4: image sizes for the speed work, and whether Pillow on the server can write WebP."""
    try:
        from PIL import Image, features
        webp = bool(features.check('webp'))
    except Exception as error:
        return {'pillow': type(error).__name__}
    sizes = {}
    for pattern in MEDIA:
        for path in sorted(HOME.glob(pattern))[:60]:
            try:
                with Image.open(path) as image:
                    sizes[str(path.relative_to(HOME))] = [image.width, image.height, path.stat().st_size]
            except Exception as error:
                sizes[str(path.relative_to(HOME))] = type(error).__name__
    folders = sorted(p.name for p in (HOME/'video/foto/UA-0013').iterdir() if p.is_dir()) if (HOME/'video/foto/UA-0013').is_dir() else []
    return {'pillow': Image.__version__ if hasattr(Image, '__version__') else 'yes', 'webp': webp,
            'sizes': sizes, 'card_folders': folders}


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
