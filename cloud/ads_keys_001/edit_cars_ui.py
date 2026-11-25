"""cars_ui.py (CRM bot): connect ua_google_ads_key (ADS-KEYS-001, owner «Да» 2026-11-25).

One block at the end of the file re-defines register(), keeping the previous one, as the earlier blocks do
(TELEGRAM-KEY-BOT). A failure inside only logs and keeps the previous handlers. Refused when the block is already
there or register() is missing.
"""
import ast

NAME = 'cars_ui.py'
MARK = '# ADS-KEYS-001'
BLOCK = '''

''' + MARK + ''': the owner's Google Ads API keys message, handled before all other handlers (module ua_google_ads_key).
_ua_google_ads_key_register = register


def register(app):
    _ua_google_ads_key_register(app)
    try:
        import ua_google_ads_key
        ua_google_ads_key.register(app)
    except Exception as e:
        log.warning('ua_google_ads_key не подключён: %s', e)
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('CARS_UI_ALREADY_INSTALLED')
    tree = ast.parse(text)
    if not any(isinstance(node, ast.FunctionDef) and node.name == 'register' for node in tree.body):
        raise ValueError('CARS_UI_REGISTER_MISSING')
    return (text.rstrip('\n') + '\n' + BLOCK).encode('utf-8')
