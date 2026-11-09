"""Home page stage tiles: put a car's photo on the tile of its stage (HOME-STAGE-PICK-001).

One job: in video/index.html, the «живе фото» of one stage tile (kiev, georgia,
sea, korea) is pointed at the chosen car. The photo itself is the car's main
photo framed by the existing rule (master_card.podgotovit_vitrinu ->
video/stage/<code>.webp), the same rule the CRM sync already uses for these
tiles, so the next sync keeps the choice. Only that one src changes; every
other byte of the page stays. The work runs under the existing publication
fence, index.html is backed up first and replaced atomically.
"""
import datetime
import hashlib
import os
import re
import shutil

BASE = '/home/Carix'
HOME = BASE + '/video/index.html'
BACKUP = BASE + '/ua_home_stage/backup'
STAGES = ('kiev', 'georgia', 'sea', 'korea')
CODE = re.compile(r'UA-\d{4}')
LIVE_IMG = re.compile(r'<img\b[^>]*\bclass="stage-live"[^>]*>')
SRC = re.compile(r'\bsrc="[^"]*"')
# Phone-size copies (srcset/sizes, SPEED-002) belong to the previous car; they are dropped
# so the browser shows the new src, and the site's own image step adds them again later.
RESPONSIVE = re.compile(r'\s(?:srcset|sizes)="[^"]*"')


class SiteError(RuntimeError):
    pass


def _tile(text, stage):
    """The one <a class="stage-card ..." data-stage="stage"> ... </a> of the page."""
    found = re.findall(r'<a\b[^>]*\bclass="stage-card[^"]*"[^>]*\bdata-stage="%s".*?</a>' % stage, text, re.S)
    if len(found) != 1:
        raise SiteError('HOME_TILE:%s:%d' % (stage, len(found)))
    return found[0]


def edit_home(text, stage, url):
    """index.html text with the live photo of the stage tile set to url; the rest unchanged."""
    if stage not in STAGES:
        raise SiteError('STAGE:%s' % stage)
    tile = _tile(text, stage)
    images = LIVE_IMG.findall(tile)
    if len(images) != 1 or len(SRC.findall(images[0])) != 1:  # \bsrc never matches srcset
        raise SiteError('HOME_LIVE_PHOTO:%s' % stage)
    image = RESPONSIVE.sub('', SRC.sub(lambda m: 'src="%s"' % url, images[0], count=1))
    return text.replace(tile, tile.replace(images[0], image, 1), 1)


def current(text, stage):
    """Car code shown now on the stage tile, or ''."""
    images = LIVE_IMG.findall(_tile(text, stage))
    found = CODE.search(images[0]) if images else None
    return found.group(0) if found else ''


def _write_atomic(path, data, mode):
    temp = path + '.ua-home-stage.tmp'
    with open(temp, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, mode)
    os.replace(temp, path)


def publish(code, stage):
    """Put the car's main photo on the stage tile. Raises SiteError; the page is unchanged then."""
    if not CODE.fullmatch(code or ''):
        raise SiteError('CODE')
    import master_card
    import publication_fence
    with publication_fence.publication_fence(timeout=30):
        path, report = master_card.podgotovit_vitrinu(code)
        if not path or not report.get('ok'):
            raise SiteError('PHOTO:%s' % report.get('prichina', 'нет фото'))
        with open(BASE + path, 'rb') as handle:
            url = '%s?v=%s' % (path, hashlib.sha256(handle.read()).hexdigest()[:8])
        with open(HOME, 'rb') as handle:
            before = handle.read()
        after = edit_home(before.decode('utf-8'), stage, url).encode('utf-8')
        if after == before:
            return
        os.makedirs(BACKUP, exist_ok=True)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        shutil.copy2(HOME, os.path.join(BACKUP, 'index-%s.html' % stamp))
        _write_atomic(HOME, after, os.stat(HOME).st_mode & 0o777)
