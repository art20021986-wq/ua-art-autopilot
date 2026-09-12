"""Relocatable isolated-copy data install/rollback verification; no live authority.

Every application mutation is inside a new TemporaryDirectory. The verifier
below is explicitly synthetic test evidence and cannot authorize production.
"""
from __future__ import annotations
import argparse
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import sys
import tempfile
import time
import unittest
import uuid

from . import data_install as d
from .render import normalize_facts, validate_page
from cloud.writer_coordination_001 import server_fence

YEAR_REVIEW_SHA256 = '581c2d89bd10417c18748b25e0bc3ac53a729f0c23408a8e327efe854dec98dd'


def synthetic_stage_authority(plan, challenge, phase):
    """Fixture only, called solely against throwaway stage roots by run()."""
    now = time.time()
    return {'status': d.PROOF_STATUS, 'challenge': challenge, 'session': plan['session'],
            'install_plan_sha256': plan['install_plan_sha256'],
            'coordination_plan_sha256': plan['coordination_plan_sha256'],
            'candidate_manifest_sha256': plan['manifest']['manifest_sha256'],
            'issued_at': now, 'expires_at': now + 20,
            'authorization_receipt_sha256': d.digest(['SYNTHETIC_STAGE_ONLY', 'authorization']),
            'pause_readback_sha256': d.digest(['SYNTHETIC_STAGE_ONLY', 'pause']),
            'drain_receipt_sha256': d.digest(['SYNTHETIC_STAGE_ONLY', 'drain']),
            'storage_quota': {'source': 'AUTHENTICATED_PYTHONANYWHERE_ACCOUNT_QUOTA',
                              'used_bytes': 0, 'quota_bytes': 10**12, 'observed_at': now,
                              'receipt_sha256': d.digest(['SYNTHETIC_STAGE_ONLY', 'quota'])}}


def _approved_year_before(raw, relative, review):
    if not relative.endswith('/UA-0016.html'):
        return raw, 0
    record = review['pages'].get(relative)
    d.require(isinstance(record, dict) and record.get('source_sha256') == d.sha(raw), 'YEAR_REVIEW_PAGE_PIN')
    edits = record.get('edits')
    d.require(isinstance(edits, list) and len(edits) == 8 and edits == sorted(edits, key=lambda x: x['start']), 'EXACT_EIGHT_REVIEWED_YEAR_SPANS')
    previous_end = -1
    for item in edits:
        start, end = item['start'], item['end']
        d.require(type(start) is int and type(end) is int and 0 <= start < end <= len(raw) and start >= previous_end, 'YEAR_REVIEW_RANGE')
        d.require(item.get('old') == '1999' and item.get('new') == '2017' and raw[start:end] == b'1999', 'YEAR_REVIEW_VALUE')
        before, after = item.get('context_before', '').encode(), item.get('context_after', '').encode()
        d.require(len(before) >= 8 and len(after) >= 8 and raw[start-len(before):start] == before and raw[end:end+len(after)] == after, 'YEAR_REVIEW_CONTEXT')
        d.require(item.get('reason') in {'main_vehicle_year', 'vehicle_title', 'vehicle_metadata', 'vehicle_summary'}, 'YEAR_REVIEW_REASON')
        previous_end = end
    d.require(any(item['reason'] == 'main_vehicle_year' for item in edits), 'YEAR_MAIN_VALUE_NOT_REVIEWED')
    result = raw
    for item in reversed(edits):
        result = result[:item['start']] + b'2017' + result[item['end']:]
    return result, len(edits)


def _copy_exact(source, target):
    item = d.read(source)
    d.exclusive(target, item['data'], item['mode'])
    os.utime(target, ns=(item['atime_ns'], item['mtime_ns']), follow_symlinks=False)
    return item['sha256']


