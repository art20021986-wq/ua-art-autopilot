"""catalog_design_guard.py (CATALOG-TAG-FIX-001): the site's Google tag block is not part of the catalog design.

The design guard compares the catalog page outside the card region with catalog_design_golden.html (2026-09-27).
GA4-TAG-001 (owner «Да» 2026-10-25) puts the site's Google tag right after <head> of every page, between its own
markers <!--UA-GTAG-V1--> … <!--/UA-GTAG-V1-->; the golden file predates it, so every catalog rebuild — and with
it every card publication — fails with SHELL_FINGERPRINT_MISMATCH (FINANCE-PROBE R8: that block is the only
difference). The shell normalization now leaves out exactly that marked block; everything else of the shell is
still compared with the golden file.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'catalog_design_guard.py'
OLD = ('    replacements = (\n'
       '        (r"(?i)(Все|Усі)\\s*·\\s*\\d+", r"\\1 · #"),\n')
NEW = ('    # CATALOG-TAG-FIX-001: the site Google tag (GA4-TAG-001, its own markers) is analytics, not design.\n'
       '    source = re.sub(r"<!--UA-GTAG-V1-->.*?<!--/UA-GTAG-V1-->", "", source, flags=re.S)\n'
       '    replacements = (\n'
       '        (r"(?i)(Все|Усі)\\s*·\\s*\\d+", r"\\1 · #"),\n')


def build(name, source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'CATALOG-TAG-FIX-001' in text:
        raise ValueError('CATALOG_GUARD_FRAGMENT:' + name)
    text = text.replace(OLD, NEW)
    compile(text, name, 'exec')
    return text.encode('utf-8')
