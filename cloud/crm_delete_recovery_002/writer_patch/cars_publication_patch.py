"""Compose publication race fix after the separately approved list/bot patches.

Only the exact reviewed publication block is transformed. Full-source baseline
binding belongs to the composition's first step; this step additionally binds
its unchanged region, so unrelated preceding approved edits are preserved.
"""
import hashlib

START = '# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:START'
END = '# UA-0012-UA-0013-PUBLISH-TRANSACTION-001-V1.0:UI:END'
BLOCK_SHA256 = '558db6d61e7976cb34f7a0054c27cb9dda76c300cce50449cbba556108f963ec'
MARKER = '# UA-ART-CRM-DELETE-RECOVERY-002:PUBLICATION-WORKER'

HELPERS = '''
from publication_fence import publication_fence as _delete_publication_fence
from ua_delete_public_guard import require_current as _delete_require_current
from ua_delete_public_guard import vin_key as _delete_vin_key


def _delete_publication_identity(card, current):
    if (not current or current.get('id') != card.get('id')
            or current.get('auto_number') != card.get('auto_number')
            or _delete_vin_key(current.get('vin')) != _delete_vin_key(card.get('vin'))):
        raise RuntimeError('PUBLICATION_CARD_IDENTITY_CHANGED')


def _delete_set_published(identity, expected, desired, actor_id, expected_row=None):
    # Caller owns publication fence. BEGIN IMMEDIATE protects check+update
    # against other CRM transactions which do not render public pages.
    _delete_require_current(identity.get('auto_number'), car_id=identity.get('id'),
                            vin=identity.get('vin'))
    cid = int(identity['id'])
    with db.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM cars WHERE id=?', (cid,)).fetchone()
        current = dict(row) if row is not None else None
        _delete_publication_identity(identity, current)
        if expected_row is not None and current != expected_row:
            raise RuntimeError('PUBLICATION_ROW_CHANGED')
        if current.get('published') != expected:
            raise RuntimeError('PUBLICATION_STATE_CHANGED')
        changed = conn.execute('UPDATE cars SET published=?,updated_at=? WHERE id=? AND published IS ?',
                               (desired, db.now(), cid, expected))
        if changed.rowcount != 1:
            raise RuntimeError('PUBLICATION_STATE_CHANGED')
        # Capture the exact raw postimage before the transaction releases its
        # write lease. Enriched card_of() aliases cannot identify this write.
        postimage = dict(conn.execute('SELECT * FROM cars WHERE id=?', (cid,)).fetchone())
    return postimage


def _ua083_restore_publish_preimage(cid, preimage, actor_id,
                                    expected_written=None, identity=None):
    # A saved callback without a current invocation's write preimage cannot
    # authorize broad restoration. In particular it cannot alter a tombstone
    # snapshot admitted after an earlier publication worker returned.
    try:
        with _delete_publication_fence(timeout=90.0):
            current = card_of(int(cid))
            if not current:
                return False
            identity = identity or current
            _delete_publication_identity(identity, current)
            _delete_require_current(identity.get('auto_number'), car_id=int(cid),
                                    vin=identity.get('vin'))
            if expected_written is None:
                return all(current.get(field) == preimage.get(field)
                           for field in ('published', 'status', 'publish_pending'))
            if not {'id', 'auto_number', 'vin', 'published'} <= set(expected_written):
                return False
            _delete_set_published(identity, expected_written['published'],
                                  preimage.get('published'), actor_id,
                                  expected_row=expected_written)
            db.log_action(actor_id, 'card_edit', 'cars', int(cid), 'published',
                          expected_written['published'], preimage.get('published'))
            return (card_of(int(cid)) or {}).get('published') == preimage.get('published')
    except Exception:
        log.exception('UA002: безопасное восстановление состояния публикации отклонено id=%s', cid)
        return False


def _delete_toggle_publication_worker(cid, captured_card, desired, actor_id, publisher):
    # This entire operation runs in one to_thread worker. No Telegram/network
    # acknowledgement await occurs while its thread owns the publication fence.
    with _delete_publication_fence(timeout=90.0):
        with db.connect() as conn:
            raw = conn.execute('SELECT * FROM cars WHERE id=?', (int(cid),)).fetchone()
            expected_before = dict(raw) if raw is not None else None
        _delete_publication_identity(captured_card, expected_before)
        current = card_of(int(cid))
        _delete_publication_identity(captured_card, current)
        _delete_require_current(current.get('auto_number'), car_id=int(cid),
                                vin=captured_card.get('vin'))
        if current.get('published') != captured_card.get('published'):
            raise RuntimeError('PUBLICATION_STATE_CHANGED_REOPEN_CARD')
        if desired and S.missing_required(current):
            raise RuntimeError('PUBLICATION_REQUIRED_FIELDS_CHANGED_REOPEN_CARD')
        preimage = _ua083_publish_preimage(current)
        expected_written = None
        write_committed = False
        try:
            expected_written = _delete_set_published(current, current.get('published'), desired, actor_id,
                                                    expected_row=expected_before)
            write_committed = True
            db.log_action(actor_id, 'card_edit', 'cars', int(cid), 'published',
                          current.get('published'), desired)
            if desired:
                ok, detail = publisher.opublikovat(current.get('auto_number'))
            else:
                ok, detail = publisher.obnovit_katalog()
            if ok is True:
                return True, detail, True
            restored = _ua083_restore_publish_preimage(cid, preimage, actor_id,
                                expected_written=expected_written, identity=current)
            return False, detail, restored
        except Exception as exc:
            # A failed compare-and-swap did not create a write to undo. Never
            # treat another operator's desired value as our own postimage.
            restored = True
            if write_committed:
                restored = _ua083_restore_publish_preimage(cid, preimage, actor_id,
                                    expected_written=expected_written, identity=current)
            log.exception('UA002: публикация не завершена id=%s', cid)
            return False, 'Публикация не завершена: %s' % exc, restored
'''


