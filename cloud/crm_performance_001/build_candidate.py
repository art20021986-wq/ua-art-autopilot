"""Build a source-pinned CRM performance candidate without writing production."""
import ast
import hashlib

SOURCE_SHA256 = {
    "cars_ui.py": "c17a45d64f17fbab2e2f032061f6037a48bb5fa038b3f02e20995b5e50fbca7b",
    "ua_crm_public_sync.py": "2b5f6a2473b263fddd6ab3266a3ba76cc9738da15178f865862098821cabcc41",
}


def once(source, before, after):
    if source.count(before) != 1:
        raise ValueError("SOURCE_ANCHOR_COUNT")
    return source.replace(before, after, 1)


def replace_function(source, name, replacement):
    nodes = [node for node in ast.parse(source).body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if len(nodes) != 1:
        raise ValueError("FUNCTION_COUNT:" + name)
    return once(source, ast.get_source_segment(source, nodes[0]), replacement.rstrip())


def patch_callbacks(source):
    source = replace_function(source, "_ua004_sync_current_stage", '''async def _ua004_sync_current_stage(card):
    if not card.get('published'):
        return ''
    try:
        from ua_crm_public_sync import notify
        notify()
        return 'Этап сохранён в CRM. Обновление сайта выполняется в фоне.'
    except Exception:
        log.exception('UA004: unable to notify the publication worker')
        return 'Этап сохранён в CRM. Обновление сайта пока не подтверждено.'
''')
    return replace_function(source, "_ua004_stage_reconcile_job", '''async def _ua004_stage_reconcile_job(context):
    # The durable worker owns publication, locking, validation and retry timing.
    # Do not reset a second retry budget when generated HTML timestamps change.
    from ua_crm_public_sync import notify
    notify()
''')


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


def build(sources):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError("SOURCE_SET")
    result = {}
    for name, transform in (("cars_ui.py", patch_callbacks),
                            ("ua_crm_public_sync.py", patch_worker)):
        raw = sources[name]
        if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256[name]:
            raise ValueError("SOURCE_CHANGED:" + name)
        candidate = transform(raw.decode('utf-8'))
        compile(candidate, name, 'exec')
        result[name] = candidate.encode('utf-8')
    return result
