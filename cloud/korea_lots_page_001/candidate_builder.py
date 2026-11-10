"""Build the KOREA-LOTS-PAGE candidate from the exact installed sources (after KOREA-AUCTION-INSTALL-20261110-R3).

- video/korea.html: the lot list (ua_korea_lots.apply); the «Дивитися онлайн» buttons lead to it.
- ua_order/auction.py: the auction enquiry may carry the chosen lot (optional field `lot`), shown in the CRM.
- video/order/quick-lead.js: a lot card's «Зв'язатися з менеджером» sends that lot.
"""
import hashlib
from pathlib import Path

import edit_quick_js
import ua_korea_lots

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
AUCTION = 'ua_order/auction.py'
SOURCE_FILES = (PAGE, AUCTION, edit_quick_js.PATH)
DEPENDENCY_SHA256 = {}
# ua_order/auction.py exactly as KOREA-AUCTION-INSTALL-20261110-R3 installed it (cloud/korea_auction_001/auction.py).
AUCTION_INSTALLED_SHA256 = '4e2febe2b8e4593a094b380ce25d4eaefdfe8cfb83069387de82515da731e52a'


def build(source, dependencies):
    """{installed path: new bytes}."""
    if hashlib.sha256(source[AUCTION]).hexdigest() != AUCTION_INSTALLED_SHA256:
        raise ValueError('KOREA_LOTS_AUCTION_MODULE_UNEXPECTED')
    page = source[PAGE].decode('utf-8')
    new_page = ua_korea_lots.apply(page)
    if new_page == page:
        raise ValueError('KOREA_LOTS_PAGE_UNCHANGED')
    return {PAGE: new_page.encode('utf-8'), AUCTION: (HERE / 'auction.py').read_bytes(),
            edit_quick_js.PATH: edit_quick_js.build(source[edit_quick_js.PATH])}


def is_page(name):
    return False  # korea.html is this site's own page; no other writer rewrites it
