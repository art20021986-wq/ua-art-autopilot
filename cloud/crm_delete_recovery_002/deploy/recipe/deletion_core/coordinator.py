"""Durable legacy deletion coordinator. Candidate only; no installation hook.

The adapter supplies authorization, the existing publication fence, the
existing db.connect(), exact route inventory, source-bound counter handling,
and HTTP observations. No provider credentials or bot startup are imported.
"""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sqlite3
import time

try:
    from .deletion_state import (DeletionStore, DeletionError, ImmediateTransaction,
                                 _snapshot, application_schema_sha256)
    from .retirement import retire_html, retire_sitemap, url_code
    from .public_write_guard import advertised_codes
except ImportError:
    from deletion_state import (DeletionStore, DeletionError, ImmediateTransaction,
                                _snapshot, application_schema_sha256)
    from retirement import retire_html, retire_sitemap, url_code
    from public_write_guard import advertised_codes


class CoordinatorError(RuntimeError):
    pass


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, reason):
    if not condition:
        raise CoordinatorError(reason)


def durable_write(path, data, mode=0o600):
    temporary = path.with_name(path.name + '.tmp-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


class Coordinator:
    """Synchronous worker API; Telegram should run it outside the event loop.

    binding attributes:
      public_root, journal_root (existing absolute canonical private folder),
      connect(), fence(), require_fence(), authorize(actor_id),
      resolve_plan(row), transform_lists(code, before_by_path),
      verify_local(plan, current_by_path), observe_http(plan).

    transform_lists must apply retire_html then the approved counter transform
    without changing any other tile. verify_local independently checks exact
    remaining membership/counters. Both run under the publication fence and
    MUST be local, bounded, and free of other lock acquisition/network I/O.
    observe_http runs outside all publication/database locks.
    """
    def __init__(self, binding, *, schema_sha256, max_http_age=60,
                 clock=time.time, fault=lambda event, path: None):
        self.binding, self.clock, self.fault = binding, clock, fault
        self.root, self.journal = Path(binding.public_root), Path(binding.journal_root)
        for path in (self.root, self.journal):
            require(path.is_absolute() and path.resolve(strict=True) == path and path.is_dir(),
                    'CANONICAL_EXISTING_ROOT_REQUIRED')
        require(not self.journal.is_relative_to(self.root / 'site') and
                not self.journal.is_relative_to(self.root / 'video'), 'PRIVATE_JOURNAL_REQUIRED')
        require((self.journal.stat().st_mode & 0o077) == 0, 'PRIVATE_JOURNAL_MODE_REQUIRED')
        require(type(max_http_age) in (int, float) and 0 < max_http_age <= 300,
                'BOUNDED_HTTP_FRESHNESS_REQUIRED')
        self.max_http_age = max_http_age
        self.store = DeletionStore(approved_application_schema_sha256=schema_sha256,
                                  verify_retirement=self._verify)

    def _public(self, name):
        require(isinstance(name, str) and name == str(PurePosixPath(name)) and
                not name.startswith('/') and '..' not in PurePosixPath(name).parts,
                'EXACT_RELATIVE_PATH_REQUIRED')
        path = self.root / name
        require(path.resolve(strict=False) == path and path.parent.is_dir() and
                not path.is_symlink(), 'CANONICAL_PUBLIC_PATH_REQUIRED')
        require(path.is_relative_to(self.root / 'site') or path.is_relative_to(self.root / 'video'),
                'PUBLIC_PATH_OUT_OF_SCOPE')
        return path

    def _private(self, name):
        require(isinstance(name, str) and re.fullmatch(r'[a-z0-9_.-]+', name), 'PRIVATE_FILE_NAME_REQUIRED')
        path = self.journal / name
        require(path.resolve(strict=False) == path and not path.is_symlink(), 'PRIVATE_PATH_CHANGED')
        return path

    def _tx(self, conn):
        return ImmediateTransaction(conn, self.binding.require_fence)

    def confirm(self, *, car_id, actor_id):
        require(self.binding.authorize(actor_id) is True, 'STAFF_AUTHORIZATION_REQUIRED')
        with self.binding.fence(), closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            token = self.store.confirm(tx, car_id=car_id, actor_id=actor_id)
            tx.commit()
            return token

    def confirmation(self, *, token, actor_id):
        """Safe display metadata; no complete private row is returned."""
        require(self.binding.authorize(actor_id) is True, 'STAFF_AUTHORIZATION_REQUIRED')
        with self.binding.fence(), closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            self.store._check(tx)
            row = conn.execute('SELECT actor_id,car_id,car_code,vin,snapshot_sha256,operation_id '
                               'FROM ua_delete_confirmations WHERE token=?', (token,)).fetchone()
            require(row is not None and row[0] == actor_id, 'CONFIRMATION_ACTOR_MISMATCH')
            return dict(zip(('actor_id', 'car_id', 'car_code', 'vin', 'snapshot_sha256', 'operation_id'), row))

    def _validate_plan(self, plan, code):
        require(isinstance(plan, dict) and set(plan) == {'mode', 'car_code', 'direct', 'lists', 'sitemaps', 'media', 'routes', 'local_only'},
                'EXACT_COORDINATOR_PLAN_REQUIRED')
        require(plan['car_code'] == code and re.fullmatch(r'UA-[0-9]{4}', code), 'PLAN_IDENTITY_MISMATCH')
        seen = set()
        for key in ('direct', 'lists', 'sitemaps', 'media'):
            names = plan[key]
            require(isinstance(names, list) and names == sorted(set(names)), 'SORTED_UNIQUE_INVENTORY_REQUIRED')
            require(not seen.intersection(names), 'OVERLAPPING_EFFECT_AND_MEDIA_INVENTORY')
            seen.update(names)
            for name in names:
                path = self._public(name)
                if key == 'direct':
                    require(url_code(name) == code and path.suffix == '.html', 'EXACT_TARGET_ALIAS_REQUIRED')
                if key == 'lists':
                    require(path.suffix == '.html' and url_code(name) is None, 'SHARED_HTML_REQUIRED')
                if key == 'sitemaps':
                    require(path.name == 'sitemap.xml', 'EXACT_SITEMAP_REQUIRED')
                if key == 'media':
                    require(path.suffix.lower() not in ('.html', '.xml', '.py', '.db'), 'MEDIA_INVENTORY_INVALID')
        require(bool(plan['lists']), 'EXPLICIT_LIST_COVERAGE_REQUIRED')
        require(plan['mode'] in ('NEVER_PUBLISHED', 'PUBLIC_OR_RESIDUAL'), 'RETIREMENT_MODE_REQUIRED')
        require((plan['mode'] == 'NEVER_PUBLISHED') == (not plan['direct']), 'MODE_DIRECT_TARGET_MISMATCH')
        routes = plan['routes']
        require(isinstance(routes, dict) and routes, 'EXACT_HTTP_ROUTE_INVENTORY_REQUIRED')
        covered = set()
        for url, name in routes.items():
            require(isinstance(url, str) and url.startswith(('https://', 'http://')) and '#' not in url,
                    'HTTP_URL_REQUIRED')
            require(name in set(plan['direct'] + plan['lists'] + plan['sitemaps']), 'UNBOUND_HTTP_ROUTE')
            covered.add(name)
        local_only = plan['local_only']
        require(isinstance(local_only, list) and local_only == sorted(set(local_only)) and
                not covered.intersection(local_only), 'EXPLICIT_UNSERVED_MIRRORS_REQUIRED')
        require(covered | set(local_only) == set(plan['direct'] + plan['lists'] + plan['sitemaps']),
                'HTTP_ROUTE_COVERAGE_INCOMPLETE')
        if plan['mode'] == 'PUBLIC_OR_RESIDUAL':
            require(bool(covered.intersection(plan['direct'])), 'PUBLIC_TARGET_HTTP_EVIDENCE_REQUIRED')
        return json.loads(encoded(plan))

    def admit(self, *, token, actor_id):
        """Backup, then atomically admit intent+job. Does not publish success."""
        require(self.binding.authorize(actor_id) is True, 'STAFF_AUTHORIZATION_REQUIRED')
        require(isinstance(token, str) and re.fullmatch(r'[0-9a-f]{32}', token), 'CONFIRMATION_TOKEN_REQUIRED')
        with self.binding.fence():
            with closing(self.binding.connect()) as conn, self._tx(conn) as tx:
                self.store._check(tx)
                confirmation = conn.execute('SELECT * FROM ua_delete_confirmations WHERE token=?', (token,)).fetchone()
                require(confirmation is not None, 'CONFIRMATION_MISSING')
                columns = [item[1] for item in conn.execute('PRAGMA table_info(ua_delete_confirmations)')]
                confirmation = dict(zip(columns, confirmation))
                require(confirmation['actor_id'] == actor_id, 'CONFIRMATION_ACTOR_MISMATCH')
                existing = confirmation['operation_id']
                if not existing:
                    found = conn.execute('SELECT operation_id FROM ua_delete_intents WHERE car_id=? OR car_code=?',
                                         (confirmation['car_id'], confirmation['car_code'])).fetchone()
                    existing = found[0] if found else None
                if existing:
                    # Delegate all duplicate/replacement checks to the state authority.
                    intent = self.store.admit(tx, token=token, actor_id=actor_id, plan={}, backup_sha256='0' * 64)
                    tx.commit()
                    return intent
                cursor = conn.execute('SELECT * FROM cars WHERE id=?', (confirmation['car_id'],))
                value = cursor.fetchone()
                require(value is not None, 'CAR_MISSING_NO_ORIGINAL_JOB')
                row = dict(zip((item[0] for item in cursor.description), value))
                require(_snapshot(row) == confirmation['snapshot'], 'STALE_CONFIRMATION')
                tx.commit()
            plan = self._validate_plan(self.binding.resolve_plan(dict(row)), row['auto_number'])
            manifest_sha = self._backup(plan, row)
            core_plan = self._core_plan(plan)
            self.fault('backup_complete', '')
            with closing(self.binding.connect()) as conn, self._tx(conn) as tx:
                intent = self.store.admit(tx, token=token, actor_id=actor_id, plan=core_plan, backup_sha256=manifest_sha)
                tx.commit()
            self.fault('intent_committed', '')
            return intent

    @staticmethod
    def _core_plan(plan):
        return {'mode': plan['mode'], 'car_code': plan['car_code'], 'public_targets': plan['direct'],
                'list_surfaces': sorted(plan['lists'] + plan['sitemaps']), 'media_targets': []}

    def _backup(self, plan, row, *, admitted_snapshot_sha256=None, target_absent=False):
        """Coherent SQLite backup, integrity check and full-row read-back.

        No whole-database restore is ever performed. The subsequent admission
        CAS refuses target changes that occurred after the captured snapshot.
        """
        self.binding.require_fence()
        prefix = 'backup-' + secrets.token_hex(16)
        database = self._private(prefix + '.sqlite')
        fd = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        with closing(self.binding.connect()) as source, closing(sqlite3.connect(database)) as target:
            # backup() itself captures one consistent database snapshot.
            source.backup(target)
            require(target.execute('PRAGMA integrity_check').fetchall() == [('ok',)], 'BACKUP_INTEGRITY_FAILED')
            require(application_schema_sha256(target) == self.store.schema_sha, 'BACKUP_SCHEMA_CHANGED')
            cursor = target.execute('SELECT * FROM cars WHERE id=?', (row['id'],))
            value = cursor.fetchone()
            if target_absent:
                require(value is None and admitted_snapshot_sha256 is not None, 'BACKUP_TARGET_REAPPEARED')
            else:
                require(value is not None and _snapshot(dict(zip((item[0] for item in cursor.description), value))) == _snapshot(row),
                        'BACKUP_TARGET_SNAPSHOT_CHANGED')
            target.commit()
        fd = os.open(database, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        before = {name: self._public(name).read_bytes() for name in plan['lists'] + plan['sitemaps']}
        transformed = self.binding.transform_lists(plan['car_code'], {name: before[name] for name in plan['lists']})
        require(isinstance(transformed, dict) and set(transformed) == set(plan['lists']), 'EXACT_LIST_TRANSFORM_REQUIRED')
        proposed = dict(transformed)
        for name in plan['sitemaps']:
            proposed[name] = retire_sitemap(before[name], plan['car_code'])
        for name in plan['lists']:
            require(isinstance(proposed[name], bytes), 'TRANSFORM_BYTES_REQUIRED')
            require(plan['car_code'] not in advertised_codes(proposed[name].decode('utf-8')), 'TARGET_STILL_IN_LIST')
        if plan['mode'] == 'NEVER_PUBLISHED':
            require(all(proposed[name] == data for name, data in before.items()), 'DRAFT_HAS_PUBLIC_RESIDUAL')
        require(self.binding.verify_local(plan, proposed) is True, 'LOCAL_PROPOSAL_VERIFICATION_FAILED')
        records = {}
        for number, name in enumerate(sorted(plan['direct'] + plan['lists'] + plan['sitemaps'])):
            path = self._public(name)
            data = (path.read_bytes() if path.exists() else None) if name in plan['direct'] else before[name]
            old_name = prefix + '-' + str(number) + '.before' if data is not None else None
            if old_name:
                durable_write(self._private(old_name), data)
            item = {'before_file': old_name, 'before_sha256': sha(data) if data is not None else None,
                    'mode': path.stat().st_mode & 0o777 if path.exists() else 0o644,
                    'after_file': None, 'after_sha256': None}
            if name not in plan['direct']:
                new_name = prefix + '-' + str(number) + '.after'
                durable_write(self._private(new_name), proposed[name])
                item.update(after_file=new_name, after_sha256=sha(proposed[name]))
            records[name] = item
        media = {name: sha(self._public(name).read_bytes()) for name in plan['media']}
        manifest = {'version': 1, 'plan': plan,
                    'snapshot_sha256': admitted_snapshot_sha256 or sha(_snapshot(row).encode()),
                    'backup_target_snapshot_sha256': None if target_absent else sha(_snapshot(row).encode()),
                    'database_file': database.name, 'database_sha256': sha(database.read_bytes()),
                    'database_integrity': 'ok', 'files': records, 'media_sha256': media}
        digest = sha(encoded(manifest))
        durable_write(self._private('manifest-' + digest + '.json'), encoded(manifest))
        self._manifest(digest)
        return digest

    def _manifest(self, digest):
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'MANIFEST_SHA_REQUIRED')
        raw = self._private('manifest-' + digest + '.json').read_bytes()
        require(sha(raw) == digest, 'MANIFEST_CORRUPTED')
        manifest = json.loads(raw)
        require(manifest['version'] == 1 and manifest['database_integrity'] == 'ok', 'MANIFEST_VERSION_OR_INTEGRITY')
        self._validate_plan(manifest['plan'], manifest['plan']['car_code'])
        require(sha(self._private(manifest['database_file']).read_bytes()) == manifest['database_sha256'], 'BACKUP_DATABASE_CORRUPTED')
        for item in manifest['files'].values():
            for prefix in ('before', 'after'):
                if item[prefix + '_file']:
                    require(sha(self._private(item[prefix + '_file']).read_bytes()) == item[prefix + '_sha256'], 'BACKUP_IMAGE_CORRUPTED')
        return manifest

    def _effective_manifest(self, intent):
        original = self._manifest(intent['backup_sha256'])
        pointer = self._private('rebase-' + intent['operation_id'] + '.json')
        if not pointer.exists():
            return original
        checkpoint = json.loads(pointer.read_bytes())
        require(set(checkpoint) == {'operation_id', 'original_backup_sha256', 'manifest_sha256'} and
                checkpoint['operation_id'] == intent['operation_id'] and
                checkpoint['original_backup_sha256'] == intent['backup_sha256'], 'REBASE_BINDING_FAILED')
        current = self._manifest(checkpoint['manifest_sha256'])
        require(current['plan'] == original['plan'] and
                current['snapshot_sha256'] == original['snapshot_sha256'] and
                current['media_sha256'] == original['media_sha256'], 'REBASE_SCOPE_CHANGED')
        return current

    def _reconcile_manifest(self, intent):
        """Renew only shared after-images against current legitimate edits.

        Original direct-page before-images remain authoritative; replacement
        target pages are never admitted by rebasing. No old whole-file image
        is restored, and a new verified backup precedes the new checkpoint.
        """
        manifest = self._effective_manifest(intent)
        changed = False
        for name, item in manifest['files'].items():
            path = self._public(name)
            data = path.read_bytes() if path.exists() else None
            digest = sha(data) if data is not None else None
            if item['after_file'] is None:
                require(digest in {item['before_sha256'], None}, 'NEWER_DIRECT_PAGE_PRESERVED:' + name)
            elif digest not in {item['before_sha256'], item['after_sha256']}:
                require(data is not None, 'SHARED_PAGE_MISSING:' + name)
                changed = True
        for name, expected in manifest['media_sha256'].items():
            require(sha(self._public(name).read_bytes()) == expected, 'NEWER_MEDIA_PRESERVED:' + name)
        if not changed:
            return manifest
        with closing(self.binding.connect()) as conn:
            cursor = conn.execute('SELECT * FROM cars WHERE id=?', (intent['car_id'],))
            value = cursor.fetchone()
            row = dict(zip((item[0] for item in cursor.description), value)) if value else {'id': intent['car_id']}
        if value:
            require(_snapshot(row) == intent['expected_snapshot'], 'REBASE_TARGET_ROW_CHANGED')
        else:
            # _load already proved the original committed intent AND job and
            # ruled out a replacement identity. Legacy loss of the row after
            # admission may therefore finish the same intent without restore.
            require(intent['state'] in ('REQUESTED', 'ROW_DELETED'), 'REBASE_MISSING_UNFINALIZED_ROW')
        digest = self._backup(manifest['plan'], row,
                              admitted_snapshot_sha256=intent['snapshot_sha256'], target_absent=value is None)
        renewed = self._manifest(digest)
        require(renewed['plan'] == manifest['plan'] and renewed['media_sha256'] == manifest['media_sha256'],
                'REBASE_SCOPE_CHANGED')
        # No direct before-image can gain authority from a newer file.
        for name in manifest['plan']['direct']:
            require(renewed['files'][name]['before_sha256'] in {manifest['files'][name]['before_sha256'], None},
                    'REBASE_DIRECT_IDENTITY_CHANGED')
        durable_write(self._private('rebase-' + intent['operation_id'] + '.json'), encoded({
            'operation_id': intent['operation_id'], 'original_backup_sha256': intent['backup_sha256'],
            'manifest_sha256': digest}))
        self.fault('rebase_committed', '')
        return renewed

    def _load(self, operation_id):
        with closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            self.store._check(tx)
            intent = self.store._job(tx, operation_id)
            self.store._assert_no_replacement(tx, intent)
            return intent

    def _current(self, manifest, *, retired):
        current = {}
        for name, item in manifest['files'].items():
            path = self._public(name)
            data = path.read_bytes() if path.exists() else None
            digest = sha(data) if data is not None else None
            expected = {item['after_sha256']} if retired else {item['before_sha256'], item['after_sha256']}
            require(digest in expected, 'NEWER_PUBLIC_FILE_PRESERVED:' + name)
            if item['after_file']:
                current[name] = data
        for name, expected in manifest['media_sha256'].items():
            require(sha(self._public(name).read_bytes()) == expected, 'NEWER_MEDIA_PRESERVED:' + name)
        return current

    def _apply(self, intent, manifest):
        self.binding.require_fence()
        require(manifest['snapshot_sha256'] == intent['snapshot_sha256'] and
                encoded(self._core_plan(manifest['plan'])).decode() == intent['plan'], 'MANIFEST_INTENT_BINDING_FAILED')
        self._current(manifest, retired=False)  # Preflight all files before any effect.
        # Shared surfaces first; direct aliases last. A durable intent already blocks writers.
        order = sorted(manifest['files'], key=lambda name: (manifest['files'][name]['after_file'] is None, name))
        for name in order:
            item, path = manifest['files'][name], self._public(name)
            data = path.read_bytes() if path.exists() else None
            digest = sha(data) if data is not None else None
            if digest == item['after_sha256']:
                continue
            require(digest == item['before_sha256'], 'NEWER_PUBLIC_FILE_PRESERVED:' + name)
            if item['after_file']:
                durable_write(path, self._private(item['after_file']).read_bytes(), item['mode'])
            else:
                path.unlink()
                directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            self.fault('public_effect', name)
        require(self.binding.verify_local(manifest['plan'], self._current(manifest, retired=True)) is True,
                'LOCAL_RETIREMENT_VERIFICATION_FAILED')

    def _http(self, plan, manifest, evidence):
        require(isinstance(evidence, dict) and set(evidence) == set(plan['routes']), 'HTTP_COVERAGE_INCOMPLETE')
        for url, name in plan['routes'].items():
            observation = evidence[url]
            require(isinstance(observation, dict) and observation.get('url') == url and
                    observation.get('redirected') is False, 'HTTP_REDIRECT_OR_IDENTITY_MISMATCH')
            observed = observation.get('observed_at')
            require(type(observed) in (int, float) and 0 <= self.clock() - observed <= self.max_http_age,
                    'HTTP_EVIDENCE_STALE')
            if name in plan['direct']:
                require(observation.get('status') in (404, 410), 'TARGET_HTTP_NOT_RETIRED')
            else:
                require(observation.get('status') == 200 and observation.get('body_sha256') == manifest['files'][name]['after_sha256'],
                        'SHARED_HTTP_AFTER_IMAGE_MISMATCH')

    def _proof(self, intent, evidence):
        proof = {key: intent[key] for key in ('operation_id', 'car_id', 'car_code', 'vin', 'snapshot_sha256', 'expected_snapshot_sha256', 'plan_sha256')}
        proof.update({key: value for key, value in json.loads(intent['plan']).items()
                      if key in ('public_targets', 'list_surfaces', 'media_targets')})
        proof.update(all_absent=True, counters_match=True, http=evidence)
        return proof

    def _verify(self, intent, proof):
        self.binding.require_fence()
        manifest = self._effective_manifest(intent)
        require(manifest['snapshot_sha256'] == intent['snapshot_sha256'] and
                encoded(self._core_plan(manifest['plan'])).decode() == intent['plan'], 'MANIFEST_INTENT_BINDING_FAILED')
        current = self._current(manifest, retired=True)
        require(self.binding.verify_local(manifest['plan'], current) is True, 'LOCAL_RETIREMENT_VERIFICATION_FAILED')
        self._http(manifest['plan'], manifest, proof.get('http'))
        return True

    def resume(self, *, operation_id):
        """Trusted startup/job-worker entry. Never inserts an old CRM snapshot."""
        # A legitimate publication can win while HTTP checks run unlocked.
        # Renew against its current bytes, with a bounded retry rather than
        # freezing the operation on historical shared after-images forever.
        for attempt in range(3):
            try:
                return self._resume_once(operation_id=operation_id)
            except CoordinatorError as error:
                if not str(error).startswith('NEWER_PUBLIC_FILE_PRESERVED:') or attempt == 2:
                    raise

    def _resume_once(self, *, operation_id):
        with self.binding.fence():
            intent = self._load(operation_id)
            if intent['state'] == 'COMPLETE':
                # This is the original completed receipt, not a new claim of
                # live HTTP verification. Later legitimate catalog updates
                # must not make a terminal callback fail or replay old files.
                return self._result(intent)
            manifest = self._reconcile_manifest(intent)
            self._apply(intent, manifest)
        evidence = self.binding.observe_http(manifest['plan'])  # Outside locks.
        self.fault('http_observed', '')
        with self.binding.fence(), closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            intent = self.store.finalize_row(tx, operation_id=operation_id, proof=self._proof(intent, evidence))
            tx.commit()
        self.fault('row_deleted', '')
        # A second live observation follows committed row deletion.
        evidence = self.binding.observe_http(manifest['plan'])
        with self.binding.fence(), closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            intent = self.store.complete(tx, operation_id=operation_id, proof=self._proof(intent, evidence))
            tx.commit()
        self.fault('complete', '')
        return self._result(intent)

    @staticmethod
    def _result(intent):
        return {'status': 'COMPLETE', 'operation_id': intent['operation_id'],
                'backup_manifest_sha256': intent['backup_sha256'], 'media_writes': 0}

    def pending(self):
        with self.binding.fence(), closing(self.binding.connect()) as conn, self._tx(conn) as tx:
            return [intent['operation_id'] for intent in self.store.pending(tx)]
