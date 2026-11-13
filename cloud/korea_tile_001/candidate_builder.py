"""Build the KOREA-TILE-001 candidate (owner 2026-11-13): the yellow tile of the home ticker shows today's car count
(always, 0 too) and the 3 nearest auction days with weekday and car count.

1. The collector as KOREA-TIME-INSTALL installed it, with collect.py, selection.py and ticker.py updated (the hourly job
   rebuilds the ticker). The collector modules come from korea_auction/ in this package (zipped flat as
   kauc_<module>.py by the transport).
2. Joined in one install (owner 2026-11-13, «4. Да»; the coordinator: the same files, one install): KOREA-ENGINE-001 —
   new fuel.py, prices.py and public.py (lots.json carries the fuel type), collect.py model name fixes, and two edits of
   video/korea.html, each its own module: engine_page (lot card «Двигун 2 996 см³ · бензин»), then model_groups (the
   «Model» list grouped by make).
"""
from pathlib import Path

import engine_page
import model_groups

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'fuel', 'html_tools', 'job', 'lots', 'model_lots', 'nbu', 'prices', 'public', 'selection',
           'session', 'ticker')
# The collector exactly as KOREA-TIME-INSTALL installs it (cloud/korea_time_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '01eddfe62dc41e672389836550893bc489a68524c1dd4a6ba8866b64b90aa068',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '4099d30238b63069ecbbf29ad5094b8d1e5788251067875461ae0c597613cf17',
    'korea_auction/lots.py': '932a64719979835cbb8c8b159e97774f87b6560cfb24f04b0fa665f9e1c00316',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': 'd147eac60e1a54eabb69239a30544ebb518b470b5dd535feeb03e12323ff7605',
    'korea_auction/public.py': '58db07d0699a5cb86f053a7bfc1f5a05f0fe4828ed9efb214da2309092ad692c',
    'korea_auction/selection.py': '02b01a2e41c01f3afea566c2cbd55a6c65ef90b243692d8425d7951d644093bd',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'a061f48f5ed203600d7c2b9fe87a40f675f9d3da52857c5780c1c65acecb2cc1',
}
KOREA = 'video/korea.html'
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (KOREA,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_TIME_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[KOREA] = model_groups.build(engine_page.build(source[KOREA]))
    return files


def is_page(name):
    return False  # the Korea page is this site's own; no other writer rewrites it (KOREA-HOW-SYNC-001)
