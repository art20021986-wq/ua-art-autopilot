"""Build an inert patch; never modify active workflows or authority records.

The rollback worktree needs the nonce reservation created after its source
commit. Both existing workflow copy steps omit that sixth durable record.
Registration of changed pinned runtime is a separate operation.
"""
from __future__ import annotations

import difflib
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCES = {
    '.github/workflows/uaart_critical.yml':
        '6f13c864a5d7b400474f3c9a1fe15e0d2d4dfca5d25dd195a628a3225d33e65a',
    '.github/workflows/uaart_transaction_watchdog.yml':
        '817fd29309b0854ffbfbe7d360a07ba0b37348e646655850b1ed99897229dffe',
}

NONCE_LOAD = '''          nonce = ledger.get('nonce')
          if not isinstance(nonce, str) or not re.fullmatch(r'[A-Za-z0-9._-]{16,128}', nonce):
              raise SystemExit('PINNED_NONCE_IDENTITY')
          nonce_path = 'state/autostart_nonces/' + nonce + '.json'
          if ledger.get('nonce_reservation_path') != nonce_path:
              raise SystemExit('PINNED_NONCE_PATH_BINDING')
          nonce_rel, nonce_data, _ = load(nonce_path, 'PINNED_NONCE')
          if hashlib.sha256(nonce_data).hexdigest() != ledger.get('nonce_reservation_sha256'):
              raise SystemExit('PINNED_NONCE_SHA_BINDING')
'''


def copied_state_script(source: str) -> str:
    """Extract the actual embedded Python block for executable regression tests."""
    end = source.index("          print('UAART_PINNED_DURABLE_STATE_COPIED')")
    begin = source.rfind("          python3 -I - <<'PY'\n", 0, end)
    if begin < 0:
        raise ValueError('COPY_BLOCK_MISSING')
    begin += len("          python3 -I - <<'PY'\n")
    end = source.index('\n          PY', end)
    lines = source[begin:end].splitlines()
    if any(line and not line.startswith('          ') for line in lines):
        raise ValueError('COPY_BLOCK_INDENT')
    result = '\n'.join(line[10:] if line else '' for line in lines) + '\n'
    compile(result, 'durable_state_copy.py', 'exec')
    return result


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError('EXPECTED_ONE_COPY_SITE')
    return source.replace(old, new, 1)


def candidate(relative: str, payload: bytes) -> bytes:
    if relative not in SOURCES or hashlib.sha256(payload).hexdigest() != SOURCES[relative]:
        raise ValueError('WORKFLOW_SOURCE_DRIFT')
    source = payload.decode('utf-8')
    old_script = copied_state_script(source)
    script = old_script
    script = replace_once(script, 'import json, os, pathlib, re', 'import hashlib, json, os, pathlib, re')
    script = replace_once(script, 'ledger_rel, ledger_data, _ = load(', 'ledger_rel, ledger_data, ledger = load(')
    script = replace_once(script, 'backup_rel, backup_data, _ = load(',
                          '\n'.join(line[10:] for line in NONCE_LOAD.rstrip('\n').splitlines())
                          + '\nbackup_rel, backup_data, _ = load(')
    script = replace_once(script, '    ledger_rel: ledger_data,',
                          '    ledger_rel: ledger_data,\n    nonce_rel: nonce_data,')
    script = replace_once(script, 'if len(items) != 5:', 'if len(items) != 6:')
    # Validate all destination paths before copying the first durable record.
    script = replace_once(script, 'for relative, data in items.items():\n',
        "for relative in items:\n"
        "    target = pinned_root / relative\n"
        "    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents if parent != pinned_root):\n"
        "        raise SystemExit('PINNED_DESTINATION_SYMLINK')\n"
        "for relative, data in items.items():\n")
    compile(script, relative, 'exec')
    indented = lambda value: '\n'.join('          ' + line if line else '' for line in value.rstrip('\n').splitlines())
    result = replace_once(source, indented(old_script), indented(script))
    if copied_state_script(result) != script:
        raise ValueError('COPY_BLOCK_ROUNDTRIP')
    return result.encode('utf-8')


def patch(root: Path = ROOT) -> str:
    result = []
    for relative in SOURCES:
        original = (root / relative).read_bytes()
        updated = candidate(relative, original)
        result.extend(difflib.unified_diff(
            original.decode().splitlines(keepends=True),
            updated.decode().splitlines(keepends=True),
            fromfile='a/' + relative, tofile='b/' + relative))
    return ''.join(result)


if __name__ == '__main__':
    print(patch(), end='')
