"""Build the SITEMAP-FIX-001 candidate (owner «Да» 2026-11-11): ua_seo_sitemap.CatalogLinks reads the catalogue's
card links in the form SPEED-002 writes (ua/UA-XXXX.html, relative to /video/).

Since SPEED-002 the parser skipped them, so ua_card_lang_job passed no published cards to ua_card_lang.reconcile,
which removed the card versions, and the sitemap lost the card URLs. With the links read again, the job rebuilds
the versions within a minute and refreshes the sitemap. One line; every other byte stays.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDITS = {
    'ua_seo_sitemap.py': [
        ("""        if '/' in href.path and not href.path.startswith('/video/'):""",
         """        if '/' in href.path and not href.path.startswith(('/video/', 'ua/', 'ru/')):  # SITEMAP-FIX-001: SPEED-002 links"""),
    ],
}
DEPENDENCY_SHA256 = {}


def targets(root):
    return tuple(EDITS)


def edit(name, value):
    text = value.decode('utf-8')
    if 'SITEMAP-FIX-001' in text:
        raise ValueError('SITEMAP_FIX_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('SITEMAP_FIX_EDIT:%s:%d' % (name, text.count(old)))
        text = text.replace(old, new)
    return text.encode('utf-8')


def build(source, dependencies, read_original=None):
    return {name: edit(name, value) for name, value in source.items()}
