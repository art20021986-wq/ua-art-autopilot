"""Build the TICKER-FIX5-001 candidate: the collector as installed by TICKER-FIX4-INSTALL-20261112, updated.

The new version also publishes every lot of the next auction day (korea_auction/public.py, job.py) to
video/korea/lots.json with photo copies in video/korea/lots/. The collector modules come from korea_auction/ in
this package (zipped flat as kauc_<module>.py by the transport). The launcher and the hourly task stay as they are.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'prices', 'public', 'selection', 'session', 'ticker')
# The collector exactly as TICKER-FIX5-INSTALL-20261112 installed it (cloud/korea_ticker_fix5_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '3e94e2a4fbd178e2fd56b9e118374d7004b7c1838c420777ed1105d08b7995d7',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '703d2f423d4e419c509cf5b2053c5189c5ae4bde85008f7ce08a75408b14b7c9',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '271e13cc1e68e2cc3481c13c22e3b4a0fd42549cca8a414adc41624a3f145d3e',
    'korea_auction/public.py': 'a79d07b3914c2edaba432a8ff24630557ad9da07b7694f38651be0ac655459d9',
    'korea_auction/selection.py': '7f92c68e5e1504eedd944b490e3d19b75e7e7984f41d54f3b256f4df49f34e11',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': '3101aa5725640e502e3b44c854706f12cd8e89ae9d698ff77676fb0bb2fa3ac3'
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
