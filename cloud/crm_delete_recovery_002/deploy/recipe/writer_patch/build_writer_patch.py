"""Offline-only hash-bound transformation; never import target private sources.

Input is the exact reviewed live source. Return candidate text; the installer
owns backup, compilation, conflict checks, production writes and restarts.
"""
import ast
import hashlib

BASELINES = {
    'cars_ui.py': 'd9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837',
    'publikaciya.py': '296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72',
    'publish_transaction_guard.py': 'b1e89bfcbe4af4890d1023293cb8290f34b6c59673b7a8e692ab64928f640159',
    'stranica.py': 'cdb532f36e6e8fd17c7f933ad347a8bb0bcd8c00644d9c8ea7d9e3ddbb6ae687',
    'ua_spec84_runtime.py': '938b8dd68f6eafa8b3022ef1dd1f03aa44fd27ec9979bef0819c36941fe022be',
    'ua_spec_permanent.py': '2ede3b57f0295cb32aabbc7d4f6e622e3fccf48710c46276d6925252a1cee65d',
    'yadro.py': '1c6bddccec30198179f9a179aa67ac8f2e40da1a794c87f2342150eb5d2ec793',
    'kadry_diagnostiki.py': '696a3b73af8e47a79d3352c6ead3a2364dd357b140a9cf7320fc4cad3d3106c0',
}
MARKER = '# UA-ART-CRM-DELETE-RECOVERY-002:WRITERS'


def _replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('EXACT_SOURCE_ANCHOR_REQUIRED')
    return source.replace(old, new, 1)


def _append(source, extra):
    tree = ast.parse(source)
    # Direct script entrypoint must run only after our wrappers are installed.
    guards = [n for n in tree.body if isinstance(n, ast.If) and
              isinstance(n.test, ast.Compare) and
              any(isinstance(x, ast.Constant) and x.value == '__main__'
                  for x in ast.walk(n.test))]
    if len(guards) > 1:
        raise ValueError('AMBIGUOUS_SCRIPT_ENTRYPOINT')
    lines = source.splitlines(keepends=True)
    if guards:
        i = guards[0].lineno - 1
        return ''.join(lines[:i]) + '\n' + extra + '\n' + ''.join(lines[i:])
    return source.rstrip() + '\n\n' + extra + '\n'


def _replace_function(source, name, replacement):
    defs = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(defs) != 1:
        raise ValueError('SINGLE_FUNCTION_REQUIRED:' + name)
    node = defs[0]
    start = min([node.lineno] + [x.lineno for x in node.decorator_list]) - 1
    lines = source.splitlines(keepends=True)
    return ''.join(lines[:start]) + replacement.strip() + '\n' + ''.join(lines[node.end_lineno:])


COMMON = '''
from publication_fence import publication_fence as _delete_publication_fence
from ua_delete_public_guard import guarded_write as _delete_guarded_write
from ua_delete_public_guard import check_locked as _delete_check_locked
from ua_delete_public_guard import require_active as _delete_require_active
'''

