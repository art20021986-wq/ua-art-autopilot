#!/usr/bin/env python3
"""Republish every published card once, through the existing durable worker.

The card revision gains the SEO page version: pages built before SEO-GROWTH-001 count
as outdated, so ua_crm_public_sync republishes them one by one with its own retries,
receipts and public freshness checks. A future SEO page change bumps the version.
"""
from __future__ import annotations

import ast
import hashlib
import sys

# Installed ua_crm_public_sync.py after CRM-DIAG-MEDIA-PUBLISH-INSTALL-20261012.
EXPECTED_SHA256 = '543c43ef64eebe260c4467363d82ccbbbc4c2c9db2dc043e9fa93d0f91aaa96b'
OLD = "        source = dict(row, _diag_files=diag_files) if diag_files else row\n"
NEW = OLD + "        source = dict(source, _seo_revision=SEO_REVISION)\n"
IMPORT_OLD = "    from ua_diag_files import names as diag_names\n"
IMPORT_NEW = IMPORT_OLD + "    from ua_seo_metadata import SEO_REVISION\n"


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
    if ''.join(body).count(OLD) != 1 or ''.join(body).count(IMPORT_OLD) != 1:
        raise BuildError('SNAPSHOT_SHAPE_CHANGED')
    patched = ''.join(body).replace(IMPORT_OLD, IMPORT_NEW).replace(OLD, NEW)
    result = ''.join(lines[:nodes[0].lineno - 1]) + patched + ''.join(lines[nodes[0].end_lineno:])
    compile(result, 'ua_crm_public_sync.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
