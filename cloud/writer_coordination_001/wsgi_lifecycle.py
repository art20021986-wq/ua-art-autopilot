"""Strict, data-only uWSGI lifecycle interpretation for two complete log captures.

This module has no platform mutation, network, or authority-creation capability.
The caller must obtain both byte strings through the authenticated platform log
transport and bind the control operation separately.  A successful interpretation
is evidence of log events only: it never grants an installation window, removes
HALT, proves loaded code, or authenticates caller-provided bytes.
"""
from __future__ import annotations

import hashlib
import re


class LifecycleError(ValueError):
    pass


MAX_BYTES = 8 * 1024 * 1024
MAX_LINES = 50000
_STAMP = re.compile(r'^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\s+(?:-\s+)?')
_MASTER = re.compile(r'(?:spawned|gracefully \(RE\)spawned) uWSGI master process \(pid: ([1-9]\d*)\)')
_WORKER = re.compile(r'spawned uWSGI worker ([1-9]\d*) \(pid: ([1-9]\d*), cores: ([1-9]\d*)\)')
_BURIAL = re.compile(r'worker ([1-9]\d*) buried after (\d+) seconds')
_START = re.compile(r'\*\*\* Starting uWSGI ([0-9.]+) .* \*\*\*')
_MAPPED = re.compile(r'mapped \d+ bytes \(\d+ KB\) for ([1-9]\d*) cores')
_OFFLOAD = re.compile(r'spawned ([1-9]\d*) offload threads for uWSGI worker ([1-9]\d*)')
_CHILD_EXIT = re.compile(r'subprocess ([1-9]\d*) exited with code (\d+)')
_UNKNOWN = re.compile(r'(?:uWSGI master|uWSGI worker|\bworker\s+\d+|HARAKIRI ON WORKER|subprocess|spooler|\bmule\b|\bgateway\b|\bdaemon\b)', re.I)