MEDIA_CLEANUP = '''
def _delete_replace_diagnostic_media(source, target):
    # Download bytes may be prepared outside this short commit lease. The
    # existing destination and relocated source are retained after retirement.
    from pathlib import Path as _delete_Path
    from ua_delete_public_guard import require_current, DeletedPublicationRefused
    source, target = _delete_Path(source), _delete_Path(target)
    root = _delete_Path(KUDA)
    left, right = source.relative_to(root), target.relative_to(root)
    if (len(left.parts) != 2 or len(right.parts) not in (2, 3)
            or left.parts[0] != right.parts[0]
            or (len(right.parts) == 3 and right.parts[1] != 'neverno')
            or target.suffix not in ('.jpg', '.mp4')):
        raise RuntimeError('DIAGNOSTIC_REPLACE_PATH_CHANGED')
    with _delete_publication_fence(timeout=90.0):
        try:
            require_current(right.parts[0])
        except DeletedPublicationRefused:
            return False
        if (source.resolve(strict=False) != source or target.resolve(strict=False) != target
                or source.is_symlink() or target.is_symlink()):
            raise RuntimeError('DIAGNOSTIC_REPLACE_PATH_CHANGED')
        os.replace(source, target)
        return True


def _delete_cleanup_diagnostic_media(path, code, car_id):
    # Only this existing cleanup unlink is fenced. Downloads and network
    # retries retain their normal worker behavior outside the publication lease.
    from pathlib import Path as _delete_Path
    from ua_delete_public_guard import require_current, DeletedPublicationRefused
    with _delete_publication_fence(timeout=90.0):
        try:
            require_current(code, car_id=car_id)
        except DeletedPublicationRefused:
            return False
        destination = _delete_Path(path)
        expected_parent = _delete_Path(KUDA) / code
        if (destination.parent != expected_parent
                or expected_parent.resolve(strict=True) != expected_parent
                or destination.is_symlink()
                or destination.suffix not in ('.jpg', '.mp4')):
            raise RuntimeError('DIAGNOSTIC_CLEANUP_PATH_CHANGED')
        os.remove(path)
        return True
'''


def _atomic_wrapper(name):
    return '''
_delete_original_{name} = {name}
def {name}(path, payload, *args, **kwargs):
    with _delete_guarded_write(path, payload):
        return _delete_original_{name}(path, payload, *args, **kwargs)
'''.format(name=name)


DIAG = '''
_delete_original_ensure_diag = _ua068_ensure_diag_files
def _ua068_ensure_diag_files(code, row):
    with _delete_publication_fence(timeout=90.0):
        _delete_require_active(code, car_id=row.get('id'), vin=row.get('vin'))
        return _delete_original_ensure_diag(code, row)
'''

STRANICA = '''
_delete_original_zapisat = zapisat
def zapisat(stem, payload, *args, **kwargs):
    # The audited writer expands stems to both roots and matching aliases.
    import pathlib as _delete_pathlib
    with _delete_publication_fence(timeout=90.0):
        for folder in (PAPKA_VID, PAPKA_SITE):
            root = _delete_pathlib.Path(folder)
            targets = {root / (str(stem) + '.html')}
            targets.update(root.glob(str(stem) + '-*.html'))
            for path in targets:
                _delete_check_locked(path, payload)
        return _delete_original_zapisat(stem, payload, *args, **kwargs)
'''

PUBLISHER = '''
_delete_original_publish = opublikovat
def opublikovat(code, proba=False):
    with _delete_publication_fence(timeout=90.0):
        _delete_require_active(code)
        return _delete_original_publish(code, proba=proba)

_delete_original_rollback = _otkat
def _otkat(backup, targets):
    # Validate the entire restore before legacy code changes its first page.
    import pathlib as _delete_pathlib
    with _delete_publication_fence(timeout=90.0):
        for target in targets:
            stored = os.path.join(backup, target.replace(BASE + '/', '').replace('/', '__'))
            if os.path.exists(stored):
                _delete_check_locked(target, _delete_pathlib.Path(stored).read_bytes())
        return _delete_original_rollback(backup, targets)
'''

URGENT = '''
_delete_original_urgent_publish = ua0009_urgent_publish
def ua0009_urgent_publish():
    with _delete_publication_fence(timeout=90.0):
        _delete_require_active('UA-0009')
        return _delete_original_urgent_publish()


def _delete_restore_urgent_backup(target, stored, expected_written):
    from pathlib import Path as _delete_Path
    before = _delete_Path(stored).read_bytes()
    # Check retired identities even when the previous bytes appear unchanged.
    with _delete_guarded_write(target, before):
        destination = _delete_Path(target)
        current = destination.read_bytes()
        if current == before:
            return
        expected = expected_written.get(target)
        if expected is None or current != expected:
            raise RuntimeError('URGENT_ROLLBACK_CURRENT_BYTES_CHANGED')
        shutil.copy2(stored, target)
        if destination.read_bytes() != before:
            raise RuntimeError('URGENT_ROLLBACK_READBACK_FAILED')
'''