def _read_facts(path):
    with d.db_read(path) as conn:
        all_rows = conn.execute('SELECT f.uid,f.payload FROM facts f JOIN vehicles v ON f.uid=v.uid AND f.revision=v.revision ORDER BY f.uid,f.key').fetchall()
        vehicles = conn.execute('SELECT uid,published,tombstoned FROM vehicles ORDER BY uid').fetchall()
        integrity = conn.execute('PRAGMA integrity_check').fetchall()
    d.require(integrity == [('ok',)], 'INSTALLED_STORE_INTEGRITY')
    d.require(vehicles == [(uid, 1, 0) for uid in d.UIDS] + [(uid, 0, 0) for uid in d.DRAFTS], 'INSTALLED_VEHICLE_SCOPE')
    facts = {uid: [] for uid in d.UIDS + d.DRAFTS}
    for uid, payload in all_rows:
        d.require(uid in facts, 'INSTALLED_FOREIGN_UID')
        facts[uid].append(json.loads(payload))
    d.require(len(all_rows) == 557 and all(not facts[uid] for uid in d.DRAFTS), 'INSTALLED_557_FACT_SCOPE')
    return facts


def run(snapshot, payload, year_review):
    snapshot, payload = d.directory(Path(snapshot).absolute()), d.directory(Path(payload).absolute())
    year_review = Path(year_review).absolute()
    reviewed_raw = d.read(year_review)['data']
    d.require(d.sha(reviewed_raw) == YEAR_REVIEW_SHA256, 'APPROVED_YEAR_REVIEW_SHA_REQUIRED')
    review = json.loads(reviewed_raw)
    d.require(review.get('schema') == 'UA-ART-MANUAL16-YEAR-SPANS-1' and set(review['pages']) == {'video/UA-0016.html', 'site/UA-0016.html'}, 'YEAR_REVIEW_SCHEMA_SCOPE')
    snapshot_raw = d.read(snapshot / 'snapshot.json')['data']
    captured = json.loads(snapshot_raw)
    records = {item['path']: item for item in captured['records']}
    input_manifest = d.make_manifest(snapshot, payload)
    source_files = d.PAGES + ['crm.db', 'vin_specs_task111_v3.db']
    source_hashes = {name: d.file_hash(snapshot / name) for name in source_files}
    for name, value in source_hashes.items():
        d.require(value == records[name]['sha256'], 'CAPTURE_PIN_MISMATCH:' + name)
    payload_hashes = {item['payload']: d.file_hash(payload / item['payload']) for item in input_manifest['files'].values()}
    if (payload / 'receipt.json').exists():
        prepared = json.loads(d.read(payload / 'receipt.json')['data'])
        d.require(prepared.get('input_snapshot_sha256') == d.sha(snapshot_raw)
                  and prepared.get('candidate_pages') == 32 and prepared.get('production_changed') is False,
                  'PREPARATION_RECEIPT_BINDING')
        candidate_pins = {page['path']: page['candidate_sha256'] for page in prepared['pages']}
        d.require(set(candidate_pins) == set(d.PAGES), 'PREPARATION_PAGE_SCOPE')
        for name in d.PAGES:
            d.require(candidate_pins[name] == payload_hashes['candidate/' + name], 'PREPARATION_CANDIDATE_PIN')
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='ua-art-spec-rebuild-stage-') as temporary:
        stage = d.directory(Path(temporary).absolute())
        root, control = stage / 'root', stage / 'control'
        for path in (root, root / 'video', root / 'site', control, control / 'sessions'):
            path.mkdir(mode=0o700)
        d.require(not root.is_relative_to(snapshot) and not snapshot.is_relative_to(root)
                  and not root.is_relative_to(payload) and not payload.is_relative_to(root), 'STAGE_INPUT_OVERLAP')
        for name in source_files:
            d.require(_copy_exact(snapshot / name, root / name) == source_hashes[name], 'COPY_CHANGED')
        for name in d.DRAFT_PAGES:
            if input_manifest['draft_files'][name] is not None:
                _copy_exact(snapshot / name, root / name)
        for name in server_fence.LOCK_NAMES:
            d.exclusive(root / name, b'ISOLATED_STAGE_EXISTING_INODE\n')
        session = {'repository': 'art20021986-wq/ua-art-autopilot', 'account': 'Carix', 'production_root': '/home/Carix',
                   'task_id': 'UA-ART-SPEC-REBUILD-10-001-STAGE', 'expected_main': '0' * 40,
                   'plan_sha256': d.digest(['SYNTHETIC_STAGE_ONLY', input_manifest['manifest_sha256']]),
                   'run_id': '1', 'run_attempt': 1, 'nonce': uuid.uuid4().hex + uuid.uuid4().hex,
                   'epoch': 1, 'source_sha256': d.file_hash(Path(server_fence.__file__).absolute())}
        (control / 'sessions' / session['nonce']).mkdir(mode=0o700)
        lease = server_fence.FenceLease(root, control, session)
        lease.acquire()
        try:
            copied_manifest = d.make_manifest(root, payload)
            d.require(copied_manifest == input_manifest, 'COPIED_MANIFEST_MISMATCH')
            plan = d.make_install_plan(session, payload, copied_manifest,
                                       coordination_plan_sha256=session['plan_sha256'], fence_sha256=session['source_sha256'])
            operation = d.DataInstall(lease, payload, plan, verify_window=synthetic_stage_authority)
            borrowed_fds = list(lease.handles)
            lease_checks_before = lease._check()
            installed = operation.apply()
            d.require(operation.read_terminal() == installed, 'INSTALL_TERMINAL_READBACK_MISMATCH')
            facts = _read_facts(root / 'spec-rebuild.db')
            visible = sum(len(normalize_facts(facts[uid])) for uid in d.UIDS)
            d.require(visible == 550, 'INSTALLED_VISIBLE_550_REQUIRED')
            page_checks = []
            for name in d.PAGES:
                uid = Path(name).stem
                current = d.read(root / name)['data']
                d.require(d.sha(current) == input_manifest['files'][name]['after_sha256'], 'INSTALLED_PAGE_HASH')
                original = d.read(snapshot / name)['data']
                approved_before, year_edits = _approved_year_before(original, name, review)
                checked = validate_page(current.decode('utf-8'), uid, facts[uid], previous=approved_before.decode('utf-8'))
                page_checks.append({'path': name, 'after_sha256': d.sha(current), 'rows': checked['rows'],
                                    'visible_vin_count': checked['visible_vin_count'], 'visible_anchor': checked['visible_anchor'],
                                    'shell_assets_sha256': checked['shell_assets_sha256'],
                                    'outside_permitted_regions_byte_changes': checked['shell_delta']['outside_permitted_regions_byte_changes'],
                                    'owner_reviewed_year_spans': year_edits, 'status': checked['status']})
            with d.db_read(root / 'crm.db') as conn:
                after_rows = d.digest(d.crm_rows(conn))
                d.require(after_rows == input_manifest['crm']['rows_after_sha256'], 'INSTALLED_FULL_18_ROWS')
            rolled_back = operation.rollback_only()
            d.require(operation.read_terminal() == rolled_back, 'ROLLBACK_TERMINAL_READBACK_MISMATCH')
            for name, item in input_manifest['files'].items():
                d.require(d.file_hash(root / name) == item['before_sha256'], 'ROLLBACK_FILE_HASH:' + name)
            with d.db_read(root / 'crm.db') as conn:
                before_rows = d.digest(d.crm_rows(conn))
                d.require(before_rows == input_manifest['crm']['rows_before_sha256'], 'ROLLBACK_FULL_18_ROWS')
            d.require(d.spec_snapshot(root / 'vin_specs_task111_v3.db') == input_manifest['legacy_spec'], 'ROLLBACK_LEGACY_SOURCE_CHANGED')
            for name, expected in input_manifest['draft_files'].items():
                d.require(d.file_hash(root / name) == expected, 'DRAFT_CHANGED')
            d.require(lease.handles == borrowed_fds and lease._check() == lease_checks_before, 'BORROWED_LEASE_CHANGED')
            result = {'schema': 'UA-ART-SPEC-REBUILD10-REAL-COPY-STAGE-1', 'status': 'PASS_ISOLATED_REAL_COPY_INSTALL_AND_ROLLBACK',
                      'started_at_utc': started, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
                      'python_version': platform.python_version(), 'platform': sys.platform,
                      'source_snapshot_observed_at_utc': captured.get('observed_at_utc'),
                      'source_snapshot_sha256': d.sha(snapshot_raw), 'candidate_manifest_sha256': input_manifest['manifest_sha256'],
                      'data_installer_sha256': plan['installer_sha256'], 'fence_source_sha256': session['source_sha256'],
                      'stage_harness_sha256': d.file_hash(Path(__file__).absolute()), 'year_review_sha256': YEAR_REVIEW_SHA256,
                      'candidate_pages': 32, 'crm_full_rows_verified': 18, 'published_cards_in_snapshot': 16,
                      'stored_facts': 557, 'visible_facts': visible, 'hidden_facts': 7,
                      'installed_state': installed['status'], 'rollback_state': rolled_back['status'],
                      'crm_rows_after_sha256': after_rows, 'crm_rows_restored_sha256': before_rows,
                      'legacy_spec_semantic_sha256': input_manifest['legacy_spec']['semantic_sha256'],
                      'html_rollback_exact': 32, 'new_database_removed_on_rollback': True, 'crm_full_rows_restored': True,
                      'crm_raw_database_replacement_on_rollback': False, 'protected_drafts': d.DRAFTS,
                      'borrowed_lock_count': len(borrowed_fds), 'borrowed_lock_handles_unchanged': True,
                      'authority': 'SYNTHETIC_FIXTURE_FOR_ISOLATED_TEMPORARY_ROOT_ONLY',
                      'production_changed': False, 'live_worker_drain_verified': False, 'fresh_source_verification': False,
                      'runtime_loaded_verified': False, 'overall_gate_b': 'NOT_EVALUATED', 'tasks_resumed': False,
                      'network_requests': 0, 'pages': page_checks}
        finally:
            lease.close()
    d.require({name: d.file_hash(snapshot / name) for name in source_files} == source_hashes, 'ORIGINAL_SNAPSHOT_CHANGED')
    d.require({name: d.file_hash(payload / name) for name in payload_hashes} == payload_hashes, 'ORIGINAL_PAYLOAD_CHANGED')
    d.require(d.file_hash(year_review) == YEAR_REVIEW_SHA256 and d.file_hash(snapshot / 'snapshot.json') == d.sha(snapshot_raw), 'REVIEW_OR_MANIFEST_CHANGED')
    result['input_files_changed'] = 0
    result['temporary_application_root_removed'] = not stage.exists()
    return result


