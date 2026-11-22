"""Public pages of four cars no longer in the CRM, removed (SEO-FIX-20261121, answer 4).

UA-0007, UA-0008, UA-0019, UA-0020 left the CRM and the catalogue; their old pages stayed open to search (UA-0007 named
a canonical that no longer exists). The base page, its hashed copy and its diagnostics page are removed (404 then);
media and the unserved site/ copies stay. Refused when a code is back in the CRM or in the catalogue."""
from contextlib import closing
import re
import sqlite3

CODES = ('UA-0007', 'UA-0008', 'UA-0019', 'UA-0020')
PAGE = re.compile(r'(UA-[0-9]{4})(?:-[0-9a-f]{8}|-diag)?\.html')


def planned(name):
    """A public page of one of the four codes (video/UA-XXXX.html, its hashed copy or diagnostics page)."""
    folder, _, page = name.rpartition('/')
    match = PAGE.fullmatch(page)
    return folder == 'video' and bool(match) and match.group(1) in CODES


def crm_codes(root):
    with closing(sqlite3.connect((root / 'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        return {str(row[0]) for row in connection.execute('SELECT auto_number FROM cars')}


def find(root, codes=None):
    codes = crm_codes(root) if codes is None else codes
    catalogue = (root / 'video' / 'katalog.html').read_text(encoding='utf-8')
    back = sorted(c for c in CODES if c in codes or c + '.html' in catalogue)
    if back:
        raise ValueError('CODE_STILL_LISTED:' + ','.join(back))
    found = []
    for path in sorted((root / 'video').glob('UA-*.html')):
        name = path.relative_to(root).as_posix()
        if planned(name) and not path.is_symlink():
            found.append(name)
    if not found:
        raise ValueError('NOTHING_TO_REMOVE')
    return tuple(found)
