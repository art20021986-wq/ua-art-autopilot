"""Server job: rebuild the home ticker (video/korea/ticker.html) and the public lot list (video/korea/lots.json).

Runs hourly on PythonAnywhere; works only at 10/12/14 Korea time Mon-Sat, or at any hour while the ticker is missing.
Lot photos are copied to the site (video/korea/img/, video/korea/lots/) so no other domain shows on the page.
One run at a time: a run that finds the previous one still working exits.
The account login is read from LOGIN (two lines: e-mail, password), a file only the owner writes.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

from . import collect, model_lots, prices, public, session, ticker
from .selection import JST

ROOT = Path('/home/Carix')
LOGIN = ROOT / 'jpauto_login.txt'
OUT = ROOT / 'video/korea'
IMG_URL = '/video/korea/img/'
LOT_PAGE = '/video/korea.html'  # its lot card opens at #lot-<id>
RUN_HOURS = (10, 12, 14)
MAX_PHOTO = 3 * 1024 * 1024
LOCK = ROOT / '.korea_auction_job.lock'
PENDING = ROOT / 'korea_auction_data/prices_pending'  # set while some lot pages or lot photos are still to do
WAITING = ROOT / 'korea_auction_data/ticker_waiting'  # TICKER-FIX3-001: set while the auction lists no lots
PHOTO_WORKERS = 6
# KOREA-ENGINE-001 (owner 2026-11-13: every photo in the lot card): photos are copied for a time, not a count, so a run
# ends before the next hourly start and no hourly run is skipped (6000 copies took ~70 min after the lot pages).
RUN_SECONDS = 50 * 60  # photo copying stops this long after the run started
FIRST_PHOTOS = 3  # copied for every lot before the rest


def due(now, ticker_exists, pending=False, stale=False):
    """Korea business mornings Mon-Sat; a missing ticker, unread lot pages or photos left, or a ticker older than the
    installed ticker code (TICKER-FIX-001: a code update shows at the next hourly run): the next hourly run (not on
    Sunday)."""
    return now.weekday() != 6 and (now.hour in RUN_HOURS or not ticker_exists or pending or stale)


def stale(page):
    """The ticker page was written before the installed ticker code (so it lacks the code's changes)."""
    return page.exists() and page.stat().st_mtime < Path(ticker.__file__).stat().st_mtime


def read_login(path=LOGIN):
    lines = [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len(lines) < 2:
        raise RuntimeError('LOGIN_FILE_INCOMPLETE')
    return lines[0], lines[1]


def write(path, data, mode=0o644):
    """Atomic replace, so the site never serves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix='.kt-')
    try:
        with os.fdopen(handle, 'wb') as fh:
            fh.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def fetch_photo(url):
    request = urllib.request.Request(url, headers={'User-Agent': session._UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError('NOT_AN_IMAGE')
        data = response.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise ValueError('PHOTO_TOO_LARGE')
    return data


def localize_photos(items, folder, fetch=fetch_photo):
    """Copy each lot's main photo to the site as it is (TICKER-FIX5-001, owner: no compression), in parallel; lots whose
    photo cannot be copied are left out and the reason goes to the task log. Old photos are removed."""
    def one(item):
        try:
            write(folder / ('%s.jpg' % item['id']), fetch(item['photo']))
            return dict(item, photo=IMG_URL + '%s.jpg' % item['id'])
        except (OSError, ValueError) as error:
            print('ticker photo %s not copied: %s: %s' % (item['id'], type(error).__name__, str(error)[:120]),
                  file=sys.stderr)
            return None

    with ThreadPoolExecutor(PHOTO_WORKERS) as pool:
        kept = [item for item in pool.map(one, items) if item]
    if not kept:  # TICKER-FIX2-001: nothing copied — keep the photos the live ticker still shows
        return kept
    names = {it['photo'].rsplit('/', 1)[1] for it in kept}
    for old in folder.glob('*.jpg'):
        if old.name not in names:
            old.unlink()
    return kept


def copy_lot_photos(lots, folder, fetch=fetch_photo, deadline=None, clock=time.monotonic):
    """Every photo of each lot into `folder`, new copies started only before `deadline` (clock()); other photos are
    removed.

    The first FIRST_PHOTOS of every lot are copied before the rest, so each lot is shown at once and the others
    follow over the next runs (owner 2026-11-12: all photos, gradually). Returns ({lot id: [photo names]}, left).
    """
    folder.mkdir(parents=True, exist_ok=True)
    order = [(n, i, public.photo_name(lot['id'], url), url)
             for i, lot in enumerate(lots) for n, url in enumerate(lot['photos'][:prices.MAX_PHOTOS])]
    wanted = {name: url for _, _, name, url in order}
    missing = [name for n, i, name, _ in sorted(order, key=lambda item: (min(item[0], FIRST_PHOTOS), item[1], item[0]))
               if not (folder / name).exists()]
    missing = list(dict.fromkeys(missing))

    late = []  # copies not started before the deadline (a failed copy is not retried before the next due run)

    def copy(name):
        if deadline is not None and clock() >= deadline:
            late.append(name)  # the next run goes on from here
            return
        try:
            write(folder / name, fetch(wanted[name]))
        except (OSError, ValueError):
            pass

    with ThreadPoolExecutor(PHOTO_WORKERS) as pool:
        list(pool.map(copy, missing))
    for old in folder.glob('*.jpg'):
        if old.name not in wanted:
            old.unlink()
    have = {path.name for path in folder.glob('*.jpg')}
    photos = {lot['id']: list(dict.fromkeys(name for name in (public.photo_name(lot['id'], url)
                                                              for url in lot['photos'][:prices.MAX_PHOTOS])
                                            if name in have)) for lot in lots}
    return photos, bool(late)


def priced(data, browser):
    """The coming days' lots with start price, VIN and photos from their lot pages (prices.py). -> (data, unread)"""
    known = prices.load()
    known, left = prices.fill(browser, data['upcoming_lots'], known)
    prices.save(known)
    return dict(data, upcoming_lots=prices.apply(data['upcoming_lots'], known)), left


def publish_galleries(photos, folder):
    """Each shown lot's gallery file (written only when it changed); files of lots no longer shown are removed."""
    folder.mkdir(parents=True, exist_ok=True)
    for lot_id, names in photos.items():
        path = folder / ('%s.json' % lot_id)
        data = json.dumps(public.gallery(names), separators=(',', ':')).encode('utf-8')
        if not path.exists() or path.read_bytes() != data:
            write(path, data)
    for old in folder.glob('*.json'):
        if old.stem not in photos:
            old.unlink()


def publish_lots(data, now, folder, deadline=None):
    """lots.json of the copied photos. -> (lots shown, photos still to copy)"""
    photos, left = copy_lot_photos(data['upcoming_lots'], folder / 'lots', deadline=deadline)
    value = public.build(data['upcoming_lots'], data['auction_date'], data['rates'], photos,
                         now.isoformat(timespec='minutes'))
    write(folder / 'lots.json', json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    publish_galleries({view['id']: photos[view['id']] for view in value['lots']}, folder / 'gallery')
    # KOREA-MODEL-LOTS-001: the order page model carousels show the week's lots of each model (from the list above)
    shown = {view['id']: view for view in value['lots']}
    listed = [dict(lot, start_usd=shown[lot['id']]['start_usd']) for lot in data['upcoming_lots'] if lot['id'] in shown]
    models = model_lots.select(listed, model_lots.KOREA, {key: view['photos'] for key, view in shown.items()},
                               now.strftime('%Y/%m/%d %H:%M'), LOT_PAGE)
    write(folder / 'model-lots.json', json.dumps(models, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    return len(value['lots']), left


def mark_pending(pending, path=None):
    """While lot pages or photos are left, the next hourly run works too."""
    path = path or PENDING
    if pending:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        path.touch()
    else:
        path.unlink(missing_ok=True)


def build(data, now, folder):
    if not data['items']:  # TICKER-FIX2-001: before the photo copy, which removes the photos it doesn't keep
        raise RuntimeError('NO_TICKER_ITEMS')
    data = dict(data, items=localize_photos(data['items'], folder))
    if not data['items']:
        raise RuntimeError('NO_TICKER_ITEMS')
    tomorrow = data['auction_date'] == (now + timedelta(days=1)).strftime('%Y/%m/%d')
    return data, ticker.render(data, tomorrow=tomorrow)


def main(now=None):
    now = now or datetime.now(JST)
    page = OUT / 'ticker.html'
    if not due(now, page.exists() and (OUT / 'lots.json').exists(), PENDING.exists() or WAITING.exists(),
               stale(page)):
        return 0
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the previous run is still working
        deadline = time.monotonic() + RUN_SECONDS
        browser = session.Session()
        data = collect.collect(*read_login(), now=now, session=browser)
        pages_left = photos_left = False
        if not data['items']:
            # TICKER-FIX3-001: the auction lists no lots yet — the tile (score legend) and the owner's cars, no lot
            # photos; the lot list stays; retried every hour until lots are listed.
            html = ticker.render(data)
            if not html:
                raise RuntimeError('NO_TICKER_ITEMS')
            write(page, html.encode('utf-8'))
            WAITING.parent.mkdir(parents=True, exist_ok=True)
            WAITING.touch()
            shown = 0
        else:
            data, html = build(data, now, OUT / 'img')
            write(page, html.encode('utf-8'))  # the ticker first: the lot pages and photos take a while
            WAITING.unlink(missing_ok=True)
            data_priced, pages_left = priced(data, browser)
            shown, photos_left = publish_lots(data_priced, now, OUT, deadline)
            mark_pending(pages_left or photos_left)
    print(json.dumps({'at': now.isoformat(timespec='minutes'), 'auction_date': data['auction_date'],
                      'lots_on_date': data['lots_on_date'], 'lots_shown': shown, 'items': len(data['items']),
                      'pages_left': pages_left, 'photos_left': photos_left}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
