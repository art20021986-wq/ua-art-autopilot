"""Build the KOREA-DRIVE-001 candidate (owner 2026-11-17: the drive in the auction lot cards).

1. The collector as KOREA-TILE-COUNTS-INSTALL installed it, with drive.py (new: the drive only as the auction writes it
   in the trim) and public.py (lots.json carries `drive`). The collector modules come from korea_auction/ in this
   package (zipped flat as kauc_<module>.py by the transport).
2. One edit of video/korea.html (drive_page): «Привід» after «КПП» in the lot window.
"""
from pathlib import Path

import drive_page

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'drive', 'fuel', 'html_tools', 'job', 'lots', 'model_lots', 'nbu', 'prices', 'public',
           'selection', 'session', 'ticker')
# The collector exactly as KOREA-TILE-COUNTS-INSTALL installs it (cloud/korea_tile_counts_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': 'a0192f95d495825c50ce21dc2a9174895ec55ab39756e15d09a2d0ef24e5cb7f',
    'korea_auction/fuel.py': '4a51b053b72dec115e5a5468f843199071598229a0bdce56ee46562404e8c676',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '68d08391b2c46eecb1ac59fc3fef6db6f3ceaf3ff15a9d3280bf31d51ea0dd9d',
    'korea_auction/lots.py': '932a64719979835cbb8c8b159e97774f87b6560cfb24f04b0fa665f9e1c00316',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '5304c3bb92b496c1f1c66bee427f2d1ce469f832193e70cae9ea114cc051ee8d',
    'korea_auction/public.py': '1b79307ad6a5456e53ed51c56a63bf48122f2dbfc843079a20ac4c356757d040',
    'korea_auction/selection.py': '895c4eda62e2fb829d8d48eb15a62f87d62f6f40898ae2cd8c2b0684595e6eeb',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'b7e25b483ebe60602eee7da494dcd80438f4034bf67a81546f3f1ec25063a244',
}
KOREA = 'video/korea.html'
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (KOREA,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_TILE_COUNTS_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[KOREA] = drive_page.build(source[KOREA])
    return files


def is_page(name):
    return False  # the Korea page is this site's own; no other writer rewrites it (KOREA-HOW-SYNC-001)
