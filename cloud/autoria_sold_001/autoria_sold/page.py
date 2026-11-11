"""The number of cars sold, read from the owner's AUTO.RIA dealer page (AUTORIA-SOLD-001).

The dealer page renders it on the server as <div id="elementsSoldCarTitle">…132…</div> (snapshot
AUTORIA-REVIEWS-COLLECT-20261026-R2); anything else gives None, so the site keeps its last good number.
"""
import re

TITLE = re.compile(r'<div id="elementsSoldCarTitle"[^>]*>(.*?)</div>', re.S)
TAGS = re.compile(r'<!--.*?-->|<[^>]*>', re.S)
MAX_SOLD = 100000


def sold_count(html):
    """Whole number of sold cars, or None when the page does not show one."""
    match = TITLE.search(html)
    if not match:
        return None
    text = ''.join(TAGS.sub('', match.group(1)).split())
    if not (text.isascii() and text.isdigit()) or not 0 < int(text) <= MAX_SOLD:
        return None
    return int(text)
