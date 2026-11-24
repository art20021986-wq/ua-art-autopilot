"""Build the KOREA-WEEKTILE-001 candidate (owner 2026-11-19): the yellow tile shows clocks (Korea, Japan, Kyiv) and the
week ahead by the auction schedule; the ticker is checked before it is written; the Korea page day buttons say
«Аукціонів немає» when there is no auction that day.

1. The collector as KOREA-SYNC-INSTALL installed it, with schedule.py, holidays.py, week_tile.py, check.py and alert.py
   (new: the CRM bot tells the CRM owners when the check fails),
   collect.py (the schedule from the search page it reads anyway; the tile week), ticker.py (clocks, week rows), job.py
   (the check before each ticker write; lots.json carries the schedule). Zipped flat as kauc_<module>.py.
2. One edit of video/korea.html (day_none_page): the day button rule; every other byte stays.
"""
from pathlib import Path

import day_none_page

HERE = Path(__file__).resolve().parent
MODULES = ('alert', 'catalog', 'check', 'collect', 'color', 'drive', 'fuel', 'holidays', 'html_tools', 'job', 'lots', 'model_lots',
           'nbu', 'prices', 'public', 'rollover', 'schedule', 'selection', 'session', 'ticker', 'week_tile')
# The collector exactly as KOREA-SYNC-INSTALL installs it (cloud/korea_sync_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': 'a0192f95d495825c50ce21dc2a9174895ec55ab39756e15d09a2d0ef24e5cb7f',
    'korea_auction/color.py': '7040bd2dfb3546534ef8eabe14a55a13c70fdde19bb56308ddcd12cbe13ad501',
    'korea_auction/drive.py': '8de0f090a74441282346da98b5604b08745fbc25e1388a2bf67dbf89203c7dce',
    'korea_auction/fuel.py': '4a51b053b72dec115e5a5468f843199071598229a0bdce56ee46562404e8c676',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '5954466116022fed32e55e73158b61a195b6d52db60bf20a41a991c00eaf187b',
    'korea_auction/lots.py': 'db18b0c94a2f5128dc0f1cb4b356dfb6d713b25f4d1260b44cd0e06d90528d24',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '491c3fb95371c86c2e37100ebff91506cecc8fd250eecac45b7c875c8b4f6a33',
    'korea_auction/public.py': 'ea9e70d529af14d6d52b27c502ffe27bfcc81290a5cb382451615c79a11d858b',
    'korea_auction/rollover.py': '4bc8a99d5bc4b7a9e08fc50decb1d4226012be135ca79a58b3fd2f7b58c74650',
    'korea_auction/selection.py': '895c4eda62e2fb829d8d48eb15a62f87d62f6f40898ae2cd8c2b0684595e6eeb',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'b7e25b483ebe60602eee7da494dcd80438f4034bf67a81546f3f1ec25063a244',
}
KOREA = 'video/korea.html'
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (KOREA,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_SYNC_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[KOREA] = day_none_page.build(source[KOREA])
    return files


def is_page(name):
    return False  # the Korea page is this site's own; no other writer rewrites it
