"""Independent scoped retirement against saved real page bytes, isolated roots.

Reason: generic stage assets use vehicle IDs; synthetic fixture HTML does not
exercise those semantics or real 18-tile catalog/counter structure.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import types

HERE = Path(__file__).parent
ROOT = HERE.parent/'pr114_review'
SOURCE = HERE.parent/'private_combined_candidate_v2'
for folder in ('task088_price_sync','task088_stage3_renderer',
               'task088_autopilot_owner_policy','task088_v5_writer_fence'):
    sys.path.insert(0, str(ROOT/'cloud'/folder))
sys.path.insert(0, '/workspace/scratch/256f936ac1c5/private_v5_current')
sys.path.insert(0, str(HERE.parent/'private_counter_candidate'))
import outbox
sys.modules['uaart_price_sync_outbox'] = outbox
import visibility_lifecycle as V
import ua_site_counters as C
from uaart_price_sync_runtime import _Anchors

def sha(data): return hashlib.sha256(data).hexdigest()
def tiles(source):
    parsed = _Anchors(source)
    return [source[left:right] for left, right in parsed.articles]

report = {'scope':'SAVED_REAL_HTML_ISOLATED_COPY_SYNTHETIC_ROUTING_NO_LIVE_PASS',
          'reason':'Semantic retirement, other-tile preservation, and current counters on real HTML.',
          'source_sha256':{}, 'checks':[], 'unchanged_suites_rerun':False}
with tempfile.TemporaryDirectory(dir=HERE, prefix='native-pages-') as temporary:
    root = Path(temporary)
    for folder in ('video','site'):
        (root/folder).mkdir()
        for name in ('katalog.html','index.html'):
            relative = folder+'/'+name
            raw = (SOURCE/relative).read_bytes()
            report['source_sha256'][relative] = sha(raw)
            (root/relative).write_bytes(raw)
    journal = root/'journal'; (journal/'visibility').mkdir(parents=True, mode=0o700)
    binding = types.SimpleNamespace(db_path=root/'crm.db',journal_root=journal,
        resolve_visibility_surfaces=lambda code:[types.SimpleNamespace(
            kind='HOME',path=root/'video/index.html')])
    legacy = (root/'site/index.html').read_bytes()
    home = (root/'video/index.html').read_text()
    before = (root/'video/katalog.html').read_text()
    records, _ = C.catalog_snapshot(before)
    assert len(records) == 18
    other_tiles = [tile for tile in tiles(before) if not V.listing_present(tile,'UA-0001')]
    assert len(other_tiles) == 17
    assert '/video/stage/UA-0001.webp' in home
    assert not V.listing_present(home,'UA-0001')
    V.retire_lists(binding,'UA-0001',sha(b'independent-retire-UA-0001'))
    after = (root/'video/katalog.html').read_text()
    assert tiles(after) == other_tiles
    assert '/video/stage/UA-0001.webp' in (root/'video/index.html').read_text()
    assert (root/'site/index.html').read_bytes() == legacy
    proof = V.verify_hidden(binding,{'id':1,'auto_number':'UA-0001','published':0})
    assert proof['live_http_verified'] is False
    assert proof['verification_scope'] == 'LOCAL_PINNED_ROUTE_FILES'
    assert str(root/'site/index.html') not in proof['shared_sha256']
    report['checks'].append('REAL_ILLUSTRATED_CAR_WITHDRAWAL_PRESERVES_OTHER_17_TILES_AND_GENERIC_MEDIA')
    # Required zero-inventory boundary uses the actual catalog grammar.
    for code in sorted(records):
        if code == 'UA-0001': continue
        previous = (root/'video/katalog.html').read_text()
        expected_other = [tile for tile in tiles(previous) if not V.listing_present(tile,code)]
        V.retire_lists(binding,code,sha(('independent-retire-'+code).encode()))
        current = (root/'video/katalog.html').read_text()
        assert tiles(current) == expected_other
    observed, counts = C.catalog_snapshot((root/'video/katalog.html').read_text())
    assert observed == {} and counts['all'] == 0
    for filename in ('video/katalog.html','site/katalog.html'):
        source = (root/filename).read_text()
        assert C.patch_catalog(source, counts) == source
    served_home = (root/'video/index.html').read_text()
    assert C.patch_home(served_home,counts) == served_home
    assert (root/'site/index.html').read_bytes() == legacy
    report['checks'].append('REAL_CATALOG_18_TO_ZERO_AND_ALL_COUNTERS_CONSISTENT')
    report['checks'].append('UNSERVED_LEGACY_HOME_EXACT_BYTES_PRESERVED')
report['implementation_sha256'] = sha((ROOT/'cloud/task088_v5_writer_fence/visibility_lifecycle.py').read_bytes())
report['counter_dependency_sha256'] = sha(Path(C.__file__).read_bytes())
report['status'] = 'PASS'
(HERE/'REAL_PAGE_RETIREMENT_PROBE.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,sort_keys=True))
