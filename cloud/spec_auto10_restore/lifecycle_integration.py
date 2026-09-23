"""Pure source patches for the hash-verified current CRM handlers and lock.

No application imports, deployment, network, SQLite or other side effects.
Apply after the additional-spec integration transforms; the target handler and
lock bodies are independently pinned to their observed exact source hashes.
"""
from __future__ import annotations

import ast
import hashlib
import textwrap

MARKER = "UA_AUTO10_LIFECYCLE_V1"
EXPECTED = {
    "delete_ok": "02dfa6f74159ad11b1952455913d382970f89ee651645d85cd5f4d7341ec99c7",
    "toggle_publish": "bb34789af93cd3d17bfd5de6a31b1e9b2b8f9c3d7ad81001ac6a1fe3ae306cd9",
    "mark_sold_ok": "e5e12201544ebc12e8f867c5e36add00a203da45da564e32dc40d97ccccb685d",
    "delete_ask": "257134e00ad805ed353078d1917ac89c856b9faf1c889aba43206e6e60f6cf94",
    "_exclusive_lock": "00bcb356dbd07f53a0b493487d86a3f269a8f70521ad37220a45a19aea666ee2",
}


class IntegrationError(RuntimeError):
    pass


def _replace(source, name, replacement):
    tree = ast.parse(source)
    functions = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name]
    if not functions:
        raise IntegrationError("LIFECYCLE_FUNCTION_MISSING:" + name)
    # Two legacy toggle handlers exist; only the last globally bound handler runs.
    if name != "toggle_publish" and len(functions) != 1:
        raise IntegrationError("LIFECYCLE_FUNCTION_DUPLICATED:" + name)
    node = functions[-1]
    body = ast.get_source_segment(source, node)
    if hashlib.sha256(body.encode()).hexdigest() != EXPECTED[name]:
        raise IntegrationError("LIFECYCLE_UNREVIEWED_FUNCTION:" + name)
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[:node.lineno - 1])
    end = sum(len(line) for line in lines[:node.end_lineno - 1]) + node.end_col_offset
    return source[:start] + textwrap.dedent(replacement).strip() + source[end:]


DELETE_OK = '''
async def delete_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    import asyncio as _ua_lifecycle_async
    import card_lifecycle as _ua_lifecycle
    try:
        ok, detail = await _ua_lifecycle_async.to_thread(
            _ua_lifecycle.delete_card, cid, q.from_user.id)
    except Exception as exc:
        log.exception("Lifecycle delete failed for car %s", cid)
        await q.message.reply_text(str(exc))
        raise ApplicationHandlerStop
    if ok:
        context.user_data.pop("car_last", None)
    await q.message.reply_text(detail, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("← Все автомобили", callback_data="cards_cars")]
    ]))
    raise ApplicationHandlerStop
'''

TOGGLE = '''
async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    if not card:
        await q.message.reply_text("Карточка не найдена.")
        raise ApplicationHandlerStop
    visible = not bool(card.get("published"))
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← Вернуться к карточке", callback_data="car_open:%d" % cid)]])
    if visible:
        miss = S.missing_required(card)
        if miss:
            await q.message.reply_text(
                "Для показа клиентам не хватает: %s" % ", ".join(miss),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Дозаполнить", callback_data="car_edit:%d" % cid)],
                    [InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)]
                ]))
            raise ApplicationHandlerStop
    import asyncio as _ua_lifecycle_async
    import card_lifecycle as _ua_lifecycle
    try:
        ok, detail = await _ua_lifecycle_async.to_thread(
            _ua_lifecycle.set_visibility, cid, visible, q.from_user.id)
    except Exception as exc:
        log.exception("Lifecycle visibility failed for car %s", cid)
        detail = str(exc)
    await q.message.reply_text(detail, reply_markup=back)
    raise ApplicationHandlerStop
'''

