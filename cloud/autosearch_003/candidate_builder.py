"""Build the AUTOSEARCH-003 candidate from the exact installed sources (after AUTOSEARCH-002, owner 2026-11-17).

Owner 17.11: «Менеджера я добавляю по такому же принципу, как клиента… В клиентах менеджера убери — верни как было…
Работа менеджера — не в боте CRM, а на сайте»; «➕ Создать менеджера» in «🧑‍💼 Менеджеры сайта» and the manager adds his
own clients on the site (mockup 33-AUTOSEARCH-MANAGERS.png, «1. Да 2. Да»).
- new: ua_site_managers.py (manager logins: the clients store with its own database), ua_site_managers_view.py and
  ua_site_managers_bot.py (CRM: list, creation in the client's 5 steps, card);
- ua_lot_alerts.py (contacts and requests per site manager; schema 3 drops the AUTOSEARCH-002 rights and requests),
  ua_lot_alerts_web.py (manager API by role), ua_lot_alerts_view.py (CRM texts): replaced;
- ua_auction_clients_bot.py: «👔 Права менеджера на сайте» removed from the client card, «🧑‍💼 Менеджеры сайта · N» on
  the home screen, registers ua_site_managers_bot;
- ua_auction_web.py: a site manager logs in with the same form (role «manager», no bids);
- video/kabinet.html: the AUTOSEARCH-002 manager section removed (back to the exact page before it, cabinet_old holds
  that section), then the site manager's cabinet added. ua_lot_alerts_whatsapp.py, lead_bot.py, korea.html stay.
"""
import hashlib
from pathlib import Path

import cabinet_manager
import cabinet_old

HERE = Path(__file__).resolve().parent
CABINET = 'video/kabinet.html'
REPLACED = ('ua_lot_alerts.py', 'ua_lot_alerts_web.py', 'ua_lot_alerts_view.py', 'ua_auction_clients_bot.py',
            'ua_auction_web.py')
NEW = ('ua_site_managers.py', 'ua_site_managers_view.py', 'ua_site_managers_bot.py')
# Installed versions (AUTOSEARCH-002) this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_lot_alerts.py': 'dfe15442a7ba372cd32b1f01555b1b3d89bc2eac74f66996068cc166d9052afc',
    'ua_lot_alerts_web.py': 'e2460ad1852718658b21324fdc4eaada06bb86e18d339db24d136ae7f75cc2b1',
    'ua_lot_alerts_view.py': '06b27fbb28bb840452fd078d0776e62faa264e74c44c0c0274feb128a20513bc',
    'ua_auction_clients_bot.py': '3d46779a54a58187013d5bb4927b7d7cdd2e217792ee7c1f6ae84ac20f5dba60',
    'ua_auction_web.py': '4007157f920de6806de6f87d273679c8b811ad62f0900ce3b106181c38b80505',
    CABINET: 'b4fb63b4d7babf17ec4c36309713761bdfc536e1d3507ce906fbb35ff222a359',
}
# The exact page before any manager section (the AUTOSEARCH-002 removal must give it back).
CABINET_BEFORE = 'b74c5ba586b6071c930eb3bd53f502ca2ff23c708ac6cff7912c6243d63fb212'
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def cabinet(page):
    """«Мій кабінет» without the AUTOSEARCH-002 manager section, then with the site manager's cabinet."""
    for part in (cabinet_old.SECTION, cabinet_old.STYLE, cabinet_old.SCRIPT):
        if page.count(part) != 1:
            raise ValueError('CABINET_V2_UNEXPECTED')
        page = page.replace(part, '')
    return page, cabinet_manager.cabinet(page)


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if _sha(source[name]) != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / name).read_bytes() for name in REPLACED + NEW}
    restored, page = cabinet(source[CABINET].decode('utf-8'))
    if _sha(restored.encode('utf-8')) != CABINET_BEFORE:
        raise ValueError('CABINET_NOT_RESTORED')
    candidate[CABINET] = page.encode('utf-8')
    return candidate
