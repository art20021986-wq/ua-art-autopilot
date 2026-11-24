"""analitika_knopka.py (the client bot's «📊 Аналитика»): every owner from ua_owners passes (vladelec.txt first)."""
NAME = 'analitika_knopka.py'
EDITS = (
    ('        return int(kto) == int(vladelec_id())\n',
     '        import ua_owners  # STAFF-FULL-ACCESS-001: every owner (vladelec.txt first + CRM «Владельцы»)\n        return int(kto) in ua_owners.ids(vladelec_id())\n'),
)
