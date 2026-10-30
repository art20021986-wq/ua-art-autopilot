#!/usr/bin/env python3
"""Read-only probe for AI-SEARCH-001: do search and AI crawlers reach uaart.com.ua?

GET only. Server: the web app's access logs (current, .1 and rotated .gz) reduced to
per-crawler and per-referrer counts, statuses, dates and top paths (no IPs, no
user data); the static-file route list. Public: robots.txt, home page and the two
hub landings reduced to text facts, and the home page fetched as each AI crawler.
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

PACKAGE = 'cloud/ai_search_probe_20261031'
TASKS = ('AI-SEARCH-PROBE-20261031',)  # repeat of 20261019, two weeks after AI-SEARCH-001
ROOT = Path(__file__).resolve().parents[2]
API = 'https://www.pythonanywhere.com/api/v0/user/Carix/'
DOMAIN = 'www.uaart.com.ua'
LOG = 'files/path/var/log/%s.access.log' % DOMAIN
SITE = 'https://' + DOMAIN
LIMIT = 64 * 1024 * 1024
ROTATED = 14
PAGES = ('/robots.txt', '/video/index.html', '/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html',
         '/video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html')
BOTS = ('GPTBot', 'OAI-SearchBot', 'ChatGPT-User', 'PerplexityBot', 'Perplexity-User', 'ClaudeBot',
        'Claude-SearchBot', 'Claude-User', 'Google-Extended', 'Googlebot', 'bingbot', 'Applebot',
        'DuckDuckBot', 'YandexBot', 'Amazonbot', 'meta-externalagent', 'CCBot', 'Bytespider')
AS_BOT = {'OAI-SearchBot': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot',
          'PerplexityBot': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)',
          'Claude-SearchBot': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; Claude-SearchBot/1.0; +https://www.anthropic.com)',
          'bingbot': 'Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm) Chrome/116.0 Safari/537.36'}
REFERRERS = {'chatgpt': ('chatgpt.com', 'chat.openai.com'), 'perplexity': ('perplexity.ai',),
             'copilot': ('copilot.microsoft.com',), 'gemini': ('gemini.google.com',), 'claude': ('claude.ai',),
             'bing': ('bing.com',), 'google': ('google.',)}
LINE = re.compile(r'\[(\d{2}/\w{3}/\d{4}):[^\]]*\] "(\S+) (\S+)[^"]*" (\d{3}) \S+ "([^"]*)" "([^"]*)"')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get(opener, request):
    for attempt in range(3):
        try:
            with opener.open(request, timeout=90) as response:
                return response.status, response.read(LIMIT)
        except urllib.error.HTTPError as error:
            code = error.code
            error.close()
            if code not in (429, 500, 502, 503, 504) or attempt == 2:
                return code, None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                return 0, None
        time.sleep(2 ** (attempt + 1))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ProbeError('REDIRECT_FORBIDDEN')


class Reader:
    def __init__(self, token, opener=None, public_opener=None):
        if not token or re.search(r'\s', token):
            raise ProbeError('TOKEN_UNAVAILABLE')
        self._token = token
        self._opener = opener or urllib.request.build_opener(NoRedirect())
        self._public = public_opener or urllib.request.build_opener(NoRedirect())

    def api(self, endpoint):
        if endpoint != 'webapps/%s/static_files/' % DOMAIN and not re.fullmatch(
                re.escape(LOG) + r'(?:\.1|\.(?:[2-9]|1[0-4])\.gz)?', endpoint):
            raise ProbeError('API_PATH_OUTSIDE_SCOPE')
        return get(self._opener, urllib.request.Request(API + endpoint, headers={
            'Authorization': 'Token ' + self._token, 'User-Agent': 'uaart-ai-search-probe/1'}))

    def public(self, path, agent='uaart-ai-search-probe/1'):
        if path not in PAGES:
            raise ProbeError('PUBLIC_PATH_OUTSIDE_SCOPE')
        return get(self._public, urllib.request.Request(SITE + path, headers={
            'User-Agent': agent, 'Cache-Control': 'no-cache'}))


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


def source(referrer, path):
    if 'utm_source=chatgpt.com' in path:
        return 'chatgpt'
    host = re.sub(r'^https?://', '', referrer).split('/')[0].lower()
    for name, needles in REFERRERS.items():
        if any(n in host for n in needles):
            return name
    return None


def analyse(texts):
    lines = parsed = 0
    dates = Counter()
    bots = {}
    refs = {}
    for text in texts:
        for line in text.splitlines():
            lines += 1
            match = LINE.search(line)
            if not match:
                continue
            parsed += 1
            day, method, path, status, referrer, agent = match.groups()
            day = time.strftime('%Y-%m-%d', time.strptime(day, '%d/%b/%Y'))
            dates[day] += 1
            clean = path.split('?')[0][:160]
            for bot in BOTS:
                if bot.lower() in agent.lower():
                    entry = bots.setdefault(bot, {'hits': 0, 'status': Counter(), 'days': set(), 'paths': Counter()})
                    entry['hits'] += 1
                    entry['status'][status] += 1
                    entry['days'].add(day)
                    entry['paths'][clean] += 1
                    break
            else:
                name = source(referrer, path)
                if name:
                    entry = refs.setdefault(name, {'visits': 0, 'days': set(), 'paths': Counter()})
                    entry['visits'] += 1
                    entry['days'].add(day)
                    entry['paths'][clean] += 1
    return {'lines': lines, 'parsed': parsed, 'first_day': min(dates) if dates else None,
            'last_day': max(dates) if dates else None, 'days': len(dates),
            'crawlers': {bot: {'hits': e['hits'], 'status': dict(e['status']), 'first_day': min(e['days']),
                               'last_day': max(e['days']), 'top_paths': e['paths'].most_common(10)}
                         for bot, e in sorted(bots.items())},
            'crawlers_never_seen': [b for b in BOTS if b not in bots],
            'referrals': {name: {'visits': e['visits'], 'first_day': min(e['days']), 'last_day': max(e['days']),
                                 'top_paths': e['paths'].most_common(10)} for name, e in sorted(refs.items())}}


def text_facts(html):
    body = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html)
    words = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', body)).strip()
    types = []
    for block in re.findall(r'(?is)<script type="application/ld\+json"[^>]*>(.*?)</script>', html):
        try:
            data = json.loads(block)
        except ValueError:
            types.append('INVALID_JSON')
            continue
        nodes = data.get('@graph', [data]) if isinstance(data, dict) else data
        types += [str(n.get('@type')) for n in nodes if isinstance(n, dict)]
    return {'bytes': len(html.encode()), 'visible_chars': len(words), 'h1': re.findall(r'(?is)<h1[^>]*>(.*?)</h1>', html)[:2],
            'h2_count': len(re.findall(r'(?i)<h2\b', html)), 'ld_types': sorted(set(types)),
            'phone': '222 20 02' in words or '2222002' in html, 'address': bool(re.search('Перемог|Побед', words)),
            'faq': bool(re.search(r'FAQ|Часті питання|Частые вопросы', html)), 'scripts': len(re.findall(r'(?i)<script\b', html))}


def collect(reader):
    found = logs(reader)
    result = {'log_files': {k: {key: v for key, v in f.items() if key != 'text'} | (
        {'lines': f['text'].count('\n')} if 'text' in f else {}) for k, f in found.items()}}
    result['access'] = analyse([f['text'] for f in found.values() if 'text' in f])
    status, raw = reader.api('webapps/%s/static_files/' % DOMAIN)
    try:
        routes = json.loads(raw) if status == 200 and raw else None
    except ValueError:
        routes = None
    result['static_routes'] = {'http': status, 'routes': routes}
    result['pages'] = {}
    for path in PAGES:
        status, raw = reader.public(path)
        text = raw.decode('utf-8', 'replace') if raw else ''
        result['pages'][path] = {'http': status, 'body': text} if path == '/robots.txt' else dict(
            http=status, **(text_facts(text) if text else {}))
    result['as_crawler'] = {}
    for bot, agent in AS_BOT.items():
        status, raw = reader.public('/video/index.html', agent)
        result['as_crawler'][bot] = {'http': status, 'bytes': len(raw) if raw else 0}
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
        print('AI_SEARCH_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
