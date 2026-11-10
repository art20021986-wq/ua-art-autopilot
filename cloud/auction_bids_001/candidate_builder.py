"""Build the AUCTION-BIDS candidate from the sources as AUCTION-CLIENTS-INSTALL-20261110 installed them.

- new: ua_auction_bids.py (checks, placement, ledger), ua_auction_bids_bot.py (staff notifications).
- ua_auction_web.py: /api/auction/bid for a logged-in client; ua_auction_clients_bot.py: registers the notifier.
- video/korea.html: «Розмістити ставку» in the lot card for a logged-in client.
"""
import hashlib
from pathlib import Path

import ua_korea_bid

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
WEB, BOT = 'ua_auction_web.py', 'ua_auction_clients_bot.py'
SOURCE_FILES = (WEB, BOT, PAGE)
DEPENDENCY_SHA256 = {}
# Exactly as AUCTION-CLIENTS-INSTALL-20261110 installed them (cloud/auction_clients_001).
INSTALLED_SHA256 = {WEB: '0ed7807b2911775c242aac337dc1b38452fbac6eddade270094ffdad0465f78b', BOT: '27e96d235af265616800916af0064de1fadd35d2d3f3a419347a3ac59a3acf08'}
NEW_FILES = ('ua_auction_bids.py', 'ua_auction_bids_bot.py')


def build(source, dependencies):
    """{installed path: new bytes}."""
    for name, digest in INSTALLED_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('AUCTION_BIDS_INSTALLED_UNEXPECTED:' + name)
    page = source[PAGE].decode('utf-8')
    new_page = ua_korea_bid.apply(page)
    if new_page == page:
        raise ValueError('AUCTION_BIDS_PAGE_UNEXPECTED')
    result = {name: (HERE / name).read_bytes() for name in NEW_FILES + (WEB, BOT)}
    result[PAGE] = new_page.encode('utf-8')
    return result


def is_page(name):
    return False  # no file of this release is rewritten by another writer
