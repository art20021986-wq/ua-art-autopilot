"""Move the order inbox to the client bot, preserving the existing order store.

Run with python3.10 -S. The archive contains only reviewed ua_order modules.
Preview validates all source pins; install keeps private backups and uses atomic
file replacement. This script never starts/stops services or sends messages.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

ROOT = Path('/home/Carix')
BACKUP = ROOT / 'client_order_inbox_20260927'
PINS = {
    'lead_bot.py': '4759a116cb2797aeed858800e4e4535575e0954a5a1ba7e842ba4a6b6570e233',
    'team_bot.py': '09b789a06f91a9a2b50dfb591e40298e6d524a6b303de5509da4c2938a6758b9',
    'vitrina.py': '405eea111238006ae59f0b1e18c01fc7755f36a28324c1ce39cc3a3266af7a87',
    'ua_order/host.py': '469058d52dc0191d216339c2b6fd618ca5e169571e3b47acf4749ddf5547bde0',
    'ua_order/bindings.py': 'a840825abde1520e431d9da3df39f6537d96984ce9b1d86137c33447379effc9',
    'ua_order/crm.py': '096eac5064be643dbb90f337bc14d8d3f3018730b65fdb6ea5f53e8556478feb',
    'ua_order/telegram.py': 'e57e3f5d2f6182293dbdd1870889ac5ee4b6f2f5ff42863a07f11cf480d180be',
}
MARKER = '    # UA-ART-ORDER-8COUNTRIES-40-001\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Host integration changed')
    return source.replace(old, new, 1)


def patch_host(name, raw):
    source = raw.decode()
    if name == 'lead_bot.py':
        source = replace_once(source, '    _register_orders(app)\n',
                              '    _register_orders(app, owner_id=MANAGER_CHAT_ID)\n')
        changed = {'build_application'}
    elif name == 'team_bot.py':
        source = replace_once(source, MARKER +
            '    from ua_order.host import crm_folder as _order_folder\n'
            '    _order_row = _order_folder(staff, (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER))\n'
            '    if _order_row:\n'
            '        rows.insert(1, _order_row)\n', '')
        source = replace_once(source, MARKER +
            '    from ua_order.host import register_team as _register_orders\n'
            '    _register_orders(app, who=who, db=db)\n', '')
        changed = {'main_menu', 'build_application'}
    else:
        tree = ast.parse(source)
        menu = next(n for n in tree.body if getattr(n, 'name', None) == 'ekran_start')
        owner = [n for n in menu.body if isinstance(n, ast.If) and 'vladelec.txt' in ast.unparse(n.test)]
        if len(owner) != 1 or len(owner[0].body) != 1:
            raise ValueError('Owner menu changed')
        assignment = owner[0].body[0]
        if (not isinstance(assignment, ast.Assign)
                or 'v_analytics' not in ast.unparse(assignment)
                or not isinstance(assignment.value, ast.BinOp)):
            raise ValueError('Owner analytics menu changed')
        rows = assignment.value.right
        if not isinstance(rows, ast.List) or len(rows.elts) != 1:
            raise ValueError('Owner menu rows changed')
        rows.elts.insert(0, ast.parse('[(FOLDER_LABEL, "orders:list")]', mode='eval').body)
        indent = ' ' * assignment.col_offset
        lines = source.splitlines(keepends=True)
        lines[assignment.lineno-1:assignment.end_lineno] = [
            indent + 'from ua_order.crm import FOLDER_LABEL\n',
            indent + ast.unparse(assignment) + '\n',
        ]
        source = ''.join(lines)
        changed = {'ekran_start'}
    before, after = ast.parse(raw), ast.parse(source)
    unchanged = lambda tree: [ast.dump(n) for n in tree.body if getattr(n, 'name', None) not in changed]
    if unchanged(before) != unchanged(after):
        raise ValueError('Unrelated host code changed')
    compile(source, name, 'exec')
    return source.encode()


def atomic(path, raw, mode):
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name+'.')
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(archive, install):
    originals = {name: (ROOT/name).read_bytes() for name in PINS}
    if any(sha(raw) != PINS[name] for name, raw in originals.items()):
        raise ValueError('Live source changed; inspect again before installation')
    with zipfile.ZipFile(archive) as package:
        expected = {name for name in PINS if name.startswith('ua_order/')}
        if set(package.namelist()) != expected:
            raise ValueError('Unexpected deployment archive')
        candidates = {name: package.read(name) for name in expected}
    candidates.update({name: patch_host(name, raw) for name, raw in originals.items()
                       if not name.startswith('ua_order/')})
    for name, raw in candidates.items():
        ast.parse(raw, feature_version=(3, 10))
        compile(raw, name, 'exec')
    manifest = {name: {'before': PINS[name], 'after': sha(raw)} for name, raw in candidates.items()}
    print(json.dumps(manifest, indent=2))
    if not install:
        print('PREVIEW PASS: seven files, order database unchanged')
        return
    BACKUP.mkdir(mode=0o700)  # A repeated installation must be reviewed.
    for name in originals:
        target = BACKUP/name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(ROOT/name, target)
    (BACKUP/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    if any((ROOT/name).read_bytes() != raw for name, raw in originals.items()):
        raise ValueError('Concurrent source update; nothing installed')
    written = []
    try:
        for name, raw in candidates.items():
            atomic(ROOT/name, raw, (ROOT/name).stat().st_mode & 0o777)
            written.append(name)
    except BaseException:
        for name in reversed(written):
            atomic(ROOT/name, originals[name], (BACKUP/name).stat().st_mode & 0o777)
        raise
    print('INSTALL PASS: seven files, order database unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    run(args.archive, args.install)
