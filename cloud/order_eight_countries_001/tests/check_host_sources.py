"""Required private-source integration checks; explicit input, no production imports.

The current host sources are intentionally not committed to the public repository.
Run with --sources /path/to/the/four/downloaded/files. Missing files fail the check.
"""
import argparse
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch as mock_patch

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationHandlerStop, CallbackQueryHandler, CommandHandler

from integrate import PINS, patch
from ua_order import host


def selected(source, names, namespace):
    tree = ast.parse(source)
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    if {node.name for node in nodes} != set(names):
        raise AssertionError('Missing host function')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<selected private host functions>', 'exec'), namespace)
    return namespace


def run(sources):
    originals, patched = {}, {}
    changed = {'lead_bot.py': {'build_application'}, 'client_ui.py': {'glavnoe_menu'},
               'team_bot.py': {'main_menu', 'build_application'}}
    protected = 0
    for name in PINS:
        raw = (Path(sources)/name).read_bytes()
        originals[name], patched[name] = raw.decode(), patch(name, raw).decode()
        before, after = ast.parse(raw), ast.parse(patched[name])
        if name in changed:
            a = [ast.dump(node) for node in before.body if getattr(node, 'name', None) not in changed[name]]
            b = [ast.dump(node) for node in after.body if getattr(node, 'name', None) not in changed[name]]
            assert a == b, 'Unrelated host code changed: ' + name
            protected += len(a)
        else:
            assert [ast.dump(n) for n in after.body[:len(before.body)]] == [ast.dump(n) for n in before.body]
        try:
            patch(name, raw+b'\n')
        except ValueError:
            pass
        else:
            raise AssertionError('Changed source was accepted')

    lead = next(n for n in ast.parse(patched['lead_bot.py']).body if getattr(n, 'name', None) == 'build_application')
    assert isinstance(lead.body[-1], ast.Return)
    assert ast.unparse(lead.body[-2]) == '_register_orders(app, owner_id=MANAGER_CHAT_ID)'
    assert patched['lead_bot.py'].index('app.handlers.clear()') < patched['lead_bot.py'].index('_register_orders(app, owner_id=MANAGER_CHAT_ID)')

    # Execute the actual unchanged registration function with inert host screen
    # callbacks. No module-level host code, tokens, files or network are loaded.
    client_namespace = {'CommandHandler': CommandHandler, 'CallbackQueryHandler': CallbackQueryHandler,
                        'ApplicationHandlerStop': ApplicationHandlerStop,
                        '_v168_client_guard_start': lambda _: None,
                        'log': SimpleNamespace(info=lambda *_: None)}
    async def screen(update, context):
        raise ApplicationHandlerStop
    for name in ('start_screen','catalog','terms_screen','menu_cb','car_screen','bron','vopros',
                 'order_start','order_answer','contacts_screen'):
        client_namespace[name] = screen
    selected(patched['client_ui.py'], {'register'}, client_namespace)
    registrations = []
    client_namespace['register'](SimpleNamespace(add_handler=lambda handler, group: registrations.append((handler, group))), None)
    assert registrations and {group for _, group in registrations} == {-1}
    assert any(isinstance(handler, CallbackQueryHandler) and handler.pattern.pattern == '^c_order$'
               for handler, _ in registrations)

    assert ast.dump(ast.parse(originals['team_bot.py'])) == ast.dump(ast.parse(patched['team_bot.py']))

    return {'status': 'PASS', 'files': 4, 'unrelated_top_level_nodes_unchanged': protected,
            'current_client_registration_group': -1, 'crm_unchanged': True,
            'source_drift_rejected': True, 'private_sources_published': False,
            'live_module_imports': False, 'real_messages_sent': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.sources), indent=2))
