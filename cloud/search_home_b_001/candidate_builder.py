"""Build the SEARCH-HOME-001 B candidate (owner «Да» 2026-11-27 03:29 UTC to the top search block).

ua_search_home.py (new): the inside of the home page's auctions section becomes the search «Пошук авто на аукціонах
світу». Every page writer gets it through site_ge_inject.inject_html (a wrapper appended at the end of the module, after
HOME-BLOCKS-001's); the static home page gets it now. Rollback restores both byte for byte (a home page the CRM sync
rewrote since gets its section back from the pre-install copy). No card, catalogue, Korea page or CRM change.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_MODULES = ('ua_search_home.py',)
PAGES = ('video/index.html',)
TAG = 'SEARCH-HOME-001 B'
INJECT_TAIL = ("\n\n# SEARCH-HOME-001 B: the home page top block «Пошук авто на аукціонах світу» (owner «Да» 2026-11-27).\n"
               "_ua_search_home_base_inject = inject_html\n"
               "def inject_html(source):\n"
               "    import ua_search_home\n"
               "    return ua_search_home.apply(_ua_search_home_base_inject(source))\n")
EDITS = ('site_ge_inject.py',)
DEPENDENCY_SHA256 = {}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def targets(root):
    """Existing files the candidate replaces (the new module is added beside them)."""
    return EDITS + tuple(name for name in PAGES if (Path(root)/name).is_file())


def edit(name, value):
    text = value.decode('utf-8')
    if TAG in text:
        raise ValueError('SEARCH_HOME_ALREADY_APPLIED:' + name)
    if 'def inject_html(' not in text or '_ua_home_blocks_base_inject' not in text:
        raise ValueError('SEARCH_HOME_INJECT_MISSING')  # built on HOME-BLOCKS-001 as installed
    return (text.rstrip('\n') + INJECT_TAIL).encode('utf-8')


def page(html):
    """The home page as the page writers will now produce it (any other page is unchanged)."""
    import ua_search_home
    return ua_search_home.apply(html)


def build(source, dependencies):
    """{name: new bytes}."""
    result = {name: (HERE/name).read_bytes() for name in NEW_MODULES}
    for name, value in source.items():
        if name in EDITS:
            result[name] = edit(name, value)
            continue
        changed = page(value.decode('utf-8')).encode('utf-8')
        if changed != value:
            result[name] = changed
    if 'video/index.html' not in result:
        raise ValueError('SEARCH_HOME_PAGE_UNCHANGED')
    return result


def is_page(name):
    return name.endswith('.html')
