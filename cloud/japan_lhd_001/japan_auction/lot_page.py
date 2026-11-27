"""A Japan lot page -> what the site shows from it: start price in yen, VIN, every photo, fuel and colour.

The page is the Korea lot page's layout (korea_auction.lots.parse_detail reads the specs, VIN, fuel and colour); the
start price is in yen. One responsibility: the lot page.
"""
import re

from korea_auction import html_tools, lots


def start_jpy(html):
    """The lot's start price in yen (the largest «Starting Price N JPY» on the page), 0 when none is given."""
    page = html_tools.text(html)
    prices = [int(p.replace(',', '')) for p in re.findall(r'Starting Price ([\d,]+) JPY', page)]
    return max(prices or [0])


def entry(html):
    """The cached lot page: {'jpy', 'vin', 'photos', 'fuel', 'color'}."""
    detail = lots.parse_detail(html)
    return {'jpy': start_jpy(html), 'vin': detail['vin'], 'photos': detail['photos'], 'fuel': detail['fuel'],
            'color': detail['color']}
