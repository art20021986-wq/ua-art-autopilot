"""Build the AUCTION-MGR-BIDS candidate from the exact installed sources (after AUCTION-LIMIT, owner 2026-11-12).

Owner 2026-11-12: variant А — every bid on the auction is placed by a person, in their own browser (nothing is sent to
the auction from the server); a manager bids for a client from the CRM bot; the client follows their bids in «Мій
кабінет»; the bot shows who placed every bid and statistics by manager.
- ua_auction_bids.py: requests from the site, a manager's bids, the first answer «поставил / не поставил» recorded
  with who gave it; the server never talks to the auction (place() and its lock are gone).
- ua_auction_bids_bot.py: «🔨 Заявка на ставку» to the staff with «🔗 Открыть лот», «✅ Поставил», «❌ Не поставил»;
  the first answer shows on every staff copy, without buttons.
- ua_auction_clients.py: a client record also gives the manager who created it (created_by).
- ua_auction_stats.py: clients-themselves / managers-for-clients counts, statistics by manager, a manager's bids.
- ua_auction_clients_view.py / ua_auction_clients_bot.py: «🔨 Ставка за клиента» (open the lot, place it, «✅ Поставил»),
  «👔 По менеджерам», «Оформил» and who placed each bid.
- ua_auction_web.py: a bid from the site becomes a request; GET /api/auction/my for «Мій кабінет».
- ua_auction_cars.py (new): the client's bought cars (the contract accounting; none yet).
- video/korea.html: the UA-KOREA-BID-V1 block replaced by its variant А version (ua_korea_bid), «Мій кабінет» in the
  login line (ua_client_cabinet.link); nothing else changes.
- video/kabinet.html (new): «Мій кабінет» (ua_client_cabinet.page, built from the live Korea page).
"""
import hashlib
from pathlib import Path

import ua_client_cabinet
import ua_korea_bid

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
# Installed versions (after AUCTION-LIMIT) this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_auction_clients.py': '6677e89f4bb68ed79c57eb9881dfa3eef04199bd44e11eca0e08fd0efd65ce77',
    'ua_auction_clients_view.py': '29c9bb11738770e9efa0bf2310615b17ab3fb459659d0d9959a4b603fc4708e7',
    'ua_auction_clients_bot.py': '0b6841451c8c7b4f883645344f9c0b0b4e66c4df0ecfe3d05e6b495258359af1',
    'ua_auction_bids.py': 'c4aef73f74b39b0809b5caa096db8ede009149abdbff2774338f1f1133102ba5',
    'ua_auction_stats.py': 'b03636c7768a9b7314a89138737b031f36fdb1d11058ab139f95233db4b379e7',
    'ua_auction_bids_bot.py': '11e3d27c5227c9d333169437b2981643b3a1230c737ff6ce178ec230c1a5dd87',
    'ua_auction_web.py': 'ac1923dfe96b8ca8b2ecdd4f0c7f9b97b6ebb5adb2f6fe0b1ac99d20ab9fce0b',
}
MODULES = tuple(SOURCE_SHA256)
NEW_MODULES = ('ua_auction_cars.py',)
SOURCE_FILES = MODULES + (PAGE,)
DEPENDENCY_SHA256 = {}


def korea(page):
    """The Korea page after this release: the variant А bid block and «Мій кабінет» in the login line."""
    if 'kc-limit' in page or 'limit_usd' in page:
        raise ValueError('KOREA_PAGE_BEFORE_AUCTION_LIMIT')
    return ua_korea_bid.replace(ua_client_cabinet.link(page))


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / name).read_bytes() for name in MODULES + NEW_MODULES}
    page = korea(source[PAGE].decode('utf-8'))
    candidate[PAGE] = page.encode('utf-8')
    candidate[ua_client_cabinet.PATH] = ua_client_cabinet.page(page).encode('utf-8')
    return candidate
