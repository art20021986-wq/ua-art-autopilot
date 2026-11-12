"""Build the KOREA-LOTS-FULL candidate: the collector, the Korea page lot list and the order page carousels, together.

Owner 2026-11-11/12 (JPAUTO-KOREA-001, KOREA-MODEL-LOTS-001):
- korea_auction/: the collector as TICKER-FIX6-INSTALL-20261112-R2 installed it, updated from this package's
  korea_auction/ (zipped flat as kauc_<module>.py by the transport): today's and the coming days' lots, VIN and every
  photo from the lot page (copied gradually, answer «1»), and model_lots.py (new): the week's lots of each order
  model written to video/korea/model-lots.json.
- video/korea.html: only the lot list block (ua_korea_lots) is replaced by its new version (auction days, VIN).
- video/podbor.html and video/order/ (order.js, gallery.js, gallery.css, order-strings.json): small edits
  (edit_order) — the model carousels show the model's auction lots first, each linking to its lot card.
The launcher and the hourly task stay as they are.
"""
from pathlib import Path

import edit_order
import ua_korea_lots

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'model_lots', 'nbu', 'prices', 'public', 'selection',
           'session', 'ticker')
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
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (PAGE,) + edit_order.SOURCE_FILES
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    collector = {name: value for name, value in source.items() if name.startswith('korea_auction/')}
    if sha is not None and {name: sha(value) for name, value in collector.items()} != INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_INSTALLED_COLLECTOR_UNEXPECTED')
    page = source[PAGE].decode('utf-8')
    if page.count(ua_korea_lots.MARK) != 1 or 'kl-tbd' not in page or 'kl-days' in page:
        raise ValueError('KOREA_LOTS_PAGE_UNEXPECTED')
    files = {'korea_auction/__init__.py': b'', PAGE: ua_korea_lots.apply(page).encode('utf-8')}
    for name in edit_order.SOURCE_FILES:
        files[name] = edit_order.build(name, source[name])
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    return files


def is_page(name):
    return False  # these pages are this site's own; no other writer rewrites them
