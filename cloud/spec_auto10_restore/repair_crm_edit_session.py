#!/usr/bin/env python3
"""Pure byte-pinned repair for cancelled specification edits in cars_ui.

No app import, IO, network or installer. Frozen final17 v2 is the sole input.
Navigating away or opening a new editor must retire the former text consumer.
"""
from __future__ import annotations

import hashlib

SOURCE_SHA256 = "32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec"
OUTPUT_SHA256 = "57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42"


def patch_source(data: bytes) -> bytes:
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise ValueError("CRM_EDIT_SESSION_SOURCE_MISMATCH")
    source = data.decode("utf-8")
    substitutions = (
        ('        context.user_data.pop("car_wait", None)\n'
         '        context.user_data.pop("car_media_wait", None)\n',
         '        context.user_data.pop("car_wait", None)\n'
         '        context.user_data.pop("car_media_wait", None)\n'
         '        context.user_data.pop("ua099_spec_edit", None)\n', 1),
        ('async def edit_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):\n'
         '    q = update.callback_query\n    await _v168_ack(q,)\n',
         'async def edit_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):\n'
         '    q = update.callback_query\n    await _v168_ack(q,)\n'
         '    drop_wait(context)\n', 1),
        ('async def additional_spec_screen(update, context):\n'
         '    q, staff = await _ua099_require_staff(update)\n',
         'async def additional_spec_screen(update, context):\n'
         '    q, staff = await _ua099_require_staff(update)\n'
         '    drop_wait(context)\n', 2),
        ('async def additional_spec_edit(update, context):\n'
         '    q, staff = await _ua099_require_staff(update)\n',
         'async def additional_spec_edit(update, context):\n'
         '    q, staff = await _ua099_require_staff(update)\n'
         '    drop_wait(context)\n', 1),
    )
    for before, after, count in substitutions:
        if source.count(before) != count:
            raise ValueError("CRM_EDIT_SESSION_PATCH_CONTEXT_CHANGED")
        source = source.replace(before, after)
    result = source.encode("utf-8")
    compile(result, "<cars_ui_edit_session_v1>", "exec")
    if hashlib.sha256(result).hexdigest() != OUTPUT_SHA256:
        raise ValueError("CRM_EDIT_SESSION_OUTPUT_MISMATCH")
    return result
