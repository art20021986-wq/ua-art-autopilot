"""ua_pay_bot.py: the payment notice goes to everyone with full rights (owner + managing admin)."""
NAME = 'ua_pay_bot.py'
EDITS = (
    ('    chats = set(db.staff_ids_by_role(db.ROLE_OWNER))\n',
     '    import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n    chats = set(ua_full_access.ids())\n'),
)
