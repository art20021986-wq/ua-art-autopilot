"""karta_klienta.py: its once-a-day warning goes to everyone with full rights (ua_full_access), each with its own once-a-day record
(the configured owner keeps the old one). If ua_full_access cannot be loaded, vladelec.txt alone, as before."""
NAME = 'karta_klienta.py'
EDITS = (
    ('def _pismo(text, kluch):\n'
     '    """Пишем владельцу не чаще раза в сутки на один и тот же повод."""\n',
     'def _pismo(text, kluch):\n'
     '    """STAFF-FULL-ACCESS-001: то же письмо каждому владельцу (vladelec.txt первым + «Владельцы» и «Управляющие» CRM)."""\n'
     '    pervyy = _chitat("vladelec.txt")\n'
     '    try:\n'
     '        import ua_full_access\n'
     '        vladelcy = ua_full_access.ids(pervyy)\n'
     '    except Exception as e:\n'
     '        _log("владельцы: " + str(e))\n'
     '        vladelcy = [pervyy] if pervyy else []\n'
     '    for nomer, komu in enumerate(vladelcy):\n'
     '        _pismo_odnomu(text, kluch if nomer == 0 else "%s:%s" % (kluch, komu), komu)\n'
     '\n'
     '\n'
     'def _pismo_odnomu(text, kluch, komu):\n'
     '    """Пишем владельцу не чаще раза в сутки на один и тот же повод."""\n'),
    ('        komu = _chitat("vladelec.txt")\n'
     '        if not token or not komu:\n',
     '        if not token or not komu:\n'),
)
