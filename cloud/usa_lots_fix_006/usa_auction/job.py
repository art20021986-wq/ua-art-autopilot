"""Hourly server job (USA-LOTS-001, owner 2026-11-27): the USA lots of IAAI's open pages on the site.

Gentle by design: at most REQUESTS requests a run, a pause between them, our own client name; each make-and-model
listing is read again only after LISTING_HOURS, each lot page once. Writes video/usa/lots.json (the USA page, the home
search summary), video/usa/gallery/<id>.json, video/usa/lots/ (photo copies: no other domain shows on the site) and
video/usa/feed.json (the home ticker's USA cards). IAAI refusing us stops the run; the published files stay. One run
at a time.
"""
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.parse

from . import fetch, pages, selection, views

ROOT = Path('/home/Carix')
OUT = ROOT / 'video/usa'
DATA = ROOT / 'usa_auction_data'
LOCK = ROOT / '.usa_auction_job.lock'
SITEMAP = 'https://www.iaai.com/Xj9rDOVMEi0hc38S/sitemap_index.xml'  # named in iaai.com/robots.txt
REQUESTS = 60
LISTINGS_PER_RUN = 6
PHOTO_RESERVE = 20  # USA-LOTS-FIX-003: requests kept for photo copies in every run
LISTING_HOURS = 12
MODELS_DAYS = 7
PHOTOS_PER_LOT = 8


def write(path, data, mode=0o644):
    """Atomic replace, so the site never serves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix='.usa-')
    try:
        with os.fdopen(handle, 'wb') as out:
            out.write(data)
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def load(path, default):
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def stamp(now):
    return now.strftime('%Y-%m-%dT%H:%MZ')


def older(value, now, hours):
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%MZ').replace(tzinfo=timezone.utc) < now - timedelta(hours=hours)
    except (TypeError, ValueError):
        return True


def names(url):
    """A listing address -> (make, model) as IAAI writes them («TOYOTA», «RAV4»)."""
    m = re.search(r'/Vehiclelisting/([^/]+)/([^/]+)', url, re.I)
    return tuple(urllib.parse.unquote_plus(part) for part in m.groups()) if m else ('', '')


def model_urls(client):
    """The listing address of each popular model, from IAAI's make-and-model sitemap: {"make|model": url}."""
    index = pages.text(client.page(SITEMAP))
    part = next((u for u in re.findall(r'https?://\S+?MakeModel1\.xml', index)), '')
    if not part:
        return {}
    found = {}
    for url in re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', client.page(part)):
        m = re.search(r'/Vehiclelisting/([^/]+)/([^/]+)/?$', url, re.I)
        if m:
            make, model = names(url)
            if selection.popular(make, model):
                found['%s|%s' % (make.lower(), model.lower())] = url
    return found


def refresh(client, data, now):
    """Read the make-and-model listings due again (oldest first), at most LISTINGS_PER_RUN."""
    if not data['models'] or older(data.get('models_at'), now, MODELS_DAYS * 24):
        data['models'], data['models_at'] = model_urls(client) or data['models'], stamp(now)
    due = sorted((data['listings'].get(k, {}).get('at', ''), k) for k in data['models']
                 if older(data['listings'].get(k, {}).get('at'), now, LISTING_HOURS))
    unreadable = 0
    for n, (_, key) in enumerate(due[:LISTINGS_PER_RUN], 1):
        url = data['models'][key]
        lots = pages.listing(client.page(url), *names(url))
        if lots and not any(lot['damage'] for lot in lots):
            # USA-LOTS-FIX-003: one listing that does not read (an odd model page) is skipped until its next turn;
            # only when every listing of the run fails, the page itself changed: stop asking IAAI
            unreadable += 1
            data['listings'][key] = {'at': stamp(now), 'lots': []}
            if unreadable == n and n >= 3:
                raise fetch.Closed('LISTING_UNREADABLE')
            continue
        data['listings'][key] = {'at': stamp(now), 'lots': lots}
    for key in list(data['listings']):
        if key not in data['models']:
            del data['listings'][key]


def read_lots(client, chosen, known, now, budget=None, enough=None):
    """Each chosen lot's page and photo list, read once and remembered in `known` as it is read (USA-LOTS-FIX-003: a
    run that hits its request limit keeps what it read); lots no longer chosen are forgotten. Stops when `enough`
    lots run and drive, or when the run has used `budget` requests (the rest is for photos)."""
    for lot_id in [k for k in known if k not in {lot['id'] for lot in chosen}]:
        del known[lot_id]
    for lot in chosen:
        if enough is not None and sum(1 for l in chosen if known.get(l['id'], {}).get('runs')) >= enough:
            break
        if budget is not None and client.requests >= budget:
            break
        if lot['id'] in known:
            continue
        try:
            entry = pages.lot(client.page('https://www.iaai.com/VehicleDetail/%s~US' % lot['id']), now)
            photo_list = entry.pop('photo_list', '')
            # USA-LOTS-FIX-002: the photo list only of a lot that runs and drives (the only ones shown)
            entry['photos'] = pages.photo_urls(client.json(photo_list)) if photo_list and entry['runs'] else []
        except (OSError, ValueError):
            continue  # USA-LOTS-FIX-002: one unreadable lot page skips that lot, not the run
        known[lot['id']] = entry
    return known


