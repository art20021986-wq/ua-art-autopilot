"""Before/after check of the card pages (SEO-PRICE-001): only the search fields may change.

The search fields are <title>, the meta description, og:title/og:description and the JSON-LD block (ua-seo-ld);
version stamps in links (?v=123) are ignored. Everything else of a page must stay byte for byte."""
import re

SEARCH_FIELDS = (
    re.compile(r'<title\b[^>]*>.*?</title>', re.S | re.I),
    re.compile(r'<meta\s+name="description"[^>]*>', re.I),
    re.compile(r'<meta\s+property="og:(?:title|description)"[^>]*>', re.I),
    re.compile(r'<script\s+type="application/ld\+json"\s+id="ua-seo-ld">.*?</script>', re.S | re.I),
)
STAMP = re.compile(r'([?&](?:v|ver|version|ts|t)=)[0-9]+')
TITLE = re.compile(r'<title\b[^>]*>(.*?)</title>', re.S | re.I)
PRICE = re.compile(r'data-ua-market=["\']ukraine["\'][^>]*?data-ua-value=["\']([0-9]+)')


def rest(page):
    """The page without its search fields and version stamps."""
    for pattern in SEARCH_FIELDS:
        page = pattern.sub('', page)
    return STAMP.sub(r'\g<1>#', page)


def price_text(value):
    return '{:,}'.format(value).replace(',', ' ') + ' $'


def card(before, after):
    """{'price': int|None, 'title_has_price': bool, 'ld_price': bool, 'other_changes': bool} of one card page."""
    found = PRICE.search(after)
    title = TITLE.search(after)
    value = int(found.group(1)) if found else None
    return {'price': value,
            'title_has_price': bool(value and title and price_text(value) in title.group(1)),
            'ld_price': '"price"' in after,
            'other_changes': before is not None and rest(before) != rest(after)}
