"""client_ui.py (the client bot's screens): notifications go to every owner from ua_owners, not to one chat.

register() takes a function that returns the owner chat ids (lead_bot passes it); each owner is sent to separately,
so one failed delivery does not stop the other. Nothing else changes.
"""
NAME = 'client_ui.py'
EDITS = (
    ('VLADELEC = None          # заполняется при register из lead_bot.MANAGER_CHAT_ID\n',
     'VLADELCY = None          # STAFF-FULL-ACCESS-001: функция «кто владельцы» (ua_owners), задаётся в register\n'
     '\n'
     '\n'
     'def _vladelcy():\n'
     '    return VLADELCY() if VLADELCY else []\n'),
    ('    try:\n'
     '        if VLADELEC:\n'
     '            kto = ("@%s" % user.username) if user.username else user.full_name\n'
     '            await context.bot.send_message(\n'
     '                chat_id=VLADELEC,\n'
     '                text=("\\U0001F440 <b>Смотрят машину</b>\\n%s \\u00b7 %s\\n"\n'
     '                      "Клиент: %s" % (card.get("auto_number") or "",\n'
     '                                      podpis(card), kto)),\n'
     '                parse_mode="HTML")\n'
     '    except Exception:\n'
     '        pass\n',
     '    kto = ("@%s" % user.username) if user.username else user.full_name\n'
     '    for vladelec in _vladelcy():\n'
     '        try:\n'
     '            await context.bot.send_message(\n'
     '                chat_id=vladelec,\n'
     '                text=("\\U0001F440 <b>Смотрят машину</b>\\n%s \\u00b7 %s\\n"\n'
     '                      "Клиент: %s" % (card.get("auto_number") or "",\n'
     '                                      podpis(card), kto)),\n'
     '                parse_mode="HTML")\n'
     '        except Exception:\n'
     '            pass\n'),
    ('    try:\n'
     '        if VLADELEC:\n'
     '            await context.bot.send_message(chat_id=VLADELEC, text=text,\n'
     '                                           parse_mode="HTML")\n'
     '    except Exception as e:\n'
     '        log.warning("Заявка не ушла: %s", e)\n',
     '    for vladelec in _vladelcy():\n'
     '        try:\n'
     '            await context.bot.send_message(chat_id=vladelec, text=text,\n'
     '                                           parse_mode="HTML")\n'
     '        except Exception as e:\n'
     '            log.warning("Заявка не ушла: %s", e)\n'),
    ('def register(app, vladelec=None):\n'
     '    global VLADELEC\n'
     '    VLADELEC = vladelec\n',
     'def register(app, vladelcy=None):\n'
     '    global VLADELCY\n'
     '    VLADELCY = vladelcy\n'),
)
