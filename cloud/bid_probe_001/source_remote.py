"""Read-only probe on the server for JPAUTO-KOREA-001 step В (client bids placed on the owner's auction account).

Logs in with the owner's login file (/home/Carix/jpauto_login.txt), opens the Korea search and ONE lot page and
reports how a bid is placed there: every form (action path, method, field names and types — values only as their
length, never their content), buttons, and the page script lines that mention bids. NO bid is placed: the probe
only sends the login form and the empty search form, exactly as the ticker job does every morning.
"""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import resource
import time
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
LOGIN = Path('/home/Carix/jpauto_login.txt')
BASE = 'https://jpauto.auction'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
BID_WORD = re.compile(r'(?i)\bbid|offer|ставк')
LONG_NUMBER = re.compile(r'\d{6,}')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
URL = re.compile(r'https?://[^\s\'"<>)]+')
TAG = re.compile(r'<(form|input|select|button|textarea)\b([^>]*)>', re.I)
ATTR = re.compile(r'([\w:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')


def clean(text):
    """No e-mail, no long numbers (ids, tokens), no full foreign URLs (the path is kept)."""
    text = EMAIL.sub('[EMAIL]', text)
    text = URL.sub(lambda m: urllib.parse.urlsplit(m.group(0)).path or '/', text)
    return LONG_NUMBER.sub('[N]', text)


class Browser:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.requests = 0

    def fetch(self, path, data=None):
        if self.requests:
            time.sleep(3)
        self.requests += 1
        headers = {'User-Agent': UA, 'Accept-Language': 'en'}
        body = None
        if data is not None:
            body = urllib.parse.urlencode(data).encode()
            headers.update({'Referer': BASE + '/', 'Origin': BASE})
        request = urllib.request.Request(urllib.parse.urljoin(BASE, path), data=body, headers=headers)
        with self.opener.open(request, timeout=60) as response:
            return response.geturl(), response.read(16 * 1024 * 1024).decode('utf-8', 'replace')


def attrs(raw):
    return {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in ATTR.finditer(raw)}


def forms(html):
    """Every form with its controls; values reported only by length."""
    result = []
    for match in re.finditer(r'<form\b[^>]*>.*?</form>', html, re.I | re.S):
        block = match.group(0)
        head = attrs(re.match(r'<form\b([^>]*)>', block, re.I).group(1))
        controls = []
        for tag in TAG.finditer(block):
            if tag.group(1).lower() == 'form':
                continue
            a = attrs(tag.group(2))
            controls.append({'tag': tag.group(1).lower(), 'type': a.get('type', ''), 'name': clean(a.get('name', '')),
                             'id': clean(a.get('id', '')), 'value_length': len(a.get('value', '')),
                             'class': a.get('class', '')[:80]})
        text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', block)).strip()
        result.append({'action': clean(head.get('action', '')), 'method': head.get('method', 'get').lower(),
                       'id': clean(head.get('id', '')), 'class': head.get('class', '')[:80],
                       'mentions_bid': bool(BID_WORD.search(block)), 'controls': controls[:40],
                       'text': clean(text)[:400]})
    return result


def bid_lines(html):
    """Script and markup lines that mention bids (cleaned, at most 60)."""
    lines = []
    for line in html.splitlines():
        if BID_WORD.search(line):
            lines.append(clean(line.strip())[:300])
    return lines[:60]


def endpoints(html):
    paths = sorted(set(re.findall(r'["\'](/[\w\-/]*(?:bid|offer)[\w\-/]*)', html, re.I)))
    return [clean(p) for p in paths][:40]


def login_pair():
    lines = [line.strip() for line in LOGIN.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError('LOGIN_FILE_INCOMPLETE')
    return lines[0], lines[1]


def report():
    email, password = login_pair()
    browser = Browser()
    browser.fetch('/')
    _, page = browser.fetch('/login/login', {'data[Bidder][email]': email, 'data[Bidder][password]': password})
    if 'data[Bidder][password]' in page:
        return {'status': 'FAIL', 'error': 'LOGIN_FAILED'}
    _, search = browser.fetch('/vehicle-search/kr/')
    form = search[search.find('id="purchase_search_form"'):]
    form = form[:form.find('</form>')]
    data = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', form):
        a = attrs(tag)
        if a.get('name') and a['name'] not in ('history_idx_url', 'koreafavoriteurl', 'koreahistoryurl'):
            data.append((a['name'], a.get('value', '')))
    _, results = browser.fetch('/vehicle-search/kr/index', data)
    detail = re.search(r'href="(/vehicle-detail/kr/\d+)', results)
    if not detail:
        return {'status': 'FAIL', 'error': 'NO_LOT_FOUND', 'requests': browser.requests}
    _, lot = browser.fetch(detail.group(1))
    return {'status': 'PASS', 'requests': browser.requests, 'no_bid_placed': True,
            'lot_page': {'forms': forms(lot), 'bid_lines': bid_lines(lot), 'endpoints': endpoints(lot),
                         'scripts': [clean(s) for s in re.findall(r'<script[^>]+src="([^"]+)"', lot)][:30],
                         'length': len(lot)},
            'results_page': {'endpoints': endpoints(results), 'bid_lines': bid_lines(results)[:20]}}


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
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + clean(str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
