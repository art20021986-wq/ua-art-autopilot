"""Build the KOREA-CARD candidate from the Korea page as KOREA-LOTS-FULL-INSTALL-20261112 left it.

video/korea.html: the lot list block is replaced in place by its new version (owner 2026-11-12): each opened lot
gets its own link (#lot-<id>), the weekday goes with its date (Пт 13.11, uk/ru/ka) and the lot card shows the VIN,
not the lot number. Nothing else changes.
"""
import ua_korea_lots

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    page = source[PAGE].decode('utf-8')
    if page.count(ua_korea_lots.MARK) != 1 or 'id="kl-days"' not in page or 'history.replaceState' in page:
        raise ValueError('KOREA_CARD_PAGE_UNEXPECTED')
    return {PAGE: ua_korea_lots.apply(page).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
