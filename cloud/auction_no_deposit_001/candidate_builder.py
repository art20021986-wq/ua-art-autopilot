"""Build the AUCTION-NO-DEPOSIT candidate from the exact installed sources (after AUCTION-MGR-BIDS, owner 2026-11-17).

Owner 2026-11-17: «Новый клиент аукционов» without step 6 «Передоплата» — 5 steps, the client is saved after the
city. The stored prepayment stays (column and older records untouched); a new client gets 0 and the existing
«💵 Депозит» button still sets it later.
- ua_auction_clients.py: create() takes no prepayment and stores 0.
- ua_auction_clients_view.py: 5 steps; the confirm screen without the prepayment; the card shows «Депозит» only
  when it is set.
- ua_auction_clients_bot.py: the creation dialogue ends after the city.
- video/kabinet.html: «Передоплата» in «Мій кабінет» only when it is set (no «0 $»); nothing else changes.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGE = 'video/kabinet.html'
# Installed versions (AUCTION-MGR-BIDS) this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_auction_clients.py': '4120c750e6dd1679bd72f37559c53ea4fbcef31c6df6d0fd30d862f7fd00da4f',
    'ua_auction_clients_view.py': '7b028bfa65c10c2ec480e11c4beb33658ca682181c5e47fa8aed146690694730',
    'ua_auction_clients_bot.py': '665157aa82b8a22f5c35d94809d27ac692cdeeeda869951b25a449221bcd82a6',
}
MODULES = tuple(SOURCE_SHA256)
SOURCE_FILES = MODULES + (PAGE,)
DEPENDENCY_SHA256 = {}
PREPAYMENT = '$("cab-dep").textContent=n(c.deposit_usd);'
PREPAYMENT_SHOWN = PREPAYMENT + '$("cab-dep").parentNode.hidden=!c.deposit_usd;'


def cabinet(page):
    if page.count(PREPAYMENT) != 1:
        raise ValueError('CABINET_PAGE_UNEXPECTED')
    return page.replace(PREPAYMENT, PREPAYMENT_SHOWN)


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / name).read_bytes() for name in MODULES}
    candidate[PAGE] = cabinet(source[PAGE].decode('utf-8')).encode('utf-8')
    return candidate
