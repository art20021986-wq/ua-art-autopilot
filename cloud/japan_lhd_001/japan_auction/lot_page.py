"""A Japan lot page -> what the site shows from it: start price in yen, VIN, every photo, fuel, colour and the steering.

The page is the Korea lot page's layout for the specs, VIN and colour (korea_auction.lots.parse_detail); in Japan the
start price is in yen, the fuel reads «Fuel Type: …», the steering «Steering Wheel Left» (probe JAPAN-LHD-PROBE-R3:
SellCa lots) and the photos are .jpg and .png files of the auction's image service. One responsibility: the lot page.
"""
import re
from urllib.parse import urljoin, urlsplit

from korea_auction import html_tools, lots
from korea_auction.session import BASE

PHOTO = re.compile(r'(?i)\.(?:jpe?g|png)$')
CHROME = ('/img/', '/css/', '/js/')  # the site's own icons and layout images


def start_jpy(html):
    """The lot's start price in yen (the largest «Starting Price N JPY» on the page), 0 when none is given."""
    prices = [int(p.replace(',', '')) for p in re.findall(r'Starting Price ([\d,]+) JPY', html_tools.text(html))]
    return max(prices or [0])


def fuel(html):
    """«Fuel Type: Gasoline» -> 'Gasoline' ('' when the page gives none)."""
    found = re.search(r'Fuel Type: (.*?)(?= [A-Z][A-Za-z ()/]*?:|$)', html_tools.text(html))
    return found.group(1).strip() if found else ''


def steering(html):
    """'Left' or 'Right' as the page's «Steering Wheel» says, '' when it does not say."""
    found = re.search(r'Steering Wheel (Left|Right)\b', html_tools.text(html))
    return found.group(1) if found else ''


def photos(html):
    """Every lot photo, in page order, once each, as full addresses; the site's own images are left out."""
    found = []
    for src in re.findall(r'<img[^>]+src="([^"]+)"', html):
        url = urljoin(BASE, src.replace('&amp;', '&'))
        path = urlsplit(url).path
        if PHOTO.search(path) and not path.startswith(CHROME):
            found.append(url)
    return list(dict.fromkeys(found))


def entry(html):
    """The cached lot page: {'jpy', 'vin', 'photos', 'fuel', 'color', 'steering'}."""
    detail = lots.parse_detail(html)
    return {'jpy': start_jpy(html), 'vin': detail['vin'], 'photos': photos(html), 'fuel': fuel(html),
            'color': detail['color'], 'steering': steering(html)}
