"""Build the AUCTION-CLIENTS candidate from the installed sources.

- new: ua_auction_clients.py (records), ua_auction_clients_view.py (bot texts), ua_auction_clients_bot.py (bot glue),
  ua_auction_web.py (/api/auction/* login).
- ua_crm_orders.py: «➕ Создать клиента», «👥 Клиенты с доступом · N» in the Korea auction folder; handlers registered.
- ua_order/host.py: the site application mounts /api/auction/* (isolated).
- video/korea.html: «Вхід для клієнтів» at the top of the lot list.
"""
from pathlib import Path

import edit_crm_orders
import edit_order_host
import ua_korea_login

HERE = Path(__file__).resolve().parent
PAGE = 'video/korea.html'
SOURCE_FILES = (edit_crm_orders.PATH, edit_order_host.PATH, PAGE)
DEPENDENCY_SHA256 = {}
NEW_FILES = ('ua_auction_clients.py', 'ua_auction_clients_view.py', 'ua_auction_clients_bot.py', 'ua_auction_web.py')


def build(source, dependencies):
    """{installed path: new bytes}."""
    page = source[PAGE].decode('utf-8')
    new_page = ua_korea_login.apply(page)
    if new_page == page:
        raise ValueError('AUCTION_CLIENTS_PAGE_UNEXPECTED')
    result = {name: (HERE / name).read_bytes() for name in NEW_FILES}
    result[edit_crm_orders.PATH] = edit_crm_orders.build(source[edit_crm_orders.PATH])
    result[edit_order_host.PATH] = edit_order_host.build(source[edit_order_host.PATH])
    result[PAGE] = new_page.encode('utf-8')
    return result


def is_page(name):
    return False  # no file of this release is rewritten by another writer