def _replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('EXACT_PUBLICATION_ANCHOR_REQUIRED')
    return source.replace(old, new, 1)


def apply_to_candidate(candidate):
    raw = candidate.encode('utf-8') if isinstance(candidate, str) else candidate
    source = raw.decode('utf-8')
    if source.count(START) != 1 or source.count(END) != 1 or MARKER in source:
        raise ValueError('UNIQUE_UNPATCHED_PUBLICATION_BLOCK_REQUIRED')
    left, right = source.index(START), source.index(END) + len(END)
    block = source[left:right]
    if hashlib.sha256(block.encode()).hexdigest() != BLOCK_SHA256:
        raise ValueError('REVIEWED_PUBLICATION_BLOCK_HASH_REQUIRED')
    block = _replace_once(block,
        '    try:\n        import asyncio as _ua083_asyncio\n',
        '    _delete_completed = False\n    _delete_restored = True\n'
        '    try:\n        import asyncio as _ua083_asyncio\n')
    block = _replace_once(block,
        '        db.update_card_field("cars", cid, "published", novoe, actor_id)\n'
        '        if novoe:\n'
        '            ok, detail = await _ua083_asyncio.to_thread(\n'
        '                _ua083_publisher.opublikovat, card.get("auto_number"))\n',
        '        ok, detail, _delete_restored = await _ua083_asyncio.to_thread(\n'
        '            _delete_toggle_publication_worker, cid, dict(card), novoe, actor_id, _ua083_publisher)\n'
        '        _delete_completed = ok is True\n'
        '        if novoe:\n')
    block = _replace_once(block,
        '            ok, detail = await _ua083_asyncio.to_thread(_ua083_publisher.obnovit_katalog)\n', '')
    block = _replace_once(block,
        '            restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)\n',
        '            restored = _delete_restored\n')
    block = _replace_once(block,
        '        restored = _ua083_restore_publish_preimage(cid, preimage, actor_id)\n',
        '        restored = _delete_restored\n')
    block = _replace_once(block,
        '        text = "Публикация отменена: %s. Выполнен откат." % exc\n',
        '        text = ("Публикация выполнена, но подтверждение не доставлено."\n'
        '                if _delete_completed else "Операция публикации не завершена: %s." % exc)\n')
    # Rebind the compatibility restore helper before callbacks can execute.
    result = source[:left] + block + '\n\n' + MARKER + '\n' + HELPERS + '\n' + source[right:]
    compile(result, 'cars_ui.py.publication-candidate', 'exec')
    return result.encode('utf-8')
