"""bezopasnost.py (the CRM guard): its owner alerts go to every owner and every owner may use /dostup and /kopiya.

Nothing of the guard is switched off: the access list, invite codes and the database copy target stay as they are;
the one-time /dostup code goes to the owner who asked for it. If ua_owners cannot be loaded, vladelec.txt alone.
"""
NAME = 'bezopasnost.py'
EDITS = (
    ('def _vladelec():\n'
     '    z = _fayl("vladelec.txt")\n'
     '    return z.split()[0] if z else ""\n',
     'def _vladelec():\n'
     '    z = _fayl("vladelec.txt")\n'
     '    return z.split()[0] if z else ""\n'
     '\n'
     '\n'
     'def _vladelcy():\n'
     '    # STAFF-FULL-ACCESS-001: vladelec.txt pervym + vse aktivnye «Vladelcy» CRM (ua_owners)\n'
     '    try:\n'
     '        import ua_owners\n'
     '        return [str(i) for i in ua_owners.ids(_vladelec())]\n'
     '    except Exception as e:\n'
     '        _log("vladelcy: " + repr(e))\n'
     '        return [_vladelec()] if _vladelec() else []\n'
     '\n'
     '\n'
     'def _vsem_vladelcam(tekst):\n'
     '    for v in _vladelcy():\n'
     '        _soobshenie(v, tekst)\n'),
    ('        _soobshenie(_vladelec(), "В рабочий бот вошёл новый человек: "\n',
     '        _vsem_vladelcam("В рабочий бот вошёл новый человек: "\n'),
    ('        _soobshenie(_vladelec(), "Чужой в рабочем боте: " + imya + " (" + str(kto)\n',
     '        _vsem_vladelcam("Чужой в рабочем боте: " + imya + " (" + str(kto)\n'),
    ('                    _soobshenie(_vladelec(),\n'
     '                                "Из открытой папки убран файл с исходниками: " + imya)\n',
     '                    _vsem_vladelcam(\n'
     '                                "Из открытой папки убран файл с исходниками: " + imya)\n'),
    ('                if tekst.startswith("/dostup") and str(\n'
     '                        getattr(update.effective_user, "id", "")) == str(_vladelec()):\n'
     '                    kod = novyy_kod()\n'
     '                    _soobshenie(_vladelec(),\n',
     '                if tekst.startswith("/dostup") and str(\n'
     '                        getattr(update.effective_user, "id", "")) in _vladelcy():\n'
     '                    kod = novyy_kod()\n'
     '                    _soobshenie(update.effective_user.id,\n'),
    ('                if tekst.startswith("/kopiya") and str(\n'
     '                        getattr(update.effective_user, "id", "")) == str(_vladelec()):\n',
     '                if tekst.startswith("/kopiya") and str(\n'
     '                        getattr(update.effective_user, "id", "")) in _vladelcy():\n'),
)
