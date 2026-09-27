"""CRM publication reconciliation using the existing transactional publisher.
No CRM writes. Persistent revision ledger, per-card retry, one publisher worker.
"""
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time

ROOT = Path('/home/Carix')
STATE = ROOT / '.crm_public_sync_state.json'
LOCK = ROOT / '.crm_public_sync_worker.lock'
LOG = logging.getLogger(__name__)
_wake = threading.Event()
_thread = None
_start_lock = threading.Lock()


def snapshot():
    from ua_delivery_status import public_status
    conn = sqlite3.connect((ROOT / 'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute('SELECT * FROM cars WHERE published=1')]
    finally:
        conn.close()
    result = {}
    codes = set()
    for row in rows:
        code = str(row.get('auto_number') or '')
        if not code or code in codes:
            raise RuntimeError('Missing or duplicate published auto_number')
        codes.add(code)
        raw = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str).encode()
        result[str(row['id'])] = {'code': code, 'sha256': hashlib.sha256(raw).hexdigest(), 'delivery_status': public_status(row.get('status'))}
    return result


def save_state(state):
    fd, name = tempfile.mkstemp(prefix='.crm_public_sync_state.', dir=str(ROOT))
    try:
        with os.fdopen(fd, 'w') as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump(state, out, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, STATE)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def initialize():
    if STATE.exists():
        raise RuntimeError('State already exists; refusing to reset pending revisions')
    # Existing rows are an installation baseline, not a claim of verification.
    # UA-0022 was explicitly published before installation; other cards untouched.
    save_state({'version': 1, 'baseline_at': time.time(), 'revisions': snapshot(),
                'retry': {}, 'last_success': None})


def notify():
    """Called after DB commit; cannot block the Telegram handler."""
    _wake.set()


def reconcile_once(publish=None, clock=time.time):
    with open(LOCK, 'a') as lock:
        os.chmod(LOCK, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'busy'
        with STATE.open() as source:
            state = json.load(source)
        if state.get('version') != 1:
            raise RuntimeError('Unsupported sync state')
        rows = snapshot()
        retry = state.setdefault('retry', {})
        for identity, revision in rows.items():
            if revision['sha256'] == state['revisions'].get(identity, {}).get('sha256'):
                continue
            attempt = retry.get(identity, {})
            if attempt.get('sha256') == revision['sha256'] and attempt.get('after', 0) > clock():
                continue
            try:
                if revision['delivery_status'] == 'hidden':
                    from ua_stage_catalog_sync import reconcile
                    reconcile(apply=True)
                else:
                    if publish is None:
                        from publikaciya import opublikovat
                        publish = opublikovat
                    ok, message = publish(revision['code'])
                    if not ok:
                        raise RuntimeError(str(message)[:500])
                    from ua_public_freshness import verify_public
                    verify_public(revision['code'])
                if snapshot().get(identity) != revision:
                    # Keep old ledger revision: a newer operator edit needs another pass.
                    LOG.warning('CRM sync: changed during publish: %s', revision['code'])
                    return 'changed_during_publish'
                state['revisions'][identity] = revision
                retry.pop(identity, None)
                state['last_success'] = {'code': revision['code'], 'at': clock()}
                save_state(state)
                LOG.info('CRM sync PASS: %s', revision['code'])
                return 'hidden' if revision['delivery_status'] == 'hidden' else 'published'
            except Exception as exc:
                count = (attempt.get('count', 0) if attempt.get('sha256') == revision['sha256'] else 0) + 1
                retry[identity] = {'sha256': revision['sha256'], 'count': count,
                                   'after': clock() + min(300, 15 * 2 ** min(count-1, 5)),
                                   'error': type(exc).__name__ + ': ' + str(exc)[:500]}
                save_state(state)
                LOG.exception('CRM sync failed; retry pending: %s', revision['code'])
                # Continue so a failing card does not starve other pending cards.
        return 'idle'


def _run():
    LOG.info('CRM public sync worker started')
    while True:
        _wake.wait(15)
        _wake.clear()
        # Debounce burst saves (media albums and multi-field edits).
        time.sleep(2)
        try:
            if reconcile_once() in ('published', 'changed_during_publish'):
                _wake.set()
        except Exception:
            LOG.exception('CRM sync worker error; retry in 15 seconds')


def start():
    global _thread
    with _start_lock:
        if _thread is not None and _thread.is_alive():
            return
        if not STATE.exists():
            raise RuntimeError('Installation baseline missing; not silently resetting sync state')
        _thread = threading.Thread(target=_run, name='crm-public-sync', daemon=True)
        _thread.start()
        _wake.set()
