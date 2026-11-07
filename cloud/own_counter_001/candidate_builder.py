"""Build the own counter candidate from the exact installed sources and the current public pages.

Writers: ua_seo_metadata.normalize (cards) and ua_seo_index (landings) add the counter next to the Google tag.
Pages now: car cards (video, site, video/ru, video/ua), their diagnostics pages, landings video/seo/{ua,ru,gu}.
analitika_yadro: the browser script no longer takes the site itself (www / bare host) for a visit source.
analitika_otchet: report days start at midnight in Kyiv instead of the server's UTC midnight.
"""
import hashlib
from pathlib import Path
import re

from release_constants import NEW_MODULES, PATCHED_MODULES
import ua_own_counter

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_metadata.py': 'b0af0db31c9aa66ff4b2867824cc8a0592beacbc006d31aca50660f59c767ac4',
    'ua_seo_index.py': '757adb13af4af7b397934fa48cb619df5a46e31a4de331db6bac25df1dde88a7',
    'analitika_yadro.py': 'afbc8a9e78da6cbdeba6bebae416192e13aa2fda359faded94ec6e0c9432b20b',
    'analitika_otchet.py': 'f70f978df1b5ff5a084441ba475871cb610cf9402752d68f9b23f7f1f3279051',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
MARK = 'UA-OWN-COUNTER-001'
IMPORT = (b'import ua_google_tag\n', b'import ua_google_tag\nimport ua_own_counter  # ' + MARK.encode() + b'\n')
PATCHES = {
    'ua_seo_metadata.py': (IMPORT, (b'    return ua_google_tag.apply(source)\n',
                                    b'    return ua_own_counter.apply(ua_google_tag.apply(source))\n')),
    'ua_seo_index.py': (IMPORT, (b"ua_google_tag.apply(html).encode('utf-8')",
                                 b"ua_own_counter.apply(ua_google_tag.apply(html)).encode('utf-8')")),
    'analitika_yadro.py': ((b"  if(h.indexOf(location.hostname)>=0) return '';\n",
                            b"  if(h.indexOf(location.hostname.replace(/^www\\./,''))>=0) return ''; // " + MARK.encode()
                            + b"\n"),),
    'analitika_otchet.py': ((
        'def granicy(period):\n'
        '    """Начало и конец периода в секундах. Сутки — по времени сервера."""\n'
        '    teper = time.time()\n'
        '    nachalo_sutok = time.mktime(time.localtime(teper)[:3] + (0, 0, 0, 0, 0, -1))\n'
        '    if period == "today":\n'
        '        return nachalo_sutok, teper\n'
        '    if period == "yesterday":\n'
        '        return nachalo_sutok - 86400, nachalo_sutok\n'
        '    if period == "7d":\n'
        '        return nachalo_sutok - 6 * 86400, teper\n'
        '    if period == "30d":\n'
        '        return nachalo_sutok - 29 * 86400, teper\n'
        '    return nachalo_sutok, teper\n'.encode(),
        ('def _kiev():  # ' + MARK + '\n'
         '    from zoneinfo import ZoneInfo\n'
         '    for imya in ("Europe/Kyiv", "Europe/Kiev"):\n'
         '        try:\n'
         '            return ZoneInfo(imya)\n'
         '        except Exception:\n'
         '            pass\n'
         '    raise RuntimeError("KIEV_TIMEZONE")\n\n\n'
         'def granicy(period):\n'
         '    """Начало и конец периода в секундах. Сутки — по времени Киева (зимой и летом)."""\n'
         '    import datetime\n'
         '    teper = time.time()\n'
         '    kiev = _kiev()\n'
         '    segodnya = datetime.datetime.fromtimestamp(teper, kiev).date()\n'
         '\n'
         '    def polnoch(dney_nazad):\n'
         '        den = segodnya - datetime.timedelta(days=dney_nazad)\n'
         '        return datetime.datetime(den.year, den.month, den.day, tzinfo=kiev).timestamp()\n'
         '    if period == "yesterday":\n'
         '        return polnoch(1), polnoch(0)\n'
         '    nazad = {"7d": 6, "30d": 29}.get(period, 0)\n'
         '    return polnoch(nazad), teper\n').encode()), (
        b'        if z not in ("unknown", "none", "null"):\n',
        ('        if "uaart" in z:  # ' + MARK + ': the site itself is not a source\n'
         '            return "Прямая ссылка"\n'
         '        if z not in ("unknown", "none", "null"):\n').encode())),
}
CARD = re.compile(r'UA-[0-9]{4,}(?:-[0-9a-f]{8})?\.html')
DIAG = re.compile(r'UA-[0-9]{4,}-diag\.html')
CARD_ROOTS = ('video', 'site', 'video/ru', 'video/ua')
DIAG_ROOTS = ('video', 'site')
LANDINGS = ('video/seo/ua', 'video/seo/ru', 'video/seo/gu')


def page_paths(root):
    """Relative paths of the public pages that get the counter now."""
    root = Path(root)
    found = []
    for folder in CARD_ROOTS:
        found.extend(p.relative_to(root).as_posix() for p in sorted((root/folder).glob('UA-*.html')) if CARD.fullmatch(p.name))
    for folder in DIAG_ROOTS:
        found.extend(p.relative_to(root).as_posix() for p in sorted((root/folder).glob('UA-*-diag.html')) if DIAG.fullmatch(p.name))
    for folder in LANDINGS:
        found.extend(p.relative_to(root).as_posix() for p in sorted((root/folder).glob('*.html')))
    return found


def patch(name, value):
    if MARK.encode() in value:
        raise ValueError('ALREADY_PATCHED:' + name)
    for old, new in PATCHES[name]:
        if value.count(old) != 1:
            raise ValueError('PATCH_ANCHOR:%s:%d' % (name, value.count(old)))
        value = value.replace(old, new)
    return value


def build(source, pages):
    for name, digest in SOURCE_SHA256.items():
        value = source.get(name)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES}
    for name in PATCHED_MODULES:
        result[name] = patch(name, source[name])
    for relative, value in pages.items():
        counted = ua_own_counter.apply(value.decode('utf-8')).encode('utf-8')
        if counted != value:
            result[relative] = counted
    return result
