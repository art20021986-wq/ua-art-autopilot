#!/usr/bin/env python3
"""Issue84 bounded code + published-card installation; default read-only preflight.

Never calls platform APIs, starts/stops processes, writes databases, WSGI,
analytics-stop, HALT or coordination intent. Operator-supplied observations are
hash-bound evidence; this script does not itself authenticate a platform UI.
"""
from pathlib import Path
import argparse
import ast
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import time
import types

ROOT = Path('/home/Carix')
STAGE = ROOT / 'spec_issue84_20260910_r1'
BACKUP = STAGE / 'install-backup'
RECEIPT = STAGE / 'install-receipt.json'
JOURNAL = STAGE / 'install-journal.jsonl'
PROOF = STAGE / 'platform-readback.json'
RELOAD_PROOF = STAGE / 'reload-readback.json'
INTENT = ROOT / '.uaart_writer_coordination/active-intent.json'
TASK = 'UA-ART-SPEC-PERSIST-18-10M-001'
LOCKS = ('.start_safe.singleton.lock', '.task082_catalog_stage_repair.lock',
    '.task082_catalog_stage_guard.lock', '.task083_catalog_dedup.lock',
    '.ua_art_publish_transaction.lock', '.crm_db.lock')
OLD_PINS = {
    'master_card.py':'f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce',
    'stranica.py':'42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc',
    'yadro.py':'1e92a22a3fc485ea2cfe3d00a50586e872b3f6e4f628923b2ab9744534406992',
    'publikaciya.py':'fb7fa77277ebc3330c85ab3744c85ac7f084074a314866a5bf388a283f2622c0',
    'vin_spec_service.py':'247943e514f34dc37265791bf56fd36e58bcbaa8b2064285544733b1afc42bae'}
NEW_MODULES = ('ua_spec_permanent.py', 'spec_retry84.py', 'ua_spec84_runtime.py', 'spec84_collector.py')
DEPS = {
    'ua_additional_spec.py':'6d2ab7b2bace29b8c0be58a6668264e695fd24f9e5e8f3ed6406da41ea45c672',
    'cars_ui.py':'2c79fffff4cad8a23cb3f8992190ff03c17210655ddd374e9548d6e88563a246',
    'konteyner.py':'bdf6b953e95cf5ae78d3d640b9ba438202e9708d48cb1c7f4e1556bb59921824',
    'start_safe.py':'21aded2b576b36c6cea84b431c691b22eb09105ca5ec13bb6fd0910452c2cbeb',
    'publish_transaction_guard.py':'ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d',
    'source_policy.py':'727e871091c2a1858489ccab70085c801c2439aa623d23312bc40d7c1280ef38',
    'profile_library.py':'1211250019cf16c74f28d96539606803db92fe9a204eddfbb2a7339d174085db'}
WSGI_PINS = {
    '/var/www/www_uaart_com_ua_wsgi.py':'3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308',
    '/home/Carix/analitika_wsgi.py':'a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94',
    '/home/Carix/analitika_yadro.py':'02d249c5f1cedb0e575736eff1e02fa78745d5e459e1f4695e67378acc082e3c',
    '/home/Carix/uaart_bridge_wsgi.py':'b0c93d88d67e8c285c1bffb40bd6f2e40c2779af7a01cebd6beab4beda685150'}
MAX_BYTES = 32 * 1024 * 1024


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_hash(value, code):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value), code)
    return value


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + '\n').encode()


