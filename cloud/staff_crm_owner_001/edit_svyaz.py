"""svyaz.py: its warnings go to everyone with full rights (ua_full_access: owner + managing admin), each with its own interval record (the configured owner
keeps the old one). If ua_full_access cannot be loaded, vladelec.txt alone, as before."""
NAME = 'svyaz.py'
EDITS = (
    ('def _vladelcu(tekst, povod, chasov=6):\n'
     '    if not _pora(povod, chasov):\n',
     'def _vladelcu(tekst, povod, chasov=6):\n'
     '    # STAFF-FULL-ACCESS-001: kazhdomu vladelcu (vladelec.txt pervym + «Vladelcy» CRM)\n'
     '    pervyy = _fayl("vladelec.txt")\n'
     '    try:\n'
     '        import ua_full_access\n'
     '        vladelcy = ua_full_access.ids(pervyy)\n'
     '    except Exception as e:\n'
     '        _log("vladelcy: " + repr(e))\n'
     '        vladelcy = [pervyy] if pervyy else []\n'
     '    for nomer, kto in enumerate(vladelcy):\n'
     '        _vladelcu_odnomu(tekst, povod if nomer == 0 else "%s:%s" % (povod, kto), chasov, kto)\n'
     '\n'
     '\n'
     'def _vladelcu_odnomu(tekst, povod, chasov, kto):\n'
     '    if not _pora(povod, chasov):\n'),
    ('    kto = _fayl("vladelec.txt")\n'
     '    if not token or not kto:\n',
     '    if not token or not kto:\n'),
)
