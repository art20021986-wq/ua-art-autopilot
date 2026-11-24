"""ai.py (BOT CRM AI drafts): the part of a draft shown to the owner is shown to everyone with full rights
(owner + managing admin, ua_full_access)."""
NAME = 'ai.py'
EDITS = (
    ('        if role == "owner":\n',
     '        import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n'
     '        if role in ua_full_access.roles():\n'),
)
