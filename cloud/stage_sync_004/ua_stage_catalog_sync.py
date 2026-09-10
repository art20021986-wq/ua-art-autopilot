"""Synchronize existing catalog stage fields and counters from committed CRM rows."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import uuid
from pathlib import Path


class StageSyncError(RuntimeError):
    pass


STAGES = {
    1: ('korea', 'korea', 'В Корее', 'У Кореї'),
    2: ('sea', 'more', 'На пароме', 'На поромі'),
    3: ('georgia', 'gruzia', 'В Грузии', 'У Грузії'),
    4: ('kiev', 'kiev', 'В Киеве', 'У Києві'),
}
ALIASES = {'korea': 'korea', 'sea': 'sea', 'more': 'sea', 'ferry': 'sea',
           'georgia': 'georgia', 'gruzia': 'georgia', 'kiev': 'kiev', 'kyiv': 'kiev'}
ARTICLE = re.compile(r'<article\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bcatalog-card\b)[^>]*>.*?</article\s*>', re.I | re.S)
VIN = re.compile(r'<div\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bua-cat-vin-v1\b)(?=[^>]*\bdata-ua-card\s*=)[^>]*>', re.I | re.S)
PILL = re.compile(r'(<div\b(?=[^>]*\bclass\s*=\s*["\'][^"\']*\bstatus-pill\b)[^>]*>)([^<]*)(</div\s*>)', re.I | re.S)
PHRASE = re.compile(r'^(\s*)(В Корее|У Кореї|На пароме|На поромі|В Грузии|У Грузії|В Киеве|У Києві)(?=\s|$)')


def stage_of(row):
    status = str(row.get('status') or '').strip().lower()
    if status.startswith('kr_'):
        return 1
    if status.startswith(('sea_', 'sold_transit')):
        return 2
    if status.startswith('ge_'):
        return 3
    if status.startswith('ua_') or status in ('sold', 'archive'):
        return 4
    raise StageSyncError('UNKNOWN_STAGE:' + str(row.get('auto_number')) + ':' + status)


def _attribute(tag, name):
    matches = list(re.finditer(r'(\s' + re.escape(name) + r'\s*=\s*)(["\'])(.*?)\2', tag, re.I | re.S))
    if len(matches) != 1:
        raise StageSyncError('ATTRIBUTE_COUNT:' + name)
    return matches[0]


def _put(tag, name, value):
    match = _attribute(tag, name)
    return tag[:match.start(3)] + str(value) + tag[match.end(3):]


def _phrase(value, stage, language=None):
    match = PHRASE.match(value)
    if not match:
        raise StageSyncError('STATUS_LABEL_SHAPE')
    ukrainian = language == 'uk' if language else match[2] in {s[3] for s in STAGES.values()}
    label = STAGES[stage][3 if ukrainian else 2]
    return value[:match.start(2)] + label + value[match.end(2):]


def _patch_article(block, stage):
    outer = re.match(r'<article\b[^>]*>', block, re.I | re.S)
    if not outer:
        raise StageSyncError('ARTICLE_SHAPE')
    tag = _put(_put(outer[0], 'data-stage', STAGES[stage][0]), 'data-ua-stage', stage)
    block = tag + block[outer.end():]
    matches = list(VIN.finditer(block))
    if len(matches) != 1:
        raise StageSyncError('VIN_MARKER_COUNT')
    match = matches[0]
    tag = _put(_put(match[0], 'data-ua-stage-tile', stage), 'data-category', STAGES[stage][1])
    block = block[:match.start()] + tag + block[match.end():]
    matches = list(PILL.finditer(block))
    if len(matches) != 1:
        raise StageSyncError('STATUS_PILL_COUNT')
    match = matches[0]
    tag = match[1]
    for language in ('ru', 'uk'):
        name = 'data-' + language
        tag = _put(tag, name, _phrase(_attribute(tag, name)[3], stage, language))
    return block[:match.start()] + tag + _phrase(match[2], stage) + match[3] + block[match.end():]


def patch_catalog_stages(source, rows):
    """Patch only explicit stage attributes and stage-label prefixes."""
    seen, changed = set(), []

    def replace(match):
        block = match[0]
        markers = list(VIN.finditer(block))
        if len(markers) != 1:
            raise StageSyncError('VIN_MARKER_COUNT')
        code = _attribute(markers[0][0], 'data-ua-card')[3].strip().upper()
        if not re.fullmatch(r'UA-[0-9]{4,}', code) or code not in rows or code in seen:
            raise StageSyncError('CATALOG_ID:' + code)
        seen.add(code)
        result = _patch_article(block, stage_of(rows[code]))
        if result != block:
            changed.append(code)
        return result

    candidate = ARTICLE.sub(replace, source)
    if seen != set(rows):
        raise StageSyncError('CATALOG_PUBLISHED_SET_MISMATCH')
    return candidate, sorted(changed)


def _validate_snapshot(counter, source, expected):
    records, counts = counter.catalog_snapshot(source)
    actual = {code: ALIASES.get(stage) for code, stage in records.items()}
    if actual != expected or any(stage is None for stage in actual.values()):
        raise StageSyncError('CATALOG_CRM_STAGE_MISMATCH')
    wanted = {'all': len(expected), **{key: 0 for key in ('kiev', 'georgia', 'sea', 'korea')}}
    for stage in expected.values():
        wanted[stage] += 1
    if counts != wanted or counts['all'] != sum(counts[key] for key in wanted if key != 'all'):
        raise StageSyncError('COUNTER_INVARIANT')
    return counts


def reconcile(*, apply=False):
    """Use the existing publisher lock. Never write CRM, primary pages or media."""
    import publish_transaction_guard as pub
    import ua_site_counters as counter

    with pub._exclusive_lock():
        rows, digest = pub._row_map()
        expected = {}
        for code, row in rows.items():
            if pub._stage(row) != stage_of(row):
                raise StageSyncError('CANONICAL_STAGE_DISAGREEMENT:' + code)
            expected[code] = STAGES[stage_of(row)][0]
        changes, changed_ids, counts, home_paths = {}, set(), None, []
        roots = tuple(Path(root) for root in pub.ROOTS)
        if len(roots) != 2 or len(set(roots)) != 2:
            raise StageSyncError('CATALOG_ROOTS')
        for root in roots:
            path = root / 'katalog.html'
            before = path.read_bytes()
            candidate, ids = patch_catalog_stages(before.decode('utf-8'), rows)
            changed_ids.update(ids)
            current = _validate_snapshot(counter, candidate, expected)
            if counts is not None and current != counts:
                raise StageSyncError('CATALOG_COPIES_DIFFER')
            counts = current
            candidate = counter.patch_catalog(candidate, counts)
            _validate_snapshot(counter, candidate, expected)
            pub._validate_catalog(candidate, rows)
            changes[path] = (before, candidate.encode('utf-8'))
            home = root / 'index.html'
            # Match deployed ua_site_counters.prepare_updates: one root may
            # contain only an index redirect, which is not a counter surface.
            if home.is_file():
                old_home = home.read_bytes()
                home_source = old_home.decode('utf-8')
                if 'outline-cta' in home_source or 'stage-card' in home_source:
                    changes[home] = (old_home, counter.patch_home(home_source, counts).encode('utf-8'))
                    home_paths.append(str(home))
        if not home_paths:
            raise StageSyncError('HOMEPAGE_COUNTER_SURFACE_MISSING')
        for code in changed_ids:
            for root in roots:
                primary = (root / (code + '.html')).read_text(encoding='utf-8')
                markers = re.findall(r'\bdata-ua-stage-current\s*=\s*["\']([1-4])["\']', primary)
                if markers != [str(stage_of(rows[code]))]:
                    raise StageSyncError('PRIMARY_STAGE_NOT_READY:' + code)
        changes = {path: pair for path, pair in changes.items() if pair[0] != pair[1]}
        result = {'status': 'CHECKED' if changes else 'NOOP', 'changed_ids': sorted(changed_ids),
                  'counts': counts, 'files': sorted(map(str, changes)), 'home_paths': home_paths}
        if not apply or not changes:
            return result
        if pub._row_map()[1] != digest:
            raise StageSyncError('CRM_CHANGED_BEFORE_INSTALL')
        backup = Path(pub.ROOT) / 'backups/stage_catalog_sync' / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex[:8])
        backup.mkdir(parents=True, exist_ok=False)
        manifest = {}
        for number, (path, (before, after)) in enumerate(changes.items()):
            saved = backup / (str(number) + '.html')
            pub._atomic(saved, before, 0o600)
            manifest[str(path)] = {'backup': saved.name, 'before': hashlib.sha256(before).hexdigest(),
                                   'after': hashlib.sha256(after).hexdigest(), 'mode': path.stat().st_mode & 0o777}
        pub._atomic(backup / 'manifest.json', json.dumps(manifest, sort_keys=True).encode(), 0o600)
        attempted = []
        try:
            for path, (before, after) in changes.items():
                if path.read_bytes() != before:
                    raise StageSyncError('SOURCE_CHANGED:' + str(path))
                attempted.append(path)
                pub._atomic(path, after, manifest[str(path)]['mode'])
                if path.read_bytes() != after:
                    raise StageSyncError('READBACK:' + str(path))
            if pub._row_map()[1] != digest:
                raise StageSyncError('CRM_CHANGED_DURING_INSTALL')
            for root in roots:
                _validate_snapshot(counter, (root / 'katalog.html').read_text(encoding='utf-8'), expected)
        except Exception as original:
            errors = []
            for path in reversed(attempted):
                before, after = changes[path]
                try:
                    current = path.read_bytes()
                    if current not in (before, after):
                        raise StageSyncError('ROLLBACK_SOURCE_CHANGED:' + str(path))
                    if current != before:
                        pub._atomic(path, before, manifest[str(path)]['mode'])
                    if path.read_bytes() != before:
                        raise StageSyncError('ROLLBACK_READBACK:' + str(path))
                except Exception as exc:
                    errors.append(str(exc))
            if errors:
                raise StageSyncError(str(original) + '; rollback: ' + '; '.join(errors)) from original
            raise
        result.update(status='APPLIED', backup=str(backup))
        return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(reconcile(apply=args.apply), ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({'status': 'FAIL', 'error': str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