def photo_name(lot_id, url):
    return '%s-%s.jpg' % (lot_id, hashlib.sha256(url.encode('utf-8')).hexdigest()[:12])


def copy_photos(client, lots, folder):
    """Up to PHOTOS_PER_LOT photos of each lot into `folder` (first photos of every lot first); copies no lot lists
    any more are removed. -> {lot id: [copy names]}"""
    folder.mkdir(parents=True, exist_ok=True)
    wanted = {lot['id']: [photo_name(lot['id'], u) for u in lot['photos'][:PHOTOS_PER_LOT]] for lot in lots}
    urls = {photo_name(lot['id'], u): u for lot in lots for u in lot['photos'][:PHOTOS_PER_LOT]}
    order = [names[n] for n in range(PHOTOS_PER_LOT) for names in wanted.values() if n < len(names)]
    for name in order:
        if (folder / name).exists():
            continue
        try:
            write(folder / name, client.photo(urls[name]))
        except fetch.Closed:
            break
        except (OSError, ValueError):
            continue
    for old in folder.iterdir():
        if old.is_file() and old.name not in urls:
            old.unlink()
    have = {p.name for p in folder.iterdir()}
    return {lot_id: [n for n in names if n in have] for lot_id, names in wanted.items()}


def publish(lots, copies, now, folder):
    value = views.build(lots, copies, stamp(now))
    write(folder / 'lots.json', dump(value))
    gallery = folder / 'gallery'
    gallery.mkdir(parents=True, exist_ok=True)
    shown = {v['id'] for v in value['lots']}
    for lot_id in shown:
        write(gallery / ('%s.json' % lot_id), dump(views.gallery(copies[lot_id])))
    for old in gallery.glob('*.json'):
        if old.stem not in shown:
            old.unlink()
    write(folder / 'feed.json', dump(views.feed(value['lots'], stamp(now))))
    return len(value['lots'])


def run(client, data, now, folder):
    """One run: listings due, the choice, the chosen lots' pages and photos, the published files."""
    stop = ''
    # USA-LOTS-FIX: listings read before the fix (no damage read) are read again; an empty one waits its turn
    data['listings'] = {k: v for k, v in data['listings'].items()
                        if not v.get('lots') or any(l.get('damage') for l in v['lots'])}
    try:
        refresh(client, data, now)
    except fetch.Closed as closed:
        stop = str(closed)
    candidates = [lot for entry in data['listings'].values() for lot in entry['lots']]  # USA-LOTS-FIX-003
    # USA-LOTS-FIX-002: the listing has no start code — candidates by the listing, «runs» by each lot page
    chosen = selection.choose(candidates, selection.SIZE * 3, selection.candidate)
    if not stop:
        try:
            # USA-LOTS-FIX-006: every chosen lot's page (not only until SIZE run), over the runs, so the days are known
            read_lots(client, chosen, data['pages'], now, budget=REQUESTS - PHOTO_RESERVE)
        except fetch.Closed as closed:
            stop = str(closed)
    today = stamp(now)
    # the lot page's own values win where it has them (an empty one keeps the listing's)
    full = [dict(lot, **{k: v for k, v in data['pages'][lot['id']].items() if v or k == 'runs'})
            for lot in chosen if lot['id'] in data['pages']]
    # USA-LOTS-FIX-004 (live 28.11: a lot page without an auction date has no auction_start — KeyError, every run)
    full = [lot for lot in full if lot.get('auction_start', '') >= today and selection.keep(lot)]
    full = selection.spread(full)  # USA-LOTS-FIX-006: the shown lots spread over the auction days
    copies = copy_photos(client, full, folder / 'lots') if not stop else {
        lot['id']: [n for n in (photo_name(lot['id'], u) for u in lot['photos'][:PHOTOS_PER_LOT])
                    if (folder / 'lots' / n).exists()] for lot in full}
    shown = publish(full, copies, now, folder)
    return {'listings': len(data['listings']), 'candidates': len(candidates), 'chosen': len(chosen),
            'pages': len(data['pages']), 'running': sum(1 for p in data['pages'].values() if p.get('runs')),
            'shown': shown, 'stop': stop}


def main(now=None):
    now = now or datetime.now(timezone.utc)
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0  # the previous run is still working
        DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
        state = DATA / 'state.json'
        data = load(state, {})
        data = {'models': data.get('models', {}), 'models_at': data.get('models_at', ''),
                'listings': data.get('listings', {}), 'pages': data.get('pages', {})}
        client = fetch.Client(REQUESTS)
        try:
            report = dict(run(client, data, now, OUT), at=stamp(now), requests=client.requests)
        except Exception as error:  # USA-LOTS-FIX-004: keep what was read and say why, never fail silently
            report = {'at': stamp(now), 'requests': client.requests, 'error': '%s: %s' % (type(error).__name__, error)}
        write(state, dump(data), mode=0o600)
        write(DATA / 'last_run.json', dump(report), mode=0o600)  # USA-LOTS-FIX-003: what the last run did
    print(json.dumps(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
