#!/usr/bin/env python3
"""Assemble exactly fifteen reviewed modules; never import application code.

The historical ten-module builder remains unchanged. This separate candidate
joins the v8 worker, publisher contracts and card allocator, using pinned raw
captures. Compilation is offline evidence, not a deployment or full Gate B.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import types

HERE = Path(__file__).resolve().parent
CONTRACT_ID = 'UA-ART-SPEC-AUTO-10-RESTORE-001-v1.0'
CANDIDATE_ID = 'UA-ART-SPEC-AUTO10-COMPLETE-15-V1'
MANIFEST_KEYS = {
    'contract_id', 'candidate_id', 'status', 'module_count', 'publication_mode',
    'production_changed', 'application_imported', 'overall_gate_b', 'base_pins',
    'source_pins', 'runtime_pins', 'helper_pins', 'execution_dependency_pins',
    'files', 'input_bindings', 'input_binding_scope', 'limitations',
}
LIMITATIONS = [
    'Compile/assembly only: final fifteen-module execution remains a separate gate.',
    'Execution dependency pins are unchanged dependencies, not installation files.',
    'No application import, database, source request, deployment or service action.',
]
BASE_PINS = {
    'card_lifecycle.py': 'a0f65fedcf91cbe01f0b891ddde31b97186e9c7ae77e51cef905cf29a81b55b7',
    'card_shell.py': '9d764eae5f73e8b75e8c863abb9c3ae8c3a44f0bd1fa2918a28a80e996556b0a',
    'cars_ui.py': '32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec',
    'profile_library.py': '6784b5641a1bd6f8e094a0bc7ca4769596f91082f46891515463a933d2225eb6',
    'publikaciya.py': '224d140151e26ff597962f17f45ec928f0716fb873e139e9686aac0256de87e8',
    'publish_transaction_guard.py': 'eb8a37c5bba85b74cf3d6ed4c326d20d69a92274dee1e75f80108b5fa9834912',
    'source_policy.py': 'e9590c1630a8c81bcacf05d620e273a341aaf407f39c3a1bd184258c17ce3f0d',
    'spec_publication.py': '3e2ed470ebc06a9cbf03357858aeaf63cc6262045384867fca6b7b95bb181718',
    'ua_additional_spec.py': '5a03cb99d1f4514539956f32a75e09e119e2e9049a91da6326adb32877518e56',
    'vin_spec_service.py': 'b3a90347c15e3063abe072f4b159b78e392a2da8f2e15f2bf9a37ba59bc9e7a7',
}
SOURCE_PINS = {
    'master_card.py': 'f64e0b82b11bfd6089509510e5b131a91b03d40bed97b16075ab2ec60da380ce',
    'cars_schema.py': '1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73',
    'db.py': 'b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086',
    'ai_filter.py': '7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6',
    'stranica.py': '42aa5fc9db162e59fcf36b7ee9b2002360205827023786a65cf2205ab16066cc',
    'catalog_design_guard.py': '51127bbc2be949e1d37f7b6995c0e5a7a32a497c8436139322ce5b0fea308d60',
    'catalog_design_golden.html': '546d5c642801cd714d81451412cb584f07dbbd58264a09f57c27b0e2d05b2dd3',
}
EXECUTION_DEPENDENCIES = ('stranica.py', 'catalog_design_guard.py', 'catalog_design_golden.html')
HELPER_PINS = {
    'prepare_candidate.py': '43ca3f03e9157c77bebe1c15f65431d7dbf464a79815f1a7607ad1b18985e235',
    'repair_master_shell.py': 'fb01f9de8b17e5b37babb56c1554de3f2cc3067668fc8db63237d9f47aafcac4',
    'repair_public_contract.py': '69765b84749f61e97ca6ac99c1a28c9bc9864a98fb38c82a527383b8c063287b',
    'allocator_integration.py': '580e23865e7a128f6f2aace3d6a1c122881c2b1141d13cc56a838e38a7d6ffa7',
}
RUNTIME_PINS = {
    'vin_spec_service.py': 'a4468d2de5fd35d0778dea0ee15ad382dcb680ec4aa344da217cfce67f088c16',
    'car_number_allocator.py': '620721125f5e6378ac6287fe1f642a6d68b874516a4b51e7955638fd257097e1',
}
OUTPUT_PINS = dict(BASE_PINS, **RUNTIME_PINS, **{
    'master_card.py': '1141dbab9d31baca570b6eb9c3470000a6847c9f20e5c67cc0de9ba7b7cfc3c8',
    'ua_additional_spec.py': '48a3f8e88bb214d6632513b6ee0b884a0d3bd95cb4bc2e786426fec42e4b2441',
    'cars_schema.py': '20da4d4e892b363cd57c8819eadf92f0d8d54383a6c3344e37391d00d5d56e8a',
    'db.py': '1d5073450b353b88f99944930ed34af0735784c3a580801bab694ecafb7f59a2',
    'ai_filter.py': '4b0326b0280e5bf9fdecab0a4f0a931525bd7700b11b6c6c37756895f55d6c89',
})
COMPLETE_FILES = tuple(sorted(OUTPUT_PINS))


class CandidateError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _safe_path(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise CandidateError('SYMLINK_FORBIDDEN')
    return path


def _read_input(path, expected=None):
    path = _safe_path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise CandidateError('INPUT_TYPE_OR_SIZE:' + path.name)
    with os.fdopen(descriptor, 'rb') as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > 4 * 1024 * 1024:
            raise CandidateError('INPUT_TYPE_OR_SIZE:' + path.name)
        data = handle.read(4 * 1024 * 1024 + 1)
        after = os.fstat(handle.fileno())
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if len(data) > 4 * 1024 * 1024 or signature(before) != signature(after) or signature(path.stat()) != signature(after):
        raise CandidateError('INPUT_CHANGED_DURING_READ:' + path.name)
    if expected is not None and sha(data) != expected:
        raise CandidateError('INPUT_HASH_MISMATCH:' + path.name)
    return data, signature(after)


def _load_helper(name):
    path = HERE/name
    data, signature = _read_input(path, HELPER_PINS[name])
    module = types.ModuleType('_complete15_' + path.stem)
    module.__file__ = str(path)
    # Only fixed, reviewed pure source-transform/I/O helpers are executed.
    # Application modules are compiled later and never executed/imported.
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module, (path, data, signature)


def _io_helpers():
    return _load_helper('prepare_candidate.py')[0]


def _recheck(inputs):
    for path, before, signature in inputs:
        after, latest = _read_input(path, sha(before))
        if after != before or latest != signature:
            raise CandidateError('INPUT_CHANGED_DURING_PREPARATION:' + path.name)


def _publish_manifest_last(stage, output, manifest, io):
    """Audited v7 dirfd/hardlink primitive, with a separate fifteen-file set."""
    parent_fd = io._open_directory(output.parent)
    stage_fd = io._open_directory(stage)
    output_fd = None
    claimed_identity = None
    created = []
    try:
        names = list(COMPLETE_FILES) + ['manifest.json']
        if set(os.listdir(stage_fd)) != set(names):
            raise CandidateError('STAGE_FILE_SET_INVALID')
        stage_identities = {}
        for name in names:
            data, info = io._read_at(stage_fd, name)
            expected = sha(_manifest_bytes(manifest)) if name == 'manifest.json' else OUTPUT_PINS[name]
            if sha(data) != expected:
                raise CandidateError('STAGE_HASH_MISMATCH:' + name)
            stage_identities[name] = io._identity(info)
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=stage_fd)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        try:
            os.mkdir(output.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as exc:
            raise CandidateError('OUTPUT_ALREADY_EXISTS') from exc
        claimed = os.stat(output.name, dir_fd=parent_fd, follow_symlinks=False)
        claimed_identity = io._identity(claimed)
        output_fd = os.open(output.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
        if io._identity(os.fstat(output_fd)) != claimed_identity:
            raise CandidateError('OUTPUT_DIRECTORY_REPLACED')
        for name in names:
            if not io._path_still_owned(parent_fd, output.name, claimed_identity):
                raise CandidateError('OUTPUT_DIRECTORY_REPLACED')
            if name == 'manifest.json':
                os.fsync(output_fd)
                os.fsync(parent_fd)
            os.link(name, name, src_dir_fd=stage_fd, dst_dir_fd=output_fd, follow_symlinks=False)
            created.append((name, stage_identities[name]))
            linked = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
            if not stat.S_ISREG(linked.st_mode) or io._identity(linked) != stage_identities[name]:
                raise CandidateError('OUTPUT_FILE_REPLACED:' + name)
        if not io._path_still_owned(parent_fd, output.name, claimed_identity):
            raise CandidateError('OUTPUT_DIRECTORY_REPLACED')
        os.fsync(output_fd)
        os.fsync(parent_fd)
        return claimed_identity, stage_identities['manifest.json']
    except BaseException:
        if output_fd is not None:
            for name, identity in reversed(created):
                try:
                    current = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
                    if stat.S_ISREG(current.st_mode) and io._identity(current) == identity:
                        os.unlink(name, dir_fd=output_fd)
                except FileNotFoundError:
                    pass
            if claimed_identity is not None and io._path_still_owned(parent_fd, output.name, claimed_identity):
                try:
                    os.rmdir(output.name, dir_fd=parent_fd)
                except OSError as cleanup_error:
                    import errno
                    if cleanup_error.errno not in {errno.ENOTEMPTY, errno.EEXIST, errno.ENOENT}:
                        raise
        raise
    finally:
        if output_fd is not None:
            os.close(output_fd)
        os.close(stage_fd)
        os.close(parent_fd)


def _manifest_bytes(manifest):
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode()


def _invalidate_owned_readiness(output, published, io):
    """On post-commit drift remove only this operation's exact ready marker."""
    try:
        descriptor = io._open_directory(output)
    except (FileNotFoundError, io.CandidateError):
        return
    try:
        if io._identity(os.fstat(descriptor)) != published[0]:
            return
        try:
            marker = os.stat('manifest.json', dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            return
        if stat.S_ISREG(marker.st_mode) and io._identity(marker) == published[1]:
            os.unlink('manifest.json', dir_fd=descriptor)
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _expected_files():
    before = dict(BASE_PINS)
    before.update({name: SOURCE_PINS[name] for name in ('master_card.py', 'cars_schema.py', 'db.py', 'ai_filter.py')})
    before['car_number_allocator.py'] = RUNTIME_PINS['car_number_allocator.py']
    return {name: {'before_sha256': before[name], 'after_sha256': OUTPUT_PINS[name],
                   'changed': before[name] != OUTPUT_PINS[name]} for name in COMPLETE_FILES}


def verify_candidate(output):
    """Read-only exact fifteen-file readiness, provenance, hash and syntax gate."""
    output = _safe_path(output)
    io = _io_helpers()
    directory_fd = io._open_directory(output)
    try:
        names = set(COMPLETE_FILES) | {'manifest.json'}
        if set(os.listdir(directory_fd)) != names:
            raise CandidateError('CANDIDATE_FILE_SET_INVALID')
        raw, manifest_info = io._read_at(directory_fd, 'manifest.json')
        try:
            manifest = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise CandidateError('MANIFEST_INVALID') from exc
        if (not isinstance(manifest, dict) or set(manifest) != MANIFEST_KEYS
                or manifest.get('candidate_id') != CANDIDATE_ID or manifest.get('contract_id') != CONTRACT_ID
                or manifest.get('status') != 'OFFLINE_COMPLETE_CANDIDATE_COMPILED'
                or manifest.get('module_count') != 15 or manifest.get('production_changed') is not False
                or manifest.get('application_imported') is not False or manifest.get('publication_mode') != 'manifest_last'
                or manifest.get('overall_gate_b') != 'NOT_EVALUATED'
                or manifest.get('input_binding_scope') != 'INFORMATIONAL_LOCAL_ASSEMBLY_PATHS_ONLY'
                or manifest.get('limitations') != LIMITATIONS
                or manifest.get('files') != _expected_files()
                or manifest.get('execution_dependency_pins') != {name: SOURCE_PINS[name] for name in EXECUTION_DEPENDENCIES}
                or manifest.get('helper_pins') != HELPER_PINS or manifest.get('base_pins') != BASE_PINS
                or manifest.get('source_pins') != SOURCE_PINS or manifest.get('runtime_pins') != RUNTIME_PINS):
            raise CandidateError('MANIFEST_SCOPE_OR_PROVENANCE_INVALID')
        observed = {}
        for name in COMPLETE_FILES:
            data, info = io._read_at(directory_fd, name)
            if sha(data) != OUTPUT_PINS[name] or manifest['files'][name].get('after_sha256') != OUTPUT_PINS[name]:
                raise CandidateError('CANDIDATE_HASH_MISMATCH:' + name)
            io._source_text(data, str(output/name))
            observed[name] = (io._identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        for name, expected in observed.items():
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or expected != (io._identity(info), info.st_size, info.st_mtime_ns, info.st_ctime_ns):
                raise CandidateError('CANDIDATE_CHANGED_DURING_VERIFICATION:' + name)
        again, info = io._read_at(directory_fd, 'manifest.json')
        if (again != raw or io._identity(info) != io._identity(manifest_info)
                or set(os.listdir(directory_fd)) != names
                or io._identity(os.stat(output, follow_symlinks=False)) != io._identity(os.fstat(directory_fd))):
            raise CandidateError('CANDIDATE_CHANGED_DURING_VERIFICATION')
        return manifest
    finally:
        os.close(directory_fd)


def prepare(base_candidate, sources, output):
    if set(sources) != set(SOURCE_PINS):
        raise CandidateError('EXACT_SOURCE_MAPPING_REQUIRED')
    base_candidate, output = _safe_path(base_candidate), _safe_path(output)
    paths = {name: _safe_path(path) for name, path in sources.items()}
    input_roots = {base_candidate, HERE} | {path.parent for path in paths.values()}
    if any(output == root or root in output.parents or output in root.parents for root in input_roots):
        raise CandidateError('INPUT_OUTPUT_OVERLAP')
    if output.exists():
        raise CandidateError('OUTPUT_ALREADY_EXISTS')
    if not output.parent.is_dir():
        raise CandidateError('OUTPUT_PARENT_MISSING')
    io, helper_input = _load_helper('prepare_candidate.py')
    inputs = [helper_input]
    io.verify_candidate(base_candidate)  # Historical gate stays fixed to ten.
    if set(os.listdir(base_candidate)) != set(BASE_PINS) | {'manifest.json'}:
        raise CandidateError('BASE_MODULE_SET_INVALID')
    candidate, before_hashes = {}, {}
    for name, digest in BASE_PINS.items():
        path = base_candidate/name
        data, signature = _read_input(path, digest)
        inputs.append((path, data, signature))
        candidate[name] = data
        before_hashes[name] = digest
    data, signature = _read_input(base_candidate/'manifest.json')
    inputs.append((base_candidate/'manifest.json', data, signature))
    source_data = {}
    for name, path in paths.items():
        data, signature = _read_input(path, SOURCE_PINS[name])
        inputs.append((path, data, signature))
        source_data[name] = data
    for name, digest in RUNTIME_PINS.items():
        path = HERE/'runtime'/name
        data, signature = _read_input(path, digest)
        inputs.append((path, data, signature))
        candidate[name] = data
        before_hashes.setdefault(name, digest)
    master, snapshot = _load_helper('repair_master_shell.py'); inputs.append(snapshot)
    contract, snapshot = _load_helper('repair_public_contract.py'); inputs.append(snapshot)
    allocator, snapshot = _load_helper('allocator_integration.py'); inputs.append(snapshot)
    transforms = {
        'master_card.py': master.patch_master_shell,
        'cars_schema.py': allocator.patch_cars_schema,
        'db.py': allocator.patch_db,
        'ai_filter.py': allocator.patch_ai_filter,
    }
    for name, patcher in transforms.items():
        candidate[name] = patcher(source_data[name].decode()).encode()
        before_hashes[name] = SOURCE_PINS[name]
    candidate['ua_additional_spec.py'] = contract.patch_public_contract(candidate['ua_additional_spec.py'].decode()).encode()
    if set(candidate) != set(COMPLETE_FILES):
        raise CandidateError('ASSEMBLED_MODULE_SET_INVALID')
    for name, data in candidate.items():
        if sha(data) != OUTPUT_PINS[name]:
            raise CandidateError('ASSEMBLED_OUTPUT_HASH_MISMATCH:' + name)
        io._source_text(data, 'complete-candidate/' + name)
    manifest = {
        'contract_id': CONTRACT_ID, 'candidate_id': CANDIDATE_ID,
        'status': 'OFFLINE_COMPLETE_CANDIDATE_COMPILED', 'module_count': 15,
        'publication_mode': 'manifest_last', 'production_changed': False,
        'application_imported': False, 'overall_gate_b': 'NOT_EVALUATED',
        'base_pins': BASE_PINS, 'source_pins': SOURCE_PINS, 'runtime_pins': RUNTIME_PINS,
        'helper_pins': HELPER_PINS,
        'execution_dependency_pins': {name: SOURCE_PINS[name] for name in EXECUTION_DEPENDENCIES},
        'files': _expected_files(),
        'input_bindings': [{'path': str(path), 'sha256': sha(data), 'bytes': len(data)} for path, data, _ in inputs],
        'input_binding_scope': 'INFORMATIONAL_LOCAL_ASSEMBLY_PATHS_ONLY',
        'limitations': list(LIMITATIONS),
    }
    _recheck(inputs)
    stage = Path(tempfile.mkdtemp(prefix='.complete-spec-candidate-', dir=output.parent))
    try:
        for name, data in candidate.items():
            with (stage/name).open('xb') as handle:
                handle.write(data)
            os.chmod(stage/name, 0o600)
        with (stage/'manifest.json').open('xb') as handle:
            handle.write(_manifest_bytes(manifest))
        _recheck(inputs)
        published = _publish_manifest_last(stage, output, manifest, io)
        try:
            if verify_candidate(output) != manifest:
                raise CandidateError('FINAL_MANIFEST_READBACK_MISMATCH')
            _recheck(inputs)
        except BaseException:
            _invalidate_owned_readiness(output, published, io)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-candidate', type=Path)
    parser.add_argument('--sources-json', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if args.verify:
        result = verify_candidate(args.output)
    else:
        if args.base_candidate is None or args.sources_json is None:
            parser.error('base-candidate and sources-json required for assembly')
        data, _ = _read_input(args.sources_json)
        result = prepare(args.base_candidate, json.loads(data), args.output)
    print(json.dumps({'status': result['status'], 'candidate_id': result['candidate_id'],
                      'module_count': result['module_count'], 'publication_mode': result['publication_mode'],
                      'output': str(args.output), 'production_changed': False, 'overall_gate_b': 'NOT_EVALUATED'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
