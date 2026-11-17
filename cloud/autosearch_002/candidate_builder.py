"""Build the AUTOSEARCH-002 candidate from the exact installed sources (after AUTOSEARCH-001, owner 2026-11-17).

Owner 17.11: a manager logs in on the site (a login the owner gives «👔 Права менеджера на сайте» in the CRM bot), saves
search criteria and the WhatsApp group link for his client; the first message is the owner's greeting, then a link to
every matching lot; the manager sends it to the group in one tap (wa.me — a bot may not post to a manually made WhatsApp
group); the client's own «🔔 Автопошук» and the client-bot Telegram link of AUTOSEARCH-001 go away («ему не надо»).
- ua_lot_alerts.py (records: managers, requests, found, views), ua_lot_alerts_web.py (manager API),
  ua_lot_alerts_view.py (CRM texts): replaced; new ua_lot_alerts_whatsapp.py (WhatsApp texts and share link) and
  ua_lot_alerts_crm.py (manager messages in the CRM bot); ua_lot_alerts_bot.py (client bot) removed;
- ua_auction_clients_bot.py: requests per viewer, the rights button for the owner, registers ua_lot_alerts_crm;
- ua_auction_web.py: docstring only (the routes follow ua_lot_alerts_web);
- lead_bot.py: the AUTOSEARCH-001 hook removed — back to the exact version before AUTOSEARCH-001;
- video/kabinet.html: the AUTOSEARCH-001 section removed (back to the exact page before it, cabinet_v1 holds that
  section), then the manager section added. video/korea.html (lot views) stays.
"""
import hashlib
from pathlib import Path

import cabinet_manager
import cabinet_v1

HERE = Path(__file__).resolve().parent
CABINET, LEAD = 'video/kabinet.html', 'lead_bot.py'
REPLACED = ('ua_lot_alerts.py', 'ua_lot_alerts_web.py', 'ua_lot_alerts_view.py', 'ua_auction_clients_bot.py',
            'ua_auction_web.py')
NEW = ('ua_lot_alerts_whatsapp.py', 'ua_lot_alerts_crm.py')
REMOVED = ('ua_lot_alerts_bot.py',)
# Installed versions (AUTOSEARCH-001) this package was written against; any other version stops the build.
SOURCE_SHA256 = {
    'ua_lot_alerts.py': '0076f2901d1a4a86f8b90d30727a75f798d8f18c5d49b9fb6549ff2e901cd824',
    'ua_lot_alerts_web.py': '5c771c7a3ef69396b6177e83a0f316595631f2bc3cc0713b514abded9dbbcc3b',
    'ua_lot_alerts_view.py': '48ef92fbaf9d7727c3ff8629152dcca28ec2f15650fe96bf3c4c74122862cb49',
    'ua_lot_alerts_bot.py': 'c40341f9ec28e2f4935e71c3d52ff6b50d8369aba728baafd7b3ef9c99eac66b',
    'ua_auction_clients_bot.py': 'bfd16ea29646feb7a4868f6fd4829188dd6164254402538391a3adb97e8686da',
    'ua_auction_web.py': 'e8175354babeb88b59e4cd0d1e64d2f996ba3101e0d4a12af96b083c0278dc44',
    LEAD: '817ae45b614abbb2c608e2a28efe667fb53abd274c73270a3a2bd87722f85f03',
    CABINET: '978f4b4902d20b748227fb6ffd586b7015f32be9fdbd047060eaaf24943bae46',
}
# The exact versions before AUTOSEARCH-001 that the removals must give back.
LEAD_BEFORE = '4f5441f70411c292a2be3b14db8a1c030f8d82328759ee194d3ed6be3c084b73'
CABINET_BEFORE = 'b74c5ba586b6071c930eb3bd53f502ca2ff23c708ac6cff7912c6243d63fb212'
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
LEAD_HOOK = ('    # AUTOSEARCH-001: automatic lot search (Telegram link from «Мій кабінет», new-lot messages)\n'
             '    try:\n'
             '        import ua_lot_alerts_bot\n'
             '        ua_lot_alerts_bot.register(app)\n'
             '    except Exception as e:\n'
             "        logging.error('ua_lot_alerts_bot не подключён: %s', e)\n")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def lead(text):
    """lead_bot.py without the AUTOSEARCH-001 hook."""
    if text.count(LEAD_HOOK) != 1:
        raise ValueError('LEAD_BOT_UNEXPECTED')
    return text.replace(LEAD_HOOK, '')


def cabinet(page):
    """«Мій кабінет» without the AUTOSEARCH-001 section, then with the manager section."""
    for part in (cabinet_v1.SECTION, cabinet_v1.STYLE, cabinet_v1.SCRIPT):
        if page.count(part) != 1:
            raise ValueError('CABINET_V1_UNEXPECTED')
        page = page.replace(part, '')
    return page, cabinet_manager.cabinet(page)


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if _sha(source[name]) != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / name).read_bytes() for name in REPLACED + NEW}
    candidate.update({name: None for name in REMOVED})
    candidate[LEAD] = lead(source[LEAD].decode('utf-8')).encode('utf-8')
    if _sha(candidate[LEAD]) != LEAD_BEFORE:
        raise ValueError('LEAD_BOT_NOT_RESTORED')
    restored, page = cabinet(source[CABINET].decode('utf-8'))
    if _sha(restored.encode('utf-8')) != CABINET_BEFORE:
        raise ValueError('CABINET_NOT_RESTORED')
    candidate[CABINET] = page.encode('utf-8')
    return candidate
