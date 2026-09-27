"""Verify the installed inbox; optionally show its existing first order to owner.

Run with python3.10 -S. No polling, database writes, or test applications.
--publish sends the actual folder once and records Telegram's message ID.
"""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path('/home/Carix')
sys.path.insert(0, str(ROOT))
for directory in ('/home/Carix/.local/lib/python3.10/site-packages',
                  '/usr/local/lib/python3.10/site-packages',
                  '/usr/local/lib/python3.10/dist-packages',
                  '/usr/lib/python3/dist-packages'):
    if Path(directory).is_dir():
        sys.path.append(directory)


def verify():
    from ua_order import bindings, host
    from ua_order.crm import list_view
    import vitrina

    folder = ROOT/'client_order_inbox_20260927'
    manifest = json.loads((folder/'manifest.json').read_text())
    for name, value in manifest.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == value['after'], name
    owner_id = int((ROOT/'vladelec.txt').read_text().strip())
    runtime = host.current()
    assert runtime is not None and runtime is not host.UNAVAILABLE
    rows, _ = runtime.service.repository.list_requests()
    first = runtime.service.repository.detail(1)
    assert first['id'] in {row['id'] for row in rows}
    jobs = []
    app = SimpleNamespace(handlers={}, bot=object(), concurrent_updates=0,
        job_queue=SimpleNamespace(get_jobs_by_name=lambda _: [],
            run_repeating=lambda fn, **options: jobs.append(options)))
    app.add_handler = lambda handler, group: app.handlers.setdefault(group, []).append(handler)
    host.register_customer(app, owner_id=owner_id)
    inbox = [handler.callback.__self__ for group in app.handlers.values() for handler in group
             if getattr(getattr(handler, 'pattern', None), 'pattern', None) == '^orders:']
    assert len(inbox) == 1 and len(jobs) == 1 and jobs[0]['name'] == bindings.JOB_NAME
    for user, chat, kind, expected in ((owner_id,owner_id,'private',True),
            (owner_id+1,owner_id+1,'private',False), (owner_id,-1,'group',False)):
        assert inbox[0].authorize(SimpleNamespace(effective_user=SimpleNamespace(id=user),
            effective_chat=SimpleNamespace(id=chat,type=kind))) is expected
    for user in (owner_id, owner_id+1, None):
        _, menu = vitrina.ekran_start(user)
        callbacks = [button[1] for row in menu for button in row]
        assert ('orders:list' in callbacks) == (user == owner_id)
        assert not any('Открыть каталог' in text or 'Подбор из' in text
                       for row in menu for text, _ in row)
    assert 'ua_order.host' not in (ROOT/'team_bot.py').read_text()
    view = list_view(runtime.service.repository, runtime.service.catalog, menu_callback='v_start')
    assert any(data == 'orders:open:1' for row in view['buttons'] for _, data in row)
    print('CHECK PASS: owner-only client menu, CRM removed, one client delivery job')
    print('CHECK PASS: first order', first['number'], 'preserved; database unchanged')
    return runtime, owner_id, view, folder


async def publish(runtime, owner_id, view, folder):
    from telegram import Bot
    from ua_order.telegram import _markup
    state = folder/'folder_message.json'
    if state.exists():
        receipt = json.loads(state.read_text())
        if receipt.get('message_id'):
            print('PUBLISH ALREADY CONFIRMED', receipt['message_id'])
            return
        raise RuntimeError('Earlier delivery needs review; do not send a duplicate')
    async with Bot(runtime.bot_token) as bot:
        chat = await bot.get_chat(owner_id)
        assert chat.type == 'private' and chat.id == owner_id
        receipt = {'chat_id': owner_id, 'bot_id': bot.id, 'state': 'sending'}
        with state.open('x') as stream:
            json.dump(receipt, stream)
        message = await bot.send_message(chat_id=owner_id, text=view['text'],
                                         reply_markup=_markup(view['buttons']))
        receipt.update(state='sent', message_id=message.message_id, bot_username=bot.username)
        temporary = state.with_suffix('.tmp')
        temporary.write_text(json.dumps(receipt)+'\n')
        temporary.replace(state)
        print('PUBLISH PASS: folder with first order sent by', bot.username,
              'message', message.message_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    checked = verify()
    if args.publish:
        asyncio.run(publish(*checked))
