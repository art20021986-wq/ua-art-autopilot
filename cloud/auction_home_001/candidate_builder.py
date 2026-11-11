"""Build the AUCTION-HOME candidate from the exact installed sources (CRM-MENU-INSTALL R2, AUCTION-CLIENTS-INSTALL
and AUCTION-BIDS-INSTALL of 2026-11-10).

- ua_menu_extra.py: «🔨 Клиенты аукциона» right under «👤 Клиенты» in the CRM bot main menu (same roles).
- ua_auction_stats.py (new): statistics and bids by date, read only.
- ua_auction_clients_view.py / ua_auction_clients_bot.py: the «🔨 Клиенты аукциона» screen, «📋 Ставки по датам»,
  the client's bids by date in the card.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Installed versions this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_menu_extra.py': '1c9e77f95acfc213117f091d12b05b3e7534ff575cdc6017e4a0502662c1c2e7',
    'ua_auction_clients_view.py': 'c12ae834af8e9dbb1fda7354a6705df8db870af90d9ce8f6fa9d658bd8ff2442',
    'ua_auction_clients_bot.py': 'fdf0d1bb20bf2573de97df9050553052007ea2bfb77c6ee6a572b0e6a005d1c5',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
NEW_FILES = ('ua_auction_stats.py',)
# Installed modules the candidate relies on unchanged.
DEPENDENCY_SHA256 = {
    'ua_auction_bids.py': '2b644407a6ac2f969d295cbb82b0a7d2d2d8be38e62fe4e7ad0b0a61747e0580',
    'ua_auction_clients.py': '3d54afd110e28f170b0e88ca1a4c387d07a48941307024f1bddc90853f414a5d',
}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    return {name: (HERE / name).read_bytes() for name in SOURCE_FILES + NEW_FILES}
