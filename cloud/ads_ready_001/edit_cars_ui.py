"""CRM bot (cars_ui.py): «Заявки с сайта» in «Клиенты» (ADS-READY-001).

One button line in clients_screen, shown when ua_site_leads finds the order package, and one block at the
end of the file that re-defines register() as the earlier blocks do (HOME-PHOTO-001, CRM-SOLD-001):
the previous registration first, then ua_site_leads.register. A failure there only logs; the CRM keeps working.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'cars_ui.py'
MARK = '# ADS-READY-001'
BUTTON_ANCHOR = '    rows.append([InlineKeyboardButton("Заявки из бота", callback_data="crm_leads")])\n'
BUTTON = ('    ' + MARK + ': site enquiries (module ua_site_leads).\n'
          '    try:\n'
          '        import ua_site_leads\n'
          '        if ua_site_leads.available():\n'
          '            rows.append([InlineKeyboardButton(ua_site_leads.BUTTON, callback_data=ua_site_leads.CALLBACK)])\n'
          '    except Exception as e:\n'
          '        log.warning("ua_site_leads: кнопка не добавлена: %s", e)\n')
BLOCK = '''

''' + MARK + ''': «Заявки с сайта» in «Клиенты» (module ua_site_leads).
_ua_site_leads_register = register


def register(app):
    _ua_site_leads_register(app)
    try:
        import ua_site_leads
        ua_site_leads.register(app)
    except Exception as e:
        log.warning('ua_site_leads не подключён: %s', e)
'''


def build(name, source):
    text = source.decode('utf-8')
    if MARK in text or text.count(BUTTON_ANCHOR) != 1 or '\ndef register(app):' not in text:
        raise ValueError('CARS_UI_FRAGMENT:' + name)
    text = text.replace(BUTTON_ANCHOR, BUTTON + BUTTON_ANCHOR)
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
