"""Build the self-contained, SHA-guarded PythonAnywhere installer."""
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = r'''#!/usr/bin/env python3
"""Install only the CRM folder adapter. Default: read-only preflight."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

ROOT = Path('/home/Carix')
SOURCE = ROOT / 'cars_ui.py'
CORE = ROOT / 'ua_crm_catalog_folders.py'
EXPECTED = '2c79fffff4cad8a23cb3f8992190ff03c17210655ddd374e9548d6e88563a246'
MARKER = b'# UA-ART-CRM-CATALOG-FOLDERS-001:START'
CORE_TEXT = __CORE_TEXT__
FRAGMENT = __FRAGMENT__

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic_write(path, data, mode=0o600, create_only=False):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        if create_only:
            try:
                os.link(temp, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise RuntimeError('Core changed; refusing concurrent overwrite')
        else:
            os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def preflight():
    original = SOURCE.read_bytes()
    if sha(original) != EXPECTED:
        raise RuntimeError('Source changed; refusing installation: ' + sha(original))
    if MARKER in original:
        raise RuntimeError('Adapter marker already exists')
    tree = ast.parse(original)
    names = {node.name for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not {'cars_list', 'card_kb', 'register', 'card_of', 'drop_wait',
            '_ua082_title_html', '_ua082_title_button'} <= names:
        raise RuntimeError('Required current CRM functions missing')
    core = CORE_TEXT.encode('utf-8')
    if CORE.exists() and CORE.read_bytes() != core:
        raise RuntimeError('Core path already contains different code')
    candidate = original + b'\n\n' + FRAGMENT.encode('utf-8')
    compile(core, str(CORE), 'exec')
    compile(candidate, str(SOURCE), 'exec')
    namespace = {'__name__': 'ua122_preflight'}
    exec(compile(core, str(CORE), 'exec'), namespace)
    catalog = ROOT / 'video/katalog.html'
    before = catalog.stat()
    ids = namespace['parse_catalog'](catalog.read_text(encoding='utf-8'))
    after = catalog.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError('Catalog changed during preflight')
    con = sqlite3.connect('file:' + str(ROOT / 'crm.db') + '?mode=ro', uri=True)
    try:
        con.row_factory = sqlite3.Row
        cards = [dict(row) for row in con.execute(
            'SELECT id, auto_number, published FROM cars ORDER BY id DESC')]
    finally:
        con.close()
    groups = namespace['partition_by_catalog'](cards, ids)
    report = {'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
              'core_sha256': sha(core), 'catalog_count': len(groups['catalog']),
              'unpublished_count': len(groups['unpublished']),
              'unpublished_numbers': [x['auto_number'] for x in groups['unpublished']]}
    return original, candidate, core, report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', metavar='BACKUP_DIRECTORY')
    args = parser.parse_args()
    if args.rollback:
        if args.apply:
            raise RuntimeError('Apply and rollback are mutually exclusive')
        backup = Path(args.rollback).resolve()
        base = (ROOT / 'backups/crm_catalog_folders_001').resolve()
        if backup.parent != base:
            raise RuntimeError('Unexpected backup directory')
        manifest = json.loads((backup / 'manifest.json').read_text())
        original = (backup / 'cars_ui.py').read_bytes()
        if sha(original) != EXPECTED or sha(SOURCE.read_bytes()) != manifest['candidate_sha256']:
            raise RuntimeError('Rollback hash mismatch; refusing concurrent overwrite')
        atomic_write(SOURCE, original, manifest['source_mode'])
        print(json.dumps({'status': 'ROLLED_BACK', 'source_sha256': sha(original)}))
        return
    original, candidate, core, report = preflight()
    if not args.apply:
        print(json.dumps(dict(report, status='PREFLIGHT_OK'), ensure_ascii=False))
        return
    mode = SOURCE.stat().st_mode & 0o777
    backup = ROOT / 'backups/crm_catalog_folders_001' / time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    backup.mkdir(parents=True, exist_ok=False)
    atomic_write(backup / 'cars_ui.py', original)
    atomic_write(backup / 'manifest.json', json.dumps(dict(report, source_mode=mode), indent=2).encode())
    if sha(SOURCE.read_bytes()) != EXPECTED:
        raise RuntimeError('Source changed after preflight; refusing installation')
    atomic_write(CORE, core, 0o644, create_only=True)
    if sha(SOURCE.read_bytes()) != EXPECTED:
        raise RuntimeError('Source changed before replacement; refusing installation')
    atomic_write(SOURCE, candidate, mode)
    if SOURCE.read_bytes() != candidate or CORE.read_bytes() != core:
        raise RuntimeError('Post-write verification failed')
    print(json.dumps(dict(report, status='INSTALLED', backup=str(backup)), ensure_ascii=False))

if __name__ == '__main__':
    main()
'''

if __name__ == '__main__':
    source = TEMPLATE.replace('__CORE_TEXT__', repr((HERE / 'catalog_core.py').read_text()))
    source = source.replace('__FRAGMENT__', repr((HERE / 'runtime_fragment.py').read_text()))
    target = HERE / 'crm_folders_install_20260910.py'
    target.write_text(source)
    compile(source, str(target), 'exec')
    print(target)
