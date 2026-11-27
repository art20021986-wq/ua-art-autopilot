"""Copies of the Japan lot photos on the site (video/japan/lots/), so no other domain shows on the page.

As the Korea copies (korea_auction.job.copy_lot_photos: first photos of every lot first, a time limit per run, photos of
lots no longer listed removed), but the Japan auction gives .jpg and .png photos: each copy keeps its own type, so the
site serves it with the right Content-Type. One responsibility: the photo copies.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import time
import urllib.request
from urllib.parse import urlsplit

from korea_auction import job as korea_job
from korea_auction import session

MAX_PHOTO = 8 * 1024 * 1024  # a .png photo is larger than a .jpg one
WORKERS = 6
FIRST = 3  # copied for every lot before the rest


def name(lot_id, url):
    """The site copy of one photo: named by its address (a copy stays right when the list grows), with its type."""
    kind = '.png' if urlsplit(url).path.lower().endswith('.png') else '.jpg'
    return '%s-%s%s' % (lot_id, hashlib.sha256(url.encode('utf-8')).hexdigest()[:12], kind)


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': session._UA})
    with urllib.request.urlopen(request, timeout=30) as response:
        if not response.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError('NOT_AN_IMAGE')
        data = response.read(MAX_PHOTO + 1)
    if len(data) > MAX_PHOTO:
        raise ValueError('PHOTO_TOO_LARGE')
    return data


def copy(lots, folder, fetch=fetch, deadline=None, clock=time.monotonic):
    """Every photo of each lot into `folder`, new copies started only before `deadline` (clock()); copies of photos no
    lot lists any more are removed. -> ({lot id: [copy names, page order]}, copies left for the next run)"""
    folder.mkdir(parents=True, exist_ok=True)
    order = [(n, i, name(lot['id'], url), url) for i, lot in enumerate(lots) for n, url in enumerate(lot['photos'])]
    wanted = {copy_name: url for _, _, copy_name, url in order}
    first_photos_first = sorted(order, key=lambda o: (min(o[0], FIRST), o[1], o[0]))
    missing = list(dict.fromkeys(c for _, _, c, _ in first_photos_first if not (folder / c).exists()))
    late = []

    def one(copy_name):
        if deadline is not None and clock() >= deadline:
            late.append(copy_name)
            return
        try:
            korea_job.write(folder / copy_name, fetch(wanted[copy_name]))
        except (OSError, ValueError):
            pass  # tried again at the next due run

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(one, missing))
    for old in folder.iterdir():
        if old.is_file() and old.name not in wanted:
            old.unlink()
    have = {path.name for path in folder.iterdir()}
    copies = {lot['id']: list(dict.fromkeys(n for n in (name(lot['id'], url) for url in lot['photos']) if n in have))
              for lot in lots}
    return copies, bool(late)
