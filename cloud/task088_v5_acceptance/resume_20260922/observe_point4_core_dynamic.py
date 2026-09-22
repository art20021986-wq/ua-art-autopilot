#!/usr/bin/env python3
"""Bounded read-only business-state observer; never an installation or writer gate.

Only a NEW 0700 directory under the existing autopilot_inbox/cloud receives
0600 reports and optional copies of public core HTML. Private source bytes and
database rows other than six public vehicle fields are never exported.
SQLite uses normal mode=ro reader locking/shared-memory semantics, NOT immutable.
Two core-HTML hash passes and two short SQLite transactions must agree.
No recursive inventory or media-byte scan is performed.
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
import posixpath
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote

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


NEW_CODES = frozenset('UA-%04d' % number for number in range(19, 23))
RUNTIME_MODULES = frozenset(('uaart_market_prices.py', 'uaart_price_sync_outbox.py',
    'uaart_price_sync_runtime.py', 'uaart_price_sync_binding.py', 'owner_policy.py',
    'price_publication.py', 'uaart_price_sync_confirmation.py', 'uaart_price_control_reader.py',
    'publication_fence.py', 'mutation_recovery.py', 'visibility_lifecycle.py'))
PART_MAX_BYTES = 800 * 1024
MAX_REFERENCES = 2048


class References(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.anchors, self.media = [], []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == 'a' and attrs.get('href'):
            self.anchors.append((attrs['href'], attrs.get('class', '')))
        for key in ('src', 'poster'):
            if attrs.get(key):
                self.media.append(attrs[key])
        if tag == 'a' and re.search(r'\.(?:jpg|jpeg|png|webp|gif|mp4|webm|pdf)(?:[?#]|$)', attrs.get('href', ''), re.I):
            self.media.append(attrs['href'])

    handle_startendtag = handle_starttag


def public_reference(page, href):
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in ('http', 'https', '') or parsed.netloc not in ('uaart.com.ua', 'www.uaart.com.ua'):
            return None
    path = parsed.path
    if not path or unquote(path) != path or '\\' in path or '\x00' in path:
        return None
    resolved = posixpath.normpath(path.lstrip('/') if path.startswith('/') else posixpath.join(posixpath.dirname(page), path))
    if not resolved.startswith(('site/', 'video/')) or resolved.startswith('../'):
        return None
    return resolved


class CoreObserver:
    def __init__(self, root, output, *, seconds=180, capture=False,
                 routing=None, self_sha256=None, part_max_bytes=PART_MAX_BYTES):
        self.root = Path(root)
        self.output = Path(output)
        self.routing = dict(ROUTING if routing is None else routing)
        self.total_deadline = time.monotonic() + seconds
        self.deadline = self.total_deadline - min(20, seconds * .2)
        self.part_max_bytes = part_max_bytes
        if not 16 * 1024 <= part_max_bytes <= PART_MAX_BYTES:
            raise Stop("EXPORT_PART_BYTE_BOUND_REQUIRED")
        self.captures = {}
        self.capture = capture
        self.output_fd = None
        self.phase = 'INITIALIZE'
        self.details = {}
        self.report = {'contract': 'PR114-POINT4-CORE-READONLY-OBSERVATION-1',
            'started_at': instant(), 'self_sha256': self_sha256,
            'status': 'PARTIAL', 'business_source_writes': False,
            'business_SQL_writes': False, 'services_changed': False,
            'private_source_bytes_exported': False, 'database_copy_created': False,
            'sqlite_mode': 'URI mode=ro; query_only; short BEGIN read transactions',
            'sqlite_reader_semantics': 'Normal reader locks/shared-memory may be used; no zero-byte-change claim for SQLite coordination files.',
            'scope': 'core_only double-read candidate inputs; not full inventory, backup, Gate B or writer exclusion.',
            'full_inventory_observed': False, 'gate_b': False, 'backup': False,
            'media_bytes_hashed': False, 'part_max_bytes': part_max_bytes,
            'export_completed': False,
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
        if time.monotonic() >= self.total_deadline:
            raise Stop('TOTAL_TIME_BOUND_EXCEEDED_BEFORE_CAPTURE_SAVE')
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
                            if time.monotonic() >= self.total_deadline:
                                raise Stop('TOTAL_TIME_BOUND_EXCEEDED_DURING_CAPTURE_SAVE')
                            self.write_new(Path(name).name, data, fd)
                finally:
                    os.close(fd)
        finally:
            os.close(top)


    def core_pass(self, number, names):
        self.phase = 'CORE_HTML_PASS_' + str(number)
        result, stamps = {}, {}
        self.details['core_pass_' + str(number)] = result
        for name in sorted(names):
            item, info, raw = self.read_file(self.root / name, collect=number == 1, maximum=MAX_HTML)
            result[name], stamps[name] = item, info
            if raw is not None:
                raw.decode('utf-8')
                if sum(len(value) for value in self.captures.values()) + len(raw) > MAX_CAPTURE_TOTAL:
                    raise Stop('PUBLIC_HTML_CAPTURE_TOTAL_BOUND_EXCEEDED')
                self.captures[name] = raw
        return result, stamps

    def diagnostic_targets(self, codes):
        targets = {}
        for folder in ('site', 'video'):
            for code in sorted(codes):
                page = folder + '/' + code + '.html'
                parsed = References(self.captures[page].decode('utf-8'))
                matching = set()
                for href, classes in parsed.anchors:
                    if 'diag' in classes or urlsplit(href).path.endswith(code + '-diag.html'):
                        target = public_reference(page, href)
                        if target is None or Path(target).name != code + '-diag.html':
                            raise Stop('NEW_CARD_DIAGNOSTIC_LINK_UNMAPPED')
                        matching.add(target)
                if len(matching) != 1:
                    raise Stop('NEW_CARD_EXACT_DIAGNOSTIC_TARGET_REQUIRED')
                targets[page] = next(iter(matching))
        return targets

    def supporting_pages(self, number):
        self.phase = 'SUPPORTING_PUBLIC_HTML_PASS_' + str(number)
        result, stamps = {}, {}
        for folder in ('video', 'site'):
            for basename in ('info.html', 'podbor.html'):
                name = folder + '/' + basename
                try:
                    item, info, raw = self.read_file(self.root / name, collect=number == 1, maximum=MAX_HTML)
                except FileNotFoundError:
                    result[name] = {'exists': False}
                    continue
                result[name], stamps[name] = item, info
                if raw is not None:
                    raw.decode('utf-8')
                    if sum(len(value) for value in self.captures.values()) + len(raw) > MAX_CAPTURE_TOTAL:
                        raise Stop('PUBLIC_HTML_CAPTURE_TOTAL_BOUND_EXCEEDED')
                    self.captures[name] = raw
        return result, stamps

    def runtime_modules(self, number):
        self.phase = 'KNOWN_RUNTIME_MODULES_PASS_' + str(number)
        result, stamps = {}, {}
        for name in sorted(RUNTIME_MODULES):
            try:
                item, info, _ = self.read_file(self.root / name, maximum=MAX_HTML)
            except FileNotFoundError:
                # read_file opens the already established root without following
                # symlinks; only this exact allowlisted basename may be absent.
                result[name] = {'exists': False}
                continue
            result[name], stamps[name] = {'exists': True, **item}, info
        return result, stamps

    def diagnostic_pass(self, number, targets):
        self.phase = 'NEW_CARD_DIAGNOSTIC_PASS_' + str(number)
        result, stamps = {}, {}
        self.details['diagnostic_pass_' + str(number)] = result
        for name in sorted(set(targets.values())):
            item, info, raw = self.read_file(self.root / name, collect=number == 1, maximum=MAX_HTML)
            result[name], stamps[name] = item, info
            if raw is not None:
                raw.decode('utf-8')
                if sum(len(value) for value in self.captures.values()) + len(raw) > MAX_CAPTURE_TOTAL:
                    raise Stop('PUBLIC_HTML_CAPTURE_TOTAL_BOUND_EXCEEDED')
                self.captures[name] = raw
        return result, stamps

    def media_metadata(self, page_names):
        self.phase = 'NEW_CARD_REFERENCED_MEDIA_STAT_ONLY'
        references = set()
        for page in sorted(page_names):
            for href in References(self.captures[page].decode('utf-8')).media:
                target = public_reference(page, href)
                if target is not None:
                    references.add(target)
                if len(references) > MAX_REFERENCES:
                    raise Stop('NEW_CARD_REFERENCE_BOUND_EXCEEDED')
        result = {}
        for name in sorted(references):
            self.check()
            try:
                info = safe_stat(self.root / name)
                result[name] = {'exists': True, 'bytes': info[2], 'mode': info[5],
                                'stat_stamp': list(info), 'content_sha256': None,
                                'scope': 'STAT_ONLY_NO_MEDIA_BYTES_READ'}
            except FileNotFoundError:
                result[name] = {'exists': False, 'scope': 'MISSING_LOCAL_REFERENCE_NO_WRITE'}
        return result

    def export_parts(self):
        """Single-line JSON parts for Files UI, each independently hash-bound."""
        artifacts = dict(self.captures)
        artifacts['published_price_rows.json'] = encoded(self.report.get('published_rows', [])) + b'\n'
        artifacts['observation_summary.json'] = encoded(self.report) + b'\n'
        for name, value in self.details.items():
            artifacts[name + '.json'] = encoded(value) + b'\n'
        manifest = {name: {'bytes': len(raw), 'sha256': sha(raw)} for name, raw in sorted(artifacts.items())}
        parts, records = [], []
        records_bytes = 0
        next_index = 0
        def part_bytes(items, number):
            return json.dumps({'kind': 'PUBLIC_INPUTS_PART', 'part': number,
                'snapshot_status': self.report['status'], 'records': items},
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        def flush():
            nonlocal records_bytes
            if not records:
                return
            raw = part_bytes(records, len(parts))
            if len(raw) > self.part_max_bytes:
                raise Stop('EXPORT_PART_BYTE_BOUND_EXCEEDED')
            name = 'public_inputs_%03d.json' % len(parts)
            self.write_new(name, raw)
            parts.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw),
                          'first_index': records[0]['index'], 'last_index': records[-1]['index']})
            records.clear()
            records_bytes = 0
        for name, raw in sorted(artifacts.items()):
            text = raw.decode('utf-8')
            for offset in range(0, len(text), 1000):
                if time.monotonic() >= self.total_deadline:
                    raise Stop('TOTAL_TIME_BOUND_EXCEEDED_DURING_EXPORT')
                row = {'index': next_index, 'name': name, 'offset_chars': offset,
                       'text': text[offset:offset + 1000]}
                row_bytes = len(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                          separators=(',', ':')).encode('utf-8'))
                estimated = len(part_bytes([], len(parts))) + records_bytes + row_bytes + len(records)
                if records and estimated > self.part_max_bytes:
                    flush()
                records.append(row)
                records_bytes += row_bytes
                next_index += 1
        flush()
        result = {'format': 'ONE_LINE_JSON_PARTS_UTF8', 'parts': parts, 'artifacts': manifest,
                  'chunk_records': next_index, 'part_max_bytes': self.part_max_bytes,
                  'reconstruction': 'Concatenate text by increasing index; require exact offset_chars per artifact, then validate bytes and sha256.'}
        self.write_new('export_manifest.json', encoded(result))
        return result

    def run(self):
        self.prepare_output()
        old_handler = signal.getsignal(signal.SIGALRM)
        def alarm(signum, frame):
            raise Stop('TOTAL_TIME_BOUND_EXCEEDED')
        signal.signal(signal.SIGALRM, alarm)
        signal.setitimer(signal.ITIMER_REAL, max(.01, self.total_deadline - time.monotonic()))
        try:
            try:
                self.phase = 'DATABASE_FIRST'
                db1 = self.database()
                self.report.update(db1)
                self.report['first_SQL_observed_at'] = instant()
                codes = set(db1['database']['published_codes'])
                # The validated published set is dynamic after normal CRM edits.
                # database() still rejects duplicate or malformed public codes.
                if not codes:
                    raise Stop('PUBLISHED_CARS_REQUIRED')
                core = {f'{folder}/{code}.html' for folder in ('site', 'video') for code in codes}
                core |= {f'{folder}/{name}.html' for folder in ('site', 'video') for name in ('index', 'katalog')}
                source_paths = {name: self.root / name for name in SOURCES | DEPENDENCIES | EXTRA}
                self.phase = 'SOURCES_ROUTING_FIRST'
                source1, source_stamp1 = self.named_files(source_paths)
                routing1, routing_stamp1 = self.named_files(self.routing)
                self.report['sources_dependencies_extra'] = source1
                self.report['routing_sources'] = routing1
                self.report['routing_scope'] = 'Source hashes only; static mapping and HTTP routing NOT observed.'
                runtime1, runtime_stamp1 = self.runtime_modules(1)
                self.report['runtime_modules'] = runtime1
                core1, core_stamp1 = self.core_pass(1, core)
                self.report['core_html'] = core1
                self.report['core_manifest_sha256'] = sha(encoded(core1))
                self.report['core_html_count'] = len(core1)
                targets = self.diagnostic_targets(codes)
                self.report['published_diagnostic_targets'] = targets
                diag1, diag_stamp1 = self.diagnostic_pass(1, targets)
                self.report['diagnostic_html'] = diag1
                support1, support_stamp1 = self.supporting_pages(1)
                self.report['supporting_html'] = support1
                new_pages = {name for name in targets if Path(name).stem in NEW_CODES}
                new_pages |= {targets[name] for name in new_pages}
                media1 = self.media_metadata(new_pages)
                self.report['media_reference_metadata'] = media1
                core2, core_stamp2 = self.core_pass(2, core)
                diag2, diag_stamp2 = self.diagnostic_pass(2, targets)
                support2, support_stamp2 = self.supporting_pages(2)
                media2 = self.media_metadata(new_pages)
                self.phase = 'SOURCES_ROUTING_SECOND'
                source2, source_stamp2 = self.named_files(source_paths)
                routing2, routing_stamp2 = self.named_files(self.routing)
                runtime2, runtime_stamp2 = self.runtime_modules(2)
                self.phase = 'DATABASE_SECOND'
                db2 = self.database()
                self.report['second_SQL_observed_at'] = instant()
                self.report['second_database'] = db2['database']
                self.report['second_schema_sha256'] = db2['schema_sha256']
                stable = {'database_and_published_rows': db1 == db2,
                    'source_hashes_and_stamps': source1 == source2 and source_stamp1 == source_stamp2,
                    'routing_hashes_and_stamps': routing1 == routing2 and routing_stamp1 == routing_stamp2,
                    'core_html_hashes_and_stamps': core1 == core2 and core_stamp1 == core_stamp2,
                    'diagnostic_hashes_and_stamps': diag1 == diag2 and diag_stamp1 == diag_stamp2,
                    'supporting_html_hashes_and_stamps': support1 == support2 and support_stamp1 == support_stamp2,
                    'runtime_modules_hashes_and_stamps': runtime1 == runtime2 and runtime_stamp1 == runtime_stamp2,
                    'known_runtime_source_overlap': all(runtime1[n] == {'exists': True, **source1[n]}
                        for n in set(runtime1) & set(source1)),
                    'referenced_media_metadata_only': media1 == media2,
                    'home_routing_equal_core': all(core1.get(n) == routing1[n] for n in routing1 if n in core1)}
                self.report['stability'] = stable
                if not all(stable.values()):
                    raise Stop('OBSERVATION_DRIFT_DO_NOT_REUSE_CANDIDATE')
                if db1['legacy_UA_fallback_requires_review']:
                    raise Stop('LEGACY_UKRAINE_FALLBACK_REQUIRES_REVIEW')
                self.check()
                self.report['status'] = 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION'
            except BaseException as exc:
                self.report['status'] = 'PARTIAL_NOT_ACCEPTED'
                self.report['stopped_phase'] = self.phase
                self.report['blockers'].append(str(exc) if isinstance(exc, Stop) else type(exc).__name__)
                if isinstance(exc, OSError):
                    self.report['errno'] = exc.errno
            self.phase = 'SAVE_COMPLETED_CORE_CAPTURES'
            if time.monotonic() >= self.total_deadline:
                raise Stop('TOTAL_TIME_BOUND_EXCEEDED_BEFORE_CAPTURE_SAVE')
            if self.captures:
                self.save_captures(self.captures)
            self.report['captured_public_html_files'] = len(self.captures)
            self.report['captured_public_html_are_partial_unless_PASS'] = True
            self.report['finished_at'] = instant()
            # Save actual observation outcome before the larger visible export.
            self.write_new('observation_outcome.json', encoded(self.report))
            self.phase = 'SPLIT_VISIBLE_EXPORT'
            self.report['plaintext_export'] = self.export_parts()
            self.report['export_completed'] = True
            self.write_new('summary.json', encoded(self.report))
            os.fsync(self.output_fd)
            return self.report
        except BaseException as exc:
            self.report['status'] = 'PARTIAL_NOT_ACCEPTED'
            self.report['stopped_phase'] = self.phase
            self.report['blockers'].append(str(exc) if isinstance(exc, Stop) else type(exc).__name__)
            # This tiny best-effort outcome is the only post-alarm write. No
            # unbounded retry or continuation of an interrupted export occurs.
            try:
                self.write_new('partial_export_outcome.json', encoded(self.report))
            except BaseException:
                pass
            return self.report
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
            os.close(self.output_fd)
            self.output_fd = None


def main():
    if not sys.flags.isolated:
        raise Stop('RUN_WITH_PYTHON_ISOLATED_FLAG_I_REQUIRED')
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--self-sha256', required=True)
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--part-max-bytes', type=int, default=PART_MAX_BYTES)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}', args.self_sha256) or not 1 <= args.seconds <= 180:
        raise Stop('VALID_SELF_PIN_AND_BOUND_REQUIRED')
    probe = CoreObserver(ROOT, args.output, seconds=args.seconds, capture=True,
                         self_sha256=args.self_sha256, part_max_bytes=args.part_max_bytes)
    actual, _, _ = probe.read_file(Path(__file__).absolute(), maximum=1024 * 1024)
    if actual['sha256'] != args.self_sha256:
        raise Stop('OBSERVER_SELF_SHA256_MISMATCH')
    result = probe.run()
    print(encoded(result).decode())
    return 0 if result['status'] == 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION' else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Stop as exc:
        print(encoded({'status': 'NOT_STARTED', 'blocker': str(exc)}).decode())
        raise SystemExit(2)