def read(path, missing=False):
    path = Path(path)
    require(path.parent.resolve() == path.parent, 'UNSAFE_PARENT:' + path.name)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        if missing:
            return None
        raise
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_BYTES,
            'UNSAFE_FILE:' + path.name)
        raw = bytearray()
        while len(raw) <= MAX_BYTES:
            chunk = os.read(fd, min(262144, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        require(len(raw) <= MAX_BYTES, 'FILE_TOO_LARGE')
        current = path.lstat()
        require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
            (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns), 'FILE_CHANGED_DURING_READ')
        return bytes(raw), info
    finally:
        os.close(fd)


def fingerprint(path):
    item = read(path, missing=True)
    return None if item is None else sha(item[0])


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def new_private(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None, 'TIMESTAMP_TIMEZONE_REQUIRED')
    return parsed.timestamp()


def guard():
    require(not INTENT.exists() and not INTENT.is_symlink(), 'EXISTING_COORDINATION_INTENT_REQUIRES_RECONCILIATION')
    require(read(ROOT / 'analitika_stop.txt')[0] == b'', 'ANALYTICS_STOP_CHANGED')
    for name, expected in DEPS.items():
        require(fingerprint(ROOT / name) == expected, 'DEPENDENCY_CHANGED:' + name)
    for path, expected in WSGI_PINS.items():
        require(fingerprint(path) == expected, 'WSGI_IMPORT_CLOSURE_CHANGED')


def platform_proof(expected):
    exact_hash(expected, 'EXACT_PLATFORM_PROOF_HASH_REQUIRED')
    raw, _ = read(PROOF)
    require(sha(raw) == expected, 'PLATFORM_PROOF_CHANGED')
    value = json.loads(raw)
    require(value.get('task_id') == 266084 and value.get('task_enabled') is False and
        value.get('original_process_absent') is True and
        value.get('observed_command') == 'python3.10 /home/Carix/start_safe.py' and
        value.get('source') == 'authenticated_pythonanywhere_ui', 'PLATFORM_PROOF_SCOPE')
    require(0 <= time.time() - timestamp(value['observed_at']) <= 180, 'PLATFORM_PROOF_NOT_CURRENT')
    return value


def reload_proof(expected):
    exact_hash(expected, 'EXACT_RELOAD_PROOF_HASH_REQUIRED')
    raw, _ = read(RELOAD_PROOF)
    require(sha(raw) == expected, 'RELOAD_PROOF_CHANGED')
    value = json.loads(raw)
    require(value.get('source') == 'authenticated_pythonanywhere_ui_and_provider_timeout' and
        value.get('webapp') == 'www.uaart.com.ua' and value.get('webapp_enabled') is True,
        'RELOAD_PROOF_SCOPE')
    require(value.get('wsgi_before_sha256') == WSGI_PINS and value.get('wsgi_after_sha256') == WSGI_PINS,
        'RELOAD_IMPORT_CLOSURE_NOT_BOUND')
    require(value.get('analytics_stop_before_sha256') == sha(b'') and
        value.get('analytics_stop_after_sha256') == sha(b''), 'RELOAD_STOP_FLAG_NOT_BOUND')
    action, observed = timestamp(value['reload_action_at']), timestamp(value['observed_at'])
    require(0 <= time.time() - observed <= 180 and action <= observed, 'RELOAD_PROOF_NOT_CURRENT')
    require(value.get('completion_evidence') == 'documented_worker_timeout_after_stop' and
        value.get('provider_documentation_url', '').rstrip('/') ==
        'https://help.pythonanywhere.com/pages/AsyncInWebApps', 'WORKER_TIMEOUT_CONTRACT_REQUIRED')
    require(value.get('max_request_seconds') == 300 and value.get('grace_seconds') == 30,
        'DOCUMENTED_REQUEST_BOUND_REQUIRED')
    require(value.get('inference') == 'worker_request_bound_elapsed_no_async_writers' and
        value.get('analytics_stop_confirmed_before_reload') is True, 'STOP_BASELINE_AND_INFERENCE_REQUIRED')
    require(observed - action >= 330, 'WORKER_REQUEST_BOUND_NOT_ELAPSED')
    ui = value['ui_reload']
    require(ui.get('disabled_observed') is True and ui.get('enabled_afterward_observed') is True and
        ui.get('error_observed') is False and action <= timestamp(ui['enabled_observed_at']) <= observed,
        'UI_RELOAD_OBSERVATION_REQUIRED')
    require(not any(key in value for key in ('application_response', 'self_redirect', 'web_open_result')),
        'NO_UNOBSERVED_HTTP_EVIDENCE_IN_TIMEOUT_MODE')
    for path, expected_hash in WSGI_PINS.items():
        require(fingerprint(path) == expected_hash, 'WSGI_IMPORT_CLOSURE_CHANGED')
    require(read(ROOT / 'analitika_stop.txt')[0] == b'', 'ANALYTICS_STOP_CHANGED')
    return value


def published_uids():
    with sqlite3.connect('file:' + str(ROOT / 'crm.db') + '?mode=ro', uri=True, timeout=5) as conn:
        conn.execute('PRAGMA query_only=ON')
        rows = conn.execute('SELECT auto_number FROM cars WHERE published=1 ORDER BY auto_number').fetchall()
    values = [row[0] for row in rows]
    require(values and len(values) == len(set(values)) and all(
        isinstance(uid, str) and re.fullmatch(r'UA-\d{4,6}', uid) for uid in values), 'PUBLISHED_UID_SET_INVALID')
    require({'UA-%04d' % n for n in range(1, 19)} <= set(values), 'REQUESTED_18_PUBLISHED_CARDS_REQUIRED')
    return sorted(values)


def preflight(expected_manifest=None):
    guard()
    require(not any(path.exists() or path.is_symlink() for path in (BACKUP, JOURNAL, RECEIPT)),
        'PREVIOUS_ISSUE84_INSTALL_STATE_REQUIRES_RECONCILIATION')
    raw = read(STAGE / 'manifest.json')[0]
    if expected_manifest is not None:
        exact_hash(expected_manifest, 'EXACT_MANIFEST_HASH_REQUIRED')
        require(sha(raw) == expected_manifest, 'MANIFEST_CHANGED')
    manifest = json.loads(raw)
    require(manifest.get('task') == TASK and manifest.get('mode') == 'PREPARE_ONLY' and
        manifest.get('production_writes') == 0 and manifest.get('database_writes') == 0, 'MANIFEST_SCOPE')
    require(set(manifest['files']) == set(OLD_PINS) | set(NEW_MODULES), 'NINE_MODULE_SCOPE_REQUIRED')
    records = []
    # New modules are installed first, then API entry points. The bot is paused.
    for name in (*NEW_MODULES, *OLD_PINS):
        item = manifest['files'][name]
        before = OLD_PINS.get(name)
        after = exact_hash(item['after_sha256'], 'CANDIDATE_HASH_REQUIRED')
        require(item['before_sha256'] == before, 'CODE_MANIFEST_PREIMAGE_PIN:' + name)
        current = read(ROOT / name, missing=True)
        require((None if current is None else sha(current[0])) == before, 'CODE_CHANGED:' + name)
        new = read(STAGE / 'candidate' / name)[0]
        require(sha(new) == after and new, 'CODE_CANDIDATE_CHANGED:' + name)
        ast.parse(new, feature_version=(3, 10))
        compile(new, name, 'exec')
        records.append(dict(target=str(ROOT / name), candidate=str(STAGE / 'candidate' / name),
            before=before, after=after, raw=None if current is None else current[0], new=new,
            meta=None if current is None else current[1]))
    pure = types.ModuleType('_issue84_pure_preflight')
    module_record = next(record for record in records if Path(record['target']).name == 'ua_spec_permanent.py')
    exec(compile(module_record['new'], module_record['candidate'], 'exec'), pure.__dict__)
    pages_raw = read(STAGE / 'pages' / 'manifest.json')[0]
    require(sha(pages_raw) == exact_hash(manifest['pages_manifest_sha256'], 'PAGES_MANIFEST_HASH_REQUIRED'),
        'PAGES_MANIFEST_CHANGED')
    pages = json.loads(pages_raw)
    uids = published_uids()
    require(pages.get('mode') == 'PREPARE_ONLY' and pages.get('task') == TASK and
        pages.get('production_writes') == 0 and pages.get('database_writes') == 0 and
        pages.get('published_uids') == uids and pages.get('page_count') == len(uids) * 2 and
        pages.get('renderer_sha256') == DEPS['ua_additional_spec.py'], 'PAGES_MANIFEST_SCOPE')
    targets = {str(ROOT / folder / (uid + '.html')) for folder in ('video', 'site') for uid in uids}
    seen = set()
    for item in pages['pages']:
        target = item['input']
        require(target in targets and target not in seen, 'PAGE_TARGET_SCOPE')
        seen.add(target)
        relative = str(Path(target).relative_to(ROOT))
        require(item['candidate'] == relative and item['uid'] == Path(target).stem and
            item['protected_byte_changes'] == 0, 'PAGE_CANDIDATE_SCOPE')
        before, meta = read(Path(target))
        candidate = STAGE / 'pages' / relative
        after = read(candidate)[0]
        require(sha(before) == item['before_sha256'] and sha(after) == item['after_sha256'],
            'PAGE_CHANGED:' + relative)
        old_spans, old_protected = pure.owned_spans(before.decode('utf-8'))
        new_spans, new_protected = pure.owned_spans(after.decode('utf-8'))
        require(old_protected.encode('utf-8') == new_protected.encode('utf-8') and
            sha(new_protected.encode('utf-8')) == item['protected_sha256'], 'PROTECTED_PAGE_BYTES_CHANGED')
        blocks = [after.decode('utf-8')[start:end] for start, end, kind in new_spans if kind == 'block']
        require(len(blocks) == 1, 'ONE_SPECIFICATION_CONTROL_REQUIRED')
        require(len(pure.validate_block(blocks[0])) == item['visible_facts'], 'SPECIFICATION_FACT_COUNT_CHANGED')
        records.append(dict(target=target, candidate=str(candidate), before=sha(before), after=sha(after),
            raw=before, new=after, meta=meta))
    require(seen == targets, 'ALL_PUBLISHED_PAGES_REQUIRED')
    required_db = {str(ROOT / name) for name in ('vin_specs_task111_v3.db', 'vin_specs_task111_v3.db-wal')}
    require(set(pages['spec_database']) == required_db, 'SIDECAR_MANIFEST_SCOPE')
    protected = dict(pages['spec_database'])
    for name in ('crm.db', 'crm.db-wal'):
        protected[str(ROOT / name)] = fingerprint(ROOT / name)
    require(protected[str(ROOT / 'crm.db')] is not None and
        protected[str(ROOT / 'vin_specs_task111_v3.db')] is not None, 'CRM_AND_SIDECAR_REQUIRED')
    protected.update(WSGI_PINS)
    for name, expected in DEPS.items():
        protected[str(ROOT / name)] = expected
    for path, expected in protected.items():
        require(fingerprint(path) == expected, 'PROTECTED_INPUT_CHANGED:' + Path(path).name)
    require(published_uids() == uids, 'PUBLISHED_SET_CHANGED_DURING_PREFLIGHT')
    return records, protected, dict(scope='NINE_MODULES_AND_ALL_PUBLISHED_CAR_HTML', task=TASK,
        manifest_sha256=sha(raw), pages_manifest_sha256=sha(pages_raw), published_cards=len(uids),
        html_targets=len(targets), code_targets=9)


def acquire_locks():
    held = []
    try:
        for name in LOCKS:
            path = ROOT / name
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'LOCK_TYPE')
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held.append((path, fd, info.st_dev, info.st_ino))
            except BaseException:
                os.close(fd)
                raise
        return held
    except BaseException:
        for _, fd, _, _ in reversed(held):
            os.close(fd)
        raise


