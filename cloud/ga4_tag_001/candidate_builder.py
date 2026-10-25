"""Build the Google tag candidate from the exact installed sources and the current public pages."""
import hashlib
from pathlib import Path
import re

from release_constants import NEW_MODULES, PATCHED_MODULES, REPLACED_MODULES
import ua_google_tag

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_metadata.py': 'ba11ec4153c596aef4a1aebe821f965177a0c13a56b3000e0d6e7e4ff13609d5',
    'ua_seo_index.py': 'd44febac96a86e2e53434f482732be6fdabd70128d6856288805d01d2451b805',
    'publish_transaction_guard.py': 'aace67f4b27ecad795eb35f126e550ab7fe91119c39c769f02b16f264060b5df',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
# Pages a visitor or Google lands on; later writes keep the tag through the hooks above.
CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html')
CARD = re.compile(r'UA-[0-9]{4,}\.html')
ROOTS = ('video', 'site')
LANDINGS = ('video/seo/ua', 'video/seo/ru', 'video/seo/gu')
# Names the catalog block uses from publish_transaction_guard.py.
REQUIRED_NAMES = (b'\ndef _install_catalog(', b'\ndef _read(', b'\ndef _atomic(', b'\ndef _sha(', b'\ndef _append_log(',
                  b'\nclass PublishError(', b'\nROOTS')
# The catalog is rebuilt from the protected design template, so the tag is added after each install.
CATALOG_BLOCK = b'''

# UA-GA4-TAG-001:START
# Google tag on the installed catalog; a failure is logged and never blocks the sale.
_UA_GA4_TAG_BASE_INSTALL = _install_catalog

def _install_catalog(source, target):
    result = _UA_GA4_TAG_BASE_INSTALL(source, target)
    for root in ROOTS:
        path = root / 'katalog.html'
        before = _read(path)
        try:
            import ua_google_tag
            after = ua_google_tag.apply(before.decode('utf-8')).encode('utf-8')
        except Exception as exc:
            _append_log('GA4_TAG_SKIPPED %s %s' % (path, type(exc).__name__))
            continue
        if after != before:
            _atomic(path, after, path.stat().st_mode & 0o777)
        if _read(path) != after:
            raise PublishError('GA4_TAG_READBACK:' + str(path))
        if str(path) in result.get('installed', {}):
            result['installed'][str(path)]['sha256'] = _sha(after)
    return result
# UA-GA4-TAG-001:END
'''


def page_paths(root):
    """Relative paths of the public pages that get the tag now."""
    root = Path(root)
    found = []
    for folder in ROOTS:
        for path in sorted((root/folder).glob('*.html')):
            if path.name in CORE or CARD.fullmatch(path.name):
                found.append(path.relative_to(root).as_posix())
    for folder in LANDINGS:
        found.extend(path.relative_to(root).as_posix() for path in sorted((root/folder).glob('*.html')))
    return found


def build(source, pages):
    for name, digest in SOURCE_SHA256.items():
        value = source.get(name)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
    for name in PATCHED_MODULES:
        if b'UA-GA4-TAG-001' in source[name]:
            raise ValueError('ALREADY_PATCHED:' + name)
        for needed in REQUIRED_NAMES:
            if needed not in source[name]:
                raise ValueError('PATCH_ANCHOR:' + needed.decode())
        result[name] = source[name].rstrip(b'\n') + b'\n' + CATALOG_BLOCK
    for relative, value in pages.items():
        tagged = ua_google_tag.apply(value.decode('utf-8')).encode('utf-8')
        if tagged != value:
            result[relative] = tagged
    return result
