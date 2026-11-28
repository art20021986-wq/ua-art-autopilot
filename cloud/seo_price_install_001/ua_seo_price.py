"""The card price for the SEO title, description and JSON-LD (SEO-PRICE-001, coordinator «можно» to the probe 2026-11-28).

ua_seo_metadata.card_facts reads the price from the market price block, but the card writers run normalize before
site_ge_inject.inject_html puts that block in (ua_price_html_v2.render). Since 2026-11-27 the cards were written
that way and lost the price in <title>, the description and the Product JSON-LD. Here the price is read from the
block the same render would put in, so the page and its search fields always name one price. Nothing is written.
"""
import re

PRICE = re.compile(r'data-ua-market=["\']ukraine["\'][^>]*?data-ua-value=["\']([0-9]+)')


def price_usd(source, render=None):
    """The Ukraine price of the card in source, or None (no block, unknown car, render error)."""
    found = PRICE.search(source)
    if not found:
        try:
            if render is None:
                from ua_price_html_v2 import render
            found = PRICE.search(render(source))
        except Exception:
            return None
    return int(found.group(1)) if found and int(found.group(1)) > 0 else None
