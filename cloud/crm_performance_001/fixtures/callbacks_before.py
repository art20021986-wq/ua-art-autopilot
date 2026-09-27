async def _ua004_sync_current_stage(card):
    if not card.get('published'):
        return ''
    try:
        from ua_stage_catalog_sync import reconcile
        await _ua004_asyncio.to_thread(reconcile, apply=True)
        _UA004_RETRY_STATE.update(signature=None, failures=0)
        return '✅ Завершил — этап в каталоге и счётчики синхронизированы.'
    except Exception:
        log.exception('UA004: этап сохранён в CRM, синхронизация каталога ожидает повтора')
        return 'Этап сохранён в CRM. Каталог пока не обновлён; выполняется повторная проверка.'

async def _ua004_stage_reconcile_job(context):
    try:
        signature = await _ua004_asyncio.to_thread(_ua004_source_signature)
        if signature == _UA004_RETRY_STATE['verified_signature']:
            return
        if signature != _UA004_RETRY_STATE['signature']:
            _UA004_RETRY_STATE.update(signature=signature, failures=0)
        if _UA004_RETRY_STATE['failures'] >= 3:
            return
        from ua_stage_catalog_sync import reconcile
        result = await _ua004_asyncio.to_thread(reconcile, apply=True)
        _UA004_RETRY_STATE['failures'] = 0
        _UA004_RETRY_STATE['verified_signature'] = signature
        if result.get('files'):
            log.info('UA004: stage sync verified: %s', result)
    except Exception:
        _UA004_RETRY_STATE['failures'] += 1
        log.exception('UA004: stage sync attempt %d/3 failed', _UA004_RETRY_STATE['failures'])
