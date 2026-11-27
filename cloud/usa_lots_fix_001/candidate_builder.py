"""Build the USA-LOTS-FIX-001 candidate: only usa_auction/pages.py, selection.py and job.py change (live 27.11: IAAI's
listing writes each value in a title="Label: value" attribute; the fixed reader takes those, model spellings such as
«MODEL-3» match, an unreadable listing stops the run, listings read before the fix are read again). Everything else stays
exactly as USA-LOTS-INSTALL-20261127 installed it, and the build refuses a server where any of it differs.
Zipped flat as uauc_<module>.py.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
USA_MODULES = ('job', 'pages', 'selection')
# Everything as USA-LOTS-INSTALL-20261127 installed it (state/receipts/USA-LOTS-INSTALL-20261127.json code_sha256,
# the "after" of cloud/usa_lots_001/deployment_plan.json).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/alert.py': '5ce013152e510547e0b66b5d1c05bfe91fd921bcff896d82c53e0783e98ae5d7',
    'korea_auction/catalog.py': '19fd0295b2d0221e348952177191d6c4a2061caed825f4b8ff4ed4fa2ac2f629',
    'korea_auction/check.py': 'a039d4f87fa3dd545d54c06da23d5eea132a06d5905006b2e51a3820e6df2815',
    'korea_auction/collect.py': '77191335a965b987040e3e770226c4b1c68a8c66c363a6061ba41f83ca547a1e',
    'korea_auction/color.py': '7040bd2dfb3546534ef8eabe14a55a13c70fdde19bb56308ddcd12cbe13ad501',
    'korea_auction/country_tabs.py': '100334b589f8b8e59e78860207ac296dbccece42c357fc2cbee545a520db15c4',
    'korea_auction/drive.py': '8de0f090a74441282346da98b5604b08745fbc25e1388a2bf67dbf89203c7dce',
    'korea_auction/fuel.py': '4a51b053b72dec115e5a5468f843199071598229a0bdce56ee46562404e8c676',
    'korea_auction/holidays.py': '68768be6f5b929211006b519d4761d7fd0322002f2f9f5e8f644f0d30156b79e',
    'korea_auction/house_days.py': '73aa206c2b2e2bb3003dc9781f77cbf3e3532bc292fc23ead97d8d25952e9665',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '0227249a43f52f1068e5fd1440a5e1c38bc1b9066cb28ed0d2f9b36534ef5ef0',
    'korea_auction/lots.py': 'db18b0c94a2f5128dc0f1cb4b356dfb6d713b25f4d1260b44cd0e06d90528d24',
    'korea_auction/model_lots.py': '13b43e123fd08137a991e87d23f399e8a0012d40e8de32f748b9f39e5f769a10',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '491c3fb95371c86c2e37100ebff91506cecc8fd250eecac45b7c875c8b4f6a33',
    'korea_auction/public.py': 'ea9e70d529af14d6d52b27c502ffe27bfcc81290a5cb382451615c79a11d858b',
    'korea_auction/rollover.py': '4bc8a99d5bc4b7a9e08fc50decb1d4226012be135ca79a58b3fd2f7b58c74650',
    'korea_auction/schedule.py': 'b02a576af1f29ed5314ec260ea6920975cedcfd0ec765dbe610483ef5592c89a',
    'korea_auction/selection.py': '895c4eda62e2fb829d8d48eb15a62f87d62f6f40898ae2cd8c2b0684595e6eeb',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'fb333be3c193764726614c5ff8fc8b8f2d76954b4f07605e01361d9dba5b64fc',
    'korea_auction/week_tile.py': '29c689d4cf06409a4f6fdac10d3c47fd50d47dd36c7e36f491651a42eb79b38d',
    'usa_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'usa_auction/fetch.py': 'bc172cd46dde788345a7a67d0dbd89b4d8def0b8afbb17d7c99d024a133370e0',
    'usa_auction/job.py': 'bd6edd31384638c32f26e9307374251dba2d393d46ea1a179722ef6ea0c1f675',
    'usa_auction/pages.py': '2f69e356e99eeb0398166a28f420f02849f84916dbccd072a179df6ee5ee5b33',
    'usa_auction/selection.py': 'f1bfe76a412abb2eb02087b678cf09b320c5312a41b0b298309cfc033d933b34',
    'usa_auction/views.py': 'bf5aa1183fec0d1858f273740cbe5fb5e5e174912ad850244ef936ce60ef844c',
    'usa_ticker_job.py': '080f34f1efff843e59afdb33d734cb8a42bc521b639d206f18ac9f06088c6f34'
}
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256))
DEPENDENCY_SHA256 = {}


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('USA_INSTALLED_COLLECTOR_UNEXPECTED')
    return {'usa_auction/%s.py' % name: (here / ('uauc_%s.py' % name)).read_bytes() for name in USA_MODULES}


def is_page(name):
    return False  # no page is part of this release
