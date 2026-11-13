"""Read-only analytics audit on the server (ANALYTICS-AUDIT-PROBE).

R6 (2026-11-13, ANALYTICS-DIRECT-001): report() breaks down the «direct / unknown» visits: GA4 Direct sessions by
landing page, device, browser and hour; own counter sessions with no source; the access log's first page request of
each visitor-day without a referrer by app (in-app browser user-agent), click id in the address and landing page.
R5 (old order page) is report_r5. R4 (2026-11-12, owner enabled the Google Analytics Data API): report_r4() asks only the Data API (read-only scope)
for 14-day totals. R3 (2026-11-08, after OWN-COUNTER-INSTALL): counter coverage, live pages, the public /ua/a.js
fix and the installed modules; report_r3/report_r2/report_r1 stay for reference.
R2 (owner «Да» 2026-11-07 to put the own counter on every page and fix its source and time): reads the current
counter, Google tag and page-writer sources (sanitized) and lists which pages lack the own counter. R1 sections
below stay for reference; report() runs the R2 reading only.

1. Public HTML files: which carry the own counter (/ua/a.js) and the Google tag, by page kind.
2. Live pages from the sitemap, fetched as a phone: the same two markers in what visitors are served.
3. Web app access logs: per-day human visitors (robots and our own checks left out) and how many of them
   reached the own counter (sent at least one /ua/a/e beacon). IP and browser are hashed in memory per day
   and never saved.
4. analytics.db opened read-only: per-day totals only.
5. Google Analytics Data API (read-only scope): per-day totals, channels and top pages.
Nothing is written outside this run's own receipt. No personal data is returned.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import sqlite3
import time
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
PUBLIC = (HOME/'video', HOME/'site')
SITE = 'https://www.uaart.com.ua'
LOG = Path('/var/log/www.uaart.com.ua.access.log')
DB = HOME/'analytics.db'
KEYS = tuple(HOME/('uaart-autopilot-110fb4d36d23' + ext) for ext in ('.json', '', '.txt'))
PROPERTY = 'properties/560695713'
DATA = 'https://analyticsdata.googleapis.com/v1beta/%s:runReport' % PROPERTY
TAG = 'G-6SRBQK6GY4'
OWN = '/ua/a.js'
DAYS = 14
PHONE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) '
         'Version/18.0 Mobile/15E148 Safari/604.1')
ROBOT = re.compile(r'bot|crawl|spider|slurp|python|curl|wget|headless|ua-?art|task\d|probe|monitor|preview|'
                   r'externalhit|http|java|okhttp|scrapy|lighthouse|go-|axios|node|feed|scan|fetch|meta-|'
                   r'chatgpt|perplexity|claude|^-?$', re.I)
LINE = re.compile(r'^(\S+) .*?\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "([^"]*)" "([^"]*)"')
SOURCES = (('google', ('google.',)), ('bing', ('bing.com',)), ('chatgpt', ('chatgpt.com', 'openai.com')),
           ('facebook', ('facebook.com', 'fb.com')), ('instagram', ('instagram.com',)),
           ('telegram', ('t.me', 'telegram.')), ('tiktok', ('tiktok.com',)), ('youtube', ('youtube.com', 'youtu.be')),
           ('autoria', ('auto.ria.com',)), ('olx', ('olx.ua',)))


def kind(relative):
    name = relative.rsplit('/', 1)[-1].lower()
    if '/preview/' in '/' + relative:
        return 'preview'
    if re.match(r'ua-\d+.*-diag', name):
        return 'diag'
    if re.match(r'ua-\d+', name):
        return 'card'
    if 'podbor' in name or '/order/' in '/' + relative:
        return 'order'
    if name in ('index.html', 'katalog.html', 'info.html', 'sravnenie.html'):
        return 'core'
    if name.startswith('google') and len(name) < 30:
        return 'verification'
    return 'landing'


def page_files():
    """{url path: (kind, own, tag)} for every public HTML file."""
    files = {}
    for root in PUBLIC:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.html')):
            if path.is_symlink() or not path.is_file():
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            relative = str(path.relative_to(HOME))
            files['/' + relative] = (kind(relative), OWN in text, TAG in text)
    return files


def coverage(files):
    by_kind, without_own, without_tag = {}, [], []
    for url, (name, own, tag) in files.items():
        row = by_kind.setdefault(name, {'html': 0, 'own': 0, 'google': 0, 'both': 0, 'none': 0})
        row['html'] += 1
        row['own'] += own
        row['google'] += tag
        row['both'] += own and tag
        row['none'] += not own and not tag
        if name != 'preview':
            if not own:
                without_own.append(url)
            if not tag:
                without_tag.append(url)
    return {'by_kind': by_kind, 'without_own_counter': without_own[:150], 'without_google_tag': without_tag[:150]}


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': PHONE, 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(4 * 1024 * 1024).decode('utf-8', 'replace')
    except urllib.error.HTTPError as error:
        return error.code, ''
    except Exception as error:
        return type(error).__name__, ''


def live():
    status, sitemap = fetch(SITE + '/sitemap.xml')
    urls = [u for u in re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', sitemap) if u.startswith(SITE + '/')][:80]
    for extra in ('/', '/video/index.html', '/video/katalog.html', '/video/podbor.html'):
        if SITE + extra not in urls:
            urls.append(SITE + extra)
    pages = {}
    for url in urls:
        code, text = fetch(url)
        pages[url[len(SITE):]] = {'http': code, 'own': OWN in text, 'google': TAG in text}
    return {'sitemap_http': status, 'pages': pages,
            'summary': {'pages': len(pages), 'own': sum(p['own'] for p in pages.values()),
                        'google': sum(p['google'] for p in pages.values())}}


def log_texts():
    found = {}
    for suffix in [''] + ['.1'] + ['.%d.gz' % n for n in range(2, 15)]:
        path = Path(str(LOG) + suffix)
        try:
            raw = path.read_bytes()
            if suffix.endswith('.gz'):
                raw = gzip.decompress(raw)
        except (OSError, EOFError) as error:
            found[suffix or 'current'] = {'error': type(error).__name__}
            if suffix not in ('', '.1'):
                break
            continue
        found[suffix or 'current'] = {'text': raw.decode('utf-8', 'replace')}
    return found


def source(referrer, path):
    match = re.search(r'utm_source=([\w.-]{1,40})', path)
    if match:
        return 'utm:' + match.group(1).lower()
    host = re.sub(r'^https?://', '', referrer).split('/')[0].split(':')[0].lower()
    if not host or host == '-':
        return 'direct'
    if host.endswith('uaart.com.ua'):
        return 'internal'
    for label, needles in SOURCES:
        if any(n in host for n in needles):
            return label
    return 'other'


def file_for(path, files):
    clean = path.split('?')[0].split('#')[0]
    if clean.endswith('/'):
        clean += 'index.html'
    return files.get(clean)


def is_page(path):
    clean = path.split('?')[0]
    return clean.endswith(('.html', '/')) or '.' not in clean.rsplit('/', 1)[-1]


def access(texts, files):
    days = {}
    for text in texts:
        for line in text.splitlines():
            match = LINE.search(line)
            if not match:
                continue
            ip, day, method, path, status, referrer, agent = match.groups()
            day = time.strftime('%Y-%m-%d', time.strptime(day, '%d/%b/%Y'))
            d = days.setdefault(day, {'visitors': {}, 'robot_requests': 0, 'page_views': 0, 'beacons': 0,
                                      'own_script_loads': 0, 'kinds': Counter(), 'unknown_pages': Counter()})
            if ROBOT.search(agent):
                d['robot_requests'] += 1
                continue
            visitor = hashlib.sha256((day + ip + agent).encode()).hexdigest()[:16]
            entry = d['visitors'].setdefault(visitor, {'pages': 0, 'beacon': False, 'own_page': False,
                                                       'google_page': False, 'first': None, 'source': 'direct',
                                                       'mobile': bool(re.search('Mobile|Android|iPhone', agent))})
            clean = path.split('?')[0]
            if method == 'POST' and clean == '/ua/a/e':
                d['beacons'] += 1
                entry['beacon'] = True
                continue
            if clean == OWN:
                d['own_script_loads'] += 1
                continue
            if method != 'GET' or not is_page(path) or not status.startswith(('2', '3')):
                continue
            d['page_views'] += 1
            entry['pages'] += 1
            page = file_for(path, files)
            name = page[0] if page else 'unmapped'
            d['kinds'][name] += 1
            if not page:
                d['unknown_pages'][clean[:120]] += 1
            if entry['first'] is None:
                entry['first'] = name
                entry['first_own'] = bool(page and page[1])
            entry['own_page'] |= bool(page and page[1])
            entry['google_page'] |= bool(page and page[2])
            label = source(referrer, path)
            if entry['source'] in ('direct', 'internal') and label not in ('direct', 'internal'):
                entry['source'] = label
    daily, unmapped = {}, Counter()
    for day, d in sorted(days.items())[-DAYS:]:
        people = [v for v in d['visitors'].values() if v['pages']]
        unmapped.update(d['unknown_pages'])
        daily[day] = {'human_visitors': len(people), 'human_page_views': d['page_views'],
                      'reached_own_counter': sum(v['beacon'] for v in people),
                      'saw_page_with_own_counter': sum(v['own_page'] for v in people),
                      'saw_page_with_google_tag': sum(v['google_page'] for v in people),
                      'landed_on': dict(Counter(v['first'] for v in people)),
                      'landed_without_own_counter': sum(not v.get('first_own') for v in people),
                      'mobile': sum(v['mobile'] for v in people), 'sources': dict(Counter(v['source'] for v in people)),
                      'one_page_only': sum(v['pages'] == 1 for v in people),
                      'page_views_by_kind': dict(d['kinds']), 'beacons': d['beacons'],
                      'own_script_loads': d['own_script_loads'], 'robot_requests': d['robot_requests']}
    return {'daily_utc': daily, 'unmapped_pages': unmapped.most_common(20)}


def own_db():
    if not DB.is_file():
        return {'error': 'MISSING'}
    connection = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, timeout=10)
    try:
        since = int(time.time()) - DAYS * 86400
        q = lambda sql: connection.execute(sql, (since,)).fetchall()
        daily = {}
        for day, visitors, sessions, views in q(
                "SELECT date(ts,'unixepoch'), COUNT(DISTINCT vid), COUNT(DISTINCT sid), "
                "SUM(tip IN ('page','card','diag')) FROM events WHERE ts>=? GROUP BY 1"):
            daily[day] = {'visitors': visitors, 'sessions': sessions, 'page_views': views}
        return {'daily_utc': daily, 'event_types': dict(q('SELECT tip, COUNT(*) FROM events WHERE ts>=? GROUP BY 1')),
                'sources': dict(q('SELECT istochnik, COUNT(*) FROM sessions WHERE nachalo>=? GROUP BY 1')),
                'oldest_event_utc': connection.execute("SELECT datetime(MIN(ts),'unixepoch') FROM events").fetchone()[0]}
    finally:
        connection.close()


def ga4():
    key = next((k for k in KEYS if k.is_file()), None)
    if not key:
        return {'error': 'KEY_MISSING'}
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(
        str(key), scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    credentials.refresh(Request())
    dates = [{'startDate': '%ddaysAgo' % (DAYS - 1), 'endDate': 'today'}]

    def run(dimensions, metrics, limit=40):
        body = {'dateRanges': dates, 'dimensions': [{'name': n} for n in dimensions],
                'metrics': [{'name': n} for n in metrics], 'limit': limit}
        request = urllib.request.Request(DATA, data=json.dumps(body).encode(), method='POST', headers={
            'Authorization': 'Bearer ' + credentials.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.loads(response.read())
        except urllib.error.HTTPError as error:
            return {'http': error.code, 'error': error.read(500).decode('utf-8', 'replace')}
        return [[c.get('value') for c in r.get('dimensionValues', []) + r.get('metricValues', [])]
                for r in value.get('rows', [])]
    return {'columns_daily': ['date', 'activeUsers', 'sessions', 'screenPageViews', 'eventCount'],
            'daily_kyiv': run(['date'], ['activeUsers', 'sessions', 'screenPageViews', 'eventCount']),
            'channels': run(['sessionDefaultChannelGroup'], ['activeUsers', 'sessions']),
            'sources': run(['sessionSource'], ['activeUsers', 'sessions'], 20),
            'pages': run(['pagePath'], ['screenPageViews', 'activeUsers'], 25),
            'devices': run(['deviceCategory'], ['activeUsers']),
            'events': run(['eventName'], ['eventCount'], 20)}


SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
FULL = ('analitika_wsgi.py', 'analitika_yadro.py', 'analitika_otchet.py', 'analitika_knopka.py', 'ua_google_tag.py',
        'ua_seo_index.py')
WSGI = Path('/var/www/www_uaart_com_ua_wsgi.py')
HASHED = ('ua_seo_metadata.py', 'publish_transaction_guard.py', 'master_card.py', 'stranica.py', 'publikaciya.py',
          'ua_seo_landings.py', 'ua_seo_finance.py', 'ua_crm_public_sync.py', 'ua_site_counters.py', 'analitika_bot.py')
NEEDLES = ('ua_google_tag', '-diag.html', "-diag'", '-diag"', 'UA-ANALIT', '/ua/a.js', 'SDVIG_KIEV')


def clean(line):
    return '[REDACTED]' if SECRET.search(line) else LONG_NUMBER.sub('[N]', line)


def sources():
    full, hashes, hits = {}, {}, {}
    for name in FULL:
        path = HOME/name
        full[name] = '\n'.join(clean(x) for x in path.read_text('utf-8', 'replace').splitlines()) if path.is_file() else None
    if WSGI.is_file():
        full[str(WSGI)] = '\n'.join(clean(x) for x in WSGI.read_text('utf-8', 'replace').splitlines())
    for name in HASHED + FULL:
        path = HOME/name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    recent = time.time() - 120 * 86400
    for path in sorted(HOME.glob('*.py')):
        try:
            if path.is_symlink() or path.stat().st_mtime < recent or path.stat().st_size > 2 * 1024 * 1024:
                continue
            lines = path.read_text('utf-8', 'replace').splitlines()
        except OSError:
            continue
        found = [{'line': n + 1, 'text': clean(lines[n])[:220]} for n in range(len(lines))
                 if any(x in lines[n] for x in NEEDLES)]
        if found:
            hits[path.name] = found[:40]
    stop = HOME/'analitika_stop.txt'
    return {'full': full, 'sha256': hashes, 'hits': hits,
            'analitika_stop': {'exists': stop.exists(),
                               'mtime_utc': time.strftime('%Y-%m-%d %H:%M', time.gmtime(stop.stat().st_mtime))
                               if stop.exists() else None}}


def pages_without_own(files):
    return {url: {'kind': k, 'google': g} for url, (k, own, g) in files.items() if not own and k != 'preview'}


def guarded(step, *args):
    try:
        return step(*args)
    except Exception as error:
        return {'error': type(error).__name__ + ':' + str(error)[:200]}


SCRIPT_MARK = 'UA-OWN-COUNTER-001'


def script():
    """R3: the public /ua/a.js after OWN-COUNTER-INSTALL carries the source fix."""
    code, text = fetch(SITE + '/ua/a.js?v=1&check=%d' % int(time.time()))
    return {'http': code, 'fixed': SCRIPT_MARK in text}


def installed():
    """R3: installed module hashes and whether the report days start at midnight in Kyiv."""
    value = {name: hashlib.sha256((HOME/name).read_bytes()).hexdigest() if (HOME/name).is_file() else None
             for name in ('ua_own_counter.py', 'ua_seo_metadata.py', 'ua_seo_index.py', 'analitika_yadro.py',
                          'analitika_otchet.py')}
    import importlib.util
    import datetime
    spec = importlib.util.spec_from_file_location('otchet_check', HOME/'analitika_otchet.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    start = datetime.datetime.fromtimestamp(module.granicy('today')[0], module._kiev())
    value['report_today_start_kiev'] = start.isoformat()
    return value


OLD_PODBOR = '/video/order/podbor.html'


def page_visits(texts, target=OLD_PODBOR):
    """Requests to one page by UTC day: people (IP+browser hashed in memory), views, robots, sources, statuses."""
    days = {}
    for text in texts:
        for line in text.splitlines():
            match = LINE.search(line)
            if not match or match.group(4).split('?')[0] != target:
                continue
            ip, day, method, path, status, referrer, agent = match.groups()
            day = time.strftime('%Y-%m-%d', time.strptime(day, '%d/%b/%Y'))
            d = days.setdefault(day, {'people': set(), 'views': 0, 'robots': 0, 'sources': Counter(), 'status': Counter()})
            d['status'][status] += 1
            if ROBOT.search(agent):
                d['robots'] += 1
                continue
            d['people'].add(hashlib.sha256((ip + agent).encode()).hexdigest()[:16])
            d['views'] += 1
            d['sources'][source(referrer, path)] += 1
    return {day: {'people': len(d['people']), 'views': d['views'], 'robots': d['robots'],
                  'sources': dict(d['sources']), 'status': dict(d['status'])} for day, d in sorted(days.items())}


def linked_from(target=OLD_PODBOR):
    """Public pages whose HTML links to the page (not drafts)."""
    found = []
    for folder in PUBLIC:
        for path in sorted(folder.rglob('*.html')):
            relative = path.relative_to(HOME).as_posix()
            if '/preview/' in '/' + relative or path.is_symlink():
                continue
            text = path.read_text('utf-8', 'replace')
            if 'order/podbor.html' in text:
                found.append(relative)
    return found[:100]


def report_r5():
    """R5 (owner «Да» 2026-11-13): who opens the old order page video/order/podbor.html, and what links to it."""
    logs = log_texts()
    texts = [v['text'] for v in logs.values() if 'text' in v]
    return {'status': 'PASS', 'log_files': len(texts), 'old_podbor': guarded(page_visits, texts),
            'linked_from': guarded(linked_from)}


APPS = (('telegram', re.compile(r'telegram', re.I)), ('instagram', re.compile(r'instagram', re.I)),
        ('facebook', re.compile(r'FBAN|FBAV|FB_IAB|FBIOS', re.I)), ('viber', re.compile(r'viber', re.I)),
        ('whatsapp', re.compile(r'whatsapp', re.I)), ('tiktok', re.compile(r'musical_ly|bytedance|tiktok', re.I)),
        ('google_app', re.compile(r'GSA/', re.I)), ('android_webview', re.compile(r'; wv\)')))
CLICK_IDS = ('fbclid', 'gclid', 'ttclid', 'utm_source', 'srsltid', 'igsh')
FIRST = re.compile(r'^(\S+) .*?\[(\d{2}/\w{3}/\d{4}):(\d{2}):[^\]]*\] "GET (\S+)[^"]*" (\d{3}) \S+ "([^"]*)" "([^"]*)"')


def app_of(agent):
    for name, pattern in APPS:
        if pattern.search(agent):
            return name
    if re.search(r'iPhone|iPad', agent) and 'Safari/' not in agent:
        return 'ios_in_app_unknown'
    return 'browser'


def bump(table, key):
    table[key] = table.get(key, 0) + 1


def top(table, n=15):
    return dict(sorted(table.items(), key=lambda x: -x[1])[:n])


def direct_log(texts):
    """First page request of each visitor-day (IP+browser hashed in memory, never kept) with no referrer."""
    seen = set()
    value = {'human_first_requests': 0, 'no_referrer': 0, 'robot_requests_no_referrer': 0, 'by_app': {},
             'by_click_id': {}, 'by_landing': {}, 'by_hour_utc': {}, 'by_device': {}}
    for text in texts:
        for row in text.splitlines():
            match = FIRST.match(row)
            if not match:
                continue
            ip, day, hour, path, status, referrer, agent = match.groups()
            if status[0] not in '23' or not is_page(path) or path.startswith(('/ua/', '/api/')):
                continue
            if ROBOT.search(agent):
                if referrer in ('', '-'):
                    value['robot_requests_no_referrer'] += 1
                continue
            key = hashlib.sha256((ip + '|' + agent + '|' + day).encode()).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            value['human_first_requests'] += 1
            if referrer not in ('', '-'):
                continue
            value['no_referrer'] += 1
            bump(value['by_app'], app_of(agent))
            bump(value['by_click_id'], ','.join(c for c in CLICK_IDS if c + '=' in path) or 'none')
            bump(value['by_landing'], path.split('?')[0])
            bump(value['by_hour_utc'], hour)
            bump(value['by_device'], 'mobile' if re.search(r'Mobile|Android|iPhone', agent) else 'desktop')
    value['by_landing'] = top(value['by_landing'])
    return value


def direct_own():
    connection = sqlite3.connect('file:%s?mode=ro' % DB, uri=True, timeout=10)
    try:
        rows = connection.execute(
            "SELECT s.istochnik, (SELECT stranica FROM events e WHERE e.sid=s.sid ORDER BY ts LIMIT 1), "
            "strftime('%H', s.nachalo, 'unixepoch') FROM sessions s WHERE s.nachalo>=?",
            (int(time.time()) - 30 * 86400,)).fetchall()
    finally:
        connection.close()
    value = {'sessions_30d': len(rows), 'by_source': {}, 'direct_landing': {}, 'direct_hour_utc': {}}
    for name, landing, hour in rows:
        bump(value['by_source'], name or '(empty)')
        if not name or name.startswith('Прямой'):
            bump(value['direct_landing'], (landing or '?').split('?')[0])
            bump(value['direct_hour_utc'], hour)
    value['direct_landing'] = top(value['direct_landing'])
    return value


def direct_ga4():
    key = next((k for k in KEYS if k.is_file()), None)
    if not key:
        return {'error': 'KEY_MISSING'}
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    credentials = service_account.Credentials.from_service_account_file(
        str(key), scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    credentials.refresh(Request())

    def run(dimensions, metric, limit=25, direct=True):
        body = {'dateRanges': [{'startDate': '29daysAgo', 'endDate': 'today'}],
                'dimensions': [{'name': n} for n in dimensions], 'metrics': [{'name': metric}],
                'limit': limit, 'orderBys': [{'metric': {'metricName': metric}, 'desc': True}]}
        if direct:
            body['dimensionFilter'] = {'filter': {'fieldName': 'sessionDefaultChannelGroup',
                                                  'stringFilter': {'value': 'Direct'}}}
        request = urllib.request.Request(DATA, data=json.dumps(body).encode(), method='POST', headers={
            'Authorization': 'Bearer ' + credentials.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                rows = json.loads(response.read()).get('rows', [])
        except urllib.error.HTTPError as error:
            return {'http': error.code, 'error': error.read(500).decode('utf-8', 'replace')}
        return [[c.get('value') for c in r.get('dimensionValues', []) + r.get('metricValues', [])] for r in rows]
    return {'channels_30d': run(['sessionDefaultChannelGroup'], 'sessions', direct=False),
            'source_medium_30d': run(['sessionSourceMedium'], 'sessions', direct=False),
            'direct_landing': run(['landingPage'], 'sessions'),
            'direct_device_browser': run(['deviceCategory', 'browser'], 'sessions'),
            'direct_hour': run(['hour'], 'sessions', 24),
            'direct_new_vs_returning': run(['newVsReturning'], 'sessions')}


def report():
    logs = log_texts()
    return {'status': 'PASS', 'google_analytics': guarded(direct_ga4), 'own': guarded(direct_own),
            'log': guarded(direct_log, [v['text'] for v in logs.values() if 'text' in v])}


def report_r4():
    return {'status': 'PASS', 'google_analytics': guarded(ga4)}


def report_r3():
    files = page_files()
    return {'status': 'PASS', 'files': coverage(files), 'live': guarded(live), 'script': guarded(script),
            'installed': guarded(installed), 'without_own': pages_without_own(files)}


def report_r2():
    files = page_files()
    return {'status': 'PASS', 'files': coverage(files), 'sources': guarded(sources),
            'without_own': pages_without_own(files)}


def report_r1():
    files = page_files()
    logs = log_texts()
    return {'status': 'PASS', 'files': coverage(files), 'live': guarded(live),
            'log_files': {k: ({'lines': v['text'].count('\n')} if 'text' in v else v) for k, v in logs.items()},
            'access': guarded(access, [v['text'] for v in logs.values() if 'text' in v], files),
            'own_analytics': guarded(own_db), 'google_analytics': guarded(ga4)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (300, 320))
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
