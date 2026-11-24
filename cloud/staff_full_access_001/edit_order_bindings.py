"""ua_order/bindings.py: the owner inbox serves every owner from ua_owners, each in a private chat with the bot.

Every owner gets each order once (the per-recipient record already exists); a failed send retries only those not
yet sent. Nothing else changes.
"""
NAME = 'ua_order/bindings.py'
EDITS = (
    ('def owner_inbox(app, runtime, *, owner_id):\n'
     '    owner_id = int(owner_id)\n'
     '    if owner_id <= 0:\n'
     "        raise ValueError('A private owner chat is required for order delivery')\n",
     'def owner_inbox(app, runtime, *, owners):\n'
     '    # STAFF-FULL-ACCESS-001: owners() returns the owner chat ids (ua_owners).\n'
     '    if not owners():\n'
     "        raise ValueError('A private owner chat is required for order delivery')\n"),
    ("                    and update.effective_chat.type == 'private'\n"
     '                    and update.effective_user.id == owner_id\n'
     '                    and update.effective_chat.id == owner_id)\n',
     "                    and update.effective_chat.type == 'private'\n"
     '                    and update.effective_chat.id == update.effective_user.id\n'
     '                    and update.effective_user.id in owners())\n'),
    ('        if owner_id not in sent:\n'
     "            parts = view.get('parts', [view['text']])\n"
     '            for index, part in enumerate(parts):\n'
     '                await app.bot.send_message(\n'
     "                    chat_id=owner_id, text=part, parse_mode='HTML',\n"
     '                    reply_markup=_markup([[(\'Открыть лид\', f\'ld:o:or:{row["id"]}\')]]) if index == len(parts)-1 else None,\n'
     '                )\n'
     '            await asyncio.to_thread(repository.notification_recipient_sent, request_id, owner_id)\n',
     '        for owner_id in owners():\n'
     '            if owner_id in sent:\n'
     '                continue\n'
     "            parts = view.get('parts', [view['text']])\n"
     '            for index, part in enumerate(parts):\n'
     '                await app.bot.send_message(\n'
     "                    chat_id=owner_id, text=part, parse_mode='HTML',\n"
     '                    reply_markup=_markup([[(\'Открыть лид\', f\'ld:o:or:{row["id"]}\')]]) if index == len(parts)-1 else None,\n'
     '                )\n'
     '            await asyncio.to_thread(repository.notification_recipient_sent, request_id, owner_id)\n'),
)
