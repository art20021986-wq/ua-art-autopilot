"""Build the KOREA-TIME-001 candidate (owner 2026-11-12): the auction start in Korea time and Kyiv time.

1. The collector as KOREA-LOTS-FULL-INSTALL installed it (ticker.py = TICKER-FIX6-R2), with ticker.py updated: every lot card in the home
   ticker shows «Торги 18.11 · 12:00 Корея · 05:00 Київ» (the hourly job rebuilds the ticker). The collector modules
   come from korea_auction/ in this package (zipped flat as kauc_<module>.py by the transport).
2. Pages (time_pages.py): video/korea.html lot list and lot card, the order page model carousels
   (video/order/order.js, order-strings.json, the order.js version in video/podbor.html).
"""
from pathlib import Path

import time_pages

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'model_lots', 'nbu', 'prices', 'public', 'selection', 'session', 'ticker')
# The collector exactly as KOREA-LOTS-FULL-INSTALL installed it (cloud/korea_lots_full_001/korea_auction, deployment_plan.json).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '01eddfe62dc41e672389836550893bc489a68524c1dd4a6ba8866b64b90aa068',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '4099d30238b63069ecbbf29ad5094b8d1e5788251067875461ae0c597613cf17',
    'korea_auction/lots.py': '932a64719979835cbb8c8b159e97774f87b6560cfb24f04b0fa665f9e1c00316',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '80b2359dd0e6529b83b8085bb1238020b5fee90c2da4c29f445810b612e3565c',
    'korea_auction/public.py': '58db07d0699a5cb86f053a7bfc1f5a05f0fe4828ed9efb214da2309092ad692c',
    'korea_auction/selection.py': '02b01a2e41c01f3afea566c2cbd55a6c65ef90b243692d8425d7951d644093bd',
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
