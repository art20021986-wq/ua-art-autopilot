#!/usr/bin/env python3
"""Let card pages link to SeaRates container tracking.

Cause (SEO-GROWTH-VERIFY-20261012): CARRIER-TRACKING-INSTALL-20260928 renders the
owner-requested SeaRates tracking link for non-ONE containers (UA-0021), but the older
TASK115 guard in ua_additional_spec.inject_public_spec allows only listed external hosts,
so every rebuild of UA-0021 fails with UA115_UNAPPROVED_EXTERNAL_HOST. The one listed
host line gains www.searates.com; nothing else changes.
"""
from __future__ import annotations

import hashlib
import sys

# Installed ua_additional_spec.py observed by SEO-SOURCE-PROBE-20261012-R2.
EXPECTED_SHA256 = '6d2ab7b2bace29b8c0be58a6668264e695fd24f9e5e8f3ed6406da41ea45c672'
OLD = '    "maps.app.goo.gl", "ecomm.one-line.com", "schema.org", "www.w3.org",\n'
NEW = '    "maps.app.goo.gl", "ecomm.one-line.com", "www.searates.com", "schema.org", "www.w3.org",\n'
SET_START = '_UA115_APPROVED_HOSTS = {\n'


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    start = text.find(SET_START)
    if text.count(SET_START) != 1 or text.count(OLD) != 1 or text.find(OLD) < start \
            or '}' in text[start:text.find(OLD)]:
        raise BuildError('APPROVED_HOSTS_SHAPE_CHANGED')
    result = text.replace(OLD, NEW)
    compile(result, 'ua_additional_spec.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
