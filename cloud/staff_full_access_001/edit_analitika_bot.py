"""analitika_bot.py (the client bot's /analitika): every owner from ua_owners passes (VLADELEC first)."""
NAME = 'analitika_bot.py'
EDITS = (
    ('        return update.effective_user and update.effective_user.id in VLADELEC\n',
     '        import ua_owners  # STAFF-FULL-ACCESS-001: every owner (VLADELEC first + CRM «Владельцы»)\n        return update.effective_user and update.effective_user.id in ua_owners.ids(VLADELEC[0])\n'),
)
