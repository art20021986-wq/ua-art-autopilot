"""SPEED-002: one address per car for search engines — links point to the card's language version.

Each card has a language version /video/ua/UA-XXXX.html (canonical, uk) and /video/ru/UA-XXXX.html; the old
/video/UA-XXXX.html stays for the bot and old links, its canonical already names the ua version. Internal links
to the old address made Google pick it over the canonical one. A version is used only when its file exists.
"""
from pathlib import Path
import re

VIDEO = Path(__file__).resolve().parent / 'video'
FOLDERS = {'uk': 'ua', 'ru': 'ru'}
CARD = re.compile(r'(?P<prefix>(?:https://www\.uaart\.com\.ua)?/video/)(?P<code>UA-[0-9]{4,})\.html')
CATALOG_LINK = re.compile(r'href="(UA-[0-9]{4,})\.html"')


def version(code, lang):
    """'ua/UA-0001.html' (or ru/) when that version exists, else None."""
    folder = FOLDERS.get(lang)
    relative = '%s/%s.html' % (folder, code)
    return relative if folder and (VIDEO / relative).is_file() else None


def preferred(url, lang):
    """A card URL in the same form, pointing to the card's version in lang when it exists."""
    match = CARD.fullmatch(url) if isinstance(url, str) else None
    found = version(match['code'], lang) if match else None
    return match['prefix'] + found if found else url


def for_lang(cars, lang):
    return [dict(car, url=preferred(car.get('url'), lang)) for car in cars]


def catalog_links(html):
    """The catalogue's card links (href="UA-XXXX.html", relative to /video/) to the ua version."""
    if not isinstance(html, str):
        return html
    return CATALOG_LINK.sub(lambda m: 'href="%s"' % (version(m[1], 'uk') or m[1] + '.html'), html)
