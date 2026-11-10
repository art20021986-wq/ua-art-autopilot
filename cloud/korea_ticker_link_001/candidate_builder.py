"""Build the KOREA-TICKER-LINK candidate: the collector as installed by KOREA-LOTS-INSTALL-20261110, updated.

The new version also publishes every lot of the next auction day (korea_auction/public.py, job.py) to
video/korea/lots.json with photo copies in video/korea/lots/. The collector modules come from korea_auction/ in
this package (zipped flat as kauc_<module>.py by the transport). The launcher and the hourly task stay as they are.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'public', 'selection', 'session', 'ticker')
# The collector exactly as KOREA-LOTS-INSTALL-20261110 installs it (cloud/korea_lots_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': 'b21ecdc1d58e02e6cbb4472995abc34b03da1e9fe46b8129c15511d2a81e9ba7',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '4a676d01629bb240d07c872fedb213d886732e240e7f5b29e2d884ea323834d8',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/public.py': 'a79d07b3914c2edaba432a8ff24630557ad9da07b7694f38651be0ac655459d9',
    'korea_auction/selection.py': '5ee9f1ea5ff533994bcd7560449d5881aee7a06ac001e514ebc69ec1fd510ae7',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': '465041408756498fc75d92ba62f70e7e2d06892ddbade7a09fd4649b089ac5a6',
}
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256))
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(value) for name, value in source.items()} != INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    return files


def is_page(name):
    return False
