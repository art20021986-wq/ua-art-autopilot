"""Build the analytics release 2 candidate from the exact installed source and the current public pages.

Pages now: the car diagnostics pages (video, site) and video/privacy.html get the Google tag (the same
ua_google_tag.apply the card writers use; the installed module is not changed).
analitika_otchet: one line under «Просмотров страниц» with every visitor by the server log (ua_server_visits).
"""
import hashlib
from pathlib import Path
import re

from release_constants import NEW_MODULES, PATCHED_MODULES
import ua_google_tag

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    # OWN-COUNTER-INSTALL-20261107 plan «after» (ANALYTICS-AUDIT-PROBE-20261108 read it installed).
    'analitika_otchet.py': '6667a8d9ccb09abc5f4792875677a82dc3e95cb063d7993395654653058d3715',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
MARK = 'UA-SERVER-VISITS-001'
PATCHES = {
    'analitika_otchet.py': ((
        '    stroki.append("👁 Просмотров страниц: %d" % prosmotry)\n'.encode(),
        ('    stroki.append("👁 Просмотров страниц: %d" % prosmotry)\n'
         '    try:  # ' + MARK + ': every visitor by the server log, also without the counter script\n'
         '        import ua_server_visits\n'
         '        stroki.extend(ua_server_visits.stroki(ot, do))\n'
         '    except Exception:\n'
         '        pass\n').encode()),),
}
DIAG = re.compile(r'UA-[0-9]{4,}-diag\.html')
DIAG_ROOTS = ('video', 'site')
SINGLE = ('video/privacy.html',)


def page_paths(root):
    """Relative paths of the public pages that get the Google tag now."""
    root = Path(root)
    found = []
    for folder in DIAG_ROOTS:
        found.extend(p.relative_to(root).as_posix() for p in sorted((root/folder).glob('UA-*-diag.html')) if DIAG.fullmatch(p.name))
    found.extend(relative for relative in SINGLE if (root/relative).is_file())
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
        tagged = ua_google_tag.apply(value.decode('utf-8')).encode('utf-8')
        if tagged != value:
            result[relative] = tagged
    return result
