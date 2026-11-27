"""Build the HOME-BLOCKS-001 candidate (owner «Да» 2026-11-27 to the mockup).

ua_home_blocks.py (new): one style block in <head> of the home page that sets the auctions, the individual order and the
cars in stock apart as framed panels. Every page writer gets it through site_ge_inject.inject_html (a wrapper appended
at the end of the module); the static home page gets it now. Rollback restores both byte for byte. No card, catalogue,
text, link, photo or CRM change. ua_head_block.py (installed by PERF-CWV-001) puts the block in <head>.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_MODULES = ('ua_home_blocks.py',)
PAGES = ('video/index.html',)
TAG = 'HOME-BLOCKS-001'
INJECT_TAIL = ("\n\n# HOME-BLOCKS-001: the home page's auctions, individual order and cars in stock set apart as panels.\n"
               "_ua_home_blocks_base_inject = inject_html\n"
               "def inject_html(source):\n"
               "    import ua_home_blocks\n"
               "    return ua_home_blocks.apply(_ua_home_blocks_base_inject(source))\n")
EDITS = ('site_ge_inject.py',)
# Installed by PERF-CWV-001 (2026-11-26); this release uses it as it is.
DEPENDENCY_SHA256 = {'ua_head_block.py': 'd2f5dbead3de3678ef4f74d27b602ae69a239cf6a1014595894c29767aa29c75'}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def page_names(root):
    root = Path(root)
    return tuple(name for name in PAGES if (root/name).is_file())


def targets(root):
    """Existing files the candidate replaces (the new module is added beside them)."""
    return EDITS + page_names(root)


def edit(name, value):
    text = value.decode('utf-8')
    if TAG in text:
        raise ValueError('HOME_BLOCKS_ALREADY_APPLIED:' + name)
    if 'def inject_html(' not in text or '_ua_perf_base_inject' not in text:
        raise ValueError('HOME_BLOCKS_INJECT_MISSING')
    return (text.rstrip('\n') + INJECT_TAIL).encode('utf-8')


def page(html):
    """The home page as the page writers will now produce it (any other page is unchanged)."""
    import ua_home_blocks
    return ua_home_blocks.apply(html)


def golden_page(html):
    return html


def build(source, dependencies):
    """{name: new bytes}; the installed ua_head_block.py must be the PERF-CWV-001 one."""
    for name, digest in DEPENDENCY_SHA256.items():
        if sha(dependencies[name]) != digest:
            raise ValueError('HOME_BLOCKS_DEPENDENCY:' + name)
    result = {name: (HERE/name).read_bytes() for name in NEW_MODULES}
    for name, value in source.items():
        if name in EDITS:
            result[name] = edit(name, value)
            continue
        changed = page(value.decode('utf-8')).encode('utf-8')
        if changed == value:
            raise ValueError('HOME_BLOCKS_PAGE_UNCHANGED:' + name)
        result[name] = changed
    return result


def is_page(name):
    return name.endswith('.html')
