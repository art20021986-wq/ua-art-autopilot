"""Build the MAPS-LINK-001 candidate: the company's Google Maps link replaced, exactly, wherever it is.

Owner 2026-10-31 («Да»): the new Maps profile link. Found by CARD-LANG-PROBE-20261031 in the modules that write
it (structured data, card and catalogue generators, the client bot) and in the public pages already written
(home, catalogue, order and info pages, every card, its copies and diagnostics page, in video/ and site/).
Only the exact old URL changes; every other byte stays. One-off installers and test pages are left as they are.
"""
from pathlib import Path

OLD = 'https://maps.app.goo.gl/4HvzWMdCp1QT2F9CA'
NEW = 'https://maps.app.goo.gl/8T9A5H8YCtSs5eHH8'
MODULES = ('ua_seo_schema.py', 'card_html.py', 'yadro.py', 'stranica_klienta.py', 'client_ui.py')
PAGE_FOLDERS = ('video', 'site')
SKIP_PAGES = ('proba',)  # old test pages, not linked from the site
DEPENDENCY_SHA256 = {}


def targets(root):
    """The modules above and every public page that holds the old link."""
    root = Path(root)
    pages = sorted('%s/%s' % (folder, path.name) for folder in PAGE_FOLDERS for path in (root/folder).glob('*.html')
                   if path.is_file() and not path.is_symlink() and not path.name.startswith(SKIP_PAGES)
                   and OLD.encode() in path.read_bytes())
    return tuple(name for name in MODULES if OLD.encode() in (root/name).read_bytes()) + tuple(pages)


def build(source, dependencies):
    result = {}
    for name, value in source.items():
        if OLD.encode() not in value or NEW.encode() in value:
            raise ValueError('MAPS_LINK:' + name)
        result[name] = value.replace(OLD.encode(), NEW.encode())
    return result
