"""vitrina.py (the client bot's screens): the owner screen («📥 Лиды», «📊 Аналитика») and every notification
to the owner go to each owner from ua_owners (vladelec.txt first, then the active CRM owners). Each send keeps its
own try/except, so one failed delivery does not stop the others. Nothing else changes.
"""
NAME = 'vitrina.py'
EDITS = (
    ('def fajl(imya, po_umolchaniyu=""):\n    try:\n        return chitat(os.path.join(BAZA_DIR, imya)).strip()\n    except Exception:\n        return po_umolchaniyu\n',
     'def fajl(imya, po_umolchaniyu=""):\n    try:\n        return chitat(os.path.join(BAZA_DIR, imya)).strip()\n    except Exception:\n        return po_umolchaniyu\n\n\ndef vladelcy():\n    """STAFF-FULL-ACCESS-001: владелец из vladelec.txt первым + все активные «Владельцы» CRM (ua_owners)."""\n    import ua_owners\n    return ua_owners.ids(fajl("vladelec.txt"))\n'),
    ('    if user_id is not None and str(user_id) == fajl("vladelec.txt"):\n',
     '    if user_id is not None and int(user_id) in vladelcy():\n'),
    ('                 [[("Написать в WhatsApp", "[URL]" % WHATSAPP)]])\n    vladelec = fajl("vladelec.txt")\n    if vladelec:\n',
     '                 [[("Написать в WhatsApp", "[URL]" % WHATSAPP)]])\n    for vladelec in vladelcy():\n'),
    ('    dannye = _podbor.pop(kto, {})\n    vladelec = fajl("vladelec.txt")\n    if vladelec:\n',
     '    dannye = _podbor.pop(kto, {})\n    for vladelec in vladelcy():\n'),
    ('                await poslat(bot, chat_id, t, k)\n                vladelec = fajl("vladelec.txt")\n                if vladelec:\n',
     '                await poslat(bot, chat_id, t, k)\n                for vladelec in vladelcy():\n'),
    ('                    await poslat(bot, chat_id, tk, kn)\n                    vladelec = fajl("vladelec.txt")\n                    if vladelec:\n',
     '                    await poslat(bot, chat_id, tk, kn)\n                    for vladelec in vladelcy():\n'),
    ('                          [("Написать в WhatsApp", "[URL]" % WHATSAPP)]])\n            vladelec = fajl("vladelec.txt")\n            if vladelec:\n',
     '                          [("Написать в WhatsApp", "[URL]" % WHATSAPP)]])\n            for vladelec in vladelcy():\n'),
    ('        imya = (soobshchenie.from_user.full_name if soobshchenie.from_user else "клиент")\n        vladelec = fajl("vladelec.txt")\n        if vladelec:\n',
     '        imya = (soobshchenie.from_user.full_name if soobshchenie.from_user else "клиент")\n        for vladelec in vladelcy():\n'),
)
