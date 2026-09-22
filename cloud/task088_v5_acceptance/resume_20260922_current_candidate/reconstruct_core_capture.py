"""Reconstruct downloaded observer parts offline, preserving exact source bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=strict_pairs)


def read(path, expected, maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('REGULAR_BOUNDED_INPUT_REQUIRED:' + str(path))
    raw = path.read_bytes()
    if digest(raw) != expected:
        raise ValueError('INPUT_SHA256_MISMATCH:' + path.name)
    return raw


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download-directory', required=True, type=Path)
    parser.add_argument('--summary-sha256', required=True)
    parser.add_argument('--export-manifest-sha256', required=True)
    parser.add_argument('--observer-sha256', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    for pin in (args.summary_sha256, args.export_manifest_sha256, args.observer_sha256):
        if not re.fullmatch('[0-9a-f]{64}', pin):
            raise ValueError('SHA256_REQUIRED')
    root = args.download_directory.resolve(strict=True)
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('NEW_OUTPUT_REQUIRED')
    summary_raw = read(root / 'summary.json', args.summary_sha256, 4 * 1024**2)
    summary = decode(summary_raw)
    if (summary.get('contract') != 'PR114-POINT4-CORE-READONLY-OBSERVATION-1'
            or summary.get('status') != 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION'
            or summary.get('export_completed') is not True
            or summary.get('self_sha256') != args.observer_sha256
            or summary.get('blockers')):
        raise ValueError('ACTUAL_TERMINAL_SUCCESS_REQUIRED')
    export_raw = read(root / 'export_manifest.json', args.export_manifest_sha256, 4 * 1024**2)
    export = decode(export_raw)
    if summary.get('plaintext_export') != export or export.get('format') != 'ONE_LINE_JSON_PARTS_UTF8':
        raise ValueError('SUMMARY_EXPORT_BINDING_MISMATCH')
    if not export.get('parts') or not export.get('artifacts'):
        raise ValueError('COMPLETE_EXPORT_REQUIRED')
    reconstructed, next_index, seen_parts = {}, 0, set()
    for number, item in enumerate(export['parts']):
        name = item['path']
        if name != 'public_inputs_%03d.json' % number or name in seen_parts:
            raise ValueError('EXACT_DISTINCT_ORDERED_PART_NAMES_REQUIRED')
        seen_parts.add(name)
        raw = read(root / name, item['sha256'], 819200)
        if len(raw) != item['bytes']:
            raise ValueError('PART_BYTES_MISMATCH')
        part = decode(raw)
        if (part.get('kind') != 'PUBLIC_INPUTS_PART' or part.get('part') != number
                or part.get('snapshot_status') != summary['status'] or not part.get('records')):
            raise ValueError('PART_CONTRACT_MISMATCH')
        if item['first_index'] != next_index:
            raise ValueError('PART_FIRST_INDEX_MISMATCH')
        for record in part['records']:
            artifact = record['name']
            if not re.fullmatch(r'(?:(?:site|video)/[A-Za-z0-9_.-]+\.html|[A-Za-z0-9_.-]+\.json)', artifact):
                raise ValueError('BOUNDED_PUBLIC_ARTIFACT_PATH_REQUIRED')
            prior = reconstructed.setdefault(artifact, '')
            if record['index'] != next_index or record['offset_chars'] != len(prior):
                raise ValueError('EXACT_RECORD_INDEX_AND_OFFSET_REQUIRED')
            reconstructed[artifact] = prior + record['text']
            next_index += 1
        if item['last_index'] != next_index - 1:
            raise ValueError('PART_LAST_INDEX_MISMATCH')
    if next_index != export['chunk_records'] or set(reconstructed) != set(export['artifacts']):
        raise ValueError('EXACT_RECONSTRUCTED_ARTIFACT_SET_REQUIRED')
    payload = {name: text.encode('utf-8') for name, text in reconstructed.items()}
    if sum(map(len, payload.values())) > 64 * 1024**2:
        raise ValueError('RECONSTRUCTED_TOTAL_BOUND_EXCEEDED')
    for name, raw in payload.items():
        item = export['artifacts'][name]
        if len(raw) != item['bytes'] or digest(raw) != item['sha256']:
            raise ValueError('RECONSTRUCTED_ARTIFACT_MISMATCH:' + name)
    if 'summary.json' in payload or 'export_manifest.json' in payload:
        raise ValueError('TERMINAL_INPUT_NAME_COLLISION')
    payload.update({'summary.json': summary_raw, 'export_manifest.json': export_raw})
    args.output.mkdir(mode=0o700)
    for name, raw in sorted(payload.items()):
        target = args.output / name
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
        if target.read_bytes() != raw:
            raise ValueError('LOCAL_OUTPUT_READBACK_MISMATCH')
    print(json.dumps({'status': 'EXACT_OFFLINE_RECONSTRUCTION_COMPLETE',
        'summary_sha256': args.summary_sha256, 'export_manifest_sha256': args.export_manifest_sha256,
        'parts': len(seen_parts), 'artifacts': len(reconstructed), 'records': next_index,
        'published_count': len(summary['database']['published_codes']),
        'output': str(args.output), 'production_written': False}))


if __name__ == '__main__':
    main()
