'''UA ART Shared Memory - core validation and IO library.
Stdlib only. No network access. No production or CRM write capability.
'''

import json
import os
import re
import hashlib

RECORD_CLASSES = {
    'FACT', 'OWNER_DIRECTIVE', 'DECISION', 'HYPOTHESIS', 'INCIDENT',
    'TASK', 'RESULT', 'WARNING', 'APPROVAL',
}

AUTHORITY_LEVELS = [
    'OWNER_DIRECTIVE', 'OWNER_APPROVAL', 'VERIFIED_PRODUCTION',
    'VERIFIED_CRM', 'CANONICAL_GITHUB', 'AUTOMATED_EVIDENCE',
    'AI_REPORT', 'HYPOTHESIS',
]

EXCLUSIVE_CLASSES = {'DECISION', 'OWNER_DIRECTIVE', 'APPROVAL', 'FACT'}

SECRET_PATTERNS = [
    re.compile(r'api[_-]?key', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'sk-[A-Za-z0-9]{10,}'),
    re.compile(r'ghp_[A-Za-z0-9]{20,}'),
    re.compile(r'BEGIN (RSA|EC|OPENSSH|PRIVATE) KEY'),
    re.compile(r'Bearer\s+[A-Za-z0-9\-_.]{10,}'),
]

REQUIRED_RECORD_FIELDS = (
    'record_id', 'record_class', 'subject', 'body', 'authority',
    'created_at', 'author', 'immutable',
)


class MemoryGuardError(Exception):
    pass


class SchemaError(MemoryGuardError):
    pass


class StaleProposalError(MemoryGuardError):
    pass


class UnsupportedClassError(MemoryGuardError):
    pass


class SecretDetectedError(MemoryGuardError):
    pass


class ForgedDirectiveError(MemoryGuardError):
    pass


class MalformedEvidenceError(MemoryGuardError):
    pass


class PathTraversalError(MemoryGuardError):
    pass


def scan_for_secrets(text):
    if not text:
        return False
    if not isinstance(text, str):
        text = json.dumps(text)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


def check_no_path_traversal(obj):
    def _walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and 'path' in key.lower():
                    if '..' in value or value.startswith('/') or value.startswith('~') or '\\' in value:
                        raise PathTraversalError('Unsafe path value detected in field: ' + key)
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)
    _walk(obj)


def load_manifest(path):
    with open(path, 'r', encoding='utf-8') as handle:
        return json.load(handle)


def save_manifest(path, manifest):
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write('\n')


def load_records(path):
    records = []
    if not os.path.exists(path):
        return records
    with open(path, 'r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_record_schema(record):
    for field in REQUIRED_RECORD_FIELDS:
        if field not in record:
            raise SchemaError('Record missing required field: ' + field)
    if record['record_class'] not in RECORD_CLASSES:
        raise UnsupportedClassError('Unsupported record_class: ' + str(record['record_class']))
    if record['authority'] not in AUTHORITY_LEVELS:
        raise SchemaError('Unknown authority level: ' + str(record['authority']))
    if not isinstance(record['immutable'], bool):
        raise SchemaError('Field immutable must be boolean')
    if not record.get('subject') or not record.get('body'):
        raise SchemaError('Record subject and body must be non-empty')


def compute_active_view(records):
    superseded_ids = set()
    for record in records:
        target = record.get('supersedes')
        if target:
            superseded_ids.add(target)
    groups = {}
    for record in records:
        if record['record_id'] in superseded_ids:
            continue
        key = (record['subject'], record['record_class'])
        groups.setdefault(key, []).append(record['record_id'])
    view = {}
    for record in records:
        rid = record['record_id']
        if rid in superseded_ids:
            view[rid] = 'SUPERSEDED'
            continue
        key = (record['subject'], record['record_class'])
        if record['record_class'] in EXCLUSIVE_CLASSES and len(groups.get(key, [])) > 1:
            view[rid] = 'CONFLICT'
        else:
            view[rid] = 'ACTIVE'
    return view


def validate_proposal(proposal, manifest, existing_records):
    for field in ('proposal_id', 'based_on_memory_version', 'author', 'created_at', 'justification', 'records'):
        if field not in proposal:
            raise SchemaError('Proposal missing required field: ' + field)
    check_no_path_traversal(proposal)
    if proposal['based_on_memory_version'] != manifest['memory_version']:
        raise StaleProposalError(
            'Proposal is based on memory_version ' + str(proposal['based_on_memory_version']) +
            ' but canonical memory_version is ' + str(manifest['memory_version'])
        )
    if not isinstance(proposal['records'], list) or not proposal['records']:
        raise SchemaError('Proposal must include at least one record')
    existing_index = {record['record_id']: record for record in existing_records}
    validated_records = []
    for record in proposal['records']:
        validate_record_schema(record)
        if record['record_class'] == 'OWNER_DIRECTIVE' and proposal['author'] != 'OWNER':
            raise ForgedDirectiveError('Only OWNER may author OWNER_DIRECTIVE records')
        supersedes = record.get('supersedes')
        if supersedes:
            target = existing_index.get(supersedes)
            if target is None:
                raise SchemaError('supersedes target not found: ' + supersedes)
            if target.get('record_class') == 'OWNER_DIRECTIVE' and target.get('immutable') and proposal['author'] != 'OWNER':
                raise ForgedDirectiveError('Cannot supersede an immutable OWNER_DIRECTIVE without OWNER authorship')
        if scan_for_secrets(record.get('body', '')):
            raise SecretDetectedError('Secret-like content detected in record body field')
        if scan_for_secrets(record.get('subject', '')):
            raise SecretDetectedError('Secret-like content detected in record subject field')
        evidence = record.get('evidence')
        if evidence is not None:
            if not isinstance(evidence, dict) or 'source' not in evidence or 'verified_at' not in evidence:
                raise MalformedEvidenceError('evidence must be an object with source and verified_at fields')
            if scan_for_secrets(json.dumps(evidence)):
                raise SecretDetectedError('Secret-like content detected in record evidence field')
        validated_records.append(record)
    combined = list(existing_records) + validated_records
    view = compute_active_view(combined)
    conflicts = sorted([rid for rid, status in view.items() if status == 'CONFLICT'])
    return validated_records, conflicts
