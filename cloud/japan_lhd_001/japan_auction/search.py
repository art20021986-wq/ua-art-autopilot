"""The Japan search of the auction account, left-hand drive only (JAPAN-LHD-001, owner 2026-11-26: «только машины с
левым рулём»): every listed lot with the auction's own «Left-Hand Drive» box checked (probe JAPAN-LHD-PROBE-R2:
left_hd[]=L, 43 of 101 036 lots on 27.11).

The results table has the Korea table's columns (korea_auction.lots.parse_results reads it); the price column is in
yen, and the house cell is «House / Port (lot)». One responsibility: the search and its rows.
"""
import re

from korea_auction import lots

SEARCH_PAGE = '/vehicle-search/jp/'
DEFAULT_ACTION = '/vehicle-search/jp/index'
LEFT_HAND = ('left_hd[]', 'L')
PAGE_LIMIT = 2000  # the largest page size the site offers (as the Korea search)
MAX_PAGES = 3
SKIP = re.compile(r'(?:favoriteurl|historyurl|history_idx_url)$')  # the account's saved searches: never sent


def form_data(html):
    """(action, data) of the search form as a browser sends it by default (hidden fields, checked boxes), plus the
    left-hand-drive box."""
    start = html.find('id="purchase_search_form"')
    if start < 0:
        raise RuntimeError('JAPAN_SEARCH_FORM_MISSING')
    form = html[start:]
    form = form[:form.find('</form>')]
    data = []
    for tag in re.findall(r'(?is)<input\b[^>]*>', form):
        name = re.search(r'name="([^"]+)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        kind = re.search(r'type="([^"]+)"', tag)
        kind = kind.group(1).lower() if kind else ''
        if not name or SKIP.search(name.group(1)) or name.group(1) == LEFT_HAND[0]:
            continue
        if kind == 'hidden' or (kind in ('checkbox', 'radio') and re.search(r'(?i)\schecked\b', tag)):
            data.append((name.group(1), value.group(1) if value else 'on'))
    if LEFT_HAND[0] not in form:
        raise RuntimeError('JAPAN_LEFT_HAND_BOX_MISSING')  # never the whole Japan list instead
    action = re.search(r'action="([^"]+)"', html[html.rfind('<form', 0, start):start + 300])
    return (action.group(1) if action else DEFAULT_ACTION), data + [LEFT_HAND]


def rows(html):
    """Results page -> lots, as korea_auction.lots.parse_results, with the yen price and the house without the port."""
    found = []
    for lot in lots.parse_results(html):
        house, _, port = lot['house'].partition(' / ')
        jpy = lot.pop('start_price_krw')
        found.append(dict(lot, house=house.strip(), port=port.strip(), start_price_jpy=jpy))
    return found


def total(html):
    return int((re.findall(r'([\d,]+) Results', html) or ['0'])[0].replace(',', ''))


def pages(html):
    """The results pager link (any page), or None."""
    found = re.search(r'href="([^"]*/vehicle-search/jp/[^"]*page=\d+[^"]*)"', html)
    return found.group(1).replace('&amp;', '&') if found else None


def left_hand_lots(session):
    """Every listed left-hand-drive lot: (count the auction gives, lots read)."""
    _, page = session.fetch(SEARCH_PAGE)
    action, data = form_data(page)
    _, html = session.fetch(action, data)
    count, found = total(html), rows(html)
    pager = pages(html)
    if pager and len(found) < count:
        found = []
        for n in range(1, MAX_PAGES + 1):
            url = re.sub(r'page=\d+', 'page=%d' % n, pager)
            url += ('&' if '?' in url else '?') + 'limit=%d' % PAGE_LIMIT
            _, html = session.fetch(url)
            batch = rows(html)
            found += batch
            if not batch or len(found) >= count:
                break
    return count, found
