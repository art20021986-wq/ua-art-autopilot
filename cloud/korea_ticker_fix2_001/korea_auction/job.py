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
import urllib.request

from . import collect, prices, public, session, ticker
from .selection import JST

ROOT = Path('/home/Carix')
LOGIN = ROOT / 'jpauto_login.txt'
OUT = ROOT / 'video/korea'
IMG_URL = '/video/korea/img/'
RUN_HOURS = (10, 12, 14)
MAX_PHOTO = 3 * 1024 * 1024
LOCK = ROOT / '.korea_auction_job.lock'
PRICES_PENDING = ROOT / 'korea_auction_data/prices_pending'  # set while some lot prices are still unread
PHOTO_WORKERS = 6


def due(now, ticker_exists, prices_pending=False, stale=False):
    """Korea business mornings Mon-Sat; a missing ticker, unread lot prices or a ticker older than the installed
    ticker code (TICKER-FIX-001: a code update shows at the next hourly run): the next hourly run (not on Sunday)."""
    return now.weekday() != 6 and (now.hour in RUN_HOURS or not ticker_exists or prices_pending or stale)


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


TICKER_PHOTO_WIDTH = 480  # TICKER-PHOTO-001: the ticker card shows 240 px; twice that for sharp phone screens


def ticker_photo(data):
    """A light JPEG copy for the ticker card (the auction original is up to 3 MB); the original if it can't be read."""
    from io import BytesIO
    try:
        from PIL import Image
        with Image.open(BytesIO(data)) as image:
            if image.width <= TICKER_PHOTO_WIDTH:
                return data
            height = max(1, round(image.height * TICKER_PHOTO_WIDTH / image.width))
            out = BytesIO()
            image.convert('RGB').resize((TICKER_PHOTO_WIDTH, height), Image.LANCZOS).save(
                out, 'JPEG', quality=82, optimize=True, progressive=True)
            return out.getvalue()
    except Exception:  # never lose a lot over its photo copy
        return data


def localize_photos(items, folder, fetch=fetch_photo):
    """Copy each lot's main photo to the site, light and in parallel (TICKER-PHOTO-001); lots whose photo cannot be
    copied are left out. Old photos are removed."""
    def one(item):
        try:
            write(folder / ('%s.jpg' % item['id']), ticker_photo(fetch(item['photo'])))
            return dict(item, photo=IMG_URL + '%s.jpg' % item['id'])
        except (OSError, ValueError):
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


def copy_lot_photos(lots, folder, fetch=fetch_photo):
    """Up to public.PHOTOS_PER_LOT photos per lot into `folder`; photos already there are kept, others removed.

    Returns {lot id: [photo names copied]}.
    """
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {public.photo_name(lot['id'], n): url
              for lot in lots for n, url in enumerate(lot['photos'][:public.PHOTOS_PER_LOT], 1)}
    missing = [name for name in wanted if not (folder / name).exists()]

    def copy(name):
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
    return {lot['id']: [public.photo_name(lot['id'], n) for n in range(1, public.PHOTOS_PER_LOT + 1)
                        if public.photo_name(lot['id'], n) in have] for lot in lots}


def priced(data, browser):
    """The day's lots with their start prices (prices.py), the ticker's own prices included."""
    known = prices.load()
    known.update({item['id']: item['start_price_krw'] for item in data['items'] if item.get('start_price_krw')})
    known, left = prices.fill(browser, data['day_lots'], known)
    prices.save(known)
    if left:
        PRICES_PENDING.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        PRICES_PENDING.touch()
    else:
        PRICES_PENDING.unlink(missing_ok=True)
    return dict(data, day_lots=prices.apply(data['day_lots'], known))


def publish_lots(data, now, folder):
    photos = copy_lot_photos(data['day_lots'], folder / 'lots')
    value = public.build(data['day_lots'], data['auction_date'], data['rates'], photos,
                         now.isoformat(timespec='minutes'))
    write(folder / 'lots.json', json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    return len(value['lots'])


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
    if not due(now, page.exists() and (OUT / 'lots.json').exists(), PRICES_PENDING.exists(), stale(page)):
        return 0
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the previous run is still working
        browser = session.Session()
        data = collect.collect(*read_login(), now=now, session=browser)
        data, html = build(data, now, OUT / 'img')
        write(page, html.encode('utf-8'))  # the ticker first: the lot prices take a while
        shown = publish_lots(priced(data, browser), now, OUT)
    print(json.dumps({'at': now.isoformat(timespec='minutes'), 'auction_date': data['auction_date'],
                      'lots_on_date': data['lots_on_date'], 'lots_shown': shown, 'items': len(data['items'])}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
