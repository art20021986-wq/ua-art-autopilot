"""KOREA-WEEKTILE-001 (owner 2026-11-19: «4 — да»): when the ticker check fails, the CRM bot tells the CRM owners.

The CRM bot's own token (team_token.txt) and its owners («👑 Владелец», db.staff_ids_by_role), as the CRM bot itself
notifies them. One message per distinct problem, again after REPEAT_SECONDS if it lasts; a failure to send is logged
and never stops the collector. Nothing else is read or written in the CRM.
"""
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request

ROOT = Path('/home/Carix')
TOKEN = ROOT / 'team_token.txt'
SENT = ROOT / 'korea_auction_data/ticker_alert.json'
REPEAT_SECONDS = 6 * 3600


def text(problems):
    return ('⚠️ Корея, сайт: лента/жёлтая плашка не совпали со списком лотов — на сайте оставлена прошлая верная '
            'версия, сборщик повторит через час.\nПричина: %s' % ', '.join(problems[:5]))


def owners():
    """The CRM owners' chat ids (read only)."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import db
    return [int(i) for i in db.staff_ids_by_role(db.ROLE_OWNER)]


def post(token, chat, message):
    data = urllib.parse.urlencode({'chat_id': chat, 'text': message}).encode('utf-8')
    url = 'https://api.telegram.org/bot%s/sendMessage' % urllib.parse.quote(token, safe=':')
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=15) as response:
        response.read()


def send(problems, sent=None, token=None, chats=owners, deliver=post, clock=time.time):
    """Tell the owners about `problems` unless the same was told less than REPEAT_SECONDS ago. -> chats told."""
    sent = sent or SENT
    key = ' '.join(sorted(p.split(':')[0] for p in problems))
    try:
        last = json.loads(sent.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        last = {}
    if last.get('key') == key and clock() - last.get('at', 0) < REPEAT_SECONDS:
        return 0
    told = 0
    try:
        secret = (token or TOKEN).read_text(encoding='utf-8').strip()
        for chat in chats():
            try:
                deliver(secret, chat, text(problems))
                told += 1
            except Exception as error:  # one owner unreachable: the others still get it
                print('korea alert not sent: %s' % type(error).__name__, file=sys.stderr)
    except Exception as error:
        print('korea alert not sent: %s' % type(error).__name__, file=sys.stderr)
    if told:
        sent.parent.mkdir(parents=True, exist_ok=True)
        sent.write_text(json.dumps({'key': key, 'at': clock()}), encoding='utf-8')
    return told
