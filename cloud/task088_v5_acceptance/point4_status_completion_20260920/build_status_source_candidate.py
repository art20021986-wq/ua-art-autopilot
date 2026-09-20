"""Exact source-only review artifact; no HTML/data/live state or authority claim."""
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

BASE = Path('/workspace/scratch/cc71e1c55fba')
REPO = BASE / 'pr114_review'
HISTORICAL = Path('/workspace/scratch/256f936ac1c5/private_v5_current')
CURRENT = BASE / 'private_inputs_ua0022_current'
SPEC = Path('/workspace/scratch/eb425df3a207/private_dependencies_20260920')
OUT = BASE / 'private_source_candidate_status'
EVIDENCE = BASE / 'status_point4_evidence/source_candidate'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, expected=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError('REGULAR_INPUT_REQUIRED:' + str(path))
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError('EXACT_PIN_REQUIRED:' + str(path))
    return raw


def write(path, data):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if read(path) != data:
        raise ValueError('OUTPUT_READBACK_FAILED')


def record(path, value):
    write(path, json.dumps(value, indent=2, sort_keys=True).encode() + b'\n')


def main():
    sys.dont_write_bytecode = True
    if OUT.exists() or EVIDENCE.exists():
        raise ValueError('NEW_UNIQUE_OUTPUT_REQUIRED')
    cloud = REPO / 'cloud'
    roots = [cloud / name for name in ('task088_price_sync', 'task088_stage3_renderer',
        'task088_autopilot_owner_policy', 'task088_v5_writer_fence')]
    public_pins = {str(path.relative_to(REPO)): sha(read(path)) for directory in roots for path in directory.glob('*.py')}
    record(EVIDENCE / 'INTENT.json', {'reason':'Bind the latest canonical 8-source/11-module composition for independent review while current 48 HTML bytes are still being recovered. No historical full candidate is regenerated.',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'public_code_sha256':public_pins,
        'script_sha256':sha(read(Path(__file__))), 'production_authority':False})
    historical_raw = gzip.decompress(base64.b64decode(read(cloud / 'task088_v5_acceptance/resume_20260915/preflight_retry/completed_report.json.gz.b64',
        '26c3641e83bf1ce634c0d9cb6cd13c4a377a976a304d2e2bbff853dd69c5b5d8')))
    if sha(historical_raw) != 'f5d1a56840288a012d334fd8f3362194d90cc86dc81877cf69ed0328e4c30fc7':
        raise ValueError('HISTORICAL_REPORT_DRIFT')
    old = json.loads(historical_raw)
    original = {name:read(HISTORICAL / name, value['before_sha256']) for name,value in old['sources'].items()}
    deps = {name:read(HISTORICAL / name, value) for name,value in old['dependencies'].items()}
    current_pins = {'cars_ui.py':'d9bd8cb352ad95892f8ac2cddcce02898ec7f3f2fe5013f1a5007bf1469db837',
        'stranica.py':'cdb532f36e6e8fd17c7f933ad347a8bb0bcd8c00644d9c8ea7d9e3ddbb6ae687',
        'publish_transaction_guard.py':'b1e89bfcbe4af4890d1023293cb8290f34b6c59673b7a8e692ab64928f640159'}
    original.update({name:read(CURRENT / name, pin) for name,pin in current_pins.items()})
    point3 = json.loads(read(cloud / 'task088_v5_writer_fence/handoff006_evidence/emergency007_point3/CANDIDATE_MANIFEST.json',
        '3a4843722a7c8c4186d3c6eef3e17f09e8cf87affe5f4d303183b9d15560acc4'))
    for name,pin in point3['dependency_before_sha256'].items():
        (original if name == 'ua_spec_permanent.py' else deps)[name] = read(SPEC / name, pin)
    counter_pin = '500ca67145faa38ca9f72ac6da85e2a7d1c351f8f2fcca4a2edeb34c22734c23'
    if old['system_inventory']['ua_site_counters.py']['sha256'] != counter_pin:
        raise ValueError('HISTORICAL_COUNTER_PIN_DRIFT')
    original['ua_site_counters.py'] = read(HISTORICAL / 'ua_site_counters.py', counter_pin)
    def audit(event, arguments):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'sqlite3.connect'):
            raise ValueError('OFFLINE_BUILD_FORBIDDEN:' + event)
    sys.addaudithook(audit)
    sys.path[:0] = [str(path) for path in roots]
    import install_package as engine
    from build_preflight_bundle import package_mapping
    if set(original) != engine.SOURCES or set(deps) != engine.DEPENDENCIES:
        raise ValueError('EXACT_SOURCE_DEPENDENCY_CLOSURE_REQUIRED')
    candidate = engine.build_source_candidates(original, deps)
    mapping = package_mapping(REPO)
    candidate.update({name:read(mapping[name]) for name in engine.MODULES})
    for name,raw in candidate.items():
        compile(raw, name, 'exec')
    for name,pin in public_pins.items():
        read(REPO / name, pin)
    OUT.mkdir(mode=0o700)
    for name,raw in candidate.items():
        write(OUT / name, raw)
    manifest = {name:{'before_sha256':sha(original[name]) if name in original else None,
        'after_sha256':sha(raw),'bytes':len(raw)} for name,raw in sorted(candidate.items())}
    result = {'contract':'PR114-STATUS-SOURCE-ONLY-REVIEW-CANDIDATE-1','status':'PASS_SOURCE_COMPOSITION_AND_COMPILE_ONLY',
        'input_source_sha256':{name:sha(raw) for name,raw in sorted(original.items())},
        'input_dependency_sha256':{name:sha(raw) for name,raw in sorted(deps.items())},
        'candidate':manifest,'candidate_manifest_sha256':sha(engine.encoded(manifest)),
        'public_code_sha256':public_pins,'private_candidate_directory':str(OUT),
        'source_files':len(engine.SOURCES),'module_files':len(engine.MODULES),
        'current_complete_server_snapshot':False,'current_html_or_rows_used':False,
        'full_candidate_generated':False,'production_written':False,'live_modules_imported':False,
        'script_sha256':sha(read(Path(__file__)))}
    record(EVIDENCE / 'RESULT.json', result)
    print(json.dumps({'status':result['status'],'candidate_manifest_sha256':result['candidate_manifest_sha256'],
        'source_files':result['source_files'],'module_files':result['module_files'],'directory':str(OUT)}))


if __name__ == '__main__':
    main()
