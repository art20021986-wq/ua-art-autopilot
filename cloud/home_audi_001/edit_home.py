"""Swap the home first-screen photo (Kia K5) for the owner Audi photo, shown whole (HOME-AUDI-001).

Only the <picture> of the first screen and one small CSS block change; every other byte stays.
The photo is never cropped: on desktop it is fitted inside its column (object-fit: contain),
on phones the frame takes the photo's own proportions. A later release replaces both in place.
"""
import re

from release_constants import PHOTO

MARK = 'ua-home-audi-001'
URL = '/' + PHOTO
# Public proof that this release is live.
CHECK = URL

HERO = re.compile(r'<section class="hero ua-order-first">.*?</section>', re.S)
PICTURE = re.compile(r'<picture>.*?</picture>', re.S)
HEAD = re.compile(r'(?=</head\s*>)', re.I)
CSS_BLOCK = re.compile(r'<style id="%s">.*?</style>' % MARK, re.S)

PICTURE_HTML = ('<picture><img src="%s" alt="Audi — UA ART COMPANY, Київ" width="1756" height="1190" '
                'fetchpriority="high" decoding="async"></picture>' % URL)
CSS = ('<style id="%s">'
       '.ua-order-first>picture img{object-fit:contain;object-position:center}'
       '@media (max-width:700px){.ua-order-first>picture{aspect-ratio:1756/1190}}'
       '</style>' % MARK)


def _once(pattern, text, name):
    found = pattern.findall(text)
    if len(found) != 1:
        raise ValueError('HOME_%s:%d' % (name, len(found)))
    return found[0]


def build(source):
    text = source.decode('utf-8')
    hero = _once(HERO, text, 'HERO')
    _once(PICTURE, hero, 'PICTURE')
    text = text.replace(hero, PICTURE.sub(lambda m: PICTURE_HTML, hero, count=1), 1)
    if MARK in text:
        text = text.replace(_once(CSS_BLOCK, text, 'CSS'), CSS, 1)
    else:
        _once(HEAD, text, 'HEAD')
        text = HEAD.sub(lambda m: CSS, text, count=1)
    return text.encode('utf-8')
