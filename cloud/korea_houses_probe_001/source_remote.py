"""Read-only probe on the server for KOREA-HOUSES-001 (owner 2026-11-28: add the Hyundai Glovis and Lotte auctions).

Logs in with the owner's login file (/home/Carix/jpauto_login.txt), as the Korea ticker job does every morning, and
reports, cleaned: every checkbox of the Korea search form (name, value, label, checked by default), the default result
count with the lots counted by auction house, and the count when one house box that is not checked by default is added
(Glovis, Lotte and any other). Only GET pages and the search form are sent; NO bid.
"""
import argparse
from collections import Counter
import http.cookiejar
import json
import os
from pathlib import Path
import re
import resource
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
LOGIN = Path('/home/Carix/jpauto_login.txt')
BASE = 'https://jpauto.auction'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
HOUSE_WORD = re.compile(r'(?i)glovis|autobell|lotte|hyundai|현대|롯데')
MAX_EXTRA = 12  # at most this many extra searches (one per house box not checked by default)
LONG_NUMBER = re.compile(r'\d{6,}')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
URL = re.compile(r'https?://[^\s\'"<>)]+')
ATTR = re.compile(r'([\w:\[\]-]+)\s*=\s*("([^"]*)"|\'([^\']*)\')')
COUNT = re.compile(r'([\d,]+) Results')
PAGE_LIMIT = 2000
MAX_PAGES = 5


def clean(text):
    """No e-mail, no long numbers (ids, tokens), no full foreign URLs (the path is kept)."""
    text = EMAIL.sub('[EMAIL]', text)
    text = URL.sub(lambda m: urllib.parse.urlsplit(m.group(0)).path or '/', text)
    return LONG_NUMBER.sub('[N]', text)


def text(html):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html)).strip()


def attrs(raw):
    return {m.group(1).lower(): (m.group(3) if m.group(3) is not None else m.group(4)) for m in ATTR.finditer(raw)}


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
        with self.opener.open(request, timeout=90) as response:
            return response.geturl(), response.read(64 * 1024 * 1024).decode('utf-8', 'replace')


def search_form(html):
    """The search form block, its action and the data a browser sends by default (hidden + checked boxes)."""
    start = html.find('id="purchase_search_form"')
    if start < 0:
        return None
    head = attrs(html[html.rfind('<form', 0, start):start + 300].split('>', 1)[0])
    block = html[start:]
    block = block[:block.find('</form>')]
    data = []
    for tag in re.findall(r'(?is)<input\b[^>]*>', block):
        a = attrs(tag)
        name, kind = a.get('name'), a.get('type', '').lower()
        if not name or name.endswith(('favoriteurl', 'historyurl')) or name == 'history_idx_url':
            continue
        if kind == 'hidden' or (kind in ('checkbox', 'radio') and re.search(r'(?i)\schecked\b', tag)):
            data.append((name, a.get('value', 'on')))
    return {'action': head.get('action') or '', 'block': block, 'data': data}


def boxes(block):
    """Every checkbox: name, value and the text right after it (its label)."""
    found = []
    for match in re.finditer(r'(?is)<input\b([^>]*type="checkbox"[^>]*)>(.{0,400}?)(?=<input\b|</(?:ul|div|td)>)',
                             block):
        a = attrs(match.group(1))
        found.append({'name': a.get('name', ''), 'value': a.get('value', 'on'), 'label': clean(text(match.group(2)))[:80],
                      'checked': bool(re.search(r'(?i)\schecked\b', match.group(1)))})
    return found


def total(html):
    return int((COUNT.findall(html) or ['0'])[0].replace(',', ''))


def rows(html):
    """Results table -> header cells and, per lot row, {header: cell text} (only rows with a detail link)."""
    tables = [t for t in re.findall(r'(?is)<table\b.*?</table>', html) if 'vehicle-detail/' in t]
    if not tables:
        return [], []
    table = max(tables, key=len)
    header = [text(c) for c in re.findall(r'(?is)<th\b.*?</th>', table)]
    found = []
    for row in re.findall(r'(?is)<tr\b.*?</tr>', table):
        if 'vehicle-detail/' not in row:
            continue
        cells = [text(c) for c in re.findall(r'(?is)<td\b.*?</td>', row)]
        link = re.search(r'href="(/vehicle-detail/[a-z]{2}/\d+)', row)
        found.append({'cells': dict(zip(header, cells)), 'detail': link.group(1) if link else ''})
    return header, found


def column(header, word):
    return next((h for h in header if word.lower() in h.lower()), None)


