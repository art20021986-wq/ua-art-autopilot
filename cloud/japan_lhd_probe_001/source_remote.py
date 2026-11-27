"""Read-only probe on the server for JAPAN-LHD-001 (owner 2026-11-26: Japan auction cars, left-hand drive only).

Logs in with the owner's login file (/home/Carix/jpauto_login.txt), as the Korea ticker job does every morning,
and reports, cleaned: which country searches the account has, the Japan search form (field names, the
left-hand-drive box, the auction houses), the result counts (all lots / left-hand drive only), the
left-hand-drive lots counted by auction house (USS apart), maker and auction day, and ONE lot page (field
labels, the steering value, photo count and host). Only GET pages and the search form are sent; NO bid.
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
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
LOGIN = Path('/home/Carix/jpauto_login.txt')
BASE = 'https://jpauto.auction'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
LHD_WORD = re.compile(r'(?i)left|lhd|\bhandle\b|steer|左')
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


def countries(html):
    """Country codes of the account's vehicle searches ('/vehicle-search/jp/' -> 'jp')."""
    return sorted(set(re.findall(r'/vehicle-search/([a-z]{2})/', html)))


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


def form_summary(block):
    """Field names with type and option count; the left-hand-drive boxes; the auction houses (USS apart)."""
    fields = Counter()
    for tag in re.findall(r'(?is)<(?:input|select)\b[^>]*>', block):
        a = attrs(tag)
        if a.get('name'):
            fields['%s|%s' % (a['name'], a.get('type', 'select').lower())] += 1
    every = boxes(block)
    lhd = [b for b in every if LHD_WORD.search(b['name'] + ' ' + b['label'])]
    houses = [b for b in every if b['name'].startswith('auction')]
    return {'fields': dict(sorted(fields.items())), 'lhd_boxes': lhd[:10],
            'auction_boxes': len(houses), 'auction_labels': [b['label'] for b in houses][:300],
            'uss_auction_boxes': sum('USS' in b['label'].upper() for b in houses)}


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


def counts(header, lots):
    """Left-hand-drive lots by auction house (lot numbers dropped), maker and auction day."""
    house_col = column(header, 'Lot') or column(header, 'House') or column(header, 'Auction')
    maker_col = column(header, 'Make') or column(header, 'Manufacturer')
    day_col = column(header, 'Start') or column(header, 'Date')

    def tally(col, cut):
        return dict(Counter(cut(lot['cells'].get(col, '')) for lot in lots).most_common(60)) if col else {}

    houses = tally(house_col, lambda v: re.sub(r'\s*\(\s*\w*\s*\)\s*$', '', v).strip())
    return {'columns': {'house': house_col, 'maker': maker_col, 'day': day_col},
            'by_house': houses, 'uss': sum(n for h, n in houses.items() if 'USS' in h.upper()),
            'by_maker': tally(maker_col, str.strip), 'by_day': tally(day_col, lambda v: v[:10])}


def lot_page(html):
    """One lot page: field labels, steering-like pairs, photo count and hosts, whether an auction sheet is shown."""
    labels = [text(c) for c in re.findall(r'(?is)<th\b.*?</th>', html)]
    pairs = re.findall(r'(?is)<th\b[^>]*>(.*?)</th>\s*<td\b[^>]*>(.*?)</td>', html)
    steering = {clean(text(k))[:40]: clean(text(v))[:40] for k, v in pairs if LHD_WORD.search(text(k))}
    photos = [s for s in re.findall(r'<img[^>]+src="([^"]+)"', html) if re.search(r'(?i)\.jpe?g', s)]
    hosts = Counter(urllib.parse.urlsplit(urllib.parse.urljoin(BASE, s)).netloc for s in photos)
    return {'labels': [clean(x)[:40] for x in labels][:80], 'steering': steering, 'photo_count': len(photos),
            'photo_hosts': dict(hosts), 'auction_sheet': 'auction sheet' in text(html).lower(), 'length': len(html)}


def lhd_lots(browser, form):
    """Search again with the left-hand-drive boxes checked; all pages with the largest page size."""
    summary = form_summary(form['block'])
    if not summary['lhd_boxes']:
        return summary, None, [], []
    data = list(form['data']) + [(b['name'], b['value']) for b in summary['lhd_boxes'] if not b['checked']]
    _, html = browser.fetch(form['action'], data)
    count = total(html)
    header, found = rows(html)
    pager = re.search(r'href="(/vehicle-search/[a-z]{2}/index/page=\d+\?[^"]+)"', html)
    if pager and len(found) < count:
        base = pager.group(1).replace('&amp;', '&')
        found = []
        for n in range(1, MAX_PAGES + 1):
            _, html = browser.fetch(re.sub(r'page=\d+', 'page=%d' % n, base) + '&limit=%d' % PAGE_LIMIT)
            header, batch = rows(html)
            found += batch
            if not batch or len(found) >= count:
                break
    return summary, count, header, found


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
    _, dashboard = browser.fetch('/customers_dashboard')
    found = countries(page + dashboard)
    if 'jp' not in found:
        return {'status': 'NO_JAPAN_SEARCH', 'countries': found, 'requests': browser.requests}
    _, search = browser.fetch('/vehicle-search/jp/')
    form = search_form(search)
    if not form:
        return {'status': 'NO_SEARCH_FORM', 'countries': found, 'page_text': clean(text(search))[:600],
                'requests': browser.requests}
    _, everything = browser.fetch(form['action'] or '/vehicle-search/jp/index', form['data'])
    summary, lhd_total, header, lots = lhd_lots(browser, form)
    value = {'status': 'PASS', 'countries': found, 'form': summary, 'total_all': total(everything),
             'total_lhd': lhd_total, 'lhd_rows_read': len(lots), 'result_columns': header[:30], 'no_bid_placed': True}
    if lots:
        value['lhd'] = counts(header, lots)
        detail = next((lot['detail'] for lot in lots if lot['detail']), '')
        if detail:
            _, html = browser.fetch(detail)
            value['lot_page'] = lot_page(html)
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
