"""Server job: rebuild the home ticker (video/korea/ticker.html) from the auction account.

Runs hourly on PythonAnywhere; works only at 10/12/14 Korea time Mon-Sat, or at any hour while the ticker is missing.
Lot photos are copied to the site (video/korea/img/) so no other domain shows on the page.
The account login is read from LOGIN (two lines: e-mail, password), a file only the owner writes.
"""
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

from . import collect, session, ticker
from .selection import JST

ROOT = Path('/home/Carix')
LOGIN = ROOT / 'jpauto_login.txt'
OUT = ROOT / 'video/korea'
IMG_URL = '/video/korea/img/'
RUN_HOURS = (10, 12, 14)
MAX_PHOTO = 3 * 1024 * 1024


def due(now, ticker_exists):
    """Korea business mornings Mon-Sat; a missing ticker is built at the next hourly run (not on Sunday)."""
    return now.weekday() != 6 and (now.hour in RUN_HOURS or not ticker_exists)


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
    """Copy each lot photo to the site; lots whose photo cannot be copied are left out. Old photos are removed."""
    kept = []
    for item in items:
        name = '%s.jpg' % item['id']
        try:
            write(folder / name, fetch(item['photo']))
        except (OSError, ValueError):
            continue
        kept.append(dict(item, photo=IMG_URL + name))
    names = {it['photo'].rsplit('/', 1)[1] for it in kept}
    for old in folder.glob('*.jpg'):
        if old.name not in names:
            old.unlink()
    return kept


def build(data, now, folder):
    data = dict(data, items=localize_photos(data['items'], folder))
    if not data['items']:
        raise RuntimeError('NO_TICKER_ITEMS')
    tomorrow = data['auction_date'] == (now + timedelta(days=1)).strftime('%Y/%m/%d')
    return data, ticker.render(data, tomorrow=tomorrow)


def main(now=None):
    now = now or datetime.now(JST)
    page = OUT / 'ticker.html'
    if not due(now, page.exists()):
        return 0
    data = collect.collect(*read_login(), now=now)
    data, html = build(data, now, OUT / 'img')
    write(page, html.encode('utf-8'))
    print(json.dumps({'at': now.isoformat(timespec='minutes'), 'auction_date': data['auction_date'],
                      'lots_on_date': data['lots_on_date'], 'items': len(data['items'])}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