def by_house(header, lots):
    """Lots by auction house (lot numbers in brackets dropped) and by auction day."""
    house_col = column(header, 'Lot') or column(header, 'House') or column(header, 'Auction')
    day_col = column(header, 'Start') or column(header, 'Date')

    def tally(col, cut):
        return dict(Counter(cut(lot['cells'].get(col, '')) for lot in lots).most_common(60)) if col else {}

    return {'columns': {'house': house_col, 'day': day_col},
            'by_house': tally(house_col, lambda v: re.sub(r'\s*\(\s*\w*\s*\)\s*$', '', v).strip()),
            'by_day': tally(day_col, lambda v: v[:10])}


def all_rows(browser, html):
    """Every lot row of a result (all pages with the largest page size)."""
    count = total(html)
    header, found = rows(html)
    pager = re.search(r'href="(/vehicle-search/[a-z]{2}/index/page=\d+\?[^"]+)"', html)
    if pager and len(found) < count:
        base = pager.group(1).replace('&amp;', '&')
        found = []
        for n in range(1, MAX_PAGES + 1):
            _, page = browser.fetch(re.sub(r'page=\d+', 'page=%d' % n, base) + '&limit=%d' % PAGE_LIMIT)
            header, batch = rows(page)
            found += batch
            if not batch or len(found) >= count:
                break
    return count, header, found


def house_boxes(every):
    """Boxes that look like auction houses: the name of a default-checked house group, or a house word in the label."""
    named = {b['name'] for b in every if b['checked'] and 'auction' in b['name'].lower()}
    return [b for b in every if b['name'] in named or HOUSE_WORD.search(b['label']) or 'auction' in b['name'].lower()]


def sanitized(html, limit=300000):
    """R3 sample for the parser tests: no scripts, styles, head, input values or greetings; cleaned; at most `limit`."""
    html = re.sub(r'(?is)<(script|style|head|noscript)\b.*?</\1>', '', html)
    html = re.sub(r'(?is)(<input\b[^>]*?)\svalue\s*=\s*("[^"]*"|\'[^\']*\')', r'\1', html)
    html = re.sub(r'(?i)(welcome|hello|ようこそ)[^<]{0,80}', r'\1', html)
    return clean(re.sub(r'\n\s*\n+', '\n', html))[:limit]


def results_sample(html, rows_kept=5):
    """The result count, the results table head and its first lot rows, and the pager and lot links."""
    tables = [t for t in re.findall(r'(?is)<table\b.*?</table>', html) if 'vehicle-detail' in t]
    table = max(tables, key=len) if tables else ''
    head = table[:table.find('<tbody')] if '<tbody' in table else table[:2000]
    lot_rows = [r for r in re.findall(r'(?is)<tr\b.*?</tr>', table) if 'vehicle-detail' in r][:rows_kept]
    return {'count_text': clean((COUNT.findall(html) or [''])[0]), 'table': sanitized(head + ''.join(lot_rows) + '</table>'),
            'pager_links': sorted(set(clean(h) for h in re.findall(r'href="([^"]*page=[^"]*)"', html)))[:10],
            'detail_links': [clean(h) for h in re.findall(r'href="([^"]*vehicle-detail[^"]*)"', html)][:5]}


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
    form = search_form(search)
    if not form:
        return {'status': 'NO_SEARCH_FORM', 'page_text': clean(text(search))[:600], 'requests': browser.requests}
    every = boxes(form['block'])
    houses = house_boxes(every)
    _, first = browser.fetch(form['action'] or '/vehicle-search/kr/index', form['data'])
    count, header, lots = all_rows(browser, first)
    value = {'status': 'PASS', 'checkboxes': [{k: b[k] for k in ('name', 'value', 'label', 'checked')} for b in every][:300],
             'house_boxes': [{k: b[k] for k in ('name', 'value', 'label', 'checked')} for b in houses][:120],
             'glovis_lotte_in_form': [b['label'] for b in every if HOUSE_WORD.search(b['label'])],
             'default_total': count, 'default_rows_read': len(lots), 'result_columns': header[:30],
             'default': by_house(header, lots), 'samples': results_sample(first), 'no_bid_placed': True}
    extra = {}
    for box in [b for b in houses if not b['checked']][:MAX_EXTRA]:
        _, html = browser.fetch(form['action'] or '/vehicle-search/kr/index', list(form['data']) + [(box['name'], box['value'])])
        extra[box['label'] or box['value']] = total(html)
    value['added_one_house_total'] = extra
    value['requests'] = browser.requests
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (150, 160))
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
