"""JPAUTO-KOREA-001 step 1: read-only probe of the owner's auction account.

Logs in with JPAUTO_EMAIL / JPAUTO_PASSWORD, opens the account home page and
the Korea search, and prints the structure of the search form (fields and their
options) plus result-table headers. Writes nothing anywhere; few requests.
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

BASE = 'https://jpauto.auction'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36'
MAX_OPTIONS = 400


class Page(HTMLParser):
    """Collects forms (inputs/selects with options), links, headings, table headers."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms, self.links, self.headings, self.tables, self.imgs = [], [], [], [], []
        self._form = None
        self._select = None
        self._option = None
        self._link = None
        self._heading = None
        self._th = None

    def _field_sink(self):
        if self._form is None:
            self._form = {'action': None, 'method': None, 'fields': [], 'implicit': True}
            self.forms.append(self._form)
        return self._form['fields']

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'form':
            self._form = {'action': a.get('action'), 'method': (a.get('method') or 'get').lower(),
                          'id': a.get('id'), 'fields': []}
            self.forms.append(self._form)
        elif tag in ('input', 'textarea'):
            self._field_sink().append({'tag': tag, 'type': a.get('type', 'text'), 'name': a.get('name'),
                                       'id': a.get('id'), 'value': a.get('value'),
                                       'placeholder': a.get('placeholder'), 'checked': 'checked' in a})
        elif tag == 'select':
            self._select = {'tag': 'select', 'name': a.get('name'), 'id': a.get('id'),
                            'multiple': 'multiple' in a, 'options': []}
            self._field_sink().append(self._select)
        elif tag == 'option' and self._select is not None:
            self._option = {'value': a.get('value'), 'text': ''}
            self._select['options'].append(self._option)
        elif tag == 'a' and a.get('href'):
            self._link = {'href': a['href'], 'text': ''}
            self.links.append(self._link)
        elif tag in ('h1', 'h2', 'h3', 'h4', 'label', 'legend'):
            self._heading = {'tag': tag, 'for': a.get('for'), 'text': ''}
            self.headings.append(self._heading)
        elif tag == 'img' and (a.get('src') or a.get('data-src')):
            self.imgs.append(a.get('data-src') or a.get('src'))
        elif tag == 'table':
            self.tables.append([])
        elif tag == 'th' and self.tables:
            self._th = ''

    def handle_endtag(self, tag):
        if tag == 'form':
            self._form = None
        elif tag == 'select':
            self._select = None
        elif tag == 'option':
            self._option = None
        elif tag == 'a':
            self._link = None
        elif tag in ('h1', 'h2', 'h3', 'h4', 'label', 'legend'):
            self._heading = None
        elif tag == 'th' and self._th is not None:
            self.tables[-1].append(' '.join(self._th.split()))
            self._th = None

    def handle_data(self, data):
        for sink in (self._option, self._link, self._heading):
            if sink is not None:
                sink['text'] += data
        if self._th is not None:
            self._th += data


def page_text(html, limit):
    text = ' '.join(re.sub(r'(?s)<(script|style).*?</\1>|<[^>]+>', ' ', html).split())
    return text[:limit]


def parse(html):
    p = Page()
    p.feed(html)
    for coll in (p.links, p.headings):
        for item in coll:
            item['text'] = ' '.join(item['text'].split())
    for form in p.forms:
        for f in form['fields']:
            for o in f.get('options', []):
                o['text'] = ' '.join(o['text'].split())
    return p


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.requests = 0
        self.trace = []

    def get(self, url, data=None):
        if self.requests:
            time.sleep(3)  # be gentle: few, spaced requests
        self.requests += 1
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        headers = {'User-Agent': UA, 'Accept-Language': 'en,ru;q=0.8'}
        if body is not None:
            headers.update({'Referer': BASE + '/', 'Origin': BASE})
        req = urllib.request.Request(urllib.parse.urljoin(BASE, url), data=body, headers=headers)
        with self.opener.open(req, timeout=40) as r:
            html = r.read(8 * 1024 * 1024).decode('utf-8', 'replace')
            self.trace.append({'url': r.geturl().replace(BASE, ''), 'http': r.status, 'bytes': len(html),
                               'set_cookie': [h.split('=', 1)[0] for h in r.headers.get_all('Set-Cookie') or []],
                               'jar': sorted(ck.name for ck in self.jar)})
            return r.geturl(), r.status, html


def summarize_form(form):
    out = {k: form.get(k) for k in ('action', 'method', 'id') if form.get(k)}
    fields = []
    for f in form['fields']:
        if f['tag'] == 'select':
            opts = f['options']
            fields.append({'select': f['name'], 'id': f['id'], 'multiple': f['multiple'],
                           'options_count': len(opts),
                           'options': [o['text'] or o['value'] for o in opts[:MAX_OPTIONS]]})
        elif (f['type'] or '').lower() not in ('password',):
            item = {'input': f['name'], 'type': f['type'], 'id': f['id']}
            if f.get('placeholder'):
                item['placeholder'] = f['placeholder']
            if (f['type'] or '').lower() in ('hidden', 'checkbox', 'radio', 'submit', 'button') and f.get('value'):
                item['value'] = f['value'][:60]
            fields.append(item)
    out['fields'] = fields
    return out


