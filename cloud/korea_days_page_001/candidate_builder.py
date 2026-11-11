"""Build the KOREA-DAYS-PAGE candidate from the Korea page as KOREA-LOTS-PAGE2-INSTALL-20261110-R2 left it.

video/korea.html: the lot list block is replaced in place by the new version (auction days on top, day and time on
the cards, «За датою торгів» sorting, VIN in the lot card). Nothing else changes.
"""
import ua_korea_lots

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    page = source[PAGE].decode('utf-8')
    if page.count(ua_korea_lots.MARK) != 1 or 'kl-tbd' not in page or 'kl-days' in page:
        raise ValueError('KOREA_DAYS_PAGE_UNEXPECTED')
    return {PAGE: ua_korea_lots.apply(page).encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
