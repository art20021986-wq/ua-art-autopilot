"""Build the KOREA-WEEKTILE-FIX candidate (server log 19.11 06:11 UTC): after the day's auction closed no ticker car
photo can be copied (the auction shows '/img/auction-closed.png'); the job then wrote no ticker at all, so the tile with
the week never showed. job.build now writes the tile with the week and the owner's cars instead (as while the auction
lists no lots). Only korea_auction/job.py changes; zipped flat as kauc_<module>.py; no page changes.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('alert', 'catalog', 'check', 'collect', 'color', 'drive', 'fuel', 'holidays', 'html_tools', 'job', 'lots',
           'model_lots', 'nbu', 'prices', 'public', 'rollover', 'schedule', 'selection', 'session', 'ticker', 'week_tile')
# The collector exactly as KOREA-WEEKTILE-INSTALL-20261119-R2 installed it (cloud/korea_week_tile_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/alert.py': '5ce013152e510547e0b66b5d1c05bfe91fd921bcff896d82c53e0783e98ae5d7',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/check.py': 'a039d4f87fa3dd545d54c06da23d5eea132a06d5905006b2e51a3820e6df2815',
    'korea_auction/collect.py': '7402f4db9f275a823daa18e7a62ee56689fd46388810aab45703515716c65cde',
    'korea_auction/color.py': '7040bd2dfb3546534ef8eabe14a55a13c70fdde19bb56308ddcd12cbe13ad501',
    'korea_auction/drive.py': '8de0f090a74441282346da98b5604b08745fbc25e1388a2bf67dbf89203c7dce',
    'korea_auction/fuel.py': '4a51b053b72dec115e5a5468f843199071598229a0bdce56ee46562404e8c676',
    'korea_auction/holidays.py': '68768be6f5b929211006b519d4761d7fd0322002f2f9f5e8f644f0d30156b79e',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': 'dbfabaf0949f028f66f99e4eff609409ff8970d3affaca8f5c0f50bb1d5812fc',
    'korea_auction/lots.py': 'db18b0c94a2f5128dc0f1cb4b356dfb6d713b25f4d1260b44cd0e06d90528d24',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '491c3fb95371c86c2e37100ebff91506cecc8fd250eecac45b7c875c8b4f6a33',
    'korea_auction/public.py': 'ea9e70d529af14d6d52b27c502ffe27bfcc81290a5cb382451615c79a11d858b',
    'korea_auction/rollover.py': '4bc8a99d5bc4b7a9e08fc50decb1d4226012be135ca79a58b3fd2f7b58c74650',
    'korea_auction/schedule.py': 'b02a576af1f29ed5314ec260ea6920975cedcfd0ec765dbe610483ef5592c89a',
    'korea_auction/selection.py': '895c4eda62e2fb829d8d48eb15a62f87d62f6f40898ae2cd8c2b0684595e6eeb',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': '2200a59ee0a596784f900d553eb0e038eaa9546b49f0023545d80e3ca5b6fbbf',
    'korea_auction/week_tile.py': '035822b24b988a36344e0208da1e408dac7e21ccf0bd00055183a2522cb68aae',
}
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256))
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_WEEKTILE_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    return files


def is_page(name):
    return False  # collector modules only
