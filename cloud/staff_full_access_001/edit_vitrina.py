"""vitrina.py (the client bot's screens): the owner screen («📥 Лиды», «📊 Аналитика») and every notification
to the owner go to each owner from ua_full_access (vladelec.txt first, then the active CRM owners). Each send keeps its
own try/except, so one failed delivery does not stop the others. Nothing else changes."""
NAME = 'vitrina.py'
EDITS = (
    ('def fajl(imya, po_umolchaniyu=""):\n    try:\n        return chitat(os.path.join(BAZA_DIR, imya)).strip()\n    except Exception:\n        return po_umolchaniyu\n',
     'def fajl(imya, po_umolchaniyu=""):\n    try:\n        return chitat(os.path.join(BAZA_DIR, imya)).strip()\n    except Exception:\n        return po_umolchaniyu\n\n\ndef vladelcy():\n    """STAFF-FULL-ACCESS-001: владелец из vladelec.txt первым + все активные «Владельцы» и «Управляющие» CRM (ua_full_access)."""\n    import ua_full_access\n    return ua_full_access.ids(fajl("vladelec.txt"))\n'),
    ('    if user_id is not None and str(user_id) == fajl("vladelec.txt"):\n',
     '    if user_id is not None and int(user_id) in vladelcy():\n'),
    ('    vladelec = fajl("vladelec.txt")\n    if vladelec:\n        try:\n            await bot.send_message(int(vladelec), dlya_vladelca, parse_mode="HTML")\n',
     '    for vladelec in vladelcy():\n        try:\n            await bot.send_message(int(vladelec), dlya_vladelca, parse_mode="HTML")\n'),
    ('    vladelec = fajl("vladelec.txt")\n    if vladelec:\n        try:\n            await bot.send_message(\n',
     '    for vladelec in vladelcy():\n        try:\n            await bot.send_message(\n'),
    ('                vladelec = fajl("vladelec.txt")\n                if vladelec:\n                    try:\n',
     '                for vladelec in vladelcy():\n                    try:\n'),
    ('                    vladelec = fajl("vladelec.txt")\n                    if vladelec:\n                        try:\n',
     '                    for vladelec in vladelcy():\n                        try:\n'),
    ('            vladelec = fajl("vladelec.txt")\n            if vladelec:\n                try:\n',
     '            for vladelec in vladelcy():\n                try:\n'),
    ('        vladelec = fajl("vladelec.txt")\n        if vladelec:\n            try:\n',
     '        for vladelec in vladelcy():\n            try:\n'),
)
