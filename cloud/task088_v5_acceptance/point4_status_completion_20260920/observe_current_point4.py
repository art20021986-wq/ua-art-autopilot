#!/usr/bin/env python3
"""Bounded read-only business-state observer; never an installation or writer gate.

Only a NEW 0700 directory under the existing autopilot_inbox/cloud receives
0600 reports and optional copies of public core HTML. Private source bytes and
database rows other than six public vehicle fields are never exported.
SQLite uses normal mode=ro reader locking/shared-memory semantics, NOT immutable.
Two complete content-hash passes and two short SQLite transactions must agree.
This observes endpoint stability; it does not provide global writer exclusion.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import stat
import sys
import time

ROOT = Path('/home/Carix')
SOURCES = frozenset(('cars_ui.py', 'yadro.py', 'stranica.py',
    'catalog_design_guard.py', 'publish_transaction_guard.py',
    'ua_stage_catalog_sync.py', 'ua_spec_permanent.py'))
DEPENDENCIES = frozenset(('db.py', 'cars_schema.py', 'start_safe.py',
    'master_card.py', 'publikaciya.py', 'team_bot.py', 'catalog_design_golden.html',
    'lock4_zhurnal.py', 'ua_additional_spec.py', 'vin_spec_service.py'))
EXTRA = frozenset(('ua_site_counters.py', 'publication_fence.py'))
FIELDS = ('id', 'auto_number', 'published', 'status', 'price_uah', 'price_georgia')
ROUTING = {'observed_wsgi_config.py': Path('/var/www/www_uaart_com_ua_wsgi.py'),
    'analitika_wsgi.py': ROOT / 'analitika_wsgi.py',
    'uaart_bridge_wsgi.py': ROOT / 'uaart_bridge_wsgi.py',
    'video/index.html': ROOT / 'video/index.html',
    'site/index.html': ROOT / 'site/index.html'}
MAX_FILES = 100000
MAX_BYTES = 12 * 1024**3
MAX_FILE = 512 * 1024**2
MAX_HTML = 8 * 1024**2
MAX_CAPTURE_TOTAL = 64 * 1024**2
MAX_ROWS = 1000000


class Stop(RuntimeError):
    pass


def encoded(value):
    # Exact install_package.encoded semantics, including ASCII and no newline.
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':')).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def instant():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def stamp(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns, stat.S_IMODE(info.st_mode))


def open_directory(path):
    """Open every component via a no-follow directory FD, including ancestors."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise Stop('ABSOLUTE_NORMAL_DIRECTORY_REQUIRED')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                          dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def safe_stat(path):
    fd = open_directory(Path(path).parent)
    try:
        info = os.stat(Path(path).name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            raise Stop('REGULAR_FILE_REQUIRED')
        return stamp(info)
    finally:
        os.close(fd)


class Observer:
    def __init__(self, root, output, *, seconds=180, capture=False,
                 routing=None, self_sha256=None):
        self.root = Path(root)
        self.output = Path(output)
        self.routing = dict(ROUTING if routing is None else routing)
        self.deadline = time.monotonic() + seconds
        self.capture = capture
        self.output_fd = None
        self.phase = 'INITIALIZE'
        self.details = {}
        self.report = {'contract': 'PR114-POINT4-READONLY-OBSERVATION-1',
            'started_at': instant(), 'self_sha256': self_sha256,
            'status': 'PARTIAL', 'business_source_writes': False,
            'business_SQL_writes': False, 'services_changed': False,
            'private_source_bytes_exported': False, 'database_copy_created': False,
            'sqlite_mode': 'URI mode=ro; query_only; short BEGIN read transactions',
            'sqlite_reader_semantics': 'Normal reader locks/shared-memory may be used; no zero-byte-change claim for SQLite coordination files.',
            'scope': 'Double-read stable observation, not an atomic global snapshot or runtime writer-exclusion gate.',
            'max_seconds': seconds, 'output': str(output), 'blockers': []}

    def check(self):
        if time.monotonic() >= self.deadline:
            raise Stop('TIME_BOUND_EXCEEDED')

    def read_file(self, path, *, collect=False, maximum=MAX_FILE):
        self.check()
        path = Path(path)
        parent_fd = open_directory(path.parent)
        fd = None
        try:
            before = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
                raise Stop('REGULAR_BOUNDED_FILE_REQUIRED')
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            if stamp(before) != stamp(os.fstat(fd)):
                raise Stop('FILE_CHANGED_BEFORE_READ')
            h = hashlib.sha256()
            chunks = [] if collect else None
            total = 0
            while True:
                self.check()
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum:
                    raise Stop('FILE_BYTE_BOUND_EXCEEDED')
                h.update(chunk)
                if collect:
                    chunks.append(chunk)
            after = os.fstat(fd)
            named = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
            if total != before.st_size or stamp(before) != stamp(after) or stamp(after) != stamp(named):
                raise Stop('FILE_CHANGED_DURING_READ')
            return ({'sha256': h.hexdigest(), 'bytes': total,
                     'mode': stat.S_IMODE(before.st_mode)}, stamp(after),
                    b''.join(chunks) if collect else None)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(parent_fd)

    def prepare_output(self):
        parent = self.root / 'autopilot_inbox' / 'cloud'
        if self.output.parent != parent or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', self.output.name):
            raise Stop('NEW_DIRECT_CHILD_OF_EXISTING_PRIVATE_INBOX_REQUIRED')
        fd = open_directory(parent)
        try:
            try:
                os.mkdir(self.output.name, mode=0o700, dir_fd=fd)
            except FileExistsError:
                raise Stop('OUTPUT_ALREADY_EXISTS_RECONCILE_DO_NOT_REPEAT') from None
            self.output_fd = os.open(self.output.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.fchmod(self.output_fd, 0o700)
        finally:
            os.close(fd)

    def write_new(self, name, data, parent_fd=None):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name):
            raise Stop('OUTPUT_BASENAME_REQUIRED')
        if parent_fd is None:
            parent_fd = self.output_fd
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent_fd)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)

    def names(self):
        found = set()
        root_fd = open_directory(self.root)
        try:
            with os.scandir(root_fd) as entries:
                for item in entries:
                    self.check()
                    if Path(item.name).suffix in ('.py', '.html', '.css', '.js'):
                        found.add(item.name)
                        if len(found) > MAX_FILES:
                            raise Stop('INVENTORY_FILE_BOUND_EXCEEDED')
        finally:
            os.close(root_fd)
        def walk(relative):
            self.check()
            directory_fd = open_directory(self.root / relative)
            try:
                with os.scandir(directory_fd) as entries:
                    for item in entries:
                        self.check()
                        name = relative + '/' + item.name
                        info = item.stat(follow_symlinks=False)
                        if stat.S_ISDIR(info.st_mode):
                            yield from walk(name)
                        elif stat.S_ISREG(info.st_mode):
                            yield name
                        else:
                            raise Stop('NONREGULAR_PUBLIC_TREE_ENTRY')
            finally:
                os.close(directory_fd)
        for base in ('site', 'video'):
            for name in walk(base):
                found.add(name)
                if len(found) > MAX_FILES:
                    raise Stop('INVENTORY_FILE_BOUND_EXCEEDED')
        return sorted(found)

    def inventory(self, number, core_names):
        self.phase = 'INVENTORY_PASS_' + str(number)
        result, stamps, captures = {}, {}, {}
        total, captured_bytes = 0, 0
        expected = self.names()
        # Preserve even interrupted manifests as explicitly partial evidence.
        self.details['inventory_pass_' + str(number)] = result
        for name in expected:
            collect = number == 1 and self.capture and name in core_names
            item, info, raw = self.read_file(self.root / name, collect=collect,
                                            maximum=MAX_HTML if name in core_names else MAX_FILE)
            total += item['bytes']
            if total > MAX_BYTES:
                raise Stop('INVENTORY_TOTAL_BYTE_BOUND_EXCEEDED')
            result[name], stamps[name] = item, info
            if collect:
                captured_bytes += len(raw)
                if captured_bytes > MAX_CAPTURE_TOTAL:
                    raise Stop('PUBLIC_HTML_CAPTURE_TOTAL_BOUND_EXCEEDED')
                try:
                    raw.decode('utf-8')
                except UnicodeDecodeError:
                    raise Stop('CAPTURED_PUBLIC_HTML_NOT_UTF8') from None
                captures[name] = raw
        if self.names() != expected:
            raise Stop('INVENTORY_MEMBERSHIP_CHANGED_DURING_PASS')
        return result, stamps, captures

    def named_files(self, names):
        files, stamps = {}, {}
        for name, path in sorted(names.items()):
            files[name], stamps[name], _ = self.read_file(path, maximum=MAX_HTML)
        return files, stamps

    def database(self):
        self.check()
        path = self.root / 'crm.db'
        initial = safe_stat(path)
        conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=0.5)
        try:
            # No private module imported. SQLite may use normal reader locks.
            conn.execute('PRAGMA query_only=ON')
            conn.set_progress_handler(lambda: int(time.monotonic() >= self.deadline), 5000)
            conn.execute('BEGIN')
            if conn.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise Stop('CRM_QUICK_CHECK_FAILED')
            identity = []
            counts = {}
            def table(name):
                cursor = conn.execute('SELECT * FROM ' + name + ' ORDER BY rowid')
                columns = [c[0] for c in cursor.description]
                h = hashlib.sha256(b'[')
                count = 0
                for row in cursor:
                    self.check()
                    count += 1
                    if count > MAX_ROWS:
                        raise Stop('DATABASE_ROW_BOUND_EXCEEDED')
                    item = dict(zip(columns, row))
                    raw = encoded(item)
                    if count > 1:
                        h.update(b',')
                    h.update(raw)
                    if name == 'cars' and item.get('published') == 1:
                        identity.append({key: item.get(key) for key in FIELDS})
                h.update(b']')
                counts[name] = count
                return h.hexdigest()
            cars_hash, audit_hash = table('cars'), table('audit')
            codes = [r['auto_number'] for r in identity]
            if len(codes) != len(set(codes)) or any(type(c) is not str or not re.fullmatch(r'UA-[0-9]{4}', c) for c in codes):
                raise Stop('PUBLISHED_IDENTITIES_INVALID')
            schema = conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall()
            result = {'database': {'cars_sha256': cars_hash, 'audit_sha256': audit_hash,
                'published_sha256': sha(encoded(identity)), 'published_codes': sorted(codes)},
                'schema_sha256': sha(encoded(schema)), 'published_rows': identity,
                'row_counts': counts, 'quick_check': 'ok',
                'legacy_UA_fallback_requires_review': any(r['price_uah'] in (None, '', 0) for r in identity)}
            conn.rollback()
            after = safe_stat(path)
            # Main DB inode replacement during a SQL read invalidates binding;
            # WAL or normal DB content changes are handled by the second SQL snapshot.
            if initial[:2] != after[:2]:
                raise Stop('DATABASE_INODE_CHANGED_DURING_SNAPSHOT')
            result['database_file_identity'] = list(after[:2])
            return result
        finally:
            conn.close()

    def save_captures(self, captures):
        os.mkdir('public_html', mode=0o700, dir_fd=self.output_fd)
        top = os.open('public_html', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                      dir_fd=self.output_fd)
        try:
            for folder in ('site', 'video'):
                os.mkdir(folder, mode=0o700, dir_fd=top)
                fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=top)
                try:
                    for name, data in captures.items():
                        if name.startswith(folder + '/'):
                            self.write_new(Path(name).name, data, fd)
                finally:
                    os.close(fd)
        finally:
            os.close(top)

    def export_text(self, captures):
        """Plain UTF-8 chunks for authenticated visible-editor retrieval.

        No base64 or private source/DB content. The final manifest hashes the
        exact reconstructed bytes, independently of JSONL whitespace/escaping.
        The inventory contains only paths/hashes/modes/sizes, never file bytes.
        """
        manifest = {}
        artifacts = dict(captures)
        artifacts['published_price_rows.json'] = encoded(self.report.get('published_rows', [])) + b'\n'
        for name, inventory in self.details.items():
            artifacts[name + '.json'] = encoded(inventory) + b'\n'
        artifacts['observation_summary.json'] = encoded(self.report) + b'\n'
        h = hashlib.sha256()
        total, index = 0, 0
        fd = os.open('public_inputs.jsonl', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=self.output_fd)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                def write_line(row):
                    nonlocal total
                    raw = (json.dumps(row, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')) + '\n').encode('utf-8')
                    stream.write(raw)
                    h.update(raw)
                    total += len(raw)
                for name, raw in sorted(artifacts.items()):
                    text = raw.decode('utf-8')
                    manifest[name] = {'bytes': len(raw), 'sha256': sha(raw)}
                    for offset in range(0, len(text), 3000):
                        write_line({'index': index, 'name': name,
                                    'offset_chars': offset, 'text': text[offset:offset+3000]})
                        index += 1
                write_line({'kind': 'FINAL_MANIFEST', 'artifacts': manifest,
                            'chunk_records': index, 'content_encoding': 'UTF-8',
                            'snapshot_status': self.report['status']})
                stream.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        return {'path': 'public_inputs.jsonl', 'bytes': total,
                'sha256': h.hexdigest(), 'chunk_records': index,
                'final_manifest': manifest}

    def run(self):
        self.prepare_output()  # Refuse reuse; never overwrite a prior outcome.
        captures = {}
        old_handler = signal.getsignal(signal.SIGALRM)
        def alarm(signum, frame):
            raise Stop('TIME_BOUND_EXCEEDED')
        signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, max(0.01, self.deadline - time.monotonic()))
        try:
            self.phase = 'DATABASE_FIRST'
            db1 = self.database()
            self.report.update(db1)
            self.report['first_SQL_observed_at'] = instant()
            core = {f'{folder}/{code}.html' for folder in ('site', 'video')
                    for code in db1['database']['published_codes']}
            core |= {f'{folder}/{name}.html' for folder in ('site', 'video') for name in ('index', 'katalog')}
            source_paths = {name: self.root / name for name in SOURCES | DEPENDENCIES | EXTRA}
            self.phase = 'SOURCES_ROUTING_FIRST'
            source1, source_stamp1 = self.named_files(source_paths)
            routing1, routing_stamp1 = self.named_files(self.routing)
            self.report['sources_dependencies_extra'] = source1
            self.report['routing_sources'] = routing1
            self.report['routing_scope'] = 'Five source hashes only; static mapping and HTTP routing are NOT freshly observed by this script.'
            inv1, stamps1, captures = self.inventory(1, core)
            if not core <= set(inv1):
                raise Stop('PUBLISHED_CORE_HTML_MISSING')
            self.report['core_html'] = {n: inv1[n] for n in sorted(core)}
            inv2, stamps2, _ = self.inventory(2, core)
            self.phase = 'SOURCES_ROUTING_SECOND'
            source2, source_stamp2 = self.named_files(source_paths)
            routing2, routing_stamp2 = self.named_files(self.routing)
            self.phase = 'DATABASE_SECOND'
            db2 = self.database()
            self.report['second_SQL_observed_at'] = instant()
            self.report['second_database'] = db2['database']
            self.report['second_schema_sha256'] = db2['schema_sha256']
            stable = {'database_and_published_rows': db1 == db2,
                'source_hashes_and_stamps': source1 == source2 and source_stamp1 == source_stamp2,
                'routing_hashes_and_stamps': routing1 == routing2 and routing_stamp1 == routing_stamp2,
                'all_inventory_hashes_and_stamps': inv1 == inv2 and stamps1 == stamps2,
                'sources_equal_inventory': all(inv1.get(n) == source1[n] for n in source1),
                'routing_root_files_equal_inventory': all(inv1.get(n) == routing1[n] for n in routing1 if n != 'observed_wsgi_config.py')}
            self.report['stability'] = stable
            self.report['system_inventory_sha256'] = sha(encoded(inv1))
            self.report['system_inventory_count'] = len(inv1)
            self.report['system_inventory_bytes'] = sum(x['bytes'] for x in inv1.values())
            if not all(stable.values()):
                raise Stop('OBSERVATION_DRIFT_DO_NOT_REUSE_CANDIDATE')
            if db1['legacy_UA_fallback_requires_review']:
                raise Stop('LEGACY_UKRAINE_FALLBACK_REQUIRES_REVIEW')
            self.check()
            self.report['status'] = 'PASS_DOUBLE_READ_STABLE_OBSERVATION'
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                self.report['blockers'].append('INTERRUPTED')
            elif isinstance(exc, Stop):
                self.report['blockers'].append(str(exc))
            else:
                # Never print private SQL values or source fragments in errors.
                self.report['blockers'].append(type(exc).__name__)
                if isinstance(exc, OSError):
                    self.report['errno'] = exc.errno
            self.report['status'] = 'PARTIAL_NOT_ACCEPTED'
            self.report['stopped_phase'] = self.phase
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        try:
            for name, value in self.details.items():
                self.write_new(name + '.json', encoded(value) + b'\n')
            if self.capture and captures:
                self.save_captures(captures)
                self.report['captured_public_html_files'] = len(captures)
                self.report['captured_public_html_are_partial_unless_PASS'] = True
            self.report['finished_at'] = instant()
            self.report['plaintext_export'] = self.export_text(captures)
            self.write_new('summary.json', encoded(self.report) + b'\n')
            os.fsync(self.output_fd)
            return self.report
        finally:
            os.close(self.output_fd)
            self.output_fd = None


def main():
    if not sys.flags.isolated:
        raise Stop('RUN_WITH_PYTHON_ISOLATED_FLAG_I_REQUIRED')
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--self-sha256', required=True)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--capture-html', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}', args.self_sha256) or not 1 <= args.seconds <= 180:
        raise Stop('VALID_SELF_PIN_AND_BOUND_REQUIRED')
    probe = Observer(ROOT, args.output, seconds=args.seconds, capture=args.capture_html,
                     self_sha256=args.self_sha256)
    actual, _, _ = probe.read_file(Path(__file__).absolute(), maximum=1024 * 1024)
    if actual['sha256'] != args.self_sha256:
        raise Stop('OBSERVER_SELF_SHA256_MISMATCH')
    result = probe.run()
    print(encoded(result).decode())
    return 0 if result['status'] == 'PASS_DOUBLE_READ_STABLE_OBSERVATION' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Stop as exc:
        print(encoded({'status': 'NOT_STARTED', 'blocker': str(exc)}).decode())
        raise SystemExit(2)
