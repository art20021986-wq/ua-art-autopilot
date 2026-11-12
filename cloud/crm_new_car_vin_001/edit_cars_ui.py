"""cars_ui.py (CRM bot): «Создать новое объявление» at the top of «🚗 Автомобили» (NEW-CAR-VIN-001, module
ua_new_car_bot).

Two exact edits: one line in the folder screen of «Автомобили» (UA-ART-CRM-CATALOG-FOLDERS-001) puts the button row
above the folders, and one block at the end of the file defines that row and re-defines register(), keeping the
previous one, as the earlier blocks do (KR-PRICES-001). A failure inside only logs and keeps the screen and handlers.
Refused when already applied, or when the anchor is not there exactly once.
"""
NAME = 'cars_ui.py'
MARK = '# NEW-CAR-VIN-001'
ANCHOR = ("            rows.append([InlineKeyboardButton('← Назад', callback_data='menu')])\n"
          "            await q.message.reply_text('Автомобили\\nВыберите папку.',\n")
LINE = '            rows[:0] = _ua_new_car_rows()  ' + MARK + '\n'
BLOCK = '''

''' + MARK + ''': «Создать новое объявление» at the top of «Автомобили» (module ua_new_car_bot).
def _ua_new_car_rows():
    try:
        import ua_new_car_bot
        return ua_new_car_bot.rows()
    except Exception as e:
        log.warning('ua_new_car_bot: кнопка не добавлена: %s', e)
        return []


_ua_new_car_register = register


def register(app):
    _ua_new_car_register(app)
    try:
        import ua_new_car_bot
        ua_new_car_bot.register(app)
    except Exception as e:
        log.warning('ua_new_car_bot не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    if text.count(ANCHOR) != 1:
        raise ValueError('CARS_UI_ANCHOR')
    if '\ndef register(app):' not in text or '\nlog = ' not in text:
        raise ValueError('CARS_UI_HOOKS_MISSING')
    text = text.replace(ANCHOR, LINE + ANCHOR)
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
