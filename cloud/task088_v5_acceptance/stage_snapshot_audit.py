"""Stage a pinned read-only audit in private scratch; never install production.

The caller supplies the reviewed immutable commit as REVIEWED_COMMIT. All six
downloaded files are verified against the reviewed hashes below before import.
Only a new private directory and its report are written. The live CRM, source,
HTML, runtime controls and task scheduler are never changed.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.request

PINS = {'audit_snapshot.py': 'd7910abc3ce30d131424a99268b85e423e955393da47bb0763fa3d5da4be225c', 'initial_html_prices.py': '670c4175349f0650d979f3aa2937eb45c6f44d1733ba2056411a8c87f68c02ea', 'patch_catalog_design_guard.py': 'a251b3e6c036645701ae8473f3c0020f8589c04815509b533cf0a531656c024f', 'patch_stranica.py': '7fe01235678cbdbeecafc3d402c75ba95c80643ea295d355208eb8749a5e5848', 'patch_yadro.py': '873fbfcd05d0d740810cb898302090f75239ca7c1d115992e524c3290f2b7fb1', 'uaart_market_prices.py': 'd3d28c5cb9a63f2c70aeede5b1636020393f24f4678144eedcb42f09226c8bc0'}
STAGING = Path('/home/Carix/autopilot_inbox/cloud')
REPO = 'https://raw.githubusercontent.com/art20021986-wq/ua-art-autopilot/'


def main(commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('IMMUTABLE_REVIEWED_COMMIT_REQUIRED')
    if not STAGING.is_dir() or any(p.is_symlink() for p in (STAGING, *STAGING.parents)):
        raise ValueError('EXISTING_PRIVATE_STAGING_REQUIRED')
    if len(PINS) != 6:
        raise ValueError('EXACT_REVIEWED_PACKAGE_REQUIRED')
    payload = {}
    for name, expected in sorted(PINS.items()):
        with urllib.request.urlopen(REPO + commit + '/cloud/task088_stage3_renderer/' + name, timeout=30) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('REVIEWED_MODULE_MISMATCH:' + name)
        compile(raw, name, 'exec')
        payload[name] = raw
    directory = Path(tempfile.mkdtemp(prefix='task088-v5-readonly-', dir=STAGING))
    for name, raw in payload.items():
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        if (directory / name).read_bytes() != raw:
            raise ValueError('STAGED_SOURCE_READBACK_FAILED')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(directory))
    report = importlib.import_module('audit_snapshot').audit_snapshot(Path('/home/Carix'))
    report['candidate_commit'] = commit
    report['candidate_module_sha256'] = PINS
    raw = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    path = directory / 'report.json'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
    if path.read_bytes() != raw:
        raise ValueError('AUDIT_REPORT_READBACK_FAILED')
    summary = {key: report[key] for key in ('started_at', 'finished_at', 'published_count', 'html_count', 'snapshot_checks', 'preview_gate', 'db')}
    summary.update(candidate_commit=commit, report_path=str(path), report_sha256=hashlib.sha256(raw).hexdigest(),
                   source_checks=report['sources'], pages_total=len(report['pages']),
                   pages_pass=sum(item['status'] == 'PASS' for item in report['pages']),
                   page_failures=[item for item in report['pages'] if item['status'] != 'PASS'],
                   html_unchanged=sum(item['status'] == 'PASS' for item in report['html_manifest']),
                   html_failures=[item for item in report['html_manifest'] if item['status'] != 'PASS'])
    print('V5_SNAPSHOT_RESULT=' + json.dumps(summary, ensure_ascii=True, sort_keys=True, separators=(',', ':')))
    return 1  # Required browser/home/full-chain gates remain unperformed.


if __name__ == '__main__':
    raise SystemExit(main(REVIEWED_COMMIT))