def selftest():
    from .tests import test_data_install
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_data_install)
    stream = io.StringIO()
    outcome = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    return {'schema': 'UA-ART-SPEC-REBUILD10-DATA-SELFTEST-1', 'status': 'PASS' if outcome.wasSuccessful() else 'FAIL',
            'python_version': platform.python_version(), 'tests_run': outcome.testsRun,
            'failures': len(outcome.failures), 'errors': len(outcome.errors), 'skipped': len(outcome.skipped),
            'authority': 'SYNTHETIC_FIXTURES_ONLY', 'production_changed': False,
            'live_worker_drain_verified': False, 'overall_gate_b': 'NOT_EVALUATED',
            'interruption_scope': 'INSTALLER_INTERRUPTION_WITH_LIVE_FENCE_HOLDER', 'log': stream.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--year-review', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--selftest', action='store_true')
    args = parser.parse_args()
    output = args.output.absolute()
    d.directory(output.parent)
    d.require(not output.exists() and not output.is_symlink(), 'NEW_OUTPUT_REQUIRED')
    if args.selftest:
        d.require(args.snapshot is None and args.payload is None and args.year_review is None, 'SELFTEST_HAS_NO_PRIVATE_INPUTS')
        result = selftest()
    else:
        d.require(args.snapshot is not None and args.payload is not None, 'SNAPSHOT_AND_PAYLOAD_REQUIRED')
        for source in (args.snapshot.absolute(), args.payload.absolute()):
            d.require(not output.is_relative_to(source), 'OUTPUT_MUST_NOT_BE_WITHIN_INPUTS')
        result = run(args.snapshot, args.payload, args.year_review or args.payload / 'year-review.json')
    d.exclusive(output, json.dumps(result, ensure_ascii=False, indent=2).encode() + b'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in {'pages', 'log'}}, ensure_ascii=False))
    return 0 if result['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())
