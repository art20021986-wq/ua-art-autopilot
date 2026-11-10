"""Morning collector: Korea lots of the next auction day -> JSON for the site ticker.

Read-only: logs in, reads the search results and a few lot cards, writes one JSON file.
Usage: python3 -I -m korea_auction.collect OUT.json   (env JPAUTO_EMAIL, JPAUTO_PASSWORD)
"""
import json
import os
import re
import sys
from datetime import datetime

from . import lots, nbu, selection
from .session import Session

SEARCH_PAGE = '/vehicle-search/kr/'
TICKER_SIZE = 15
MAX_DETAILS = 25
PAGE_LIMIT = 2000
MAX_PAGES = 5


def _search_form_data(html):
    """Hidden fields of the Korea search form (no filters = all lots)."""
    form = html[html.find('id="purchase_search_form"'):]
    form = form[:form.find('</form>')]
    data = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', form):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name and name.group(1) not in ('history_idx_url', 'koreafavoriteurl', 'koreahistoryurl'):
            data.append((name.group(1), value.group(1) if value else ''))
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


def ticker_item(lot, detail, rates):
    price = detail['start_price_krw'] or lot['start_price_krw']
    return {
        'id': lot['id'],
        'title': '%s %s' % (lot['maker'].title(), lot['model']),
        'model': selection.top_model(lot),
        'year': lot['year'], 'mileage_km': lot['mileage_km'], 'score': lot['score'],
        'fuel': detail['fuel'], 'start_price_krw': price,
        'start_price_usd': nbu.krw_to_usd(price, rates),
        'photo': (detail['photos'] or lot['photos'])[0],
        'auction_start_jst': lot['auction_start'],
        'hot': selection.is_hot(price, detail['market_sold_krw']),
    }


def collect(email, password, now=None):
    s = Session()
    s.login(email, password)
    total, all_lots = fetch_all_lots(s)
    date = selection.next_auction_date(all_lots, now)
    rates = nbu.fetch_rates()
    items, details = [], 0
    for lot in selection.candidates(all_lots, date) if date else []:
        if len(items) >= TICKER_SIZE or details >= MAX_DETAILS:
            break
        details += 1
        _, html = s.fetch(lot['detail_url'])
        detail = lots.parse_detail(html)
        if detail['start_price_krw'] or lot['start_price_krw']:
            items.append(ticker_item(lot, detail, rates))
    return {
        'generated_at': (now or datetime.now(selection.JST)).isoformat(timespec='minutes'),
        'auction_date': date,
        'lots_total': total, 'lots_parsed': len(all_lots),
        'lots_on_date': sum(1 for l in all_lots if selection.auction_date(l) == date),
        'nbu': {'date': rates['date'], 'usd_uah': rates['USD'], 'krw_uah': rates['KRW']},
        'items': items, 'requests': s.requests,
    }


def main(argv):
    result = collect(os.environ['JPAUTO_EMAIL'], os.environ['JPAUTO_PASSWORD'])
    with open(argv[1], 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps(result, ensure_ascii=False))  # auction lot data only; no account details
    if not result['items']:
        raise SystemExit('NO_TICKER_ITEMS')


if __name__ == '__main__':
    main(sys.argv)
