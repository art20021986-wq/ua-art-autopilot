"""analitika_bot.py (the client bot's /analitika): everyone with full rights (ua_full_access: owner + managing admin) passes (VLADELEC first)."""
NAME = 'analitika_bot.py'
EDITS = (
    ('        return update.effective_user and update.effective_user.id in VLADELEC\n',
     '        import ua_full_access  # STAFF-FULL-ACCESS-001: every owner (VLADELEC first + CRM «Владельцы» и «Управляющие»)\n        return update.effective_user and update.effective_user.id in ua_full_access.ids(VLADELEC[0])\n'),
)
