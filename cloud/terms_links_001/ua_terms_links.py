"""TERMS-LINKS-001 (owner 2026-11-11): no link to the terms page (info.html) on the site — the detailed purchase
information and the contract replace it. apply(html) drops every <a> whose href is info.html (any path, query or
fragment), with the text inside it; a navigation left empty is dropped too. The page info.html itself stays.
"""
import re

LINK = re.compile(r'<a\b[^>]*\bhref="(?:[^"]*/)?info\.html(?:[?#][^"]*)?"[^>]*>.*?</a>', re.S | re.I)
EMPTY_NAV = re.compile(r'<header><nav>\s*</nav></header>')


def apply(html):
    if 'info.html' not in html:
        return html
    return EMPTY_NAV.sub('', LINK.sub('', html))


def has_link(html):
    return LINK.search(html) is not None
