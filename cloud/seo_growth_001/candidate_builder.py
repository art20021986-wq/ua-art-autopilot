"""Build the SEO growth candidate from the exact installed sources."""
import hashlib
from pathlib import Path

import build_guard
import build_public_sync
from release_constants import NEW_MODULES, REPLACED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    'ua_seo_metadata.py': 'c630fa7f5d939684353c5a41ee6cef2dd421bec667be400288c3f2459b15e567',
    'ua_seo_sitemap.py': 'c73b249ee546310b20da8acc4d66d2006a8950ea4378366cb74f25c971b8b00d',
    'publish_transaction_guard.py': build_guard.EXPECTED_SHA256,
    'ua_crm_public_sync.py': build_public_sync.EXPECTED_SHA256,
}
DEPENDENCY_SHA256 = {}


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES + REPLACED_MODULES}
    result['publish_transaction_guard.py'] = build_guard.build(source['publish_transaction_guard.py'])
    result['ua_crm_public_sync.py'] = build_public_sync.build(source['ua_crm_public_sync.py'])
    return result
