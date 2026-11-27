"""Server job (JAPAN-LHD-001, owner 2026-11-27 «Да»): the Japan auctions' left-hand-drive lots on the site.

Hourly on PythonAnywhere (japan_ticker_job.py), working at RUN_HOURS Japan time Mon-Sat, or at any hour while lot pages
or photos are left; after the Japan midnight it only drops the past days. Writes video/japan/lots.json (the Japan page),
video/japan/gallery/<id>.json, video/japan/lots/ (photo copies, so no other domain shows on the page) and
video/japan/feed.json (the home ticker's Japan cars and «Японія» tab; the Korea job reads it). One run at a time.
The account login is the Korea job's (LOGIN). The shared pieces — session, atomic write, photo copies, the week —
are the Korea collector's (korea_auction), unchanged.
"""
from datetime import datetime
import fcntl
import json
from pathlib import Path
import re
import sys
import time

from korea_auction import job as korea_job
from korea_auction import rollover, session
from korea_auction.selection import JST, auction_date

from . import lot_page, money, photos, search, views

ROOT = Path('/home/Carix')
OUT = ROOT / 'video/japan'
DATA = ROOT / 'japan_auction_data'
PAGES = DATA / 'pages.json'  # each lot page read once: {lot id: lot_page.entry}
PENDING = DATA / 'pending'  # set while lot pages or photos are left
LOCK = ROOT / '.japan_auction_job.lock'
RUN_HOURS = (9, 12, 15, 18, 21)  # Japan time; the list is small (~50 lots), a few reads a day
ROLLOVER_HOUR = 0
RUN_SECONDS = 40 * 60  # photo copies start only this long after the run started
PAGE_SECONDS = 20 * 60  # lot pages are read only this long after the run started


def due(now, published, pending=False):
    """Japan business hours Mon-Sat; no lot list yet or work left: the next hourly run (not on Sunday)."""
    return now.weekday() != 6 and (now.hour in RUN_HOURS or not published or pending)


def load_pages(path=None):
    try:
        value = json.loads((path or PAGES).read_bytes())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def read_pages(browser, lots, known, until=None, clock=time.monotonic):
    """Each lot's page (start price in yen, VIN, photos, fuel, colour), read once and remembered; lots that left the
    list are forgotten; none read after `until`. -> (known, lots still unread)"""
    known = {k: v for k, v in known.items() if k in {lot['id'] for lot in lots}}
    for lot in lots:
        if lot['id'] in known:
            continue
        if until is not None and clock() >= until:
            break
        try:
            _, html = browser.fetch(lot['detail_url'])
        except OSError:
            continue
        known[lot['id']] = lot_page.entry(html)
    return known, sum(1 for lot in lots if lot['id'] not in known)


# JAPAN-LHD-FIX-001 (live 27.11: the auction's «Left-Hand Drive» box also matches «LEFT SIDE DOOR», «LEFT POWER SLIDE
# DOOR» in Auct Kyouyuu / JU Kyouyuu lot texts — right-hand-drive Japanese cars): left-hand drive only on proof.
EXPLICIT = re.compile(r'\bLEFT[- ]?HAND\b|\bLEFT STEERING\b|\bLHD\b|左ハンドル')


def left_hand(lot, page):
    """The lot is left-hand drive: its text says so in so many words («LEFT HAND DRIVE», «LEFT STEERING WHEEL», «LHD»),
    or its lot page says «Steering Wheel Left» and its text has no other «LEFT» (a door, a mirror) the box could match."""
    text = ' '.join((lot.get('model', ''), lot.get('trim', ''))).upper()
    return bool(EXPLICIT.search(text)) or (page.get('steering') == 'Left' and 'LEFT' not in text)


def with_pages(lots, known):
    """The left-hand-drive lots (left_hand; a lot whose page is not read yet waits) with their lot page's price, VIN,
    photos, fuel and colour (owner 2026-11-26: only left-hand drive)."""
    out = []
    for lot in lots:
        page = known.get(lot['id'], {})
        if not left_hand(lot, page):
            continue
        out.append(dict(lot, start_price_jpy=page.get('jpy') or lot['start_price_jpy'], vin=page.get('vin', ''),
                        photos=page.get('photos') or lot['photos'], fuel=page.get('fuel', ''),
                        color=page.get('color', '')))
    return out


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def publish(lots, rates, now, folder, deadline=None, fetch=photos.fetch):
    """lots.json, the galleries and feed.json of the lots whose photos were copied. -> (lots shown, photos left)"""
    copies, left = photos.copy(lots, folder / 'lots', fetch=fetch, deadline=deadline)
    stamp = now.isoformat(timespec='minutes')
    value = views.build(lots, rates, copies, stamp)
    korea_job.write(folder / 'lots.json', _json(value))
    shown = {view['id']: copies[view['id']] for view in value['lots']}
    gallery = folder / 'gallery'
    gallery.mkdir(parents=True, exist_ok=True)
    for lot_id, names in shown.items():
        path, data = gallery / ('%s.json' % lot_id), _json(views.gallery(names))
        if not path.exists() or path.read_bytes() != data:
            korea_job.write(path, data)
    for old in gallery.glob('*.json'):
        if old.stem not in shown:
            old.unlink()
    korea_job.write(folder / 'feed.json', _json(views.feed(value['lots'], now.strftime('%Y/%m/%d'), stamp)))
    return len(value['lots']), left


def roll(now, folder=None):
    """After the Japan midnight: lots.json and feed.json without the past days (the feed's week again from today)."""
    folder = folder or OUT
    today = now.strftime('%Y/%m/%d')
    try:
        value = json.loads((folder / 'lots.json').read_bytes())
    except (OSError, ValueError):
        return
    value = rollover.current_lots(value, today)
    korea_job.write(folder / 'lots.json', _json(value))
    korea_job.write(folder / 'feed.json', _json(views.feed(value['lots'], today, now.isoformat(timespec='minutes'))))


def main(now=None):
    now = now or datetime.now(JST)
    full = due(now, (OUT / 'lots.json').exists(), PENDING.exists())
    if not full and now.hour != ROLLOVER_HOUR:
        return 0
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the previous run is still working
        if not full:
            roll(now)
            print(json.dumps({'at': now.isoformat(timespec='minutes'), 'rollover': True}))
            return 0
        started = time.monotonic()
        browser = session.Session()
        browser.login(*korea_job.read_login())
        count, lots = search.left_hand_lots(browser)
        lots = [lot for lot in lots if auction_date(lot) >= now.strftime('%Y/%m/%d')]
        known, pages_left = read_pages(browser, lots, load_pages(), started + PAGE_SECONDS)
        DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
        korea_job.write(PAGES, _json(known), mode=0o600)
        shown, photos_left = publish(with_pages(lots, known), money.fetch_rates(), now, OUT, started + RUN_SECONDS)
        korea_job.mark_pending(pages_left or photos_left, PENDING)
    print(json.dumps({'at': now.isoformat(timespec='minutes'), 'listed': count, 'read': len(lots), 'shown': shown,
                      'pages_left': pages_left, 'photos_left': photos_left, 'requests': browser.requests}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
