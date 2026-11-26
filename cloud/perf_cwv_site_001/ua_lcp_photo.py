"""The first catalogue photos load at once (PERF-CWV-001, owner «да» 2026-11-26).

Every catalogue photo carries loading="lazy", the first one too, so the browser starts it only after the layout is done
and at normal priority; that photo is the largest thing on a phone screen (Lighthouse LCP 4.2-4.4 s, ≤ 2.5 s is good).
Guidance (web.dev «Browser-level image lazy loading», «Optimize resource loading with the Fetch Priority API»): do not
lazy-load images in the first screen and give the main one fetchpriority="high". So in the first EAGER cards
loading="lazy" becomes loading="eager" in place (the first one also gets fetchpriority="high"); all other photos stay
lazy. Only the catalogue (.catalog-grid) changes; the photo addresses and the cards stay as they are.
"""
import re

EAGER = 2
GRID = 'class="catalog-grid"'
LAZY = ' loading="lazy"'
FIRST = ' loading="eager" fetchpriority="high"'
NEXT = ' loading="eager"'
PHOTO = re.compile(r'(<a\b[^>]*\bclass="catalog-photo"[^>]*>\s*)(<img\b[^>]*>)', re.S)


def _photos(html, change):
    if not isinstance(html, str) or GRID not in html:
        return html
    start = html.index(GRID)
    count = [0]

    def each(match):
        index = count[0]
        count[0] += 1
        return match.group(1) + (change(match.group(2), index) if index < EAGER else match.group(2))

    return html[:start] + PHOTO.sub(each, html[start:])


def _eager(tag, index):
    return tag.replace(LAZY, FIRST if index == 0 else NEXT, 1) if tag.count(LAZY) == 1 else tag


def _lazy(tag, index):
    mark = FIRST if index == 0 else NEXT
    return tag.replace(mark, LAZY, 1) if tag.count(mark) == 1 else tag


def apply(html):
    return _photos(html, _eager)


def remove(html):
    return _photos(html, _lazy)
