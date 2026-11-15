"""cars_ui.py (CRM bot): the bot profile texts in Telegram (CRM-BOT-PROFILE-001, module ua_bot_profile).

One block at the end of the file re-defines register(), keeping the previous one, as the earlier blocks do
(CRM-HOME-BUTTON-001). A failure inside only logs and keeps the previous handlers. Refused when the block is already there
or register() is missing.
"""
import ast

NAME = 'cars_ui.py'
MARK = '# CRM-BOT-PROFILE-001'
BLOCK = '''

''' + MARK + ''': description, profile line and «Меню» captions in Telegram (module ua_bot_profile).
_ua_bot_profile_register = register


def register(app):
    _ua_bot_profile_register(app)
    try:
        import ua_bot_profile
        ua_bot_profile.register(app)
    except Exception as e:
        log.warning('ua_bot_profile не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    if 'register' not in names or '\nlog = ' not in text:
        raise ValueError('CARS_UI_HOOKS_MISSING')
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
