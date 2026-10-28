"""Home page photo: put a framed photo on the first screen (HOME-PHOTO-001).

One job: store the JPEG under a content-hashed name in video/order/ and point the
first-screen <picture> of video/index.html at it. Only that <picture> and one
CSS block change; every other byte of the page stays. index.html is backed up
first and replaced atomically; if it changed meanwhile, nothing is written.
Earlier photos stay on disk, so any of them can be put back.
"""
import datetime
import hashlib
import io
import os
import re
import shutil

from PIL import Image

BASE = '/home/Carix'
HOME = BASE + '/video/index.html'
ORDER = BASE + '/video/order'
BACKUP = BASE + '/ua_home_photo/backup'
SITE = 'https://www.uaart.com.ua/'

MARK = 'ua-home-photo-001'
OLD_MARK = 'ua-home-audi-001'   # CSS block of the photo this module replaces (HOME-AUDI-001)
HERO = re.compile(r'<section class="hero ua-order-first">.*?</section>', re.S)
PICTURE = re.compile(r'<picture>.*?</picture>', re.S)
HEAD = re.compile(r'(?=</head\s*>)', re.I)
PICTURE_HTML = ('<picture><img src="%s" alt="Авто під замовлення — UA ART COMPANY, Київ" width="%d" height="%d" '
                'fetchpriority="high" decoding="async"></picture>')
CSS = ('<style id="%s">'
       '.ua-order-first>picture img{object-fit:contain;object-position:center}'
       '@media (max-width:700px){.ua-order-first>picture{aspect-ratio:%d/%d}}'
       '</style>')


class SiteError(RuntimeError):
    pass


def _once(pattern, text, name):
    found = pattern.findall(text)
    if len(found) != 1:
        raise SiteError('HOME_%s:%d' % (name, len(found)))
    return found[0]


def edit_home(text, url, width, height):
    """index.html text with the first-screen photo set to url; the rest unchanged."""
    hero = _once(HERO, text, 'HERO')
    _once(PICTURE, hero, 'PICTURE')
    picture = PICTURE_HTML % (url, width, height)
    text = text.replace(hero, PICTURE.sub(lambda m: picture, hero, count=1), 1)
    css = CSS % (MARK, width, height)
    for mark in (MARK, OLD_MARK):
        if mark in text:
            block = re.compile(r'<style id="%s">.*?</style>' % mark, re.S)
            return text.replace(_once(block, text, 'CSS'), css, 1)
    _once(HEAD, text, 'HEAD')
    return HEAD.sub(lambda m: css, text, count=1)


def _write_atomic(path, data, mode):
    temp = path + '.ua-home-photo.tmp'
    with open(temp, 'wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, mode)
    os.replace(temp, path)


def publish(jpeg):
    """Put the photo on the home page; returns the page address. Raises SiteError, nothing changed then."""
    width, height = Image.open(io.BytesIO(jpeg)).size
    name = 'home-%s.jpg' % hashlib.sha256(jpeg).hexdigest()[:12]
    url = '/video/order/' + name
    with open(HOME, 'rb') as handle:
        before = handle.read()
    after = edit_home(before.decode('utf-8'), url, width, height).encode('utf-8')
    photo = os.path.join(ORDER, name)
    if not os.path.exists(photo):
        _write_atomic(photo, jpeg, 0o644)
    if after == before:
        return SITE
    os.makedirs(BACKUP, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    shutil.copy2(HOME, os.path.join(BACKUP, 'index-%s.html' % stamp))
    with open(HOME, 'rb') as handle:
        if handle.read() != before:
            raise SiteError('HOME_CHANGED_MEANWHILE')
    _write_atomic(HOME, after, os.stat(HOME).st_mode & 0o777)
    return SITE
