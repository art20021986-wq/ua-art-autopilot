"""team_bot.py (BOT CRM): owner-only actions and owner notifications for everyone with full rights (ua_full_access:
owner + managing admin). The roles stay as they are; nothing else changes."""
NAME = 'team_bot.py'
EDITS = (
    ('import db\nimport ai\n',
     'import db\nimport ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\nimport ai\n'),
    ('    return staff and staff["role"] == db.ROLE_OWNER\n',
     '    return staff and staff["role"] in ua_full_access.roles()\n'),
    ('    # Сообщаем владельцу, что человек вошёл\n    for oid in db.staff_ids_by_role(db.ROLE_OWNER):\n',
     '    # Сообщаем владельцу, что человек вошёл\n    for oid in ua_full_access.ids():\n'),
    ('        # Некому передавать — предупреждаем владельца, чтобы запись не зависла\n        for oid in db.staff_ids_by_role(db.ROLE_OWNER):\n',
     '        # Некому передавать — предупреждаем владельца, чтобы запись не зависла\n        for oid in ua_full_access.ids():\n'),
    ('    db.set_inbox_status(inbox_id, db.ST_NEED_INFO, staff["user_id"])\n    for oid in db.staff_ids_by_role(db.ROLE_OWNER):\n',
     '    db.set_inbox_status(inbox_id, db.ST_NEED_INFO, staff["user_id"])\n    for oid in ua_full_access.ids():\n'),
    ('    ))\n    for uid in db.staff_ids_by_role(db.ROLE_OWNER):\n',
     '    ))\n    for uid in ua_full_access.ids():\n'),
    ('    try:\n        ids = db.staff_ids_by_role(db.ROLE_OWNER)\n',
     '    try:\n        ids = ua_full_access.ids()\n'),
)
