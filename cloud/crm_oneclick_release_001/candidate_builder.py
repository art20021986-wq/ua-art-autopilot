"""Compose one-click publication with the reviewed active-catalog/stage repair."""
import ast
import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
import performance_builder as PERF
STAGE = PERF.STAGE
SOURCE_SHA256 = {**STAGE.SOURCE_SHA256,
    'ua_crm_public_sync.py': STAGE.DEPENDENCY_SHA256['ua_crm_public_sync.py']}
DEPENDENCY_SHA256 = {name: value for name, value in STAGE.DEPENDENCY_SHA256.items()
                     if name != 'ua_crm_public_sync.py'}
once = STAGE.once


def patch_worker(source):
    source = PERF.patch_worker(source)
    source = once(source, "        retry = state.setdefault('retry', {})", """        retry = state.setdefault('retry', {})
        import ua_publish_requests as requests
        explicit = requests.pending(ROOT)
        for identity, request in explicit.items():
            if identity not in rows or rows[identity]['delivery_status'] == 'hidden':
                requests.finish(ROOT, request['token'], 'cancelled')
        rows = dict(sorted(rows.items(), key=lambda item: item[0] not in explicit))""")
    source = once(source,
        "            if revision['sha256'] == state['revisions'].get(identity, {}).get('sha256'):",
        "            request = explicit.get(identity)\n"
        "            if (not request and revision['sha256'] == state['revisions'].get(identity, {}).get('sha256')):")
    source = once(source,
        "                LOG.info('CRM sync PASS: %s', revision['code'])",
        "                if request and revision['delivery_status'] != 'hidden':\n"
        "                    requests.finish(ROOT, request['token'], 'verified', revision['sha256'])\n"
        "                LOG.info('CRM sync PASS: %s', revision['code'])")
    return source


def patch_ui(source):
    template = (HERE / 'ui_handlers.py').read_text()
    functions = {node.name: ast.get_source_segment(template, node)
                 for node in ast.parse(template).body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for name in ('ad_screen', 'preview'):
        source = STAGE.replace_function(source, name, lambda _, n=name: functions[n])
    source = once(source,
        '    rows.append([InlineKeyboardButton("Как видит покупатель",\n'
        '                                      callback_data="car_preview:%d" % cid)])\n', '')
    # Keep the existing explicit hide action, with an unambiguous new callback.
    source = once(source,
        '        InlineKeyboardButton(\n'
        '            "Скрыть от клиентов" if card.get("published") else "Показать клиентам",\n'
        '            callback_data="car_pub:%d" % cid),\n', '')
    source = once(source, '    rows.append([InlineKeyboardButton("Удалить", callback_data="car_del:%d" % cid)])',
        '    if card.get("published"):\n'
        '        rows.append([InlineKeyboardButton("Скрыть от клиентов", callback_data="car_hide:%d" % cid)])\n'
        '    rows.append([InlineKeyboardButton("Удалить", callback_data="car_del:%d" % cid)])')
    source = once(source, '    actor_id = q.from_user.id\n    preimage = _ua083_publish_preimage(card)',
        '    if q.data.startswith("car_hide:") and not card.get("published"):\n'
        '        await q.message.reply_text("Объявление уже скрыто.", reply_markup=_ua099_back(cid))\n'
        '        raise ApplicationHandlerStop\n'
        '    actor_id = q.from_user.id\n    preimage = _ua083_publish_preimage(card)')
    source = once(source,
        '    app.add_handler(CallbackQueryHandler(toggle_publish, pattern=r"^car_pub:"), group=g)',
        '    app.add_handler(CallbackQueryHandler(_ua_oneclick_legacy_publish, pattern=r"^car_pub:"), group=g)\n'
        '    app.add_handler(CallbackQueryHandler(toggle_publish, pattern=r"^car_hide:"), group=g)')
    source += '\n\n' + '\n\n'.join(code for name, code in functions.items()
                                     if name not in ('ad_screen', 'preview'))
    source += '''

async def _ua_oneclick_legacy_publish(update, context):
    q, staff = await _ua099_require_staff(update)
    cid = int(q.data.split(':')[-1])
    await q.message.reply_text('Кнопка устарела. Откройте карточку и нажмите «Разместить объявление».',
                               reply_markup=_ua099_back(cid))
    raise ApplicationHandlerStop

_ua_oneclick_previous_register = register
def register(app):
    if app.job_queue is None:
        raise RuntimeError('Publication receipt JobQueue is required')
    _ua_oneclick_previous_register(app)
    if not app.job_queue.get_jobs_by_name('oneclick-publication-receipts'):
        app.job_queue.run_repeating(_ua_oneclick_receipts, interval=5, first=2,
            name='oneclick-publication-receipts', job_kwargs={'max_instances': 1, 'coalesce': True})
'''
    source = once(source, "progress = await q.message.reply_text('Запускаю публикацию…', reply_markup=_ua099_back(cid))",
        "progress = await q.message.reply_text('Размещаю объявление. При временном сбое повторю автоматически.', reply_markup=_ua099_back(cid))")
    return source


def build(sources, dependencies):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError('SOURCE_SET')
    if set(dependencies) != set(DEPENDENCY_SHA256):
        raise ValueError('DEPENDENCY_SET')
    for name, expected in SOURCE_SHA256.items():
        if hashlib.sha256(sources[name]).hexdigest() != expected:
            raise ValueError('SOURCE_CHANGED:' + name)
    candidate = PERF.build(sources, dependencies)
    candidate['cars_ui.py'] = patch_ui(candidate['cars_ui.py'].decode()).encode()
    candidate['ua_crm_public_sync.py'] = patch_worker(sources['ua_crm_public_sync.py'].decode()).encode()
    candidate['ua_publish_requests.py'] = (HERE / 'ua_publish_requests.py').read_bytes()
    for name, value in candidate.items():
        compile(value, name, 'exec')
    return candidate
