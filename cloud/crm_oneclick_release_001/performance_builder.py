"""Build a source-pinned CRM performance candidate without writing production."""
import hashlib
import importlib.util
from pathlib import Path


import stage_builder as STAGE

SOURCE_SHA256 = {
    **STAGE.SOURCE_SHA256,
    "ua_crm_public_sync.py": "2b5f6a2473b263fddd6ab3266a3ba76cc9738da15178f865862098821cabcc41",
}
DEPENDENCY_SHA256 = {name: digest for name, digest in STAGE.DEPENDENCY_SHA256.items()
                     if name != 'ua_crm_public_sync.py'}


def once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("SOURCE_ANCHOR_COUNT")
    return source.replace(before, after, 1)


def patch_worker(source):
    source = once(source, "        retry = state.setdefault('retry', {})", '''        retry = state.setdefault('retry', {})
        # A catalog set mismatch affects the whole publication, not one car.
        # Persist the cooldown so restarts and repeated UI wakes do not defeat it.
        source_revision = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        catalog_retry = state.get('catalog_retry', {})
        if (catalog_retry.get('source_revision') == source_revision
                and catalog_retry.get('after', 0) > clock()):
            return 'catalog_retry_pending'
        if catalog_retry and catalog_retry.get('source_revision') != source_revision:
            # Fresh operator data may resolve the mismatch; keep its chance to run.
            blocked_code = catalog_retry.get('code')
            retry = {key: value for key, value in retry.items()
                     if blocked_code not in value.get('error', '')} if blocked_code else retry
            state['retry'] = retry
            state.pop('catalog_retry', None)''')
    source = once(source, "                retry.pop(identity, None)",
                  "                retry.pop(identity, None)\n                state.pop('catalog_retry', None)")
    source = once(source, "min(300, 15 * 2 ** min(count-1, 5))",
                  "min(900, 15 * 2 ** min(count-1, 6))")
    source = once(source,
                  "                save_state(state)\n                LOG.exception('CRM sync failed; retry pending: %s', revision['code'])",
                  '''                catalog_error = next((code for code in (
                    'CATALOG_ROW_SET_MISMATCH', 'CATALOG_PUBLISHED_SET_MISMATCH'
                ) if code in str(exc)), None)
                if catalog_error:
                    state['catalog_retry'] = {'source_revision': source_revision,
                                              'after': clock() + 900, 'code': catalog_error}
                save_state(state)
                LOG.exception('CRM sync failed; retry pending: %s', revision['code'])
                if catalog_error:
                    return 'catalog_retry_pending'
'''.rstrip())
    return once(source, "in ('published', 'changed_during_publish'):",
                "in ('published', 'hidden', 'changed_during_publish'):")


def build(sources, dependencies):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError("SOURCE_SET")
    for name, raw in sources.items():
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError("SOURCE_CHANGED:" + name)
    if set(dependencies) != set(DEPENDENCY_SHA256):
        raise ValueError('DEPENDENCY_SET')
    # Reuse the current stage repair. Never overwrite its router/inventory fixes
    # with an independently built cars_ui.py.
    result = STAGE.build({name: sources[name] for name in STAGE.SOURCE_SHA256},
                         {**dependencies, 'ua_crm_public_sync.py': sources['ua_crm_public_sync.py']})
    candidate = patch_worker(sources['ua_crm_public_sync.py'].decode('utf-8'))
    compile(candidate, 'ua_crm_public_sync.py', 'exec')
    result['ua_crm_public_sync.py'] = candidate.encode('utf-8')
    return result
