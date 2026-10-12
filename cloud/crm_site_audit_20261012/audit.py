"""CRM ↔ site comparison for every car; pure functions, no I/O.

Reuses the reviewed field and photo verifiers (public_fields, public_media).
Each check returns PASS, FAIL (with a short reason) or SKIP (with why).
"""
from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
import re

# Unchanged copies of the reviewed verifiers from crm_site_consistency_001.
import public_fields
import public_media

HIDDEN_STATUSES = frozenset(('archive', 'sold', 'draft', '', None))
MARKET_RE = re.compile(r'data-ua-market="(ukraine|georgia)"[^>]*?data-ua-value="([^"]*)"')


def plain_text(html):
    """Visible text approximation: drop scripts/styles/tags, collapse spaces."""
    html = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', html)
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', html)).split())


def catalog_articles(catalog):
    """Map car code -> its <article> fragment in the catalog."""
    result = {}
    for chunk in catalog.split('<article')[1:]:
        body = '<article' + chunk.split('</article>', 1)[0] + '</article>'
        codes = set(re.findall(r'data-ua-card="(UA-\d{4,})"', body))
        if len(codes) == 1:
            code = codes.pop()
            if code in result:
                raise ValueError('Duplicate catalog card ' + code)
            result[code] = body
    return result


def markets(html):
    found = {}
    for market, value in MARKET_RE.findall(html):
        found.setdefault(market, set()).add(value)
    return {k: sorted(v) for k, v in found.items()}


def money(value):
    if value in (None, ''):
        return ''
    number = float(value)
    return str(int(number)) if number == int(number) else str(number)


def check(fn):
    try:
        detail = fn()
        return {'result': 'PASS', **({'detail': detail} if detail else {})}
    except Skip as skip:
        return {'result': 'SKIP', 'why': str(skip)}
    except Exception as error:  # every verifier failure is a finding, never a crash
        return {'result': 'FAIL', 'reason': str(error)[:300]}


class Skip(Exception):
    pass


class _Stage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth, self.text = 0, []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get('class', '').split()
        if self.depth:
            self.depth += 1
        elif 'etap' in classes and 'tut' in classes:
            self.depth = 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.text.append(data)


def card_stage(page):
    parser = _Stage()
    parser.feed(page)
    return ' '.join(' '.join(parser.text).split())


def audit_car(card, page, fragment, prices_json):
    code = card['auto_number']
    expected = {'ukraine': [money(card.get('price_uah'))], 'georgia': [money(card.get('price_georgia'))]}

    def need(value, what):
        if value is None:
            raise Skip(what + ' missing')
        return value

    def price(html, where):
        got = markets(need(html, where))
        if got.get('ukraine') != expected['ukraine']:
            raise RuntimeError('UA price site=%s CRM=%s' % (got.get('ukraine'), expected['ukraine']))
        if got.get('georgia') != expected['georgia']:
            note = ' (Kyiv rule hides GE)' if card.get('status') == 'ua_arrived' and got.get('georgia') == [''] else ''
            raise RuntimeError('GE price site=%s CRM=%s%s' % (got.get('georgia'), expected['georgia'], note))

    def photo_count():
        shown = re.findall(r'(\d+)\s*фото', need(fragment, 'catalog card'))
        visible = len(public_media.visible_photo_ids(card))
        if [int(x) for x in shown] != [visible] * len(shown) or not shown:
            raise RuntimeError('catalog photo count %s, CRM visible %d' % (shown, visible))

    def description():
        text = ' '.join(str(card.get('description') or '').split())
        if not text:
            raise Skip('no CRM description')
        if text not in plain_text(need(page, 'card page')):
            raise RuntimeError('CRM description not shown on card page')

    def stage():
        status = card.get('status')
        tile = re.findall(r'<article[^>]*data-stage="([^"]*)"', need(fragment, 'catalog card'))
        pill = re.findall(r'class="status-pill"[^>]*>([^<]*)<', fragment)
        on_page = card_stage(need(page, 'card page'))
        return {'crm_status': status, 'catalog_stage': tile, 'catalog_pill': pill, 'card_current_step': on_page}

    return {
        'code': code,
        'card_page_fields': check(lambda: public_fields.verify_core_fields(need(page, 'card page'), card)),
        'catalog_fields': check(lambda: public_fields.verify_core_fields(need(fragment, 'catalog card'), card, catalog=True)),
        'photos': check(lambda: public_media.verify_photo_structure(need(page, 'card page'), card)),
        'catalog_photo_count': check(photo_count),
        'price_card_page': check(lambda: price(page, 'card page')),
        'price_catalog': check(lambda: price(fragment, 'catalog card')),
        'price_live_json': check(lambda: price((prices_json.get('cars') or {}).get(code, {}).get('full'), 'live price JSON')),
        'description': check(description),
        'stage': check(stage),
    }


def audit(cards, catalog, pages, prices_json, served=None, page_files=()):
    """cards: CRM rows; pages: code -> server HTML or None; served: path -> bool."""
    articles = catalog_articles(catalog)
    shown = {c['auto_number'] for c in cards if c.get('published') == 1 and c.get('status') not in HIDDEN_STATUSES}
    known = {c['auto_number'] for c in cards}
    summary = {
        'crm_cars': len(cards),
        'crm_should_be_on_site': sorted(shown),
        'catalog_cards': sorted(articles),
        'missing_from_catalog': sorted(shown - set(articles)),
        'catalog_not_published_in_crm': sorted(set(articles) - shown),
        'catalog_not_in_crm': sorted(set(articles) - known),
        'card_pages_without_crm_car': sorted(f for f in page_files
                                             if re.fullmatch(r'UA-\d{4,}\.html', f) and f[:-5] not in known),
        'published_but_hidden_status': sorted(c['auto_number'] for c in cards
                                              if c.get('published') == 1 and c.get('status') in HIDDEN_STATUSES),
        'served_bytes_differ_from_server': sorted(k for k, ok in (served or {}).items() if ok is False),
    }
    cars = [audit_car(c, pages.get(c['auto_number']), articles.get(c['auto_number']), prices_json)
            for c in sorted(cards, key=lambda c: c['auto_number']) if c['auto_number'] in shown]
    counts = {}
    for car in cars:
        for name, value in car.items():
            if isinstance(value, dict):
                counts.setdefault(name, {}).setdefault(value['result'], 0)
                counts[name][value['result']] += 1
    return {'summary': summary, 'check_totals': counts, 'cars': cars}
