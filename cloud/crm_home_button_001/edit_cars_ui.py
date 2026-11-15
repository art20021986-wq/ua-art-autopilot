"""cars_ui.py (CRM bot): the persistent «🏠 Главная» button (CRM-HOME-BUTTON-001, module ua_home_button).

One block at the end of the file re-defines register(), keeping the previous one, as the earlier blocks do
(CRM-PAYMENTS-001). A failure inside only logs and keeps the previous handlers. Refused when the block is already there
or register() is missing.
"""
import ast

NAME = 'cars_ui.py'
MARK = '# CRM-HOME-BUTTON-001'
BLOCK = '''

''' + MARK + ''': the persistent «🏠 Главная» button at the bottom of the chat (module ua_home_button).
_ua_home_button_register = register


def register(app):
    _ua_home_button_register(app)
    try:
        import ua_home_button
        ua_home_button.register(app)
    except Exception as e:
        log.warning('ua_home_button не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    if 'register' not in names or '\nlog = ' not in text:
        raise ValueError('CARS_UI_HOOKS_MISSING')
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
