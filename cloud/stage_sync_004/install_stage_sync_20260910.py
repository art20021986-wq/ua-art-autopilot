"""Install the narrowly scoped CRM stage-to-catalog adapter after a dry run."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from datetime import datetime, timezone

ROOT = Path('/home/Carix')
MARK = '# UA-ART-STAGE-SYNC-004:START'
WRAPPER = '''
# UA-ART-STAGE-SYNC-004:START
import asyncio as _ua004_asyncio
import hashlib as _ua004_hashlib
import sqlite3 as _ua004_sqlite3
from pathlib import Path as _ua004_Path

_UA004_BASE_REGISTER = register
_UA004_RETRY_STATE = {'signature': None, 'verified_signature': None, 'failures': 0}

def _ua004_source_signature():
    with _ua004_sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True) as conn:
        rows = conn.execute('SELECT id,auto_number,status,published FROM cars ORDER BY id').fetchall()
    # Late completion of the existing page exporter permits a fresh retry.
    stamps = []
    for _, code, _, published in rows:
        if not published or not code:
            continue
        for root in ('video', 'site'):
            path = _ua004_Path('/home/Carix') / root / (code + '.html')
            stamps.append((str(path), path.stat().st_mtime_ns if path.exists() else None))
    for root in ('video', 'site'):
        for name in ('katalog.html', 'index.html'):
            path = _ua004_Path('/home/Carix') / root / name
            stamps.append((str(path), path.stat().st_mtime_ns if path.exists() else None))
    return _ua004_hashlib.sha256(repr((rows, stamps)).encode()).hexdigest()

async def _ua004_sync_current_stage(card):
    if not card.get('published'):
        return ''
    try:
        from ua_stage_catalog_sync import reconcile
        await _ua004_asyncio.to_thread(reconcile, apply=True)
        _UA004_RETRY_STATE.update(signature=None, failures=0)
        return '✅ Завершил — этап в каталоге и счётчики синхронизированы.'
    except Exception:
        log.exception('UA004: этап сохранён в CRM, синхронизация каталога ожидает повтора')
        return 'Этап сохранён в CRM. Каталог пока не обновлён; выполняется повторная проверка.'

async def _ua004_stage_reconcile_job(context):
    try:
        signature = await _ua004_asyncio.to_thread(_ua004_source_signature)
        if signature == _UA004_RETRY_STATE['verified_signature']:
            return
        if signature != _UA004_RETRY_STATE['signature']:
            _UA004_RETRY_STATE.update(signature=signature, failures=0)
        if _UA004_RETRY_STATE['failures'] >= 3:
            return
        from ua_stage_catalog_sync import reconcile
        result = await _ua004_asyncio.to_thread(reconcile, apply=True)
        _UA004_RETRY_STATE['failures'] = 0
        _UA004_RETRY_STATE['verified_signature'] = signature
        if result.get('files'):
            log.info('UA004: stage sync verified: %s', result)
    except Exception:
        _UA004_RETRY_STATE['failures'] += 1
        log.exception('UA004: stage sync attempt %d/3 failed', _UA004_RETRY_STATE['failures'])

def register(app):
    _UA004_BASE_REGISTER(app)
    if app.job_queue is None:
        log.error('UA004: existing CRM job queue unavailable; direct stage sync remains active')
        return
    if not app.job_queue.get_jobs_by_name('ua-stage-catalog-sync-004'):
        app.job_queue.run_repeating(_ua004_stage_reconcile_job, interval=15, first=3,
                                   name='ua-stage-catalog-sync-004',
                                   job_kwargs={'max_instances': 1, 'coalesce': True})
# UA-ART-STAGE-SYNC-004:END
'''

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic(path, data):
    path = Path(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def candidate(source):
    if MARK in source:
        raise RuntimeError('Already installed; refusing duplicate hook')
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
                 and node.name == 'stage_set']
    if len(functions) != 1:
        raise RuntimeError('Unexpected stage_set definition count')
    function = functions[0]
    assignments = [node for node in function.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'lines'
                           for target in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.List):
        raise RuntimeError('Unexpected stage acknowledgement layout')
    node = assignments[0]
    before = ast.get_source_segment(source, function)
    if 'saved != code' not in before or 'card = card_of(cid)' not in before:
        raise RuntimeError('Missing saved-stage verification')
    lines = source.splitlines(keepends=True)
    lines[node.end_lineno:node.end_lineno] = [
        '    if _ua004_sync_note:\n',
        '        lines.append(_ua004_sync_note)\n',
    ]
    lines[node.lineno - 1:node.lineno - 1] = [
        '    _ua004_sync_note = await _ua004_sync_current_stage(card)\n'
    ]
    result = ''.join(lines) + '\n' + WRAPPER
    ast.parse(result)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--expected-ui-sha')
    parser.add_argument('--expected-module-sha')
    args = parser.parse_args()
    target = ROOT / 'cars_ui.py'
    module = ROOT / 'ua_stage_catalog_sync.py'
    original = target.read_bytes()
    module_bytes = module.read_bytes()
    ast.parse(module_bytes.decode('utf-8'))
    proposed = candidate(original.decode('utf-8')).encode('utf-8')
    report = {'operation': 'UA-ART-STAGE-SYNC-004', 'mode': 'check',
              'ui_before_sha': sha(original), 'ui_after_sha': sha(proposed),
              'module_sha': sha(module_bytes), 'changed_runtime_files': [str(target)],
              'website_restart': False, 'database_write': False}
    if args.apply:
        if args.expected_ui_sha != sha(original) or args.expected_module_sha != sha(module_bytes):
            raise RuntimeError('Dry-run hashes do not match current files')
        backup = ROOT / 'backups' / 'stage_sync_004' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(target, backup / 'cars_ui.py')
        shutil.copy2(module, backup / 'ua_stage_catalog_sync.py')
        atomic(target, proposed)
        if target.read_bytes() != proposed:
            atomic(target, original)
            raise RuntimeError('Runtime hook readback failed; restored')
        report.update(mode='applied', backup=str(backup))
        atomic(backup / 'install_report.json', json.dumps(report, ensure_ascii=False, indent=2).encode())
    print(json.dumps(report, ensure_ascii=False))

if __name__ == '__main__':
    main()
