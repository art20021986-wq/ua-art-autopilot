"""CRM ↔ site comparison for every car; pure functions, no I/O.

Reuses the reviewed field and photo verifiers (public_fields, public_media).
Each check returns PASS, FAIL (with a short reason) or SKIP (with why).
"""
from __future__ import annotations

from html import unescape
import re

# Copies of the reviewed verifiers from crm_site_consistency_001 (title rule updated).
import json

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


def first(pattern, html):
    found = re.findall(pattern, html or '', re.S)
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', found[0])).split()) if found else None


def card_gallery(page, card):
    """Current card layout: <section class="um-gallery" data-ua-media="photo"> with JSON photo list."""
    code = card['auto_number']
    blocks = re.findall(r'<section class="um-gallery" data-ua-media="photo".*?<script type="application/json"'
                        r' class="um-data">(.*?)</script>', page, re.S)
    if len(blocks) != 1:
        raise RuntimeError('Missing or ambiguous photo gallery')
    sources = [item.get('src') for item in json.loads(blocks[0])]
    pattern = r'foto/' + re.escape(code) + r'/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|webp)'
    if any(not isinstance(s, str) or not re.fullmatch(pattern, s) for s in sources) or len(set(sources)) != len(sources):
        raise RuntimeError('Foreign or duplicate gallery photo')
    visible = len(public_media.visible_photo_ids(card))
    if len(sources) != visible:
        raise RuntimeError('card gallery %d photos, CRM visible %d' % (len(sources), visible))
    cover = card.get('cover_photo')
    if cover and sources and sources[0] != 'foto/%s/%s' % (code, cover):
        raise RuntimeError('first photo %s, CRM cover %s' % (sources[0], cover))
    return {'photos': len(sources)}


def text_lines(value):
    value = re.sub(r'(?i)<br\s*/?>', '\n', str(value or ''))
    return ' '.join(unescape(re.sub(r'<[^>]+>', ' ', value)).split())


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
        sources = {k: text_lines(card.get(k)) for k in ('description', 'condition_text') if text_lines(card.get(k))}
        shown = first(r"<div class='tehtekst'>(.*?)</div>", re.sub(r'(?i)<br\s*/?>', ' ', need(page, 'card page')))
        if not sources:
            raise Skip('no CRM description or condition text' + ('; site shows a description' if shown else ''))
        if shown is None:
            raise RuntimeError('CRM text present, card shows no description')
        matched = [k for k, v in sources.items() if v == shown]
        if not matched:
            raise RuntimeError('card description differs from CRM %s' % '/'.join(sources))
        return {'matches': matched}

    def stage():
        card_chip = first(r"<div class='chip'>(.*?)</div>", need(page, 'card page'))
        pill = first(r'class="status-pill"[^>]*>(.*?)</div>', need(fragment, 'catalog card'))
        tile = re.findall(r'<article[^>]*data-stage="([^"]*)"', fragment)
        detail = {'crm_status': card.get('status'), 'catalog_stage': tile, 'catalog_pill': pill, 'card_chip': card_chip}
        if not card_chip or not pill or card_chip.split(' · ')[0] != pill.split(' · ')[0]:
            raise RuntimeError('stage differs between card and catalog: %s' % detail)
        return detail

    return {
        'code': code,
        'card_page_fields': check(lambda: public_fields.verify_core_fields(need(page, 'card page'), card)),
        'catalog_fields': check(lambda: public_fields.verify_core_fields(need(fragment, 'catalog card'), card, catalog=True)),
        'photos': check(lambda: card_gallery(need(page, 'card page'), card)),
        'catalog_photo_count': check(photo_count),
        'price_card_page': check(lambda: price(page, 'card page')),
        'price_catalog': check(lambda: price(fragment, 'catalog card')),
        'price_live_json': check(lambda: price((prices_json.get('cars') or {}).get(code, {}).get('full'), 'live price JSON')),
        'description': check(description),
        'stage': check(stage),
    }


def cars_report(cards, shown, pages, articles, prices_json):
    return [audit_car(c, pages.get(c['auto_number']), articles.get(c['auto_number']), prices_json)
            for c in sorted(cards, key=lambda c: c['auto_number']) if c['auto_number'] in shown]


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
    labels = {}
    for c in cards:
        pill = first(r'class="status-pill"[^>]*>(.*?)</div>', articles.get(c['auto_number']))
        if pill:
            labels.setdefault(str(c.get('status')), set()).add(pill.split(' · ')[0])
    summary['stage_label_by_crm_status'] = {k: sorted(v) for k, v in sorted(labels.items())}
    summary['crm_status_with_several_stage_labels'] = sorted(k for k, v in labels.items() if len(v) > 1)
    cars = cars_report(cards, shown, pages, articles, prices_json)
    counts = {}
    for car in cars:
        for name, value in car.items():
            if isinstance(value, dict):
                counts.setdefault(name, {}).setdefault(value['result'], 0)
                counts[name][value['result']] += 1
    return {'summary': summary, 'check_totals': counts, 'cars': cars}
