"""catalog_design_golden.html (CATALOG-TAG-FIX-001): the golden catalog carries the office map link of MAPS-LINK-001.

MAPS-LINK-001 (owner «Да» 2026-10-31) replaced the office Google Maps link 4HvzWMdCp1QT2F9CA with 8T9A5H8YCtSs5eHH8 in
the modules and in every page, but not in the catalog design guard's golden file; the live catalog header link
therefore differs from it (FINANCE-PREFLIGHT CATALOG-TAG R2: the only difference besides the Google tag block).
Exactly that link is replaced, nothing else of the golden file changes.
"""
NAME = 'catalog_design_golden.html'
OLD = 'https://maps.app.goo.gl/4HvzWMdCp1QT2F9CA'
NEW = 'https://maps.app.goo.gl/8T9A5H8YCtSs5eHH8'


def build(name, source):
    text = source.decode('utf-8')
    if text.count(OLD) < 1 or NEW in text:
        raise ValueError('GOLDEN_MAP_LINK:' + name)
    return text.replace(OLD, NEW).encode('utf-8')
