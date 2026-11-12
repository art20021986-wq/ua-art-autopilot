"""Build the KOREA-LOTS-FULL candidate: the collector and the Korea page lot list, together in one install.

Owner 2026-11-11/12 (JPAUTO-KOREA-001): the lot card shows the VIN and every photo of the lot (copied gradually,
answer «1»), the coming auction days are listed (weekday, date) and the list sorts by auction date.
- korea_auction/: the collector as KOREA-SCORE-INSTALL-20261111-R6 installed it, updated from this package's
  korea_auction/ (zipped flat as kauc_<module>.py by the transport): every coming day, VIN and photos from the lot page.
- video/korea.html: only the lot list block (ua_korea_lots) is replaced by its new version.
The launcher and the hourly task stay as they are.
"""
from pathlib import Path

import ua_korea_lots

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'prices', 'public', 'selection', 'session', 'ticker')
# The collector exactly as KOREA-SCORE-INSTALL-20261111-R6 installed it (cloud/korea_score_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '53b64c3a8ace10b8fe5eeb1e7a68a202a4be07aff254eb1d1b97b9a6d0b71227',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': 'e58271d3328ca8d840c389f13897db440737740da6ece58a54246212ff95c08b',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '271e13cc1e68e2cc3481c13c22e3b4a0fd42549cca8a414adc41624a3f145d3e',
    'korea_auction/public.py': 'a79d07b3914c2edaba432a8ff24630557ad9da07b7694f38651be0ac655459d9',
    'korea_auction/selection.py': '5ee9f1ea5ff533994bcd7560449d5881aee7a06ac001e514ebc69ec1fd510ae7',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': '50aa8b3639fbf1b77fcedfee37d4d76760c9205bc883fb52d49db06366fe6d00',
}
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    collector = {name: value for name, value in source.items() if name != PAGE}
    if sha is not None and {name: sha(value) for name, value in collector.items()} != INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_INSTALLED_COLLECTOR_UNEXPECTED')
    page = source[PAGE].decode('utf-8')
    if page.count(ua_korea_lots.MARK) != 1 or 'kl-tbd' not in page or 'kl-days' in page:
        raise ValueError('KOREA_LOTS_PAGE_UNEXPECTED')
    files = {'korea_auction/__init__.py': b'', PAGE: ua_korea_lots.apply(page).encode('utf-8')}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    return files


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
