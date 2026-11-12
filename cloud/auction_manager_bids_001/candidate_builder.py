"""Build the AUCTION-MGR-BIDS candidate from the exact installed sources (AUCTION-LIMIT install, owner 2026-11-12).

Owner 2026-11-12: a manager bids for a client from the CRM bot, and the bot shows who placed every bid.
- ua_auction_bids.py: the ledger keeps who placed a bid (placed_by; older ledgers get the column, older bids stay
  the client's); one bid at a time to the auction account (a lock file shared by the web app and the bot).
- ua_auction_clients.py: a client record also gives the manager who created it (created_by).
- ua_auction_stats.py: clients-themselves / managers-for-clients counts, statistics by manager, a manager's bids.
- ua_auction_clients_view.py / ua_auction_clients_bot.py: «🔨 Ставка за клиента» in the client card, «👔 По менеджерам»
  on the «🔨 Клиенты аукциона» screen, «Оформил» and who placed each bid in the card and the bids of a date.
No page, web app or table change beyond the new ledger column.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Installed versions (after AUCTION-LIMIT) this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_auction_clients.py': '6677e89f4bb68ed79c57eb9881dfa3eef04199bd44e11eca0e08fd0efd65ce77',
    'ua_auction_clients_view.py': '29c9bb11738770e9efa0bf2310615b17ab3fb459659d0d9959a4b603fc4708e7',
    'ua_auction_clients_bot.py': '0b6841451c8c7b4f883645344f9c0b0b4e66c4df0ecfe3d05e6b495258359af1',
    'ua_auction_bids.py': 'c4aef73f74b39b0809b5caa096db8ede009149abdbff2774338f1f1133102ba5',
    'ua_auction_stats.py': 'b03636c7768a9b7314a89138737b031f36fdb1d11058ab139f95233db4b379e7',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES}
