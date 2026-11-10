"""Build the KOREA-LOTS candidate: the collector as installed by KOREA-TICKER-INSTALL-20261110, updated.

The new version also publishes every lot of the next auction day (korea_auction/public.py, job.py) to
video/korea/lots.json with photo copies in video/korea/lots/. The collector modules come from korea_auction/ in
this package (zipped flat as kauc_<module>.py by the transport). The launcher and the hourly task stay as they are.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'public', 'selection', 'session', 'ticker')
# The collector exactly as KOREA-TICKER-INSTALL-20261110 installs it (cloud/korea_ticker_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '9376e4fdd4aa38b1e2b28d7901782f308c954b4697e1bb4e094a66fd3d34ac7f',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '2f87e8f46c561572dc53ee185a288ff1a3f49ee1b46e5198bbd517ab634b8519',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/selection.py': '5ee9f1ea5ff533994bcd7560449d5881aee7a06ac001e514ebc69ec1fd510ae7',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'efb4581b80fe089e5f6c80b1da513f78ea2a0563192a90888b0fc31bf5e3054d',}
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
