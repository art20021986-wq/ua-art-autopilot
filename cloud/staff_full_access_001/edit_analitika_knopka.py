"""analitika_knopka.py (the client bot's «📊 Аналитика»): everyone with full rights (ua_full_access: owner + managing admin) passes (vladelec.txt first)."""
NAME = 'analitika_knopka.py'
EDITS = (
    ('        return int(kto) == int(vladelec_id())\n',
     '        import ua_full_access  # STAFF-FULL-ACCESS-001: every owner (vladelec.txt first + CRM «Владельцы» и «Управляющие»)\n        return int(kto) in ua_full_access.ids(vladelec_id())\n'),
)