SNAPSHOT = '''
_delete_original_snapshot_restore = Snapshot.restore
def _delete_snapshot_restore(self):
    # No partial file removal before an invalid restored payload is rejected.
    with _delete_publication_fence(timeout=90.0):
        manifest = json.loads((self.root / 'manifest.json').read_text(encoding='utf-8'))
        for path in sorted(self.present):
            item = manifest[str(path)]
            stored = (self.root / str(item['stored_relative'])).resolve()
            if self.root.resolve() not in stored.parents or not stored.is_file():
                raise PublishError('DELETE_RESTORE_SCOPE')
            data = _ua099_gzip.decompress(_read(stored))
            if _sha(data) != item['sha256']:
                raise PublishError('DELETE_RESTORE_HASH')
            _delete_check_locked(path, data)
        return _delete_original_snapshot_restore(self)
Snapshot.restore = _delete_snapshot_restore
'''

SPEC_LOCK = '''
_delete_original_spec_lock = write_lock
@contextmanager
def write_lock(root='/home/Carix', timeout=30.0):
    from publication_fence import publication_fence
    # Runtime must be patched simultaneously: its raw publication flock is
    # replaced by the same reentrant registry before this module is restarted.
    with publication_fence(timeout=timeout):
        with _delete_original_spec_lock(root, timeout=timeout):
            yield
'''

SPEC_RUNTIME_GUARD = '''
@contextlib.contextmanager
def _writer_guard(uid):
    from publication_fence import publication_fence, FenceTimeout
    from ua_delete_public_guard import require_active, DeletedPublicationRefused
    deadline = time.monotonic() + 2.0
    while True:
        leases = contextlib.ExitStack()
        try:
            if (ROOT / '.uaart_writer_coordination' / 'active-intent.json').exists():
                raise RuntimeDeferred('COORDINATED_WRITER_ACTIVE')
            # Preserve reviewed global order: repair, stage guard, dedup,
            # publication, CRM. Reordering publication ahead of repair would
            # invert the order still used by other legacy writer processes.
            for name in WRITER_LOCKS:
                path = ROOT / name
                if path.is_symlink() or not path.is_file():
                    raise RuntimeDeferred('EXISTING_WRITER_LOCK_MISSING')
                if path == ROOT / '.ua_art_publish_transaction.lock':
                    # Same inode, shared registry, nonblocking per attempt.
                    leases.enter_context(publication_fence(timeout=0.0))
                    continue
                fd = os.open(str(path), os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
                leases.callback(os.close, fd)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                leases.callback(fcntl.flock, fd, fcntl.LOCK_UN)
        except (BlockingIOError, FenceTimeout):
            leases.close()
            if time.monotonic() >= deadline:
                raise RuntimeDeferred('WRITER_BUSY')
            _stop.wait(0.05)
            continue
        except BaseException:
            leases.close()
            raise
        break
    try:
        if (ROOT / '.uaart_writer_coordination' / 'active-intent.json').exists():
            raise RuntimeDeferred('COORDINATED_WRITER_ACTIVE')
        try:
            require_active(uid)
        except DeletedPublicationRefused as exc:
            raise RuntimeDeferred(str(exc)) from exc
        import ua_spec_permanent
        with ua_spec_permanent.write_lock(ROOT, timeout=2.0):
            yield
    finally:
        leases.close()
'''


