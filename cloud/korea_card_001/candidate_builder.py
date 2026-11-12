"""Build the KOREA-CARD candidate from the Korea page as KOREA-LOTS-FULL-INSTALL-20261112 left it.

video/korea.html: the lot list block is replaced in place by its new version (owner 2026-11-12): each opened lot
gets its own link (#lot-<id>), the weekday goes with its date (Пт 13.11, uk/ru/ka) and the lot card shows the VIN,
not the lot number. KOREA-LOTS-FULL replaced the list block together with the client login and bid blocks that sat
inside it; they are put back by their own modules (ua_korea_login.py, ua_korea_bid.py: unchanged copies of
cloud/auction_clients_001 and cloud/auction_bids_001), and the new list keeps such blocks from now on.
Nothing else changes.
"""
import ua_korea_bid
import ua_korea_login
import ua_korea_lots

PAGE = 'video/korea.html'
SOURCE_FILES = (PAGE,)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    page = source[PAGE].decode('utf-8')
    if page.count(ua_korea_lots.MARK) != 1 or 'id="kl-days"' not in page or 'history.replaceState' in page:
        raise ValueError('KOREA_CARD_PAGE_UNEXPECTED')
    page = ua_korea_lots.apply(page)
    for block in (ua_korea_login, ua_korea_bid):  # the login first: the bid block goes right after it
        if block.MARK not in page:
            page = block.apply(page)
    return {PAGE: page.encode('utf-8')}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
