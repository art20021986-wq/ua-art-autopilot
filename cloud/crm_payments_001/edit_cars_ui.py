"""cars_ui.py (CRM bot): «💳 Платежи» in the order card (CRM-PAYMENTS-001, module ua_pay_bot).

One block at the end of the file re-defines register(), keeping the previous one, as the earlier blocks do
(KR-PRICES-001). A failure inside only logs and keeps the previous handlers. Refused when the block is already there
or register() is missing.
"""
import ast

NAME = 'cars_ui.py'
MARK = '# CRM-PAYMENTS-001'
BLOCK = '''

''' + MARK + ''': «💳 Платежи» in the order card of «👤 Клиенты» (module ua_pay_bot).
_ua_pay_register = register


def register(app):
    _ua_pay_register(app)
    try:
        import ua_pay_bot
        ua_pay_bot.register(app)
    except Exception as e:
        log.warning('ua_pay_bot не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    if 'register' not in names or '\nlog = ' not in text:
        raise ValueError('CARS_UI_HOOKS_MISSING')
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
