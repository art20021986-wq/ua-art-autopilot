#!/usr/bin/env python3
"""Read-only on-disk Preview binding and supplied observer comparison, NOT a Gate.

Execute with python3.10 -I -B. No imports of live application code, no network,
no image bytes, no database access, no secret files, no writes. Only bounded
known Preview JSON/HTML/Python sources and one hash-pinned observer JSON are read.
The caller owns obtaining and saving the real V3 observer result separately.
A match proves on-disk binding, NOT running-worker binding or browser rendering.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

PR_HEAD = '2e8f30fe54c8ecd86acf888de86d9ca62ba01706'
PARENT = Path('/home/Carix/autopilot_inbox/cloud')
WORK = PARENT / 'task088-v5-preview-stage-zlcw0vma/gallery-preview-j6b3l4hd'
BUNDLE = WORK / 'candidate'
WSGI = Path('/var/www/carix_pythonanywhere_com_wsgi.py')
BASELINE_GALLERY_SHA = 'e893bdd1ce9a83ceaffc629bb2d5b56cb23dddb7f1d73b4c0cfbe7fc4a95d2da'
BASELINE_OBSERVER_SHA = '7f0bf4c31088350fed169366e46e19f04ef85bca00238f23bd56c8c7342f1806'
BASELINE_OBSERVED_AT = '2026-09-14T16:50:36.435375+00:00'
WSGI_SHA = '9b9578fe30e233cea6e46678da60dd360cae1861fca2723c08e19272bc75b555'
CONFIG_SHA = 'ab4b13e5f6c2a0f05801a6e89891b38474852c6cfc3db229f9fff72dabcca5ee'
MANIFEST_SHA = 'c6febae073064d66c89a553a1d23538c8dc71c40c9737c440d33a3ba457611ca'
GALLERY_ROUTE_SHA = '457df9c40064e7e5c5510d339e264e549ddfc4b1a2ae2bd2380c0501b46c2c74'
RUNTIME = {'common.py': 'cb30a2b61d28438a9844e79b1bc8550f92885dab8b6dc0d76c2789827c9893fa', 'routing_proof.py': 'fd483b95d5b0a2bc92146d1c137decb9e368706248b7469c9c1243a3fd622c5d', 'viewport_harness.py': '3b6830eff2d35ed94688707018e606b0d404a00bcb4dce80fa0dadab89b0bae1', 'wsgi_entry.py': '7b7b9056b55c41a5031e430cf470b10ae66fd812f792a3cd65cb931c1ced02e7', 'wsgi_preview.py': 'ba8188817fe309e42082024007ff892342283937a76a45fe8e3fcc2c975c2ee4'}
BASELINE = {'database': {'audit_sha256': '1674892165b6b42f3a726559a3ac6eac22981a3a83b7371ade8dc4cf9a095171', 'cars_sha256': 'fb3a161124b7c883e3755ddbc2b84060a6fe91954ac52f6cf7a4b93ae1db4244', 'published_codes': ['UA-0001', 'UA-0002', 'UA-0003', 'UA-0004', 'UA-0005', 'UA-0006', 'UA-0007', 'UA-0008', 'UA-0009', 'UA-0010', 'UA-0011', 'UA-0012', 'UA-0013', 'UA-0014', 'UA-0015', 'UA-0016', 'UA-0017', 'UA-0018'], 'published_sha256': '746227be9abe97b4e07afd50c8dd393268a2a9a6c576c63ce089d636d6d7658d'}, 'source_sha256': {'cars_ui.py': '4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde', 'catalog_design_guard.py': '51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60', 'publish_transaction_guard.py': '3d80712290e0881ebe7583231b532de422f808e6f18b5f6a90566d9e1eed3e0d', 'stranica.py': '2794f01c00a49f1a55c66f3e6af4657808f857e9167f59a5da84c9b8430d724a', 'ua_stage_catalog_sync.py': 'c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb', 'yadro.py': '1c6bddccec30198179f9a179aa67ac8f2e40da1a794c87f2342150eb5d2ec793'}, 'dependency_sha256': {'cars_schema.py': '1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73', 'catalog_design_golden.html': '228aaf503ef9728683020e15cb83c66550b77d45c8d7c341cc87f5f5768eb2c7', 'db.py': 'b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086', 'master_card.py': '27e32420bbec9f1e0a25621e1c20dda20944537daa40c1ccac574689cd6c3f6e', 'publikaciya.py': '296c389b477472032bad714e41f12bfa4b7e47ad784ac6900ba55f136d939c72', 'start_safe.py': '21aded2b576b36c6cea84b431c691b22eb09105ca5ec13bb6fd0910452c2cbeb', 'team_bot.py': 'aebe2c091fdf1f19a8a011784dd70e2d648dc04607ec64374e4ff9f402e995af'}, 'schema_sha256': '2f11c8573be88b0dc8da1adf12fcdc6c5105844f0a0300797fc907f9544ff8c2', 'stage_counts': {'georgia': 5, 'kiev': 5, 'korea': 4, 'sea': 4}, 'full_backup_source_bytes': 986727605, 'observer_payload_sha256': {'install_package.py': '3d74fc2a71160af18cb8dc705fbaa76ca367a348a6c984f59a4b4768e6fac673', 'observe_install_inputs.py': '626bb2142367b1b1d251fc131ee6365d6285fea6daa0cd08d2b8bc565d56a42f'}, 'hidden_public_files_included_in_complete_inventory': 17, 'system_inventory_sha256': 'b78bf862e08c4b549956b803245a851366085ae93ccc59291fde46656eec4dea', 'system_inventory_count': 9625}


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def require(condition, code):
    if not condition:
        raise ValueError(code)


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read(path, expected, limit):
    """Only call with explicit known nonsecret paths; never follow symlinks."""
    require(path.is_absolute() and path.resolve(strict=True) == path,
            'EXACT_NONSYMLINK_PATH_REQUIRED')
    require(not any(part.startswith('.') for part in path.parts),
            'HIDDEN_PATH_NOT_ALLOWED')
    require(re.fullmatch(r'[0-9a-f]{64}', expected or '') is not None,
            'EXPECTED_HASH_REQUIRED')
    with open(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        first = os.fstat(stream.fileno())
        require(stat.S_ISREG(first.st_mode) and 0 <= first.st_size <= limit,
                'BOUNDED_REGULAR_FILE_REQUIRED')
        raw = stream.read(limit + 1)
        last = os.fstat(stream.fileno())
    external = path.lstat()
    key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(len(raw) <= limit and key(first) == key(last) == key(external),
            'FILE_CHANGED_DURING_READ')
    require(sha(raw) == expected, 'PINNED_FILE_HASH_MISMATCH')
    return raw


def object_from(raw):
    value = json.loads(raw, object_pairs_hook=strict_pairs)
    require(type(value) is dict, 'JSON_OBJECT_REQUIRED')
    return value


def relative(value):
    require(type(value) is str, 'RELATIVE_PATH_REQUIRED')
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and
            '..' not in path.parts and not any(p.startswith('.') for p in path.parts),
            'CANONICAL_NONHIDDEN_RELATIVE_PATH_REQUIRED')
    return path


def preview_binding():
    wsgi_raw = read(WSGI, WSGI_SHA, 65536)
    config_raw = read(WORK / 'config.json', CONFIG_SHA, 16384)
    config = object_from(config_raw)
    expected = {'contract': 'UA-ART-V5-PROTECTED-PREVIEW-1',
                'preview_origin': 'https://carix.pythonanywhere.com',
                'bundle_root': str(BUNDLE), 'manifest_sha256': MANIFEST_SHA,
                'access_policy': 'PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED'}
    require(config == expected, 'EXACT_PUBLIC_PREVIEW_CONFIG_REQUIRED')
    # Source bytes are compared, never imported or executed.
    runtime = {name: sha(read(WORK / 'runtime' / name, pin, 1024 * 1024))
               for name, pin in RUNTIME.items()}
    raw = read(BUNDLE / 'manifest.json', MANIFEST_SHA, 4 * 1024 * 1024)
    manifest = object_from(raw)
    require(manifest.get('contract') == expected['contract'] and
            manifest.get('preview_gate') == 'NOT_PASSED',
            'EXACT_PREVIEW_BUNDLE_CONTRACT_REQUIRED')
    files = manifest.get('files')
    require(type(files) is dict and len(files) == 1221,
            'PINNED_MANIFEST_FILE_SET_REQUIRED')
    provenance_raw = read(BUNDLE / 'provenance.json',
                          manifest.get('provenance_sha256'), 4 * 1024 * 1024)
    provenance = object_from(provenance_raw)
    require(provenance.get('published_count') == 18,
            'HISTORICAL_PUBLISHED_COUNT_MISMATCH')
    html_hashes, cards, routes, literal_hashes = {}, {}, set(), {}
    for route, item in sorted(files.items()):
        require(type(item) is dict, 'MANIFEST_ITEM_REQUIRED')
        # Image and other asset bytes are deliberately never read.
        if item.get('storage') != 'bundle' or not route.endswith('.html'):
            continue
        name = relative(item.get('path'))
        require(name.parts[0] == 'public', 'ONLY_PUBLIC_BUNDLE_HTML_REQUIRED')
        html_raw = read(BUNDLE / name, item.get('sha256'), 4 * 1024 * 1024)
        require(len(html_raw) == item.get('bytes'), 'HTML_SIZE_MISMATCH')
        html_hashes[route] = sha(html_raw)
        match = re.fullmatch(r'/video/(UA-[0-9]{4})\.html', route)
        if not match:
            continue
        code = match.group(1)
        declarations = re.findall(r'\b(?:var|let|const)\s+kadry\s*=\s*(\[.*?\])\s*;',
                                  html_raw.decode('utf-8'), re.S)
        require(len(declarations) == 1, 'ONE_GALLERY_LITERAL_REQUIRED')
        paths = json.loads(declarations[0])
        require(type(paths) is list and len(paths) > 0 and all(
            type(p) is str and re.fullmatch(r'foto/' + code + r'/[0-9]{3}\.jpg', p)
            for p in paths), 'EXACT_GALLERY_LITERAL_REQUIRED')
        require(len(paths) == len(set(paths)), 'DUPLICATE_GALLERY_ROUTE')
        for path in paths:
            item_route = '/video/' + path
            item_meta = files.get(item_route)
            require(type(item_meta) is dict and
                    item_meta.get('content_type') == 'image/jpeg' and
                    re.fullmatch(r'[0-9a-f]{64}', item_meta.get('sha256', '')) and
                    type(item_meta.get('bytes')) is int and item_meta['bytes'] > 0,
                    'GALLERY_ROUTE_MANIFEST_METADATA_MISSING')
            if item_meta.get('storage') == 'asset':
                require(item_meta.get('root') == 'video' and item_meta.get('path') == path,
                        'GALLERY_ASSET_ROUTE_METADATA_MISMATCH')
            else:
                require(item_meta.get('storage') == 'bundle' and
                        item_meta.get('path') == 'public/video/' + path,
                        'GALLERY_BUNDLE_ROUTE_METADATA_MISMATCH')
            routes.add(item_route)
        cards[code] = len(paths)
        literal_hashes[code] = sha(encoded(paths))
    require(sorted(cards) == BASELINE['database']['published_codes'],
            'PREVIEW_CARD_SET_CHANGED')
    # Same sort/encoding as reviewed refresh helper; these routes are ASCII.
    route_sha = sha(encoded(sorted(routes)))
    require(len(routes) == 560 and route_sha == GALLERY_ROUTE_SHA,
            'GALLERY_ROUTE_SET_CHANGED')
    require(cards.get('UA-0015') == 37, 'OWNER_CARD_GALLERY_COUNT_CHANGED')
    price_routes = ['/video/index.html', '/video/katalog.html'] + [
        '/video/' + code + '.html' for code in sorted(cards)]
    require(all(route in html_hashes for route in price_routes),
            'TWENTY_PRICE_SURFACES_REQUIRED')
    # Detect changes to core pointers/runtime/manifest while reading HTML.
    read(WSGI, WSGI_SHA, 65536)
    read(WORK / 'config.json', CONFIG_SHA, 16384)
    read(BUNDLE / 'manifest.json', MANIFEST_SHA, 4 * 1024 * 1024)
    for name, pin in RUNTIME.items():
        read(WORK / 'runtime' / name, pin, 1024 * 1024)
    return {'status': 'MATCH', 'scope': 'ON_DISK_JSON_HTML_SOURCE_HASH_BINDING_ONLY',
            'wsgi_sha256': sha(wsgi_raw), 'config_sha256': sha(config_raw),
            'manifest_sha256': sha(raw), 'runtime_sha256': runtime,
            'provenance_sha256': sha(provenance_raw),
            'published_codes': sorted(cards), 'gallery_counts': cards,
            'gallery_literal_sha256': literal_hashes,
            'gallery_routes': len(routes), 'gallery_routes_sha256': route_sha,
            'resource_metadata_entries': len(files),
            'html_files_matched': len(html_hashes),
            'price_surface_hashes': {route: html_hashes[route] for route in price_routes},
            'all_bundle_html_hashes_sha256': sha(encoded(html_hashes)),
            'image_bytes_read': 0, 'http_requests': 0,
            'running_wsgi_worker_observed': False, 'browser_rendering_observed': False}


def observer_binding(path_text, expected):
    path = Path(path_text)
    require(path.is_absolute() and path.is_relative_to(PARENT) and
            re.fullmatch(r'(?:install|observe|observation|readback)[A-Za-z0-9_.-]*\.json', path.name),
            'EXACT_PRIVATE_OBSERVER_JSON_PATH_REQUIRED')
    raw = read(path, expected, 8 * 1024 * 1024)
    report = object_from(raw)
    require(report.get('contract') == 'TASK088-V5-INSTALL-OBSERVATION-1' and
            report.get('status') in ('PASS', 'OBSERVED_QUOTA_PENDING') and
            report.get('environment') == 'PRODUCTION_READ_ONLY' and
            report.get('read_only') is True and
            all(report.get(k) is False for k in ('live_files_written', 'crm_written', 'bot_restarted')),
            'ACTUAL_READ_ONLY_OBSERVER_CONTRACT_REQUIRED')
    stamp = datetime.datetime.fromisoformat(report['observed_at'].replace('Z', '+00:00'))
    require(stamp.tzinfo is not None, 'OBSERVATION_TIMEZONE_REQUIRED')
    age = (now() - stamp).total_seconds()
    require(0 <= age <= 1800, 'OBSERVER_STALE_OR_FUTURE')
    inventory = report.get('system_inventory')
    require(type(inventory) is dict, 'OBSERVER_COMPLETE_INVENTORY_REQUIRED')
    actual = {k: report.get(k) for k in BASELINE if
              k not in ('system_inventory_sha256', 'system_inventory_count')}
    actual['system_inventory_sha256'] = sha(encoded(inventory))
    actual['system_inventory_count'] = len(inventory)
    comparisons = {key: ('MATCH' if actual[key] == expected_value else 'DIFFERENT')
                   for key, expected_value in BASELINE.items()}
    return {'status': 'MATCH' if set(comparisons.values()) == {'MATCH'} else 'DRIFT_REVIEW_REQUIRED',
            'report_sha256': sha(raw), 'observed_at': report['observed_at'],
            'age_seconds_at_comparison': round(age, 3),
            'baseline_observed_at': BASELINE_OBSERVED_AT,
            'comparison': comparisons,
            'actual_section_sha256': {k: sha(encoded(actual[k])) for k in sorted(actual)},
            'system_inventory_sha256': actual['system_inventory_sha256'],
            'system_inventory_count': len(inventory),
            'source_files_count': len(report.get('source_sha256', {})),
            'dependency_files_count': len(report.get('dependency_sha256', {})),
            'quota_result': 'SEPARATE_ACTUAL_QUOTA_REVIEW_REQUIRED',
            'no_new_db_observation_by_this_script': True}


def sanitized_error(error):
    message = str(error)
    return {'status': 'REVIEW_REQUIRED', 'error_type': type(error).__name__,
            'code': message if re.fullmatch(r'[A-Z0-9_]{1,100}', message)
            else 'REDACTED_ERROR_MESSAGE'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observer-report', required=True)
    parser.add_argument('--observer-sha256', required=True)
    args = parser.parse_args()
    result = {'contract': 'PR114-FRESH-READONLY-PREVIEW-BINDING-NOT-A-GATE-1',
              'started_at': now().isoformat(), 'reviewed_pr_head': PR_HEAD,
              'baseline_gallery_receipt_sha256': BASELINE_GALLERY_SHA,
              'baseline_observer_report_sha256': BASELINE_OBSERVER_SHA,
              'production_written': False, 'crm_written': False,
              'files_written': False, 'network_requests': 0, 'image_bytes_read': 0,
              'full_preview': 'NOT_PASSED', 'gate_created': False,
              'scope_note': 'Owner visual evidence remains separate. Filesystem matches cannot prove worker state, all-card image rendering, freshness after this observation, writer exclusion, Gate B, backup, publication or live synchronization.'}
    try:
        require(sys.flags.isolated and sys.dont_write_bytecode,
                'PYTHON_ISOLATED_NO_BYTECODE_REQUIRED')
        try:
            result['preview'] = preview_binding()
        except Exception as error:
            result['preview'] = sanitized_error(error)
        try:
            result['observer'] = observer_binding(args.observer_report, args.observer_sha256)
        except Exception as error:
            result['observer'] = sanitized_error(error)
        result['status'] = ('MATCH_SCOPED_BINDINGS_ONLY' if
                            result['preview']['status'] == result['observer']['status'] == 'MATCH'
                            else 'REVIEW_REQUIRED')
    except Exception as error:
        result.update(sanitized_error(error))
    result['finished_at'] = now().isoformat()
    print(encoded(result).decode())
    return 0 if result['status'] == 'MATCH_SCOPED_BINDINGS_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
