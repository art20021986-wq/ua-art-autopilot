"""Build the AUTOSEARCH candidate from the exact installed sources (owner 2026-11-17, tasks/AUTOSEARCH-001.md).

Owner: «автопоиск автомобиль с аукционов в личном кабинете с уведомлением … Telegram … До 10 сохраненных поисков»;
CRM: «видел общую статистику кто что смотрит и … кто на что подписан» (макеты 33-AUTOSEARCH*.png, «Да»).
- new: ua_lot_alerts.py (records, matching), ua_lot_alerts_web.py (cabinet API), ua_lot_alerts_bot.py (client bot:
  Telegram link and new-lot messages), ua_lot_alerts_view.py (CRM texts);
- ua_auction_web.py: /api/auction/alerts* for a logged-in client;
- ua_auction_clients_bot.py: «🔔 Автопоиск» block, button and screen; the client's searches and views in the card;
- lead_bot.py: one guarded register call of ua_lot_alerts_bot (client bot), before the lead desk;
- video/kabinet.html: «🔔 Автопошук» under «Мої ставки»; video/korea.html: a logged-in client's opened lot is counted.
Nothing else changes; every edit of a live file must match exactly once.
"""
import hashlib
from pathlib import Path

import cabinet_alerts

HERE = Path(__file__).resolve().parent
CABINET, KOREA, LEAD = 'video/kabinet.html', 'video/korea.html', 'lead_bot.py'
NEW = ('ua_lot_alerts.py', 'ua_lot_alerts_web.py', 'ua_lot_alerts_bot.py', 'ua_lot_alerts_view.py')
REPLACED = ('ua_auction_web.py', 'ua_auction_clients_bot.py')
# Installed versions this package was written against; any other version stops the build. korea.html is edited by
# its exact place only (other packages change other parts of it).
SOURCE_SHA256 = {
    'ua_auction_web.py': '1ef39473725e36fb2ca50ca89199f582d791c94fe7ff4ea49778818f8b9b373e',
    'ua_auction_clients_bot.py': '363d603e61856bce6729b862562f75463b1d6abd1511ea80b6564c3d7fcb14ce',
    LEAD: '4f5441f70411c292a2be3b14db8a1c030f8d82328759ee194d3ed6be3c084b73',
    CABINET: 'b74c5ba586b6071c930eb3bd53f502ca2ff23c708ac6cff7912c6243d63fb212',
}
SOURCE_FILES = tuple(SOURCE_SHA256) + (KOREA,)
NEW_FILES = NEW
DEPENDENCY_SHA256 = {}
LEAD_MARK = '    # LEAD-FOLDERS-001: the lead desk'
LEAD_HOOK = ('    # AUTOSEARCH-001: automatic lot search (Telegram link from «Мій кабінет», new-lot messages)\n'
             '    try:\n'
             '        import ua_lot_alerts_bot\n'
             '        ua_lot_alerts_bot.register(app)\n'
             '    except Exception as e:\n'
             "        logging.error('ua_lot_alerts_bot не подключён: %s', e)\n")


def lead(text):
    if text.count(LEAD_MARK) != 1 or 'ua_lot_alerts_bot' in text:
        raise ValueError('LEAD_BOT_UNEXPECTED')
    return text.replace(LEAD_MARK, LEAD_HOOK + LEAD_MARK)


def build(source, dependencies):
    for name, digest in SOURCE_SHA256.items():
        if hashlib.sha256(source[name]).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    candidate = {name: (HERE / name).read_bytes() for name in NEW + REPLACED}
    candidate[LEAD] = lead(source[LEAD].decode('utf-8')).encode('utf-8')
    candidate[CABINET] = cabinet_alerts.cabinet(source[CABINET].decode('utf-8')).encode('utf-8')
    candidate[KOREA] = cabinet_alerts.korea(source[KOREA].decode('utf-8')).encode('utf-8')
    return candidate
