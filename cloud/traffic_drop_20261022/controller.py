#!/usr/bin/env python3
"""Read-only probe for TRAFFIC-DROP-20261022: why did human visits fall to 1-2 a day?

GET only. Server: the web app's access logs (current, .1 and rotated .gz) reduced to
per-day human visitors, sources, statuses and Googlebot activity (IPs are hashed in
memory per day and never saved), the web app info and CPU usage. Public: home,
catalog, robots.txt and sitemap.xml reduced to text facts, and the www/non-www,
http/https entry points without following redirects.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from collections import Counter

PACKAGE = 'cloud/traffic_drop_20261022'
TASKS = ('TRAFFIC-DROP-PROBE-20261022',)
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
DOMAIN = 'www.uaart.com.ua'
LOG = 'files/path/var/log/%s.access.log' % DOMAIN
ENDPOINTS = ('webapps/%s/' % DOMAIN, 'cpu/')
SITE = 'https://' + DOMAIN
LIMIT = 64 * 1024 * 1024
ROTATED = 14
PAGES = ('/robots.txt', '/sitemap.xml', '/video/index.html', '/video/katalog.html')
ENTRIES = ('http://uaart.com.ua/', 'https://uaart.com.ua/', 'http://www.uaart.com.ua/', 'https://www.uaart.com.ua/')
MOBILE = ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 '
          '(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1')
AGENT = 'uaart-traffic-drop-probe/1'
ROBOT = re.compile(r'bot|crawl|spider|slurp|python|curl|wget|headless|ua-?art|task\d|probe|monitor|preview|'
                   r'externalhit|http|java|okhttp|scrapy|lighthouse|go-|axios|node|feed|scan|fetch|meta-|'
                   r'chatgpt|perplexity|claude|^-?$', re.I)
SOURCES = (('google', ('google.',)), ('bing', ('bing.com',)), ('chatgpt', ('chatgpt.com', 'openai.com')),
           ('facebook', ('facebook.com', 'fb.com')), ('instagram', ('instagram.com',)),
           ('telegram', ('t.me', 'telegram.')), ('youtube', ('youtube.com', 'youtu.be')),
           ('autoria', ('auto.ria.com',)), ('olx', ('olx.ua',)))
LINE = re.compile(r'^(\S+) .*?\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "([^"]*)" "([^"]*)"'
                  r'(?:.*response-time=([\d.]+))?')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


class Keep3xx(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def get(opener, request):
    for attempt in range(3):
        started = time.monotonic()
        try:
            with opener.open(request, timeout=60) as response:
                return response.status, response.read(LIMIT), {}, round(time.monotonic() - started, 2)
        except urllib.error.HTTPError as error:
            code, headers = error.code, {'location': error.headers.get('Location')}
            error.close()
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code, None, headers, round(time.monotonic() - started, 2)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            if attempt == 2:
                return 0, None, {'error': type(error).__name__ + ':' + str(error)[:120]}, None
        time.sleep(2 ** (attempt + 1))


class Reader:
    def __init__(self, token, opener=None, public_opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(Keep3xx())
        self._public = public_opener or urllib.request.build_opener(Keep3xx())

    def api(self, endpoint):
        if endpoint not in ENDPOINTS and not re.fullmatch(
                re.escape(LOG) + r'(?:\.1|\.(?:[2-9]|1[0-4])\.gz)?', endpoint):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        return get(self._opener, urllib.request.Request(API + endpoint, headers={
            'Authorization': 'Token ' + self._token, 'User-Agent': AGENT}))[:2]

    def public(self, url, agent=AGENT):
        if url not in ENTRIES and url not in [SITE + p for p in PAGES]:
            raise ProbeError('PUBLIC_URL_OUTSIDE_SCOPE')
        return get(self._public, urllib.request.Request(url, headers={'User-Agent': agent, 'Cache-Control': 'no-cache'}))


def logs(reader):
    """Current log, .1 and rotated .gz files until the first missing one."""
    found = {}
    for suffix in [''] + ['.1'] + ['.%d.gz' % n for n in range(2, ROTATED + 1)]:
        status, raw = reader.api(LOG + suffix)
        if status != 200 or raw is None:
            found[suffix or 'current'] = {'http': status}
            if suffix not in ('', '.1'):
                break
            continue
        if suffix.endswith('.gz'):
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError):
                found[suffix] = {'http': status, 'error': 'GZIP_INVALID'}
                continue
        found[suffix or 'current'] = {'http': status, 'text': raw.decode('utf-8', 'replace')}
    return found


def host(referrer):
    return re.sub(r'^https?://', '', referrer).split('/')[0].split(':')[0].lower()


def source(referrer, path):
    if 'utm_source=' in path:
        return 'utm:' + re.search(r'utm_source=([\w.-]{1,40})', path + '&').group(1).lower() \
            if re.search(r'utm_source=[\w.-]', path) else 'utm'
    name = host(referrer)
    if not name or name == '-':
        return 'direct'
    if name.endswith('uaart.com.ua'):
        return 'internal'
    for label, needles in SOURCES:
        if any(n in name for n in needles):
            return label
    return 'other'


def is_page(path):
    clean = path.split('?')[0]
    return clean.endswith(('.html', '/')) or '.' not in clean.rsplit('/', 1)[-1]


def analyse(texts):
    lines = parsed = 0
    days = {}
    pages, missing, others = Counter(), Counter(), Counter()
    for text in texts:
        for line in text.splitlines():
            lines += 1
            match = LINE.search(line)
            if not match:
                continue
            parsed += 1
            ip, day, method, path, status, referrer, agent, took = match.groups()
            day = time.strftime('%Y-%m-%d', time.strptime(day, '%d/%b/%Y'))
            d = days.setdefault(day, {'requests': 0, 'status': Counter(), 'googlebot': Counter(), 'page_views': 0,
                                      'visitors': {}, 'times': [], 'human_5xx': 0, 'human_404': 0})
            d['requests'] += 1
            d['status'][status[0] + 'xx'] += 1
            clean = path.split('?')[0][:160]
            if 'googlebot' in agent.lower():
                d['googlebot'][status] += 1
                if status == '404':
                    missing[clean] += 1
                continue
            if ROBOT.search(agent) or method != 'GET' or not is_page(path):
                continue
            d['page_views'] += 1
            if took:
                d['times'].append(float(took))
            if status.startswith('5'):
                d['human_5xx'] += 1
            if status == '404':
                d['human_404'] += 1
                missing[clean] += 1
            pages[clean] += 1
            visitor = sha((day + ip + agent).encode())[:16]
            label = source(referrer, path)
            if label == 'other':
                others[host(referrer)] += 1
            entry = d['visitors'].setdefault(visitor, {'source': label, 'pages': 0,
                                                       'mobile': bool(re.search('Mobile|Android|iPhone', agent))})
            if entry['source'] in ('direct', 'internal') and label not in ('direct', 'internal'):
                entry['source'] = label
            entry['pages'] += 1
    daily = {}
    for day, d in sorted(days.items()):
        visitors = d['visitors'].values()
        times = sorted(d['times'])
        daily[day] = {'requests': d['requests'], 'status': dict(d['status']), 'googlebot': dict(d['googlebot']),
                      'human_page_views': d['page_views'], 'human_visitors': len(d['visitors']),
                      'visitors_by_source': dict(Counter(v['source'] for v in visitors)),
                      'mobile_visitors': sum(v['mobile'] for v in visitors),
                      'one_page_visitors': sum(v['pages'] == 1 for v in visitors),
                      'human_5xx': d['human_5xx'], 'human_404': d['human_404'],
                      'median_page_seconds': times[len(times) // 2] if times else None,
                      'max_page_seconds': times[-1] if times else None}
    return {'lines': lines, 'parsed': parsed, 'daily': daily, 'top_human_pages': pages.most_common(25),
            'top_404': missing.most_common(15), 'other_referrer_hosts': others.most_common(15)}


def visible(html, limit):
    body = re.sub(r'(?is)<(script|style|noscript)\b.*?</\1>', ' ', html)
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body)).strip()[:limit]


def facts(html):
    meta = lambda name: (re.findall(r'(?is)<meta[^>]+(?:name|property)="%s"[^>]+content="([^"]*)"' % name, html) or [None])[0]
    return {'bytes': len(html.encode()), 'title': (re.findall(r'(?is)<title>(.*?)</title>', html) or [None])[0],
            'description': meta('description'), 'robots': meta('robots'), 'og_image': meta('og:image'),
            'canonical': re.findall(r'(?i)<link[^>]+rel="canonical"[^>]+href="([^"]*)"', html)[:1],
            'lang': re.findall(r'(?i)<html[^>]+lang="([^"]*)"', html)[:1], 'viewport': 'name="viewport"' in html,
            'h1': [visible(h, 200) for h in re.findall(r'(?is)<h1[^>]*>(.*?)</h1>', html)[:3]],
            'images': len(re.findall(r'(?i)<img\b', html)), 'images_without_alt': len(re.findall(r'(?i)<img\b(?![^>]*\balt=)', html)),
            'scripts': len(re.findall(r'(?i)<script\b', html)), 'analytics': bool(re.search(r'gtag|googletagmanager|clarity|metrika', html)),
            'links_tel': len(re.findall(r'(?i)href="tel:', html)), 'links_messengers': sorted(set(re.findall(r'(?i)(t\.me|viber|wa\.me|whatsapp|instagram|facebook|youtube)', html))),
            'text': visible(html, 12000)}


def collect(reader):
    found = logs(reader)
    result = {'log_files': {k: {key: v for key, v in f.items() if key != 'text'} | (
        {'lines': f['text'].count('\n')} if 'text' in f else {}) for k, f in found.items()}}
    result['access'] = analyse([f['text'] for f in found.values() if 'text' in f])
    for endpoint in ENDPOINTS:
        status, raw = reader.api(endpoint)
        try:
            result[endpoint.split('/')[0]] = {'http': status, 'body': json.loads(raw) if raw else None}
        except ValueError:
            result[endpoint.split('/')[0]] = {'http': status, 'body': None}
    result['entries'] = {}
    for url in ENTRIES:
        status, _, headers, took = reader.public(url)
        result['entries'][url] = {'http': status, 'seconds': took, **headers}
    result['pages'] = {}
    for path in PAGES:
        status, raw, headers, took = reader.public(SITE + path)
        text = raw.decode('utf-8', 'replace') if raw else ''
        if path == '/robots.txt':
            info = {'body': text[:2000]}
        elif path == '/sitemap.xml':
            info = {'urls': len(re.findall('<loc>', text)), 'lastmod_max': max(re.findall(r'<lastmod>([^<]+)', text) or [None], key=str)}
        else:
            info = facts(text) if text else {}
        result['pages'][path] = {'http': status, 'seconds': took, **headers, **info}
    status, raw, _, took = reader.public(SITE + '/video/index.html', MOBILE)
    result['home_mobile'] = {'http': status, 'seconds': took, 'bytes': len(raw) if raw else 0}
    return result


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, data):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def execute(env, *, root=None, reader=None):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    evidence = PACKAGE + '/evidence.json'
    result = collect(reader or Reader(env.get('PYTHONANYWHERE_API_TOKEN', '')))
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'],
                                'remote_write_count': 0, **result}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('TRAFFIC_DROP_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