def _require(condition, code):
    if not condition:
        raise LifecycleError(code)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inspect_log(raw: bytes) -> dict:
    """Parse an entire bounded capture; reject ambiguous process generations.

    Worker identity includes the master spawn byte offset and worker spawn byte
    offset, not only its PID or slot.  PID reuse in a later generation is valid.
    A new master while older workers remain alive is ambiguous and is rejected.
    Unsupported lifecycle formats stop interpretation instead of being ignored.
    """
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, 'LOG_BYTES_OR_SIZE')
    _require(raw.endswith(b'\n') and b'\0' not in raw, 'LOG_INCOMPLETE_LINE_OR_NUL')
    try:
        lines = raw.decode('utf-8', errors='strict').splitlines(keepends=True)
    except UnicodeError as exc:
        raise LifecycleError('LOG_NOT_UTF8') from exc
    _require(len(lines) <= MAX_LINES, 'LOG_LINE_LIMIT')
    events, alive, terminated, children = [], {}, [], []
    master = None
    closed = False
    startup = None
    startup_claimed = False
    mapped_cores = None
    preforking = False
    prefix_boundary = None
    ignored_prefix_bytes = 0
    offset = 0
    for number, encoded in enumerate(lines, 1):
        line = _STAMP.sub('', encoded.rstrip('\r\n'), count=1)
        base = {'line': number, 'offset': offset}
        offset += len(encoded.encode('utf-8'))
        match = _START.fullmatch(line)
        if match:
            _require(not alive, 'STARTUP_WITH_UNTERMINATED_WORKERS')
            _require(master is None or closed, 'STARTUP_WITH_OPEN_MASTER')
            _require(startup is None or startup_claimed, 'DUPLICATE_UNCLAIMED_STARTUP')
            if startup is None and base['offset']:
                _require(prefix_boundary is not None, 'INCOMPLETE_HISTORY_WITHOUT_SHUTDOWN_BOUNDARY')
                ignored_prefix_bytes = base['offset']
            startup = {**base, 'version': match[1]}
            startup_claimed = False
            mapped_cores, preforking = None, False
            events.append({**base, 'kind': 'STARTUP', 'version': match[1]})
            continue
        if startup is None:
            # Rotated logs can begin at the end of an old process.  Only a
            # complete subsequent startup after its shutdown boundary is used;
            # the omitted history is explicit and never treated as drained.
            if line == 'goodbye to uWSGI.':
                prefix_boundary = base['offset']
            elif _UNKNOWN.search(line):
                prefix_boundary = None
            continue
        match = _MAPPED.fullmatch(line)
        if match:
            _require(master is None or closed, 'MAPPED_CORES_DURING_OPEN_MASTER')
            _require(mapped_cores is None, 'DUPLICATE_CORE_CAPACITY')
            mapped_cores = int(match[1])
            continue
        if line == '*** Operational MODE: preforking ***':
            _require(master is None or closed, 'MODE_DURING_OPEN_MASTER')
            preforking = True
            continue
        match = _MASTER.fullmatch(line)
        if match:
            _require(not alive, 'NEW_MASTER_WITH_UNTERMINATED_WORKERS')
            _require(master is None or closed, 'MASTER_GENERATION_BOUNDARY_MISSING')
            _require(not startup_claimed, 'NEW_MASTER_WITHOUT_NEW_STARTUP')
            _require(mapped_cores is not None and preforking, 'COMPLETE_PREFORK_STARTUP_REQUIRED')
            master = {'pid': int(match[1]), 'offset': base['offset'],
                      'startup_offset': startup['offset'], 'mapped_cores': mapped_cores}
            closed = False
            startup_claimed = True
            events.append({**base, 'kind': 'MASTER_SPAWN', 'master': dict(master)})
            continue
        match = _WORKER.fullmatch(line)
        if match:
            _require(master is not None and not closed, 'WORKER_WITHOUT_OPEN_MASTER')
            slot, pid, cores = map(int, match.groups())
            _require(slot not in alive, 'DUPLICATE_LIVE_WORKER_SLOT')
            _require(all(worker['pid'] != pid for worker in alive.values()), 'DUPLICATE_LIVE_WORKER_PID')
            _require(pid != master['pid'], 'WORKER_PID_EQUALS_MASTER')
            worker = {'slot': slot, 'pid': pid, 'cores': cores,
                      'master_offset': master['offset'], 'spawn_offset': base['offset']}
            alive[slot] = worker
            _require(sum(item['cores'] for item in alive.values()) <= mapped_cores, 'WORKERS_EXCEED_MAPPED_CORES')
            events.append({**base, 'kind': 'WORKER_SPAWN', 'worker': dict(worker)})
            continue
        match = _OFFLOAD.fullmatch(line)
        if match:
            slot = int(match[2])
            _require(slot in alive, 'OFFLOAD_WITHOUT_LIVE_WORKER')
            events.append({**base, 'kind': 'OFFLOAD_THREADS', 'worker': dict(alive[slot]),
                           'threads': int(match[1])})
            continue
        match = _CHILD_EXIT.fullmatch(line)
        if match:
            _require(master is not None and not closed, 'CHILD_EXIT_WITHOUT_OPEN_MASTER')
            child = {**base, 'kind': 'UNSCOPED_CHILD_EXIT', 'pid': int(match[1]),
                     'exit_code': int(match[2]), 'master_offset': master['offset']}
            children.append(child)
            events.append(child)
            continue
        match = _BURIAL.fullmatch(line)
        if match:
            slot = int(match[1])
            _require(master is not None and not closed and slot in alive, 'BURIAL_WITHOUT_UNIQUE_LIVE_WORKER')
            worker = alive.pop(slot)
            terminated.append(worker)
            events.append({**base, 'kind': 'WORKER_BURIED', 'worker': worker})
            continue
        if line in ('goodbye to uWSGI.', 'binary reloading uWSGI...'):
            _require(master is not None and not closed, 'MASTER_CLOSE_WITHOUT_OPEN_MASTER')
            _require(not alive, 'MASTER_CLOSE_WITH_UNTERMINATED_WORKERS')
            closed = True
            events.append({**base, 'kind': 'MASTER_CLOSE', 'master': dict(master)})
            continue
        _require(_UNKNOWN.search(line) is None, 'UNSUPPORTED_LIFECYCLE_LINE:' + str(number))
    _require(master is not None, 'MASTER_BASELINE_MISSING')
    return {'schema': 'UA-ART-WSGI-LIFECYCLE-OBSERVATION-1',
            'source_sha256': _sha(raw), 'source_bytes': len(raw), 'line_count': len(lines),
            'ignored_historical_prefix_bytes': ignored_prefix_bytes,
            'ignored_historical_prefix_sha256': _sha(raw[:ignored_prefix_bytes]),
            'events': events, 'current_master': master, 'current_master_closed': closed,
            'pending_startup': dict(startup) if not startup_claimed else None,
            'alive_workers': sorted(alive.values(), key=lambda worker: worker['slot']),
            'terminated_workers': terminated, 'unscoped_child_exits': children,
            'current_generation_scope_blockers': ['UNSCOPED_CHILD_PROCESSES'] if any(
                child['master_offset'] == master['offset'] for child in children) else [],
            'transport_authenticated': False,
            'external_writer_verified': False, 'installation_authorized': False}


