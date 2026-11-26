"""Build the SEARCH-HOME-001 install A candidate (owner «Да» 2026-11-26, see tasks/SEARCH-HOME-001.md).

1. The collector exactly as KOREA-TOP-TILE-INSTALL installed it, plus country_tabs.py (new: Korea / America / Japan
   tabs on the week tile) and ticker.py (uses it; the score legend titled «аукціони Кореї»). Zipped flat as kauc_*.py.
2. video/korea.html: the offer line text (offer_text.py); every other byte stays.
3. video/korea/logistics.json: port costs in Georgia 400 $ (logistics_port.py).
4. New: video/usa.html (ua_usa_page.py, from the new korea.html shell), video/usa/usa-calc.js, video/usa/tariffs.json
   (today's copy; the server job refreshes it weekly), usa_costs.py and usa_tariffs_sync.py in the home folder.
"""
from pathlib import Path

import logistics_port
import offer_text
import ua_usa_page

HERE = Path(__file__).resolve().parent
MODULES = ('alert', 'catalog', 'check', 'collect', 'color', 'country_tabs', 'drive', 'fuel', 'holidays', 'house_days',
           'html_tools', 'job', 'lots', 'model_lots', 'nbu', 'prices', 'public', 'rollover', 'schedule', 'selection',
           'session', 'ticker', 'week_tile')
# The collector exactly as KOREA-TOP-TILE-INSTALL-20261126 installed it (cloud/korea_top_tile_001/deployment_plan.json).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/alert.py': '5ce013152e510547e0b66b5d1c05bfe91fd921bcff896d82c53e0783e98ae5d7',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/check.py': 'a039d4f87fa3dd545d54c06da23d5eea132a06d5905006b2e51a3820e6df2815',
    'korea_auction/collect.py': '77191335a965b987040e3e770226c4b1c68a8c66c363a6061ba41f83ca547a1e',
    'korea_auction/color.py': '7040bd2dfb3546534ef8eabe14a55a13c70fdde19bb56308ddcd12cbe13ad501',
    'korea_auction/drive.py': '8de0f090a74441282346da98b5604b08745fbc25e1388a2bf67dbf89203c7dce',
    'korea_auction/fuel.py': '4a51b053b72dec115e5a5468f843199071598229a0bdce56ee46562404e8c676',
    'korea_auction/holidays.py': '68768be6f5b929211006b519d4761d7fd0322002f2f9f5e8f644f0d30156b79e',
    'korea_auction/house_days.py': '73aa206c2b2e2bb3003dc9781f77cbf3e3532bc292fc23ead97d8d25952e9665',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '375b864c2a7c35b159e3947d96b1ef81d4e10bb480ccd7c70c502c54cec6ca6b',
    'korea_auction/lots.py': 'db18b0c94a2f5128dc0f1cb4b356dfb6d713b25f4d1260b44cd0e06d90528d24',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '491c3fb95371c86c2e37100ebff91506cecc8fd250eecac45b7c875c8b4f6a33',
    'korea_auction/public.py': 'ea9e70d529af14d6d52b27c502ffe27bfcc81290a5cb382451615c79a11d858b',
    'korea_auction/rollover.py': '4bc8a99d5bc4b7a9e08fc50decb1d4226012be135ca79a58b3fd2f7b58c74650',
    'korea_auction/schedule.py': 'b02a576af1f29ed5314ec260ea6920975cedcfd0ec765dbe610483ef5592c89a',
    'korea_auction/selection.py': '895c4eda62e2fb829d8d48eb15a62f87d62f6f40898ae2cd8c2b0684595e6eeb',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': '9ace46422ea9ca36d794b8eb59d3a24a5f3f6eed965c67336f1ed68b78864d93',
    'korea_auction/week_tile.py': 'dbeaf622b2920524f64c6e0aea897545612ddaa72f8df524fb92737c71b0d8a6',
}
KOREA = 'video/korea.html'
LOGISTICS = 'video/korea/logistics.json'
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (KOREA, LOGISTICS)
DEPENDENCY_SHA256 = {}
NEW_FILES = {'video/usa/usa-calc.js': 'usa-calc.js', 'video/usa/tariffs.json': 'usa_tariffs.json',
             'usa_costs.py': 'usa_costs.py', 'usa_tariffs_sync.py': 'usa_tariffs_sync.py'}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_TOP_TILE_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[KOREA] = offer_text.build(source[KOREA])
    files[LOGISTICS] = logistics_port.build(source[LOGISTICS])
    files['video/usa.html'] = ua_usa_page.build(files[KOREA].decode('utf-8')).encode('utf-8')
    for name, local in NEW_FILES.items():
        files[name] = (here / local).read_bytes()
    return files


def is_page(name):
    return False  # these pages are this site's own; no other writer rewrites them