def transform(name, source):
    raw = source.encode('utf-8') if isinstance(source, str) else source
    if name not in BASELINES or hashlib.sha256(raw).hexdigest() != BASELINES[name]:
        raise ValueError('REVIEWED_LIVE_SOURCE_HASH_REQUIRED:' + name)
    source = raw.decode('utf-8')
    if MARKER in source:
        raise ValueError('ALREADY_PATCHED')
    extra = MARKER + '\n' + COMMON
    if name == 'yadro.py':
        extra += _atomic_wrapper('zapisat_atomarno') + DIAG
    elif name == 'stranica.py':
        source = _replace_once(source,
            '                with io.open(_put, "w", encoding="utf-8") as _f:\n',
            '                _delete_check_locked(_put, _tekst)\n                with io.open(_put, "w", encoding="utf-8") as _f:\n')
        extra += STRANICA + DIAG
    elif name == 'publikaciya.py':
        source = _replace_once(source,
            '    rezervy = {}\n',
            '    rezervy = {}\n    _delete_urgent_written = {}\n')
        source = _replace_once(source,
            '            _zapisat_atomarno(cel, katalog)\n            zapisannye.append(cel)\n',
            '            _zapisat_atomarno(cel, katalog)\n'
            '            from pathlib import Path as _delete_Path\n'
            '            _delete_urgent_written[cel] = _delete_Path(cel).read_bytes()\n'
            '            zapisannye.append(cel)\n')
        source = _replace_once(source,
            '        for cel, kopiya in rezervy.items():\n'
            '            try:\n'
            '                shutil.copy2(kopiya, cel)\n'
            '            except Exception:\n'
            '                pass\n',
            '        _delete_restore_failed = False\n'
            '        for cel, kopiya in rezervy.items():\n'
            '            try:\n'
            '                _delete_restore_urgent_backup(cel, kopiya, _delete_urgent_written)\n'
            '            except Exception:\n'
            '                _delete_restore_failed = True\n'
            '        if _delete_restore_failed:\n'
            '            return False, "Публикация не завершена; восстановление каталога отклонено защитной проверкой."\n')
        extra += _atomic_wrapper('_zapisat_atomarno') + PUBLISHER + URGENT
    elif name == 'publish_transaction_guard.py':
        extra += _atomic_wrapper('_atomic') + SNAPSHOT
    elif name == 'ua_spec_permanent.py':
        extra += SPEC_LOCK
    elif name == 'ua_spec84_runtime.py':
        source = _replace_function(source, '_writer_guard', SPEC_RUNTIME_GUARD)
        extra += '''
_delete_original_spec_atomic = _atomic_existing
def _atomic_existing(path, before, after):
    with _delete_guarded_write(path, after):
        return _delete_original_spec_atomic(path, before, after)
'''
    elif name == 'cars_ui.py':
        return apply_cars_ui_to_candidate(source.encode('utf-8')).decode('utf-8')
    elif name == 'kadry_diagnostiki.py':
        source = _replace_once(source,
            '            os.replace(vremenno, kuda_put)\n',
            '            if not _delete_replace_diagnostic_media(vremenno, kuda_put):\n'
            '                return False\n')
        source = _replace_once(source,
            '                os.replace(put, cel)\n',
            '                if not _delete_replace_diagnostic_media(put, cel):\n'
            '                    return put\n')
        source = _replace_once(source,
            '        os.replace(put, os.path.join(storona, imya))\n',
            '        if not _delete_replace_diagnostic_media(put, os.path.join(storona, imya)):\n'
            '            return put\n')
        source = _replace_once(source,
            '                    os.remove(os.path.join(papka, imya))\n'
            '                    stalo.pop(imya, None)\n',
            '                    if _delete_cleanup_diagnostic_media(os.path.join(papka, imya), nom, ryad["id"]):\n'
            '                        stalo.pop(imya, None)\n')
        extra += MEDIA_CLEANUP
    result = _append(source, extra)
    compile(result, name, 'exec')
    return result


def apply_cars_ui_to_candidate(candidate_bytes):
    from cars_publication_patch import apply_to_candidate
    return apply_to_candidate(candidate_bytes)