def compare_captures(before: bytes, after: bytes, *, expected_worker_slots: tuple[int, ...],
                     operation: str) -> dict:
    """Derive only an ordered-log result for a separately authenticated operation.

    DISABLE requires the baseline master to close and no later process start.
    RELOAD permits later generations only after the baseline master closes; it
    does not attest that any new generation loaded the intended source bytes.
    Log truncation or rotation always fails here and requires a fresh baseline.
    """
    _require(operation in ('DISABLE', 'RELOAD'), 'OPERATION_SCOPE')
    _require(type(expected_worker_slots) is tuple and expected_worker_slots
             and all(type(slot) is int and slot > 0 for slot in expected_worker_slots)
             and tuple(sorted(set(expected_worker_slots))) == expected_worker_slots,
             'REVIEWED_WORKER_SLOTS_REQUIRED')
    baseline = inspect_log(before)
    observed = inspect_log(after)
    _require(len(after) > len(before) and after.startswith(before), 'LOG_NOT_STRICT_APPEND_ONLY')
    _require(not baseline['current_master_closed'], 'BASELINE_MASTER_NOT_RUNNING')
    _require(baseline['pending_startup'] is None and observed['pending_startup'] is None,
             'INCOMPLETE_NEW_STARTUP')
    _require(tuple(worker['slot'] for worker in baseline['alive_workers']) == expected_worker_slots,
             'BASELINE_WORKER_INVENTORY_MISMATCH')
    _require(sum(worker['cores'] for worker in baseline['alive_workers']) == baseline['current_master']['mapped_cores'],
             'BASELINE_MAPPED_CORE_COVERAGE_INCOMPLETE')
    _require(not baseline['current_generation_scope_blockers'], 'UNSCOPED_CHILD_PROCESSES')
    appended = [event for event in observed['events'] if event['offset'] >= len(before)]
    _require(not any(event['kind'] == 'UNSCOPED_CHILD_EXIT' for event in appended), 'UNSCOPED_CHILD_PROCESSES')
    old = baseline['alive_workers']
    burials = [event['worker'] for event in appended if event['kind'] == 'WORKER_BURIED']
    _require(all(worker in burials for worker in old), 'OLD_WORKERS_NOT_ALL_BURIED')
    _require(any(event['kind'] == 'MASTER_CLOSE' and event['master'] == baseline['current_master']
                 for event in appended), 'OLD_MASTER_CLOSE_NOT_OBSERVED')
    _require(not any(worker in observed['alive_workers'] for worker in old), 'OLD_WORKER_STILL_LIVE')
    if operation == 'DISABLE':
        _require(not observed['alive_workers'] and observed['current_master_closed'], 'DISABLE_HAS_LIVE_WORKERS')
        _require(not any(event['kind'] in ('STARTUP', 'MASTER_SPAWN', 'WORKER_SPAWN') for event in appended),
                 'PROCESS_STARTED_DURING_DISABLE')
    return {'schema': 'UA-ART-WSGI-LOG-TRANSITION-1',
            'status': 'PREEXISTING_WORKERS_TERMINATED_IN_ORDERED_LOG', 'operation': operation,
            'before_sha256': baseline['source_sha256'], 'before_bytes': len(before),
            'after_sha256': observed['source_sha256'], 'after_bytes': len(after),
            'baseline_master': baseline['current_master'], 'baseline_workers': old,
            'appended_lifecycle_events': appended, 'current_workers': observed['alive_workers'],
            'evidence_scope': 'COMPLETE_LOG_BYTES_ONLY_REQUIRES_AUTHENTICATED_OPERATION_BINDING',
            'transport_authenticated': False, 'loaded_runtime_verified': False,
            'external_writer_verified': False, 'installation_authorized': False}
