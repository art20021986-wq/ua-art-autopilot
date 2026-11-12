"""Build the KOREA-TIME-001 candidate (owner 2026-11-12): the auction start in Korea time and Kyiv time.

1. The collector as TICKER-FIX6-INSTALL-20261112-R2 installed it, with ticker.py updated: every lot card in the home
   ticker shows «Торги 18.11 · 12:00 Корея · 05:00 Київ» (the hourly job rebuilds the ticker). The collector modules
   come from korea_auction/ in this package (zipped flat as kauc_<module>.py by the transport).
2. video/korea.html, the lot card: «Початок торгів (час Кореї) 2026/11/18 12:00» becomes
   «Початок торгів 18.11 · 12:00 Корея · 05:00 Київ» (Kyiv time worked out in the visitor's browser, summer time
   included; without it the Korea time alone). Three exact replacements in the lot list script; nothing else changes.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULES = ('catalog', 'collect', 'html_tools', 'job', 'lots', 'nbu', 'prices', 'public', 'selection', 'session', 'ticker')
# The collector exactly as TICKER-FIX6-INSTALL-20261112-R2 installed it (cloud/korea_ticker_fix6_001/korea_auction).
INSTALLED_SHA256 = {
    'korea_auction/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'korea_auction/catalog.py': '8bd5fb28edade7696228c43826831d856aa9bd9b1b2e620cfc1c652992b40f3c',
    'korea_auction/collect.py': '074c4179b350107482a36e861bdb67a1854f0bc0c0d02eeb1570983b5ab89301',
    'korea_auction/html_tools.py': '2baacd8a4ed1402b352c70c14475954eedd0c1aff98aa602fcab1a6ad20a9802',
    'korea_auction/job.py': '703d2f423d4e419c509cf5b2053c5189c5ae4bde85008f7ce08a75408b14b7c9',
    'korea_auction/lots.py': '9a764841f379dbdaaff5dda0e5c69e82b23826561ae8624a1314478b1cbc7ae9',
    'korea_auction/nbu.py': '0b1abeb8a940b3ccd70e31a4eecc8e8e5cbcaf24c528fc38ac9d56152f148b25',
    'korea_auction/prices.py': '271e13cc1e68e2cc3481c13c22e3b4a0fd42549cca8a414adc41624a3f145d3e',
    'korea_auction/public.py': 'a79d07b3914c2edaba432a8ff24630557ad9da07b7694f38651be0ac655459d9',
    'korea_auction/selection.py': 'f3caeacb641f2282562a2270b20cc99b663a20ddc5ae18e887cecfd66342d417',
    'korea_auction/session.py': 'a39f03ec675ad2f8817efbcd76ef81e3d11bfd647ed4992ec65a1b2db79c18f9',
    'korea_auction/ticker.py': 'aff2b4ca9b3eb715e7b0f1f0a8235f395b103bfa3c989e25bb4cb569f4d0d2a9',
}
PAGE = 'video/korea.html'
SOURCE_FILES = tuple(sorted(INSTALLED_SHA256)) + (PAGE,)
DEPENDENCY_SHA256 = {}

# The lot list script on korea.html (cloud/korea_lots_*/ua_korea_lots.py, as live on 2026-11-12): each piece once.
MARK = '"kyiv": ['
LABEL_FROM = '"start": ["Початок торгів (час Кореї)", "Начало торгов (время Кореи)", "ვაჭრობის დაწყება (კორეის დრო)"]'
LABEL_TO = ('"start": ["Початок торгів", "Начало торгов", "ვაჭრობის დაწყება"], "kr": ["Корея", "Корея", "კორეა"], '
            '"kyiv": ["Київ", "Киев", "კიევი"]')
ROW_FROM = 'row("start",l.auction_start)'
# row() escapes its value; the time line carries translated words (t() gives the site's data-uk/ru/ka spans)
ROW_TO = '(l.auction_start?"<dt>"+t("start")+"</dt><dd>"+when(l.auction_start)+"</dd>":"")'
FUNC_AT = 'function row(k,v){'
# 'YYYY/MM/DD HH:MM' (Korea, UTC+9) -> '18.11 · 12:00 Корея · 05:00 Київ'; the Kyiv day is added when it differs.
WHEN = ('function when(s){var m=/^(\\d{4})\\/(\\d\\d)\\/(\\d\\d) (\\d\\d:\\d\\d)/.exec(s||"");if(!m)return esc(s);'
        'var out=m[3]+"."+m[2]+" · "+m[4]+" "+t("kr"),at=new Date(m[1]+"-"+m[2]+"-"+m[3]+"T"+m[4]+":00+09:00"),p=null;'
        '["Europe/Kyiv","Europe/Kiev"].some(function(z){try{p={};new Intl.DateTimeFormat("en-GB",{timeZone:z,'
        'day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(at)'
        '.forEach(function(x){p[x.type]=x.value;});return true;}catch(e){p=null;return false;}});'
        'if(!p||!p.hour)return out;var h=p.hour==="24"?"00":p.hour,d=p.day+"."+p.month;'
        'return out+" · "+h+":"+p.minute+(d===m[3]+"."+m[2]?"":" ("+d+")")+" "+t("kyiv");}')


def patch_page(page):
    if MARK in page:
        raise ValueError('KOREA_TIME_ALREADY_ON_PAGE')
    for piece in (LABEL_FROM, ROW_FROM, FUNC_AT):
        if page.count(piece) != 1:
            raise ValueError('KOREA_PAGE_UNEXPECTED:' + piece[:24])
    return page.replace(LABEL_FROM, LABEL_TO).replace(ROW_FROM, ROW_TO).replace(FUNC_AT, WHEN + FUNC_AT)


def build(source, dependencies, here=HERE, sha=None):
    if sha is not None and {name: sha(source[name]) for name in INSTALLED_SHA256} != INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_INSTALLED_COLLECTOR_UNEXPECTED')
    files = {'korea_auction/__init__.py': b''}
    for name in MODULES:
        files['korea_auction/%s.py' % name] = (here / ('kauc_%s.py' % name)).read_bytes()
    files[PAGE] = patch_page(source[PAGE].decode('utf-8')).encode('utf-8')
    return files


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it (KOREA-HOW-SYNC-001)