def probe_results(c, kp, nav_hrefs):
    """Submit the Korea search for one maker and read the first lot card."""
    form = next((f for f in kp.forms if f.get('id') == 'purchase_search_form'), None)
    if not form:
        return {'error': 'SEARCH_FORM_NOT_FOUND'}, None
    data = [(f['name'], f.get('value') or '') for f in form['fields']
            if f['tag'] == 'input' and f.get('name') and (f['type'] or '').lower() == 'hidden'
            and f['name'] not in ('history_idx_url', 'koreafavoriteurl', 'koreahistoryurl')]
    maker = next((f for f in form['fields'] if f.get('name') == 'maker[]'), {'options': []})
    hyundai = next((o['value'] for o in maker['options'] if o['text'].upper() == 'HYUNDAI'), None)
    if hyundai:
        data.append(('maker[]', hyundai))
    url, status, html = c.get(form['action'], data)
    rp = parse(html)
    lots = [l for l in rp.links if l['href'] not in nav_hrefs and re.search(r'\d{5,}', l['href'])
            and (not l['href'].startswith(('http://', 'https://')) or l['href'].startswith(BASE))]
    results = {'url': url.replace(BASE, ''), 'http': status, 'maker_value': hyundai,
               'table_headers': [t for t in rp.tables if t][:5],
               'text': page_text(html, 3500),
               'lot_links': [{'text': l['text'][:80], 'href': l['href'].replace(BASE, '')} for l in lots[:15]],
               'img_samples': rp.imgs[:15]}
    if not lots:
        return results, None
    lurl, lstatus, lhtml = c.get(lots[0]['href'])
    lp = parse(lhtml)
    lot = {'url': lurl.replace(BASE, ''), 'http': lstatus,
           'headings': [h['text'] for h in lp.headings if h['text']][:60],
           'table_headers': [t for t in lp.tables if t][:8],
           'text': page_text(lhtml, 3500), 'imgs': lp.imgs[:25]}
    return results, lot


def main():
    email = os.environ.get('JPAUTO_EMAIL', '').strip()
    password = os.environ.get('JPAUTO_PASSWORD', '').strip()
    if not email or not password:
        raise SystemExit('JPAUTO_SECRETS_MISSING')
    c = Client()
    _, _, login_html = c.get('/')
    login_form = next((f for f in parse(login_html).forms if f.get('action') and 'login' in f['action']), None)
    if not login_form:
        raise SystemExit('LOGIN_FORM_NOT_FOUND')
    data = {f['name']: f.get('value') or '' for f in login_form['fields']
            if f.get('name') and f['tag'] == 'input' and (f['type'] or '').lower() == 'hidden'}
    data['data[Bidder][email]'] = email
    data['data[Bidder][password]'] = password
    url, status, home = c.get(login_form['action'], data)
    home_page = parse(home)
    logged_in = not any('password' in (f.get('name') or '').lower()
                        for form in home_page.forms for f in form['fields'])
    report = {'login_ok': logged_in, 'after_login_url': url.replace(BASE, ''), 'http': status}
    if not logged_in:
        report['page_text'] = page_text(home, 600).replace(email, '<email>')
        report['trace'] = c.trace
        report['hidden_fields_sent'] = sorted(k for k in data if not k.startswith('data[Bidder]'))
        report['secrets'] = {'password_set': bool(password),
                                    'email_has_at': '@' in email}
        print(json.dumps(report, ensure_ascii=False, indent=1))
        raise SystemExit('LOGIN_FAILED')

    seen, nav = set(), []
    for link in home_page.links:
        key = (link['href'], link['text'])
        if key not in seen and not link['href'].startswith(('#', 'javascript', 'mailto', 'tel')):
            seen.add(key)
            nav.append({'text': link['text'], 'href': link['href'].replace(BASE, '')})
    report['home'] = {'headings': [h['text'] for h in home_page.headings if h['text']][:40],
                      'links': nav[:120],
                      'forms': [summarize_form(f) for f in home_page.forms],
                      'table_headers': [t for t in home_page.tables if t][:5]}

    korea = [l for l in nav if re.search(r'korea|корея|корея|\bkr\b|한국', l['text'] + ' ' + l['href'], re.I)]
    report['korea_links'] = korea
    if korea:
        kurl, kstatus, khtml = c.get(korea[0]['href'])
        kp = parse(khtml)
        report['korea'] = {'url': kurl.replace(BASE, ''), 'http': kstatus,
                           'headings': [h['text'] for h in kp.headings if h['text']][:80],
                           'forms': [summarize_form(f) for f in kp.forms],
                           'table_headers': [t for t in kp.tables if t][:5],
                           'dates_seen': sorted(set(re.findall(r'20\d\d[-/.]\d{1,2}[-/.]\d{1,2}', khtml)))[:40],
                           'weekdays_seen': sorted(set(re.findall(
                               r'\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b', khtml)))}
        report['results'], report['lot'] = probe_results(c, kp, {l['href'] for l in nav})
    report['requests_made'] = c.requests
    text = json.dumps(report, ensure_ascii=False, indent=1)
    text = text.replace(email, '<email>')
    print(text)
    out = os.environ.get('JPAUTO_REPORT')
    if out:
        with open(out, 'w', encoding='utf-8') as fh:
            fh.write(text)


if __name__ == '__main__':
    sys.exit(main())
