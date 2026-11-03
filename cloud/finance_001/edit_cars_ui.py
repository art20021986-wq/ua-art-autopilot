"""CRM bot (cars_ui.py): «Кредиты и лизинг» in «Клиенты» (FINANCE-001).

One button line in clients_screen, right after «Заявки с сайта», and one block at the end of the file that
re-defines register() as the earlier blocks do: the previous registration first, then ua_finance_crm.register.
A failure there only logs; the CRM keeps working. Each original fragment must occur exactly once and an
applied fragment is refused.
"""
NAME = 'cars_ui.py'
MARK = '# FINANCE-001'
BUTTON_ANCHOR = '    rows.append([InlineKeyboardButton("Заявки из бота", callback_data="crm_leads")])\n'
BUTTON = ('    ' + MARK + ': visits to the finance partners (module ua_finance_crm).\n'
          '    try:\n'
          '        import ua_finance_crm\n'
          '        rows.append([InlineKeyboardButton(ua_finance_crm.BUTTON, callback_data=ua_finance_crm.CALLBACK)])\n'
          '    except Exception as e:\n'
          '        log.warning("ua_finance_crm: кнопка не добавлена: %s", e)\n')
BLOCK = '''

''' + MARK + ''': «Кредиты и лизинг» in «Клиенты» (module ua_finance_crm).
_ua_finance_crm_register = register


def register(app):
    _ua_finance_crm_register(app)
    try:
        import ua_finance_crm
        ua_finance_crm.register(app)
    except Exception as e:
        log.warning('ua_finance_crm не подключён: %s', e)
'''


def build(name, source):
    text = source.decode('utf-8')
    if MARK in text or text.count(BUTTON_ANCHOR) != 1 or '\ndef register(app):' not in text:
        raise ValueError('CARS_UI_FRAGMENT:' + name)
    text = text.replace(BUTTON_ANCHOR, BUTTON + BUTTON_ANCHOR)
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
