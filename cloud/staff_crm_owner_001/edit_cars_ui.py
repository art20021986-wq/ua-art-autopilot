"""cars_ui.py (BOT CRM cars): its owner check passes everyone with full rights (owner + managing admin)."""
NAME = 'cars_ui.py'
EDITS = (
    ('    return bool(staff) and staff.get("role") == db.ROLE_OWNER\n',
     '    import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n    return bool(staff) and staff.get("role") in ua_full_access.roles()\n'),
)
