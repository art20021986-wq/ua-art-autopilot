"""cars_ui.py (CRM bot): «💲 Цены Корея» in the owner's main menu (ORDER-PROCESS-001, module ua_kr_prices_bot).

One block at the end of the file re-defines with_stats_button() and register(), keeping the previous ones, as the
earlier blocks do (HOME-PHOTO-001). A failure inside only logs and keeps the previous menu and handlers. Refused when
the block is already there or the two functions are missing.
"""
import ast

NAME = 'cars_ui.py'
MARK = '# KR-PRICES-001'
BLOCK = '''

''' + MARK + ''': «💲 Цены Корея» in the owner's main menu (module ua_kr_prices_bot).
_ua_kr_prices_menu = with_stats_button


def with_stats_button(markup):
    menu = _ua_kr_prices_menu(markup)
    try:
        import ua_kr_prices_bot
        return ua_kr_prices_bot.with_button(markup, menu)
    except Exception as e:
        log.warning('ua_kr_prices_bot: кнопка не добавлена: %s', e)
        return menu


_ua_kr_prices_register = register


def register(app):
    _ua_kr_prices_register(app)
    try:
        import ua_kr_prices_bot
        ua_kr_prices_bot.register(app)
    except Exception as e:
        log.warning('ua_kr_prices_bot не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    names = {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    if not {'with_stats_button', 'register'} <= names or '\nlog = ' not in text:
        raise ValueError('CARS_UI_HOOKS_MISSING')
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
