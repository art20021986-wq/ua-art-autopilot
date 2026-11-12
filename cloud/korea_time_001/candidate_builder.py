"""Build the KOREA-TIME-001 candidate (owner 2026-11-12): the auction start in Korea time and Kyiv time.

1. The collector as TICKER-FIX6-INSTALL-20261112-R2 installed it, with ticker.py updated: every lot card in the home
   ticker shows «Торги 18.11 · 12:00 Корея · 05:00 Київ» (the hourly job rebuilds the ticker). The collector modules
   come from korea_auction/ in this package (zipped flat as kauc_<module>.py by the transport).
2. Pages (time_pages.py): video/korea.html lot list and lot card, the order page model carousels
   (video/order/order.js, order-strings.json, the order.js version in video/podbor.html).
"""
from pathlib import Path

import time_pages

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'prices', 'public', 'selection', 'session', 'ticker')
# The collector exactly as TICKER-FIX6-INSTALL-20261112-R2 installed it (cloud/korea_ticker_fix6_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '074c4179b350107482a36e861bdb67a1854f0bc0c0d02eeb1570983b5ab89301',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '703d2f423d4e419c509cf5b2053c5189c5ae4bde85008f7ce08a75408b14b7c9',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '271e13cc1e68e2cc3481c13c22e3b4a0fd42549cca8a414adc41624a3f145d3e',
    'korea_auction/public.py': 'a79d07b3914c2edaba432a8ff24630557ad9da07b7694f38651be0ac655459d9',
    'korea_auction/selection.py': 'f3caeacb641f2282562a2270b20cc99b663a20ddc5ae18e887cecfd66342d417',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'aff2b4ca9b3eb715e7b0f1f0a8235f395b103bfa3c989e25bb4cb569f4d0d2a9',
}
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + time_pages.FILES
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    for name in time_pages.FILES:
        files[name] = time_pages.build(name, source[name].decode('utf-8')).encode('utf-8')
    return files


def is_page(name):
    return False  # these pages are this site's own; no other writer rewrites it (KOREA-HOW-SYNC-001)
