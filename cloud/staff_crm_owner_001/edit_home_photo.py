"""ua_home_photo_bot.py («Фото главной страницы»): open to everyone with full rights (owner + managing admin)."""
NAME = 'ua_home_photo_bot.py'
EDITS = (
    ("    return bool(staff) and staff['active'] and staff['role'] == db.ROLE_OWNER\n",
     "    import ua_full_access  # STAFF-FULL-ACCESS-001: the owner and the managing admin have the same rights\n    return bool(staff) and staff['active'] and staff['role'] in ua_full_access.roles()\n"),
)
