"""Read-only probe on the server for SEO-PLAN-003 item 7 (social links at the bottom of every page).

Reads only, sanitized (credential-like lines redacted, foreign URLs and long numbers masked):
- the shared page-write hook and the SEO modules in full (site_ge_inject, ua_seo_index, ua_seo_metadata, ua_seo_schema);
- which top-level modules call inject_html or write pages (file, sha256, matching lines);
- the footer (or the end of <body>) of one page of every kind, and the count of pages per folder.
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
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org|auto\.ria\.com|t\.me|instagram\.com|'
                          r'youtube\.com|wa\.me|viber\.click|maps\.app\.goo\.gl)(?:[/\'"\s?]|$)')
FULL = ('site_ge_inject.py', 'ua_seo_index.py', 'ua_seo_metadata.py', 'ua_seo_schema.py', 'ua_seo_header.py')
NEEDLE = re.compile(r'inject_html|</footer>|site-footer|<footer')
PAGES = ('video/index.html', 'video/katalog.html', 'video/podbor.html', 'video/info.html', 'video/privacy.html',
         'video/UA-0001.html', 'video/ua/UA-0001.html', 'video/ru/UA-0001.html', 'video/UA-0001-diag.html',
         'video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html', 'video/seo/ua/kredyt-lizynh-avto.html',
         'video/seo/gu/avtomobili-koreidan-sakartveloshi.html', 'site/index.html', 'site/podbor.html', 'site/UA-0001.html')
FOLDERS = ('video', 'video/ua', 'video/ru', 'video/seo/ua', 'video/seo/ru', 'video/seo/gu', 'video/gu', 'site')
SKIP_DIRS = {'backups', 'autopilot_inbox', 'node_modules', 'video', 'site', '__pycache__', 'archive'}


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


def full_sources():
    result = {}
    for name in FULL:
        text = text_of(HOME / name)
        result[name] = None if text is None else {'sha256': hashlib.sha256(text.encode()).hexdigest(),
                                                  'source': sanitized(text)}
    return result


def callers():
    found = {}
    for path in sorted(HOME.glob('*.py')):
        text = text_of(path)
        if text is None or not NEEDLE.search(text):
            continue
        lines = text.splitlines()
        found[path.name] = {'sha256': hashlib.sha256(text.encode()).hexdigest(),
                            'lines': [{'line': n + 1, 'text': sanitized_line(l)[:300]}
                                      for n, l in enumerate(lines) if NEEDLE.search(l)][:40]}
    return found


def footer(path):
    text = text_of(HOME / path)
    if text is None:
        return None
    start = text.rfind('<footer')
    end = text.rfind('</body>')
    piece = text[start:end + 7] if start >= 0 else text[max(0, end - 2500):end + 7]
    return {'bytes': len(text.encode()), 'has_footer': start >= 0, 'footers': text.count('<footer'),
            'end': sanitized(piece)[:4000]}


def counts():
    result = {}
    for folder in FOLDERS:
        base = HOME / folder
        result[folder] = len(list(base.glob('*.html'))) if base.is_dir() else None
    return result


def report(home=None):
    global HOME
    if home is not None:
        HOME = home
    return {'status': 'PASS', 'sources': full_sources(), 'callers': callers(),
            'footers': {p: footer(p) for p in PAGES}, 'counts': counts()}


# R2 (SOCIAL-LINKS-001 installed 2026-11-10): which public pages carry the icon row now.
ROW = '<!--UA-SOCIAL-V1-->'
GROUPS = {'cards': ('video', r'UA-[0-9]{4,}\.html'), 'diag': ('video', r'UA-[0-9]{4,}-diag\.html'),
          'cards_ua': ('video/ua', r'UA-[0-9]{4,}\.html'), 'cards_ru': ('video/ru', r'UA-[0-9]{4,}\.html'),
          'landings_ua': ('video/seo/ua', r'.+\.html'), 'landings_ru': ('video/seo/ru', r'.+\.html'),
          'landings_gu': ('video/seo/gu', r'.+\.html'), 'top': ('video', r'(?!UA-).+\.html')}


def report_r2(home=None):
    global HOME
    if home is not None:
        HOME = home
    result = {}
    for group, (folder, pattern) in GROUPS.items():
        base = HOME / folder
        names = sorted(p.name for p in base.glob('*.html') if re.fullmatch(pattern, p.name)) if base.is_dir() else []
        missing, double = [], []
        for name in names:
            count = (text_of(base / name) or '').count(ROW)
            if count == 0:
                missing.append(name)
            elif count > 1:
                double.append(name)
        result[group] = {'pages': len(names), 'with_row': len(names) - len(missing) - len(double),
                         'missing': missing[:40], 'double': double}
    return {'status': 'PASS', 'rows': result}


# R3: why cards did not get the row — the card builder's approved external hosts, the CRM sync ledger
# (pending retries with their errors, last success) and card page times.
def report_r3(home=None):
    global HOME
    if home is not None:
        HOME = home
    import ast
    hosts = None
    spec = text_of(HOME / 'ua_additional_spec.py')
    if spec:
        for node in ast.parse(spec).body:
            if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == '_UA115_APPROVED_HOSTS' for t in node.targets):
                hosts = sorted(ast.literal_eval(node.value))
    state = {}
    raw = text_of(HOME / '.crm_public_sync_state.json')
    if raw:
        value = json.loads(raw)
        state = {'last_success': value.get('last_success'), 'catalog_retry': {k: v for k, v in (value.get('catalog_retry') or {}).items()
                                                                                if k != 'source_revision'},
                 'retry': {k: {f: (sanitized_line(str(v)) [:300] if f in ('error', 'message', 'last_error') else v)
                               for f, v in item.items() if f != 'sha256'} for k, item in (value.get('retry') or {}).items()}}
    times = {}
    for folder in ('video', 'video/ua', 'video/ru'):
        base = HOME / folder
        if base.is_dir():
            times[folder] = {p.name: round(p.stat().st_mtime) for p in sorted(base.glob('UA-*.html'))}
    return {'status': 'PASS', 'approved_hosts': hosts, 'sync': state, 'times': times, 'rows': report_r2(HOME)['rows']}


# R4: card language versions — catalogue link forms and their targets, versions on disk, sitemap card URLs.
def report_r4(home=None):
    global HOME
    if home is not None:
        HOME = home
    video = HOME / 'video'
    catalog = text_of(video / 'katalog.html') or ''
    hrefs = re.findall(r'href=["\']((?:[^"\']*/)?UA-[0-9]{4,}\.html)["\']', catalog)
    forms = {}
    for href in hrefs:
        forms.setdefault('ua/' if href.startswith('ua/') else 'other' if '/' in href else 'plain', set()).add(href)
    broken = sorted(h for h in set(hrefs) if not (video / h.split('/video/')[-1]).is_file())
    sitemap = text_of(video / 'sitemap.xml') or ''
    locs = re.findall(r'<loc>([^<]+)</loc>', sitemap)
    cards = [l for l in locs if re.search(r'UA-[0-9]{4,}\.html$', l)]
    by_form = {}
    for loc in cards:
        key = '/video/ua/' if '/video/ua/' in loc else '/video/ru/' if '/video/ru/' in loc else '/video/'
        by_form[key] = by_form.get(key, 0) + 1
    return {'status': 'PASS',
            'catalog_links': {k: sorted(v) for k, v in forms.items()}, 'catalog_links_broken': broken,
            'versions': {d: sorted(p.name for p in (video / d).glob('UA-*.html')) for d in ('ua', 'ru') if (video / d).is_dir()},
            'sitemap': {'urls': len(locs), 'card_urls': by_form, 'cards': sorted(cards)[:80]},
            'katalog_mtime': round((video / 'katalog.html').stat().st_mtime) if (video / 'katalog.html').is_file() else None}


# R5 (after CARD-SYNC-FIX2-INSTALL-20261111-R2): rows, sync retries and versions in one read.
def report_r5(home=None):
    r3, r4 = report_r3(home), report_r4(home)
    return {'status': 'PASS', 'rows': r3['rows'], 'sync': r3['sync'], 'approved_hosts': r3['approved_hosts'],
            'versions': r4['versions'], 'catalog_links_broken': r4['catalog_links_broken'], 'sitemap': r4['sitemap']}


# R6 (owner 2026-11-12: the Korea ticker legend is not on the site): why video/korea/ticker.html is not rewritten.
def _file(path):
    if not path.exists():
        return None
    st = path.stat()
    return {'bytes': st.st_size, 'mtime': round(st.st_mtime)}


def _tail(path, lines=40):
    text = text_of(path) if path.is_file() else None
    if text is None:
        return None
    return [sanitized_line(l)[:300] for l in text.splitlines()[-lines:]]


def report_r6(home=None):
    global HOME
    if home is not None:
        HOME = home
    import glob
    out = HOME / 'video/korea'
    ticker = text_of(out / 'ticker.html') or ''
    package = {}
    for path in sorted((HOME / 'korea_auction').glob('*.py')) if (HOME / 'korea_auction').is_dir() else []:
        text = text_of(path) or ''
        package[path.name] = {'sha256': hashlib.sha256(text.encode()).hexdigest(), 'mtime': round(path.stat().st_mtime),
                              'kt_legend': text.count('kt-legend')}
    data = HOME / 'korea_auction_data'
    logs = {}
    for pattern in ('/var/log/*1576351*', '/var/log/*/*1576351*', '/var/log/*sched*', '/var/log/tasks/*',
                    str(HOME / '*.log'), str(HOME / 'korea_auction_data/*.log'), str(HOME / 'logs/*korea*')):
        for name in sorted(glob.glob(pattern))[-6:]:
            path = Path(name)
            if path.is_file() and ('korea' in name or 'sched' in name or 'task' in name or '1576351' in name):
                logs[name] = _tail(path)
    var_log = sorted(p.name for p in Path('/var/log').iterdir())[:80] if Path('/var/log').is_dir() else None
    login = HOME / 'jpauto_login.txt'
    job = text_of(HOME / 'korea_ticker_job.py')
    return {'status': 'PASS',
            'ticker_html': dict(_file(out / 'ticker.html') or {}, kt_legend=ticker.count('kt-legend')),
            'lots_json': _file(out / 'lots.json'), 'package': package,
            'data_dir': {p.name: _file(p) for p in sorted(data.iterdir())[:40]} if data.is_dir() else None,
            'lock': _file(HOME / '.korea_auction_job.lock'),
            'login_lines': len([l for l in (text_of(login) or '').splitlines() if l.strip()]) if login.is_file() else None,
            'job_script': sanitized(job)[:2000] if job else None, 'logs': logs, 'var_log': var_log}


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
        value = report_r6()  # R6 ticker; report_r5() R5, report_r4() R4, report_r3() R3, report_r2() R2, report() R1
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
