#!/usr/bin/env python3
"""Make the published revision of a card include its downloaded diagnostics files.

Cause (CRM-VIDEO-PROBE-20261012-R3..R5): kadry_diagnostiki downloads diagnostics media
every 120 s in its own thread, while ua_crm_public_sync republishes only when the CRM
row changes. UA-0020 was published at 04:24:08 before its video arrived and never again.
With the file names in the revision, the existing worker republishes once the file lands.
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed ua_crm_public_sync.py observed by CRM-VIDEO-PROBE-20261012-R5.
EXPECTED_SHA256 = '8c65eeb598c15007f489e2eaa0453362c97b9c426a3f67cf02c6a09a0d37015f'
OLD = "        raw = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()\n"
NEW = ("        diag_files = diag_names(code)\n"
       "        source = dict(row, _diag_files=diag_files) if diag_files else row\n"
       "        raw = json.dumps(source, sort_keys=True, ensure_ascii=False, default=str).encode()\n")
IMPORT_OLD = "    from ua_delivery_status import public_status\n"
IMPORT_NEW = IMPORT_OLD + "    from ua_diag_files import names as diag_names\n"


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'snapshot']
    if len(nodes) != 1:
        raise BuildError('SNAPSHOT_NOT_UNIQUE')
    lines = text.splitlines(keepends=True)
    body = lines[nodes[0].lineno - 1:nodes[0].end_lineno]
    if body.count(OLD) != 1 or body.count(IMPORT_OLD) != 1:
        raise BuildError('SNAPSHOT_SHAPE_CHANGED')
    patched = ''.join(body).replace(IMPORT_OLD, IMPORT_NEW).replace(OLD, NEW)
    result = ''.join(lines[:nodes[0].lineno - 1]) + patched + ''.join(lines[nodes[0].end_lineno:])
    compile(result, 'ua_crm_public_sync.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