def check_locked(held, protected):
    guard()
    for path, fd, dev, ino in held:
        current = path.lstat()
        require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1 and
            (current.st_dev, current.st_ino) == (dev, ino) ==
            (os.fstat(fd).st_dev, os.fstat(fd).st_ino), 'LOCK_CHANGED')
    for path, expected in protected.items():
        require(fingerprint(path) == expected, 'PROTECTED_INPUT_CHANGED:' + Path(path).name)


def replace(record, new, expected, restore=False):
    """CAS an existing target, or atomically create a previously absent target."""
    path = Path(record['target'])
    require(fingerprint(path) == expected, 'TARGET_CHANGED:' + path.name)
    require(path.parent.resolve() == path.parent, 'PARENT_CHANGED')
    fd, temporary = tempfile.mkstemp(prefix='.ua-spec-issue84-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(new)
            stream.flush()
            meta = record['meta']
            os.fchmod(stream.fileno(), 0o600 if meta is None else stat.S_IMODE(meta.st_mode))
            if meta is not None:
                os.fchown(stream.fileno(), meta.st_uid, meta.st_gid)
            os.fsync(stream.fileno())
        require(fingerprint(path) == expected, 'TARGET_CHANGED_BEFORE_REPLACE')
        if restore and record['meta'] is not None:
            os.utime(temporary, ns=(record['meta'].st_atime_ns, record['meta'].st_mtime_ns))
        if expected is None:
            # link() provides atomic no-clobber creation; remove temporary link
            # before the normal one-link readback invariant is checked.
            os.link(temporary, path, follow_symlinks=False)
            os.unlink(temporary)
        else:
            os.replace(temporary, path)
        fsync_dir(path.parent)
        require(fingerprint(path) == sha(new), 'TARGET_READBACK_FAILED')
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def check_rollback_set(records):
    """All targets/backups must match owned states before any compensation."""
    for index, record in enumerate(records):
        require(fingerprint(record['target']) in (record['before'], record['after']),
            'FOREIGN_TARGET_BLOCKS_ROLLBACK')
        backup = BACKUP / ('%03d.bin' % index)
        require(fingerprint(backup) == record['before'], 'BACKUP_CHANGED')


def compensate(record):
    current = fingerprint(record['target'])
    require(current in (record['before'], record['after']), 'FOREIGN_TARGET_BLOCKS_ROLLBACK')
    if current == record['before']:
        return
    if record['before'] is None:
        require(fingerprint(record['target']) == record['after'], 'NEW_TARGET_CHANGED_BEFORE_UNLINK')
        Path(record['target']).unlink()
        fsync_dir(Path(record['target']).parent)
        require(fingerprint(record['target']) is None, 'NEW_TARGET_ROLLBACK_READBACK')
    else:
        replace(record, record['raw'], record['after'], restore=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true')
    parser.add_argument('--manifest-sha256')
    parser.add_argument('--platform-proof-sha256')
    parser.add_argument('--reload-proof-sha256')
    args = parser.parse_args()
    if args.install:
        exact_hash(args.manifest_sha256, 'EXACT_MANIFEST_HASH_REQUIRED')
    records, protected, pins = preflight(args.manifest_sha256)
    if not args.install:
        print(json.dumps(dict(status='PREFLIGHT_PASS', targets=len(records), production_writes=0,
            database_writes=0, platform_pause_verified=False, **pins)))
        return
    platform_proof(args.platform_proof_sha256)
    reload_proof(args.reload_proof_sha256)
    held = acquire_locks()
    try:
        records, protected, pins = preflight(args.manifest_sha256)
        check_locked(held, protected)
        platform_proof(args.platform_proof_sha256)
        reload_proof(args.reload_proof_sha256)
        BACKUP.mkdir(mode=0o700)
        fsync_dir(STAGE)
        backup_manifest = []
        for index, record in enumerate(records):
            name = '%03d.bin' % index
            meta = record['meta']
            if record['raw'] is not None:
                new_private(BACKUP / name, record['raw'])
            backup_manifest.append(dict(target=record['target'], backup=None if meta is None else name,
                before_sha256=record['before'], after_sha256=record['after'],
                mode=None if meta is None else stat.S_IMODE(meta.st_mode),
                uid=None if meta is None else meta.st_uid, gid=None if meta is None else meta.st_gid,
                atime_ns=None if meta is None else meta.st_atime_ns,
                mtime_ns=None if meta is None else meta.st_mtime_ns))
        new_private(BACKUP / 'manifest.json', canonical(backup_manifest))
        new_private(JOURNAL, b'')
        def event(value):
            fd = os.open(JOURNAL, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
            try:
                with os.fdopen(fd, 'ab', closefd=False) as stream:
                    stream.write((json.dumps(value, sort_keys=True) + '\n').encode())
                    stream.flush()
                    os.fsync(fd)
            finally:
                os.close(fd)
        evidence = dict(platform_proof_sha256=args.platform_proof_sha256,
            reload_proof_sha256=args.reload_proof_sha256)
        event(dict(event='BACKUPS_READY', targets=len(records), **evidence, **pins))
        try:
            for record in records:
                require(fingerprint(record['target']) == record['before'], 'PREIMAGE_CHANGED')
                require(fingerprint(record['candidate']) == record['after'], 'CANDIDATE_CHANGED')
            for record in records:
                check_locked(held, protected)
                platform_proof(args.platform_proof_sha256)
                reload_proof(args.reload_proof_sha256)
                if record['before'] == record['after']:
                    event(dict(event='UNCHANGED_READBACK', target=record['target']))
                    continue
                event(dict(event='WRITE_INTENT', target=record['target'], after_sha256=record['after']))
                replace(record, record['new'], record['before'])
                event(dict(event='WRITE_READBACK', target=record['target']))
            check_locked(held, protected)
            require(all(fingerprint(record['target']) == record['after'] for record in records), 'FINAL_READBACK')
            result = dict(status='INSTALLED_LOCAL_READBACK', targets=len(records),
                protected_databases_unchanged=True, runtime_loaded_verified=False,
                public_https_verified=False, tasks_resumed=False, **evidence, **pins)
            event(dict(event='TERMINAL_INSTALLED', **result))
            new_private(RECEIPT, canonical(result))
            print(json.dumps(result))
        except BaseException as exc:
            event(dict(event='INSTALL_INTERRUPTED', error=type(exc).__name__, reason=str(exc)))
            try:
                check_locked(held, protected)
                check_rollback_set(records)
                for record in reversed(records):
                    check_locked(held, protected)
                    if fingerprint(record['target']) != record['before']:
                        event(dict(event='ROLLBACK_INTENT', target=record['target']))
                        compensate(record)
                require(all(fingerprint(record['target']) == record['before'] for record in records),
                    'ROLLBACK_READBACK')
                status = 'ROLLED_BACK_READBACK'
            except BaseException as rollback_error:
                status = 'ROLLBACK_BLOCKED_RECONCILIATION_REQUIRED'
                event(dict(event=status, error=type(rollback_error).__name__, reason=str(rollback_error)))
            result = dict(status=status, error=type(exc).__name__, reason=str(exc), tasks_resumed=False,
                runtime_loaded_verified=False, **evidence, **pins)
            event(dict(event='TERMINAL_ERROR', **result))
            if not RECEIPT.exists():
                new_private(RECEIPT, canonical(result))
            print(json.dumps(result))
            raise
    finally:
        for _, fd, _, _ in reversed(held):
            os.close(fd)


if __name__ == '__main__':
    main()
