#!/usr/bin/env python3
"""Refresh the derived search files each time the publisher installs the catalog.

Cause (SEO-SOURCE-PROBE-20261012): katalog.html is written only by
publish_transaction_guard._install_catalog, never through publikaciya._zapisat_atomarno,
so ua_seo_sitemap.sync_after_write never ran and the sitemap froze. The appended block
wraps the last _install_catalog, like UA-SITE-COUNTERS-123, inside the same lock.
A failure is logged and reported, never blocks a car publication: the files are derived.
"""
from __future__ import annotations

import hashlib
import sys

# Installed publish_transaction_guard.py observed by SEO-SOURCE-PROBE-20261012.
EXPECTED_SHA256 = '9b41f15e8455ec7e579bea1e194e6c855cc50b7b0e060ee2a010301d28c981e8'
MARKER = '# UA-ART-SEO-GROWTH-001:START'
BLOCK = '''
# UA-ART-SEO-GROWTH-001:START
_UA_SEO_GROWTH_BASE_INSTALL = _install_catalog


def _install_catalog(source, target):
    result = _UA_SEO_GROWTH_BASE_INSTALL(source, target)
    try:
        from ua_seo_index import refresh as _ua_seo_refresh
        result['seo_index'] = _ua_seo_refresh(VIDEO)
    except Exception as exc:  # derived search files never block a publication
        result['seo_index'] = {'status': 'FAIL', 'error': type(exc).__name__ + ':' + str(exc)[:200]}
        _append_log('SEO_INDEX_FAIL ' + result['seo_index']['error'])
    return result
# UA-ART-SEO-GROWTH-001:END
'''


class BuildError(RuntimeError):
    pass


def build(source: bytes, *, expected=EXPECTED_SHA256) -> bytes:
    if hashlib.sha256(source).hexdigest() != expected:
        raise BuildError('SOURCE_HASH_MISMATCH')
    text = source.decode('utf-8')
    if MARKER in text or 'def _install_catalog(' not in text:
        raise BuildError('GUARD_SHAPE_CHANGED')
    result = text.rstrip('\n') + '\n' + BLOCK
    compile(result, 'publish_transaction_guard.py', 'exec')
    return result.encode('utf-8')


if __name__ == '__main__':
    sys.stdout.buffer.write(build(open(sys.argv[1], 'rb').read()))
