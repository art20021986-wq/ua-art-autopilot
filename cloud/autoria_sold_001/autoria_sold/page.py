"""The owner's figures on the AUTO.RIA dealer page: cars sold, years on AUTO.RIA, buyer reviews (AUTORIA-SOLD-001).

The dealer page renders them on the server (snapshot AUTORIA-REVIEWS-COLLECT-20261026-R2):
<div id="elementsSoldCarTitle">…132…</div>, <div id="elementsWorkWith"><strong>5+ років</strong> працює з AUTO.RIA</div>
and the «Відгуки» tab <label for="tabsIdrevs">…<span class="common-badge …">18</span></label>. Anything else gives
None, so the site keeps its last good figure.
"""
import re

SOLD = re.compile(r'<div id="elementsSoldCarTitle"[^>]*>(.*?)</div>', re.S)
WORK = re.compile(r'<div id="elementsWorkWith"[^>]*>(.*?)</div>', re.S)
REVIEWS = re.compile(r'<label for="tabsIdrevs"[^>]*>.*?<span class="common-badge[^"]*"[^>]*>(.*?)</span>', re.S)
YEARS = re.compile(r'([0-9]{1,2}\+?) (?:рік|роки|років)')
TAGS = re.compile(r'<!--.*?-->|<[^>]*>', re.S)
MAX_COUNT = 100000


def _text(pattern, html):
    match = pattern.search(html)
    return ' '.join(TAGS.sub('', match.group(1)).split()) if match else ''


def _count(text):
    text = text.replace(' ', '')
    if not (text.isascii() and text.isdigit()) or not 0 < int(text) <= MAX_COUNT:
        return None
    return int(text)


def sold_count(html):
    """Whole number of sold cars, or None when the page does not show one."""
    return _count(_text(SOLD, html))


def reviews_count(html):
    """Whole number of buyer reviews, or None."""
    return _count(_text(REVIEWS, html))


def years(html):
    """Years on AUTO.RIA as the page writes them ('5+'), or None."""
    match = YEARS.match(_text(WORK, html))
    return match.group(1) if match and match.group(1).rstrip('+') != '0' else None


def figures(html):
    """The figures the page shows, by name; a figure that cannot be read is left out."""
    found = {'years': years(html), 'sold': sold_count(html), 'reviews': reviews_count(html)}
    return {name: value for name, value in found.items() if value is not None}
