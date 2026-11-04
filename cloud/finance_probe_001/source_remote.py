"""Read-only probe on the server for FINANCE-001 (tasks/FINANCE-001.md).

Returns, sanitized (credential-like lines redacted, foreign URLs and long numbers masked), the modules the
finance release will touch or rely on: the order package (web route, storage), the CRM bot «Клиенты» screen,
the landing generator and card post-processing, the card public sync (why republishing fails), and the WSGI
lines that mount the order API. Only the storage kind is read from the order settings, never other values.
Each file's sha256 is kept for a later exact edit. Nothing is written outside this run's own receipt.
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
WSGI = Path('/var/www/www_uaart_com_ua_wsgi.py')
SETTINGS = HOME / 'order_requests/settings.json'
FULL = ('ua_order/web.py', 'ua_order/repository.py', 'ua_order/mysql_repository.py', 'ua_order/mysql_schema.py',
        'ua_order/runtime.py', 'ua_order/host.py', 'ua_order/crm.py', 'ua_order/telegram.py', 'ua_order/bindings.py',
        'ua_order/rate_limit.py', 'ua_site_leads.py', 'ua_seo_landings.py', 'ua_seo_order_models.py',
        'ua_seo_metadata.py', 'ua_seo_sitemap.py', 'ua_seo_schema.py', 'ua_card_lang.py', 'ua_card_lang_job.py',
        'ua_crm_public_sync.py', 'ua_google_tag.py', 'video/order/order-strings.json', 'video/podbor.html',
        # R2: the order page styles the card buttons depend on, and the site's own click analytics.
        'video/order/order.css', 'video/order/gallery.css', 'video/order/quick-lead.css', 'video/order/model-price.css',
        'analitika_yadro.py', 'analitika_wsgi.py',
        # R6: the catalog design guard that refuses card publications (TASK090 SHELL_FINGERPRINT_MISMATCH).
        'catalog_design_guard.py')
# Large files: only the matching lines (with their numbers) and the hash.
PARTIAL = {
    'cars_ui.py': re.compile(r'def clients_screen|Заявки с сайта|Заявки из бота|ua_site_leads|cards_clients|^def register'),
    # R3: how the language script treats per-language pages (/video/ua/, /video/ru/, /video/seo/) and the header.
    'video/ua-site-languages.js': re.compile(r'Поставити запитання|Задать вопрос|vopros|card_texts|/video/ua/|/video/ru/|seo/|'
                                             r'shapka|versioned|switcher|data-site-lang|langButtons|function choose'),
    'stranica.py': re.compile(r"id='vopros'|kn_kupit|vtoraya"),
}
SYNC_STATE = HOME / '.crm_public_sync_state.json'
UA115 = re.compile(r'UA115|UNAPPROVED_EXTERNAL_HOST')
GUARD = re.compile(r'SEO068 canonical|TASK090_CATALOG_CONTRACT|SHELL_FINGERPRINT')
MAX_SOURCE = 900 * 1024
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org|googletagmanager\.com|t\.me)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def read(path):
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    return raw if len(raw) <= MAX_SOURCE else None


def full(path):
    raw = read(path)
    return None if raw is None else {
        'sha256': hashlib.sha256(raw).hexdigest(),
        'source': '\n'.join(sanitized_line(line) for line in raw.decode('utf-8', 'replace').splitlines())}


def lines(path, pattern, context=0):
    if not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    text = raw.decode('utf-8', 'replace').splitlines()
    hits = sorted({i for n, l in enumerate(text) if pattern.search(l)
                   for i in range(max(0, n - context), min(len(text), n + context + 1))})
    return {'sha256': hashlib.sha256(raw).hexdigest(),
            'lines': [{'line': n + 1, 'text': sanitized_line(text[n])[:400]} for n in hits][:300]}


def storage_kind():
    try:
        return json.loads(SETTINGS.read_text(encoding='utf-8')).get('storage')
    except Exception as error:
        return type(error).__name__


def sync_state():
    """Only the failure picture: retry/error keys and their values, sanitized and bounded."""
    try:
        value = json.loads(SYNC_STATE.read_text(encoding='utf-8'))
    except Exception as error:
        return type(error).__name__
    keep = {k: v for k, v in value.items() if re.search(r'retr|error|fail|last', k, re.I)}
    # R5: when the sync tries each card again (seconds from now) and its current error, unmasked times.
    import time
    now = time.time()
    retry = value.get('retry') or {}
    schedule = {key: {'count': item.get('count'), 'next_in_seconds': round(float(item.get('after') or 0) - now),
                      'error': sanitized_line(str(item.get('error', '')))[:220]}
                for key, item in retry.items() if isinstance(item, dict)}
    last = value.get('last_success') or {}
    return {'state': sanitized_line(json.dumps(keep, ensure_ascii=False, sort_keys=True))[:12000],
            'schedule': schedule, 'last_success_ago_seconds': round(now - float(last.get('at') or 0)) if last else None}


def home_header():
    """Stage 5: the home page's top block as visitors get it (a public page: kept as it is, not masked) — the
    <header class="site-header"> markup, the page's own <style> text and its stylesheet links — so the landing
    pages can carry the same block."""
    path = HOME / 'video/index.html'
    if not path.is_file():
        return None
    page = path.read_text(encoding='utf-8', errors='replace')
    header = re.search(r'<header class="site-header">.*?</header>', page, re.S)
    styles = re.findall(r'<style[^>]*>(.*?)</style>', page, re.S)
    links = re.findall(r'<link[^>]+rel=["\']stylesheet["\'][^>]*>', page)
    css = HOME / 'video/ua-v203.css'  # the site stylesheet the home page links (public, kept as it is)
    script = HOME / 'video/ua-site-languages.js'
    language_lines = [l.strip()[:300] for l in script.read_text(encoding='utf-8', errors='replace').splitlines()
                      if re.search(r'searchParams|URLSearchParams|[?&]lang=|function valid|localStorage', l)][:40] \
        if script.is_file() else None
    return {'stylesheet': css.read_text(encoding='utf-8', errors='replace')[:400000] if css.is_file() else None,
            'language_lines': language_lines,
            'sha256': hashlib.sha256(page.encode()).hexdigest(), 'header': header.group(0) if header else None,
            'styles': [s for s in styles if 'header' in s or 'brand' in s or 'lang-toggle' in s][:6],
            'stylesheets': links[:20]}


def shell_diff():
    """R7: the catalog shell (page outside the card region) of the golden file and of the live catalog, normalized
    as catalog_design_guard does, split at tags, and their difference (stdlib difflib); read only."""
    import difflib
    import importlib.util
    path = HOME / 'catalog_design_guard.py'
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location('probe_catalog_guard', path)
    guard = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[spec.name] = guard  # its dataclasses look the module up while it loads
    spec.loader.exec_module(guard)
    def parts(name):
        text = guard._normalize_shell((HOME / name).read_text(encoding='utf-8', errors='replace'))
        return [sanitized_line(x)[:300] for x in re.split(r'(?=<)', text) if x.strip()]
    golden, live = parts('catalog_design_golden.html'), parts('video/katalog.html')
    lines = list(difflib.unified_diff(golden, live, 'golden', 'katalog', n=1, lineterm=''))
    return {'golden_parts': len(golden), 'live_parts': len(live), 'diff': lines[:400]}


def report(home=None, wsgi=None):
    global HOME, SETTINGS, SYNC_STATE
    if home is not None:
        HOME, SETTINGS, SYNC_STATE = home, home / 'order_requests/settings.json', home / '.crm_public_sync_state.json'
    files = {name: full(HOME / name) for name in FULL}
    files.update({name: lines(HOME / name, pattern, 3) for name, pattern in PARTIAL.items()})
    files['wsgi'] = lines(wsgi or WSGI, re.compile(r'ua_order|mount|import|application'))
    ua115 = {}
    for path in sorted(HOME.glob('*.py')):
        found = lines(path, UA115, 6)
        if found and found['lines']:
            ua115[path.name] = found
    # R4: the publication check that refuses a card whose canonical is not /video/UA-XXXX.html (SEO068 canonical).
    guard = {}
    for path in sorted(HOME.glob('*.py')):
        found = lines(path, GUARD, 30)
        if found and found['lines']:
            guard[path.name] = found
    video = HOME / 'video'
    cards = sorted(p for p in video.glob('UA-*.html') if re.fullmatch(r'UA-[0-9]{4,}\.html', p.name))
    linked = [p.name for p in cards if 'id="ua-finance-link"' in p.read_text(encoding='utf-8', errors='replace')]
    # The language versions visitors and search engines open (CARD-LANG-001), and when each was written.
    versions = {}
    for folder in ('ua', 'ru'):
        for p in sorted((video / folder).glob('UA-*.html')):
            text = p.read_text(encoding='utf-8', errors='replace')
            versions['%s/%s' % (folder, p.name)] = {'link': 'id="ua-finance-link"' in text, 'mtime': round(p.stat().st_mtime)}
    shells = {}
    for name in ('video/katalog.html', 'catalog_design_golden.html'):
        path = HOME / name
        if path.is_file():
            raw = path.read_bytes()
            shells[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                            'mtime': round(path.stat().st_mtime)}
    shells['diff'] = shell_diff()
    shells['home_header'] = home_header()
    catalog = (HOME / 'video/katalog.html')
    shells['catalog_cards'] = sorted(set(re.findall(r'href=["\'](?:[^"\']*/)?(UA-[0-9]{4,})\.html',
                                                    catalog.read_text(encoding='utf-8', errors='replace')))) if catalog.is_file() else None
    return {'status': 'PASS', 'files': files, 'cards_with_finance_link': linked, 'card_versions': versions, 'cards_total': len(cards), 'shells': shells, 'order_storage': storage_kind(), 'sync_state': sync_state(),
            'ua115_sources': ua115, 'guard_sources': guard}


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
