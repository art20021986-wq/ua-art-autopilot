#!/usr/bin/env python3
"""SEO-DAILY-001: read-only check of every sitemap page of the live site, as Googlebot sees the HTML (stdlib only).

Usage: python3 cloud/seo_daily/crawl.py out.json        # then: python3 cloud/seo_daily/crawl.py --summary out.json
Per page: status, redirect, canonical, robots/noindex, lang, title, description, h1, hreflang, JSON-LD types,
viewport, response time. Internal links outside the sitemap get their status only. Nothing is written to the site.
Limits follow Google Search Central: title is shown up to ~60-70 characters, description up to ~160.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser

BASE = 'https://www.uaart.com.ua'
AGENT = 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
TITLE_MAX, DESCRIPTION_MIN, DESCRIPTION_MAX, SLOW_SECONDS = 70, 70, 170, 3.0


class Page(HTMLParser):
    """The SEO fields of one HTML page."""

    def __init__(self):
        super().__init__()
        self.data = {'lang': '', 'title': '', 'description': None, 'robots': '', 'canonical': [], 'hreflang': [],
                     'h1': [], 'ld': [], 'links': set(), 'viewport': False}
        self._open, self._text = None, ''

    def handle_starttag(self, tag, attrs):
        a = {k: v or '' for k, v in attrs}
        name, rel = a.get('name', '').lower(), a.get('rel', '').lower()
        if tag == 'html':
            self.data['lang'] = a.get('lang', '')
        elif tag == 'link' and rel == 'canonical':
            self.data['canonical'].append(a.get('href', ''))
        elif tag == 'link' and rel == 'alternate' and a.get('hreflang'):
            self.data['hreflang'].append([a['hreflang'], a.get('href', '')])
        elif tag == 'meta' and name in ('robots', 'googlebot'):
            self.data['robots'] += a.get('content', '') + ' '
        elif tag == 'meta' and name == 'description':
            self.data['description'] = a.get('content', '')
        elif tag == 'meta' and name == 'viewport':
            self.data['viewport'] = True
        elif tag == 'a' and a.get('href'):
            self.data['links'].add(a['href'])
        if tag in ('title', 'h1') or (tag == 'script' and a.get('type') == 'application/ld+json'):
            self._open, self._text = tag, ''

    def handle_data(self, data):
        if self._open:
            self._text += data

    def handle_endtag(self, tag):
        if self._open != tag:
            return
        text = re.sub(r'\s+', ' ', self._text).strip()
        if tag == 'title':
            self.data['title'] = text
        elif tag == 'h1':
            self.data['h1'].append(text)
        else:
            self.data['ld'] += ld_types(self._text)
        self._open = None


def ld_types(text):
    try:
        value = json.loads(text)
    except ValueError:
        return ['INVALID_JSON']
    items = value if isinstance(value, list) else [value]
    nodes = [n for i in items if isinstance(i, dict) for n in i.get('@graph', [i]) if isinstance(n, dict)]
    return [str(n.get('@type')) for n in nodes]


def parse(html):
    page = Page()
    page.feed(html)
    page.data['links'] = sorted(page.data['links'])
    return page.data


def issues(page):
    """Plain findings for one crawled page (empty list = nothing to fix)."""
    found = []
    if page['status'] != 200:
        return ['status %s' % page['status']]
    if page['final'] != page['url']:
        found.append('redirect ' + page['final'])
    if len(page['canonical']) != 1:
        found.append('canonical x%d' % len(page['canonical']))
    elif page['canonical'][0] != page['url']:
        found.append('canonical -> ' + page['canonical'][0])
    if 'noindex' in page['robots'] + page.get('x_robots', ''):
        found.append('noindex')
    if not page['title']:
        found.append('no title')
    elif len(page['title']) > TITLE_MAX:
        found.append('title %d chars' % len(page['title']))
    if not page['description']:
        found.append('no description')
    elif not DESCRIPTION_MIN <= len(page['description']) <= DESCRIPTION_MAX:
        found.append('description %d chars' % len(page['description']))
    if len(page['h1']) != 1:
        found.append('h1 x%d' % len(page['h1']))
    if not page['viewport']:
        found.append('no viewport')
    if 'INVALID_JSON' in page['ld']:
        found.append('structured data invalid')
    if page['seconds'] > SLOW_SECONDS:
        found.append('slow %.1f s' % page['seconds'])
    return found


def fetch(url, tries=3):
    """(status, final url, body, seconds, headers); the host drops bursts, so a reset is retried after a pause."""
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    for attempt in range(tries):
        start = time.time()
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.status, response.geturl(), response.read(), time.time() - start, dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, url, b'', time.time() - start, {}
        except OSError as error:
            if attempt == tries - 1:
                return type(error).__name__, url, b'', time.time() - start, {}
            time.sleep(3 * (attempt + 1))


def crawl_page(url):
    status, final, body, seconds, headers = fetch(url)
    page = parse(body.decode('utf-8', 'replace'))
    page.update(url=url, status=status, final=final, seconds=round(seconds, 2), bytes=len(body),
                x_robots=headers.get('X-Robots-Tag', ''))
    page['issues'] = issues(page)
    return page


def internal_links(pages, known):
    found = set()
    for page in pages:
        for href in page['links']:
            url = urllib.parse.urljoin(page['final'], href.split('#')[0])
            if url.startswith(BASE + '/') and not url.startswith(BASE + '/api/'):
                found.add(url)
    return sorted(found - set(known))


def main(out):
    sitemap = fetch(BASE + '/sitemap.xml')[2].decode('utf-8', 'replace')
    urls = re.findall(r'<loc>\s*(.*?)\s*</loc>', sitemap)
    with ThreadPoolExecutor(3) as pool:
        pages = list(pool.map(crawl_page, urls))
        extra = internal_links(pages, urls)
        statuses = list(pool.map(lambda u: fetch(u)[0], extra))
    robots = fetch(BASE + '/robots.txt')[2].decode('utf-8', 'replace')
    value = {'checked_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'robots_txt': robots,
             'sitemap_urls': len(urls), 'pages': pages, 'links_outside_sitemap': dict(zip(extra, statuses))}
    with open(out, 'w', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=1)


def summary(path):
    value = json.load(open(path, encoding='utf-8'))
    print('checked', value['checked_at'], 'sitemap', value['sitemap_urls'])
    for page in value['pages']:
        if page['issues']:
            print(page['url'].replace(BASE, ''), page['lang'], '; '.join(page['issues']))
    broken = {u: s for u, s in value['links_outside_sitemap'].items() if s != 200}
    print('broken internal links:', broken or 'none')


if __name__ == '__main__':
    if sys.argv[1] == '--summary':
        summary(sys.argv[2])
    else:
        main(sys.argv[1])