SOLD = '''
async def mark_sold_ok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    import asyncio as _ua_lifecycle_async
    import card_lifecycle as _ua_lifecycle
    try:
        ok, detail = await _ua_lifecycle_async.to_thread(
            _ua_lifecycle.mark_sold, cid, q.from_user.id)
    except Exception as exc:
        log.exception("Lifecycle sold transition failed for car %s", cid)
        detail = str(exc)
    await q.message.reply_text(detail, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("← Вернуться к карточке", callback_data="car_open:%d" % cid)]
    ]))
    raise ApplicationHandlerStop
'''

LOCK = '''
def _exclusive_lock():
    # UA_AUTO10_LIFECYCLE_V1: nested publication in the same thread shares one
    # OS file lock; other threads/processes still wait with the original timeout.
    deadline = time.monotonic() + WAIT_SECONDS
    if not _ua_lifecycle_mutex.acquire(timeout=max(0, WAIT_SECONDS)):
        raise PublishError("PUBLISH_LOCK_TIMEOUT")
    handle = None
    acquired = False
    nested = getattr(_ua_lifecycle_thread, "depth", 0) > 0
    try:
        if nested:
            _ua_lifecycle_thread.depth += 1
            try:
                yield
            finally:
                _ua_lifecycle_thread.depth -= 1
            return
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        handle = open(LOCK, "a+")
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PublishError("PUBLISH_LOCK_TIMEOUT")
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))
        _ua_lifecycle_thread.depth = 1
        try:
            # Recovery precedes every outer publisher/readback/rollback entry.
            # Its nested acquisition shares this lock and does not recurse.
            import card_lifecycle as _ua_lifecycle_recovery
            import sys as _ua_lifecycle_sys
            _ua_lifecycle_recovery.recover_pending(
                guard=_ua_lifecycle_sys.modules[__name__])
            yield
        finally:
            _ua_lifecycle_thread.depth = 0
    finally:
        try:
            if handle is not None:
                try:
                    if acquired:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()
        finally:
            _ua_lifecycle_mutex.release()
'''


def patch_cars_ui(source):
    if MARKER in source:
        raise IntegrationError("LIFECYCLE_ALREADY_PATCHED")
    for name, replacement in (("delete_ok", DELETE_OK), ("toggle_publish", TOGGLE),
                              ("mark_sold_ok", SOLD)):
        source = _replace(source, name, replacement)
    # Retain the actual confirmation callback; only correct the preservation text.
    tree = ast.parse(source)
    node = next(node for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "delete_ask")
    old = ast.get_source_segment(source, node)
    new = old.replace(
        '"Удалить карточку %s?\\nВернуть её будет нельзя. Фото, видео и история "\n        "пропадут вместе с ней."',
        '"Удалить карточку %s из CRM и с сайта?\\nФото, видео и спецификация "\n        "останутся в резерве. Прямые ссылки на карточку будут отключены."'
    )
    if old == new:
        raise IntegrationError("LIFECYCLE_DELETE_CONFIRMATION_NOT_FOUND")
    source = _replace(source, "delete_ask", new)
    source += "\n# " + MARKER + ": CRM callbacks use card_lifecycle.\n"
    compile(source, "candidate/cars_ui.py", "exec")
    return source


def patch_publish_transaction_guard(source):
    if MARKER in source:
        raise IntegrationError("LIFECYCLE_ALREADY_PATCHED")
    source = _replace(source, "_exclusive_lock", LOCK)
    # The original @contextlib.contextmanager decorator is preserved by _replace.
    source += '''\n# UA_AUTO10_LIFECYCLE_V1: initialized before module import returns.
import threading as _ua_lifecycle_threading
_ua_lifecycle_mutex = _ua_lifecycle_threading.RLock()
_ua_lifecycle_thread = _ua_lifecycle_threading.local()
LIFECYCLE_REENTRANT_LOCK = True
'''
    compile(source, "candidate/publish_transaction_guard.py", "exec")
    return source
