"""ua_home_stage_bot.py (home page stage pick): open to everyone with full rights (owner + managing admin)."""
NAME = 'ua_home_stage_bot.py'
EDITS = (
    ("    return bool(staff) and bool(staff.get('active')) and staff.get('role') == db.ROLE_OWNER\n",
     "    import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n    return bool(staff) and bool(staff.get('active')) and staff.get('role') in ua_full_access.roles()\n"),
)
