"""Morning collector: Korea lots of the next auction day -> JSON for the site ticker.

Read-only: logs in, reads the search results and a few lot cards, writes one JSON file.
Usage: python3 -I -m korea_auction.collect OUT.json   (env JPAUTO_EMAIL, JPAUTO_PASSWORD)
"""
import json
import os
import random
import re
import sys
from datetime import datetime

from . import catalog, lots, nbu, selection
from .session import Session

SEARCH_PAGE = '/vehicle-search/kr/'
TICKER_SIZE = 150  # TICKER-FIX5-001 (owner 2026-11-12): up to ten times more popular-model auction cars
MAX_DETAILS = 180
PAGE_LIMIT = 2000
MAX_PAGES = 5


def _search_form_data(html):
    """Hidden fields and default-checked boxes of the Korea search form (no other filters = all lots)."""
    form = html[html.find('id="purchase_search_form"'):]
    form = form[:form.find('</form>')]
    data = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', form):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name and name.group(1) not in ('history_idx_url', 'koreafavoriteurl', 'koreahistoryurl'):
            data.append((name.group(1), value.group(1) if value else ''))
    # TICKER-FIX4-001: the boxes the form checks by default (auction groups, closed orders) go too, as a browser sends
    # them; without them the site lists «0 Results» since 11.11 (probe SOCIAL-PROBE-20261112-R12: with them 989).
    for tag in re.findall(r'(?is)<input[^>]*type="(?:checkbox|radio)"[^>]*>', form):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name and re.search(r'(?i)\schecked\b', tag):
            data.append((name.group(1), value.group(1) if value else 'on'))
    action = re.search(r'action="([^"]+)"', html[html.find('id="purchase_search_form"') - 300:])
    return (action.group(1) if action else '/vehicle-search/kr/index'), data


def fetch_all_lots(s):
    """All current Korea lots, using the largest page size the site offers."""
    _, page = s.fetch(SEARCH_PAGE)
    action, data = _search_form_data(page)
    _, html = s.fetch(action, data)
    total = int((re.findall(r'([\d,]+) Results', html) or ['0'])[0].replace(',', ''))
    found = lots.parse_results(html)
    pager = re.search(r'href="(/vehicle-search/kr/index/page=\d+\?[^"]+)"', html)
    if pager and len(found) < total:
        base = pager.group(1).replace('&amp;', '&')
        found = []
        for n in range(1, MAX_PAGES + 1):
            url = re.sub(r'page=\d+', 'page=%d' % n, base) + '&limit=%d' % PAGE_LIMIT
            _, html = s.fetch(url)
            batch = lots.parse_results(html)
            found += batch
            if not batch or len(found) >= total:
                break
    return total, found


def display_name(maker, model):
    """'KIA', 'SANTA FE' -> 'Kia Santa Fe'; words with digits stay as is ('K5', 'G80')."""
    words = (maker + ' ' + model).split()
    return ' '.join(w if any(c.isdigit() for c in w) else '-'.join(p.capitalize() for p in w.split('-'))
                    for w in words)


def ticker_item(lot, detail, rates):
    price = detail['start_price_krw'] or lot['start_price_krw']
    return {
        'id': lot['id'],
        'title': display_name(lot['maker'], lot['model']),
        'model': selection.top_model(lot) or lot['model'],
        'year': lot['year'], 'mileage_km': lot['mileage_km'], 'score': lot['score'],
        'fuel': detail['fuel'], 'start_price_krw': price,
        'start_price_usd': nbu.krw_to_usd(price, rates),
        'photo': (detail['photos'] or lot['photos'])[0],
        'auction_start_jst': lot['auction_start'],
        'hot': selection.is_hot(price, detail['market_sold_krw']),
    }


OWN_IN_TICKER = 8


def _own_for_ticker(cars, rng=random):
    """Owner's cars with photo and price, absolute links, random order, at most OWN_IN_TICKER."""
    ready = [dict(c, title=display_name(*c['title'].split(' ', 1)), photo=catalog.absolute(c['photo']),
                  url=catalog.absolute(c['url']))
             for c in cars if c['photo'] and c['price_usd']]
    rng.shuffle(ready)
    return ready[:OWN_IN_TICKER]


def collect(email, password, now=None, session=None):
    s = session or Session()
    s.login(email, password)
    total, all_lots = fetch_all_lots(s)
    date = selection.next_auction_date(all_lots, now)
    rates = nbu.fetch_rates()
    own_cars = catalog.parse(catalog.fetch())
    rules = catalog.model_rules(own_cars)
    today, next_days = selection.today_and_next_days(all_lots, now)
    tomorrow = selection.day_after(today)
    items, details = [], 0
    for day in selection.ticker_dates(all_lots, now):  # TICKER-FIX6-001: next days, then today, until full
        for lot in selection.candidates(all_lots, day, lambda l: catalog.same_model(l, rules)):
            if len(items) >= TICKER_SIZE or details >= MAX_DETAILS:
                break
            details += 1
            _, html = s.fetch(lot['detail_url'])
            detail = lots.parse_detail(html)
            if detail['start_price_krw'] or lot['start_price_krw']:
                items.append(dict(ticker_item(lot, detail, rates), tomorrow=day == tomorrow))
    return {
        'generated_at': (now or datetime.now(selection.JST)).isoformat(timespec='minutes'),
        'auction_date': date,
        # KOREA-TILE-001 (owner 2026-11-13): the yellow tile — today's car count and the 3 nearest auction days
        'lots_today': sum(1 for l in all_lots if selection.auction_date(l) == today),
        'houses_today': selection.houses(all_lots, today),
        'next_days': [{'date': d, 'lots': n, 'houses': selection.houses(all_lots, d)} for d, n in next_days],
        'lots_total': total, 'lots_parsed': len(all_lots),
        'lots_on_date': sum(1 for l in all_lots if selection.auction_date(l) == date),
        'nbu': {'date': rates['date'], 'usd_uah': rates['USD'], 'krw_uah': rates['KRW']},
        'items': items, 'requests': s.requests,
        'own': _own_for_ticker(own_cars),
        # for the public lot list (public.py); not part of the ticker
        # every lot of the coming auction days (owner 2026-11-11: the visitor picks the day)
        'upcoming_lots': selection.upcoming(all_lots, now), 'rates': rates,
    }


def main(argv):
    result = collect(os.environ['JPAUTO_EMAIL'], os.environ['JPAUTO_PASSWORD'])
    with open(argv[1], 'w', encoding='utf-8') as fh:
        json.dump({k: v for k, v in result.items() if k != 'upcoming_lots'}, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != 'upcoming_lots'}, ensure_ascii=False))  # no account data
    if not result['items']:
        raise SystemExit('NO_TICKER_ITEMS')


if __name__ == '__main__':
    main(sys.argv)
