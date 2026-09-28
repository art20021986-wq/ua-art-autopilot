"""Build only from the reviewed live WSGI hash. Never deploy or reload."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ua_crm_deleted_routes import validate_legacy_routes

BASELINE = '3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308'
MARKER = '# UA-ART-CRM-DELETE-RECOVERY-002-EXACT-ROUTES-V1'
# Exact preimages in the authoritative emergency plan, combined with the
# observed static mapping /video/ -> /home/Carix/video/. The /site/ mirror
# has no public mapping and deliberately contributes no guessed URLs.
INCIDENT_PLAN_SHA256 = '891dbad7211277f1613655da9cbcb2ea19f80937c375bc2575767858c2aa6442'
OBSERVED_LEGACY_ROUTES = ('/video/UA-0002-a6f9d391.html',
                          '/video/UA-0002-diag.html', '/video/UA-0002.html')


def transform(source, *, legacy_routes=OBSERVED_LEGACY_ROUTES):
    raw = source.encode('utf-8') if isinstance(source, str) else source
    if hashlib.sha256(raw).hexdigest() != BASELINE:
        raise ValueError('REVIEWED_LIVE_WSGI_HASH_REQUIRED')
    routes = sorted(validate_legacy_routes(legacy_routes))
    original = raw.decode('utf-8')
    addition = '''

{marker}
from ua_crm_deleted_routes import DeletedRoutes as _ua_delete_Routes
_ua_delete_routes = _ua_delete_Routes(legacy_routes={routes!r})
_ua_delete_original_seo_payload = _ua_seo068_wsgi_payload
def _ua_seo068_wsgi_payload(path):
    value = _ua_delete_original_seo_payload(path)
    if path == '/sitemap.xml' and value is not None:
        return _ua_delete_routes.filter_sitemap(value[0]), value[1]
    return value
application = _ua_delete_routes.wrap(application)
'''.format(marker=MARKER, routes=routes)
    result = original + addition
    compile(result, 'www_uaart_com_ua_wsgi.py', 'exec')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--legacy-route', action='append', dest='routes',
                        help='Verified exact incident route; may be repeated')
    args = parser.parse_args()
    routes = OBSERVED_LEGACY_ROUTES if args.routes is None else tuple(args.routes)
    candidate = transform(args.source.read_bytes(), legacy_routes=routes).encode('utf-8')
    with args.output.open('xb') as target:
        target.write(candidate)
    print(json.dumps({'source_sha256': BASELINE,
                      'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
                      'legacy_routes': sorted(routes), 'production_write': False}, sort_keys=True))


if __name__ == '__main__':
    main()
