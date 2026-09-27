"""Build private, exact-source host patches locally. Never installs or reloads."""
import argparse
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path

PINS = {
    'lead_bot.py': '27270e38f1b7ed913140127231149b6d862876f3b3a02a58c4a852b40ce8a3f8',
    'client_ui.py': '8e3a61fdc89f78623725b6e639277ce0bfbf8993d052e09806f0837da8fd1363',
    'team_bot.py': 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af',
    'www_uaart_com_ua_wsgi.py': 'fc2d1d5b58b34d2dae2d2faf011a9cc7cf45d7940df0f58cc25bbaf3e7293c25',
}
MARKER = '# UA-ART-ORDER-8COUNTRIES-40-001'


def function(source, name):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1:
        raise ValueError('Expected one host function: ' + name)
    return nodes[0]


def before_return(source, name, addition):
    node = function(source, name)
    if not isinstance(node.body[-1], ast.Return):
        raise ValueError('Host return structure changed: ' + name)
    lines = source.splitlines(keepends=True)
    lines.insert(node.body[-1].lineno - 1, addition)
    return ''.join(lines)


def patch(name, raw):
    if hashlib.sha256(raw).hexdigest() != PINS[name]:
        raise ValueError('Current source differs from audited source: ' + name)
    source = raw.decode('utf-8')
    if MARKER in source:
        raise ValueError('Order integration is already present')
    if name == 'lead_bot.py':
        source = before_return(source, 'build_application',
            f'    {MARKER}\n'
            '    from ua_order.host import register_customer as _register_orders\n'
            '    _register_orders(app)\n')
    elif name == 'client_ui.py':
        node = function(source, 'glavnoe_menu')
        lines = source.splitlines(keepends=True)
        lines.insert(node.body[0].lineno - 1,
            f'    {MARKER}\n'
            '    from ua_order.host import customer_label as _order_label\n')
        source = ''.join(lines)
        old = 'InlineKeyboardButton("Подобрать под заказ из Кореи", callback_data="c_order")'
        if source.count(old) != 1:
            raise ValueError('Customer order label changed')
        source = source.replace(old, 'InlineKeyboardButton(_order_label(), callback_data="c_order")')
    elif name == 'team_bot.py':
        source = before_return(source, 'main_menu',
            f'    {MARKER}\n'
            '    from ua_order.host import crm_folder as _order_folder\n'
            '    _order_row = _order_folder(staff, (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER))\n'
            '    if _order_row:\n'
            '        rows.insert(1, _order_row)\n')
        source = before_return(source, 'build_application',
            f'    {MARKER}\n'
            '    from ua_order.host import register_team as _register_orders\n'
            '    _register_orders(app, who=who, db=db)\n')
    else:
        # Must remain outside analytics, bridge, SEO and public-price wrappers.
        source += (f'\n{MARKER}\n'
                   'from ua_order.host import mount_application as _mount_orders\n'
                   'application = _mount_orders(application)\n')
    ast.parse(source, feature_version=(3, 10))
    return source.encode('utf-8')


def build(sources, output):
    sources, output = Path(sources).resolve(), Path(output).resolve()
    if output.exists() or output == Path('/home/Carix') or Path('/home/Carix') in output.parents:
        raise ValueError('Use a fresh local directory; live installation is not supported')
    # Validate all four files before writing any output.
    originals = {name: (sources / name).read_bytes() for name in PINS}
    patched = {name: patch(name, raw) for name, raw in originals.items()}
    output.mkdir(parents=True, mode=0o700)
    manifest = {'specification': 'UA-ART-ORDER-8COUNTRIES-40-001 v1.1',
                'production_write': False, 'gate_b': 'NOT_PASSED', 'files': {}}
    diff = []
    for name, raw in patched.items():
        file = output / name
        file.write_bytes(raw)
        os.chmod(file, 0o600)
        manifest['files'][name] = {
            'before_sha256': PINS[name], 'after_sha256': hashlib.sha256(raw).hexdigest(),
        }
        diff.extend(difflib.unified_diff(originals[name].decode().splitlines(True),
                                       raw.decode().splitlines(True), fromfile=name, tofile=name))
    (output / 'integration.patch').write_text(''.join(diff))
    os.chmod(output / 'integration.patch', 0o600)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.sources, args.output), indent=2))
