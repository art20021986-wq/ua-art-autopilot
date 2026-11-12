"""ua_lead_desk.py: the lead desk serves every owner from ua_owners (it already takes a recipients list)."""
NAME = 'ua_lead_desk.py'
EDITS = (
    ('def register(app, *, owner_id):\n',
     'def register(app, *, owners):\n'),
    ('    owner = int(owner_id)\n'
     '\n'
     '    def authorize(update):\n'
     '        # Staff only, in their private chat. Today: the owner (MANAGER_CHAT_ID); more staff later.\n'
     "        return bool(update.effective_user and update.effective_chat and update.effective_chat.type == 'private'\n"
     '                    and update.effective_user.id == owner and update.effective_chat.id == owner)\n',
     '\n'
     '    def authorize(update):\n'
     '        # Owners only (ua_owners, STAFF-FULL-ACCESS-001), each in a private chat with the bot.\n'
     "        return bool(update.effective_user and update.effective_chat and update.effective_chat.type == 'private'\n"
     '                    and update.effective_chat.id == update.effective_user.id\n'
     '                    and update.effective_user.id in owners())\n'),
    ('authorize=authorize, recipients=lambda: [owner], clock=time.time)\n',
     'authorize=authorize, recipients=owners, clock=time.time)\n'),
)
