"""CRM bot (cars_ui.py): the card language versions job (CARD-LANG-001).

One block at the end of the file that re-defines register() as the earlier blocks do (HOME-PHOTO-001,
ADS-READY-001): the previous registration first, then ua_card_lang_job.schedule. A failure only logs.
An applied block is refused.
"""
NAME = 'cars_ui.py'
MARK = '# CARD-LANG-001'
BLOCK = '''

''' + MARK + ''': card language versions, once a minute (module ua_card_lang_job).
_ua_card_lang_register = register


def register(app):
    _ua_card_lang_register(app)
    try:
        import ua_card_lang_job
        ua_card_lang_job.schedule(app)
    except Exception as e:
        log.warning('ua_card_lang_job не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text or '\ndef register(app):' not in text:
        raise ValueError('CARS_UI_FRAGMENT:' + NAME)
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
