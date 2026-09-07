#!/usr/bin/env python3
"""Fresh-source patcher for the TASK116 non-Production candidate.

It is intentionally usable only on an explicit preview tree.  Each patch is
fail-closed and idempotent; stale complete module copies are never installed.
"""
from __future__ import annotations

import argparse
import ast
import errno
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Callable

from recovery_core import RecoveryGuardError, resolved_under, stable_digest


MARKER = "UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001-V1.0"
HIDDEN_LITERAL = "{'kr_bought', 'sea_loaded', 'sea_transit', 'ua_handed'}"
SEAL_PREFIX = "# UA116-PATCH-SHA256:"


def _seal_payload(name: str, source_without_seal: str) -> str:
    return stable_digest({"module": name, "source": source_without_seal})


def _seal_candidate(name: str, source: str) -> str:
    """Attach a deterministic integrity seal to a freshly patched module."""

    if SEAL_PREFIX in source:
        raise RecoveryGuardError("PATCH_SEAL_DUPLICATE", name)
    body = source.rstrip() + "\n"
    return body + SEAL_PREFIX + _seal_payload(name, body) + "\n"


def _verify_patch_seal(name: str, source: str) -> None:
    lines = source.splitlines(keepends=True)
    indices = [index for index, line in enumerate(lines) if line.startswith(SEAL_PREFIX)]
    if len(indices) != 1 or indices[0] != len(lines) - 1:
        raise RecoveryGuardError("PATCH_SEAL_MISSING_OR_MISPLACED", name)
    supplied = lines[-1][len(SEAL_PREFIX) :].strip()
    body = "".join(lines[:-1])
    expected = _seal_payload(name, body)
    if supplied != expected:
        raise RecoveryGuardError("PATCH_SEAL_MISMATCH", name)


def _require_fragments(name: str, source: str, fragments: tuple[str, ...]) -> None:
    missing = [fragment for fragment in fragments if fragment not in source]
    if missing:
        raise RecoveryGuardError(
            "PATCH_MARKER_INCOMPLETE", name + ":" + ",".join(missing[:3])
        )


def _verify_module_invariants(name: str, source: str) -> None:
    """Reject a marker-bearing module whose safety patch was removed/changed."""

    compile(source, name, "exec")
    required: dict[str, tuple[str, ...]] = {
        "cars_ui.py": (
            f"# {MARKER}: preview is strictly read-only",
            f"# {MARKER}: cars_ui",
            "prepare_for_publish_async(card)",
            "Production gate закрыт",
            "доверенным TASK116 release-controller",
            "await _ua116_asyncio.wait_for(",
            "if code in _UA116_HIDDEN_STATUS_CODES:",
            "group=-10",
        ),
        "konteyner.py": (
            f"# {MARKER}: konteyner",
            "code not in _UA116_HIDDEN_STATUS_CODES",
            "_UA116_HIDDEN_STATUS_CODES = frozenset",
        ),
        "source_policy.py": (
            f"# {MARKER}: source_policy",
            "minimum_facts = PUBLIC_MIN_VISIBLE_SPEC_ROWS",
            "from recovery_core import PUBLIC_MIN_VISIBLE_SPEC_ROWS",
        ),
        "vin_spec_service.py": (
            f"# {MARKER}: vin_spec_service",
            f"# {MARKER}: runtime heartbeat is evidence, not an AST guess",
            f"# {MARKER}: immutable runtime store",
            "visible >= PUBLIC_MIN_VISIBLE_SPEC_ROWS",
            "DEFERRED_TO_EXPLICIT_PUBLISH",
            "process_pending_primary_jobs(limit=1)",
            "def bootstrap_immutable_revisions():",
            "enqueue_card(card, force=True)",
            '"RECOVERY_PENDING"',
            "_store_facts = _ua116_store_facts",
        ),
        "ua_additional_spec.py": (
            f"# {MARKER}: ua_additional_spec",
            "def _ua116_exact_active(value):",
            "active.vin_sha256 != _ua116_vin_sha256(current_vin)",
            "display-only fallback prevents the old specification disappearing",
            "return _UA116_BASE_FETCH_SPECS",
            "return _ua116_vin_service.SPEC_DB",
            "data-ua-spec-card",
            "data-ua-spec-revision",
            "card_identity_errors as _ua116_card_identity_errors",
            "expected_spec=active",
        ),
    }
    _require_fragments(name, source, required[name])

    tree = ast.parse(source)
    if name == "cars_ui.py":
        previews = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "preview"
        ]
        if len(previews) != 1:
            raise RecoveryGuardError("PATCH_MARKER_INCOMPLETE", name + ":preview")
        preview_calls = [
            node
            for node in ast.walk(previews[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "opublikovat"
        ]
        if preview_calls:
            raise RecoveryGuardError("PATCH_PREVIEW_SIDE_EFFECT_PRESENT", name)
        toggles = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "toggle_publish"
        ]
        if len(toggles) != 1:
            raise RecoveryGuardError("PATCH_MARKER_INCOMPLETE", name + ":toggle_publish")
        toggle_calls = [
            node
            for node in ast.walk(toggles[0])
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "opublikovat"
        ]
        if toggle_calls:
            raise RecoveryGuardError("PATCH_LEGACY_PUBLISH_BYPASS_PRESENT", name)


def _already_patched(name: str, source: str, module_marker: str) -> bool:
    if module_marker not in source:
        if MARKER in source or SEAL_PREFIX in source:
            raise RecoveryGuardError("PATCH_MARKER_INCOMPLETE", name)
        return False
    _verify_patch_seal(name, source)
    _verify_module_invariants(name, source)
    return True


def _safe_read_text(
    path: Path, *, expected_identity: tuple[int, int] | None = None
) -> tuple[str, os.stat_result]:
    """Read one regular, unlinked source without following a raced symlink."""

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise RecoveryGuardError("PATCH_SOURCE_MISSING", path.name) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path)) from exc
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RecoveryGuardError("PATCH_SOURCE_NOT_REGULAR", path.name)
        if info.st_nlink != 1:
            raise RecoveryGuardError("PATCH_SOURCE_HARDLINK_FORBIDDEN", path.name)
        identity = (info.st_dev, info.st_ino)
        if expected_identity is not None and identity != expected_identity:
            raise RecoveryGuardError("PATCH_SOURCE_CHANGED_DURING_APPLY", path.name)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            descriptor = -1
            return stream.read(), info
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _replace_once(source: str, old: str, new: str, code: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RecoveryGuardError(code, f"expected=1 actual={count}")
    return source.replace(old, new, 1)


def _insert_before_once(source: str, needle: str, addition: str, code: str) -> str:
    return _replace_once(source, needle, addition + needle, code)


def _remove_hidden_button_appends(source: str, function_name: str) -> tuple[str, int]:
    """Remove explicit legacy-button ``rows.append`` statements by AST span."""

    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if not functions:
        return source, 0
    if len(functions) != 1:
        raise RecoveryGuardError("HIDDEN_BUTTON_FUNCTION_AMBIGUOUS", function_name)
    matches: list[ast.Expr] = []
    for node in ast.walk(functions[0]):
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "append":
            continue
        constants = " ".join(
            str(item.value)
            for item in ast.walk(node)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        )
        if "car_setstage:" in constants and any(
            code in constants for code in ("kr_bought", "sea_loaded", "sea_transit", "ua_handed")
        ):
            matches.append(node)
    if not matches:
        return source, 0
    lines = source.splitlines(keepends=True)
    for node in sorted(matches, key=lambda item: item.lineno, reverse=True):
        indent = " " * node.col_offset
        lines[node.lineno - 1 : node.end_lineno] = [
            indent + "# " + MARKER + ": legacy status button removed\n"
        ]
    return "".join(lines), len(matches)


def _remove_preview_publish_try(source: str) -> str:
    tree = ast.parse(source)
    previews = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "preview"
    ]
    if not previews:
        raise RecoveryGuardError("CARS_UI_PREVIEW_NOT_FOUND")
    preview = max(previews, key=lambda node: node.lineno)
    matches: list[ast.Try] = []
    for node in preview.body:
        if not isinstance(node, ast.Try):
            continue
        calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
        if any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "opublikovat"
            for call in calls
        ):
            matches.append(node)
    if not matches:
        # Already patched source has the marker and is accepted by caller.
        raise RecoveryGuardError("CARS_UI_PREVIEW_PUBLISH_CALL_NOT_FOUND")
    if len(matches) != 1:
        raise RecoveryGuardError("CARS_UI_PREVIEW_PUBLISH_CALL_AMBIGUOUS")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    indent = " " * node.col_offset
    replacement = (
        indent
        + "# "
        + MARKER
        + ": preview is strictly read-only\n"
        + indent
        + "await q.message.reply_text(\"Предпросмотр готов. Сайт не изменён.\")\n"
    )
    lines[node.lineno - 1 : node.end_lineno] = [replacement]
    return "".join(lines)


def _replace_toggle_publish_try(source: str) -> str:
    """Disconnect the unsafe legacy publisher pending the trusted controller."""

    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "toggle_publish"
    ]
    if len(functions) != 1:
        raise RecoveryGuardError("CARS_UI_TOGGLE_PUBLISH_SHAPE", str(len(functions)))
    function = functions[0]
    matches: list[ast.If] = []
    for node in function.body:
        if not isinstance(node, ast.If):
            continue
        calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
        if any(
            isinstance(call.func, ast.Attribute) and call.func.attr == "opublikovat"
            for call in calls
        ):
            matches.append(node)
    if len(matches) != 1:
        raise RecoveryGuardError("CARS_UI_PUBLISH_CALL_SHAPE", str(len(matches)))
    node = matches[0]
    lines = source.splitlines(keepends=True)
    indent = " " * node.col_offset
    body = " " * (node.col_offset + 4)
    replacement = (
        indent + "if novoe:\n"
        + body + "await q.message.reply_text(\n"
        + body + "    'Публикация через старый CRM-вызов отключена. Карточка осталась скрыта; '\n"
        + body + "    'нужен доверенный TASK116 release-controller после Gate B.')\n"
        + body + "raise ApplicationHandlerStop\n"
    )
    lines[node.lineno - 1 : node.end_lineno] = [replacement]
    return "".join(lines)


def patch_cars_ui(source: str) -> str:
    if _already_patched("cars_ui.py", source, f"# {MARKER}: cars_ui"):
        return source

    source = _remove_preview_publish_try(source)
    source = _replace_toggle_publish_try(source)
    # Two observed renderers use different line wrapping; both reduce to one of
    # these exact fragments.  Only the active cars_ui fragment may match.
    variants = (
        (
            "for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]",
            "for code, (stage_no, label) in S.STATUSES.items() "
            "if stage_no == number and code not in _UA116_HIDDEN_STATUS_CODES]",
        ),
        (
            "for code, (stage_no, label) in S.STATUSES.items()\n"
            "                if stage_no == number]",
            "for code, (stage_no, label) in S.STATUSES.items()\n"
            "                if stage_no == number and code not in _UA116_HIDDEN_STATUS_CODES]",
        ),
    )
    matched = [(old, new) for old, new in variants if old in source]
    if len(matched) != 1:
        raise RecoveryGuardError("CARS_UI_STATUS_LOOP_SHAPE", str(len(matched)))
    source = _replace_once(source, *matched[0], "CARS_UI_STATUS_LOOP_COUNT")

    stage_anchor = '    _, cid, code = q.data.split(":")\n    cid = int(cid)\n'
    guard = (
        stage_anchor
        + "    if code in _UA116_HIDDEN_STATUS_CODES:\n"
        + "        await q.message.reply_text(\n"
        + "            \"Эта старая кнопка больше не используется. Выберите текущий этап.\",\n"
        + "            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(\n"
        + "                \"← К карточке\", callback_data=\"car_open:%d\" % cid)]]))\n"
        + "        raise ApplicationHandlerStop\n"
        + "    if code not in S.STATUSES:\n"
        + "        await q.message.reply_text(\"Неизвестный этап. Данные не изменены.\")\n"
        + "        raise ApplicationHandlerStop\n"
    )
    source = _replace_once(
        source, stage_anchor, guard, "CARS_UI_STAGE_SET_ANCHOR"
    )

    vin_anchor = (
        '        set_field(card_id, field, vin, actor_id)\n'
        '        return True, "Записано: %s" % vin\n'
    )
    vin_hook = (
        '        set_field(card_id, field, vin, actor_id)\n'
        "        try:\n"
        "            import asyncio as _ua116_asyncio\n"
        "            import ua116_runtime_bridge as _ua116_runtime\n"
        "            _ua116_state = await _ua116_asyncio.wait_for(\n"
        "                _ua116_asyncio.to_thread(\n"
        "                    _ua116_runtime.handle_saved_vin, card_id=card_id,\n"
        "                    vin=vin, actor_id=actor_id), timeout=35.0)\n"
        "            return True, \"Записано: %s\\nСпецификация: %s\" % (\n"
        "                vin, _ua116_state.get('owner_text', 'подготовка запущена'))\n"
        "        except Exception as _ua116_exc:\n"
        "            log.exception(\"TASK116 VIN preparation failed card=%s\", card_id)\n"
        "            return True, \"VIN записан. Подготовка спецификации требует повтора: %s\" % type(_ua116_exc).__name__\n"
    )
    source = _replace_once(source, vin_anchor, vin_hook, "CARS_UI_VIN_HOOK_ANCHOR")

    publish_anchor = '    db.update_card_field("cars", cid, "published", novoe, q.from_user.id)\n'
    publish_guard = (
        "    if novoe:\n"
        "        import ua116_runtime_bridge as _ua116_runtime\n"
        "        _ua116_ready = await _ua116_runtime.prepare_for_publish_async(card)\n"
        "        if not _ua116_ready.get('ok'):\n"
        "            await q.message.reply_text(_ua116_ready.get('owner_text') or \"Публикация ожидает спецификацию.\")\n"
        "            raise ApplicationHandlerStop\n\n"
        "        await q.message.reply_text(\n"
        "            \"Карточка подготовлена, но Production gate закрыт. \"\n"
        "            \"Публикация выполняется только доверенным TASK116 release-controller.\")\n"
        "        raise ApplicationHandlerStop\n\n"
        + publish_anchor
    )
    source = _replace_once(
        source, publish_anchor, publish_guard, "CARS_UI_PUBLISH_GUARD_ANCHOR"
    )

    support = f'''\n\n# {MARKER}: cars_ui
_UA116_HIDDEN_STATUS_CODES = frozenset({HIDDEN_LITERAL})
_UA116_BASE_REGISTER = register

async def _ua116_block_legacy_stage(update, context):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    await q.message.reply_text(
        "Эта старая кнопка больше не используется. Данные не изменены.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(
            "← К карточке", callback_data="car_open:%s" % q.data.split(":")[1])]]))
    raise ApplicationHandlerStop

def register(app):
    _UA116_BASE_REGISTER(app)
    app.add_handler(CallbackQueryHandler(
        _ua116_block_legacy_stage,
        pattern=r"^car_setstage:\\d+:(?:kr_bought|sea_loaded|sea_transit|ua_handed)$"),
        group=-10)
'''
    return source.rstrip() + support


def patch_konteyner(source: str) -> str:
    if _already_patched("konteyner.py", source, f"# {MARKER}: konteyner"):
        return source
    variants = (
        (
            "if stage_no == nomer_etapa]",
            "if stage_no == nomer_etapa and code not in _UA116_HIDDEN_STATUS_CODES]",
        ),
        (
            "if stage_no == number]",
            "if stage_no == number and code not in _UA116_HIDDEN_STATUS_CODES]",
        ),
    )
    matched = [(old, new) for old, new in variants if old in source]
    if len(matched) != 1:
        raise RecoveryGuardError("KONTEYNER_STATUS_LOOP_SHAPE", str(len(matched)))
    source = _replace_once(source, *matched[0], "KONTEYNER_STATUS_LOOP_COUNT")
    source, _removed = _remove_hidden_button_appends(source, "_ekran")
    return (
        source.rstrip()
        + f"\n\n# {MARKER}: konteyner\n"
        + f"# explicit legacy buttons removed: {_removed}\n"
        + f"_UA116_HIDDEN_STATUS_CODES = frozenset({HIDDEN_LITERAL})\n"
    )


def patch_source_policy(source: str) -> str:
    if _already_patched("source_policy.py", source, f"# {MARKER}: source_policy"):
        return source
    source = _replace_once(
        source,
        '    minimum_facts = 10 if profile else 4\n',
        '    minimum_facts = PUBLIC_MIN_VISIBLE_SPEC_ROWS\n',
        "SOURCE_POLICY_MINIMUM_ANCHOR",
    )
    anchor = 'POLICY_VERSION = "UA111-10SRC-V3"\n'
    source = _replace_once(
        source,
        anchor,
        anchor
        + "from recovery_core import PUBLIC_MIN_VISIBLE_SPEC_ROWS\n"
        + f"# {MARKER}: source_policy\n",
        "SOURCE_POLICY_VERSION_ANCHOR",
    )
    return source


def patch_vin_service(source: str) -> str:
    if _already_patched(
        "vin_spec_service.py", source, f"# {MARKER}: vin_spec_service"
    ):
        return source
    source = _replace_once(
        source,
        '        written = _store_facts(uid, facts)\n'
        '        status = "READY" if result.get("status") == "READY" and written >= 1 else "NEEDS_REVIEW"\n',
        '        written = _store_facts(uid, vin, facts, result.get("status") == "READY")\n'
        '        visible = _ua116_visible_count(uid, vin)\n'
        '        status = "READY" if visible >= PUBLIC_MIN_VISIBLE_SPEC_ROWS else "NEEDS_REVIEW"\n',
        "VIN_SERVICE_READY_THRESHOLD_ANCHOR",
    )
    source = _replace_once(
        source,
        '        sync_status, sync_detail = _refresh_published(card) if written >= 1 else ("NOT_REQUIRED", "нет подтверждённых фактов")\n',
        '        sync_status, sync_detail = ("DEFERRED_TO_EXPLICIT_PUBLISH", "сайт не менялся") if written >= 1 else ("NOT_REQUIRED", "нет подтверждённых фактов")\n',
        "VIN_SERVICE_IMPLICIT_PUBLISH_ANCHOR",
    )
    # The targeted coordinator must be able to atomically claim a brand-new
    # PENDING job instead of waiting behind the global backlog.
    source = source.replace(
        "AND status IN ('NEEDS_REVIEW','FAILED','READY')",
        "AND status IN ('PENDING','NEEDS_REVIEW','FAILED','READY')",
    )
    if source.count("status IN ('PENDING','NEEDS_REVIEW','FAILED','READY')") != 2:
        raise RecoveryGuardError("VIN_SERVICE_TARGET_CLAIM_SHAPE")
    helper_anchor = "def _process_claimed(\n"
    helper = f'''from recovery_core import PUBLIC_MIN_VISIBLE_SPEC_ROWS

def _ua116_visible_count(uid, vin):
    from spec_revision_store import get_active as _ua116_get_active
    from recovery_core import vin_sha256 as _ua116_vin_sha256
    _ua116_active = _ua116_get_active(SPEC_DB, uid)
    if not _ua116_active or _ua116_active.vin_sha256 != _ua116_vin_sha256(vin):
        return 0
    return _ua116_active.visible_count

# {MARKER}: vin_spec_service
'''
    source = _insert_before_once(
        source, helper_anchor, helper, "VIN_SERVICE_PROCESS_ANCHOR"
    )
    heartbeat_helper = f'''
def _ua116_record_heartbeat(error="", success=False):
    _ua116_now = utc_now()
    try:
        with connect_spec(False) as _ua116_con:
            _ua116_depth = int(_ua116_con.execute(
                "SELECT COUNT(*) FROM vin_spec_jobs WHERE status IN ('PENDING','RUNNING','PROCESSING')"
            ).fetchone()[0] or 0)
            _ua116_values = {{
                "worker_instance_id": WORKER_NAME + ":" + str(__import__('os').getpid()),
                "last_cycle_at": _ua116_now,
                "last_cycle_error": str(error or "")[:500],
                "queue_depth": str(_ua116_depth),
            }}
            if success:
                _ua116_values["last_success_at"] = _ua116_now
            for _ua116_key, _ua116_value in _ua116_values.items():
                _ua116_con.execute(
                    "INSERT OR REPLACE INTO vin_spec_state(key,value,updated_at) VALUES(?,?,?)",
                    (_ua116_key, _ua116_value, _ua116_now))
            _ua116_con.commit()
    except Exception:
        pass

# {MARKER}: runtime heartbeat is evidence, not an AST guess
'''
    source = _insert_before_once(
        source, "def _worker_loop() -> None:\n", heartbeat_helper,
        "VIN_SERVICE_WORKER_LOOP_ANCHOR",
    )
    loop_anchor = "    while not _stop_event.is_set():\n        try:\n"
    source = _replace_once(
        source,
        loop_anchor,
        "    while not _stop_event.is_set():\n"
        "        _ua116_record_heartbeat()\n"
        "        try:\n",
        "VIN_SERVICE_WORKER_CYCLE_ANCHOR",
    )
    source = _replace_once(
        source,
        "            scan_new_vins()\n            process_one()\n",
        "            scan_new_vins()\n"
        "            import ua116_runtime_bridge as _ua116_runtime\n"
        "            _ua116_runtime.process_pending_primary_jobs(limit=1)\n"
        "            process_one()\n",
        "VIN_SERVICE_PRIMARY_QUEUE_WORKER_ANCHOR",
    )
    old_except = (
        "        except Exception:\n"
        "            # Deliberately fail the current cycle only; each job keeps its own\n"
        "            # retry/error state and the CRM bot must remain available.\n"
        "            pass\n"
        "        _stop_event.wait(SCAN_SECONDS)\n"
    )
    new_except = (
        "            _ua116_record_heartbeat(success=True)\n"
        "        except Exception as _ua116_exc:\n"
        "            _ua116_record_heartbeat(\n"
        "                error=type(_ua116_exc).__name__ + ':' + str(_ua116_exc))\n"
        "        _stop_event.wait(SCAN_SECONDS)\n"
    )
    source = _replace_once(
        source, old_except, new_except, "VIN_SERVICE_WORKER_ERROR_ANCHOR"
    )
    runtime_anchor = 'if __name__ == "__main__":\n'
    runtime_support = f'''\n# {MARKER}: immutable runtime store
_UA116_BASE_ENQUEUE_CARD = enqueue_card
_UA116_BASE_START_WORKER = start_worker

def _ua116_revision_id(uid, vin, rows):
    from recovery_core import stable_digest as _ua116_digest, vin_sha256 as _ua116_vin_hash
    return "task116-" + _ua116_digest({{
        "uid": uid,
        "vin_sha256": _ua116_vin_hash(vin),
        "policy_version": source_policy.POLICY_VERSION,
        "facts": [item.public_dict() for item in rows],
    }})[:32]

def _ua116_fact_rows(raw_rows):
    from recovery_core import SpecFact as _UA116Fact
    result = []
    for raw in raw_rows:
        item = dict(raw)
        item.setdefault("display_value", item.get("field_value"))
        item.setdefault("visible", bool(item.get("is_visible", 1)))
        item.setdefault("manual", bool(item.get("is_manual", 0)))
        result.append(_UA116Fact.from_mapping(item))
    return result

def _ua116_store_facts(uid, vin, facts, source_ready):
    from recovery_core import RecoveryGuardError as _UA116Error
    from recovery_core import vin_sha256 as _ua116_vin_hash
    from spec_revision_store import get_active as _ua116_get, stage_and_activate as _ua116_activate, record_rejected_candidate as _ua116_reject
    rows = _ua116_fact_rows(facts)
    revision_id = _ua116_revision_id(uid, vin, rows)
    active = _ua116_get(SPEC_DB, uid)
    if active and active.vin_sha256 == _ua116_vin_hash(vin):
        return active.visible_count
    if not source_ready:
        try:
            _ua116_reject(
                SPEC_DB, uid=uid, vin=vin,
                policy_version=source_policy.POLICY_VERSION,
                revision_id=revision_id + "-rejected",
                visible_count=len([item for item in rows if item.visible]),
                reject_code="SOURCE_NOT_READY")
        except Exception:
            pass
        return 0
    try:
        receipt = _ua116_activate(
            SPEC_DB, uid=uid, vin=vin, policy_version=source_policy.POLICY_VERSION,
            revision_id=revision_id, rows=rows)
    except _UA116Error as exc:
        if exc.code == "SPEC_NOT_READY":
            try:
                _ua116_reject(
                    SPEC_DB, uid=uid, vin=vin,
                    policy_version=source_policy.POLICY_VERSION,
                    revision_id=revision_id + "-rejected",
                    visible_count=len([item for item in rows if item.visible]),
                    reject_code=exc.code)
            except Exception:
                pass
            return 0
        raise
    return int(receipt.get("visible_count") or 0)

_store_facts = _ua116_store_facts

def enqueue_card(card, *, force=False):
    """Non-destructive job enqueue; specification rows are never deleted/hidden."""
    uid = canonical_uid(card.get("car_uid"))
    vin = source_policy.normalize_vin(card.get("vin"))
    if not uid:
        raise ServiceError("INVALID_CARD_UID")
    ensure_schema()
    now = utc_now()
    with connect_spec(False) as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE vin_spec_jobs SET status='SUPERSEDED',finished_at=? "
            "WHERE car_uid=? AND vin<>? AND status<>'SUPERSEDED'",
            (now, uid, vin))
        row = conn.execute(
            "SELECT id,status,attempts FROM vin_spec_jobs "
            "WHERE car_uid=? AND vin=? AND policy_version=?",
            (uid, vin, source_policy.POLICY_VERSION)).fetchone()
        if row:
            if force or (row["status"] == "FAILED" and int(row["attempts"] or 0) < MAX_ATTEMPTS):
                conn.execute(
                    "UPDATE vin_spec_jobs SET status='PENDING',attempts=CASE WHEN ? THEN 0 ELSE attempts END,"
                    "last_error=NULL,requested_at=?,started_at=NULL,finished_at=NULL,"
                    "site_sync_status='NOT_REQUIRED',site_sync_detail=NULL WHERE id=?",
                    (int(bool(force)), now, int(row["id"])))
                conn.commit()
                return True
            conn.commit()
            return False
        conn.execute(
            "INSERT INTO vin_spec_jobs(car_id,car_uid,vin,policy_version,status,requested_at) "
            "VALUES(?,?,?,?,?,?)",
            (card.get("car_id"), uid, vin, source_policy.POLICY_VERSION, "PENDING", now))
        conn.commit()
    return True

def _ua116_legacy_snapshot(uid):
    with connect_spec(True) as conn:
        if not _table_exists(conn, "additional_specification"):
            return []
        rows = conn.execute(
            "SELECT a.field_key,a.field_value,a.confidence,"
            "COALESCE(m.label_ru,a.field_key) label_ru,COALESCE(m.category,'additional') category,"
            "COALESCE(m.unit,'') unit,COALESCE(m.evidence_count,0) evidence_count,"
            "COALESCE(m.source_domains_json,'[]') source_domains_json,"
            "COALESCE(m.is_manual,0) is_manual,COALESCE(m.is_visible,1) is_visible "
            "FROM additional_specification a LEFT JOIN additional_specification_meta m "
            "ON m.car_uid=a.car_uid AND m.field_key=a.field_key "
            "WHERE a.car_uid=? AND a.is_price_field=0 ORDER BY a.field_key", (uid,)).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["source_domains"] = json.loads(item.pop("source_domains_json") or "[]")
        except Exception:
            item["source_domains"] = []
        result.append(item)
    return _ua116_fact_rows(result)

def bootstrap_immutable_revisions():
    """Activate bound snapshots and queue every other exact VIN for recovery."""
    from recovery_core import PUBLIC_MIN_VISIBLE_SPEC_ROWS as _UA116_MIN, vin_sha256 as _ua116_vin_hash
    from spec_revision_store import initialize as _ua116_initialize, get_active as _ua116_get, stage_and_activate as _ua116_activate
    ensure_schema()
    _ua116_initialize(SPEC_DB)
    failures = []
    pending = []
    migrated = 0
    for card in read_cards():
        try:
            uid = canonical_uid(card.get("car_uid"))
            vin = source_policy.normalize_vin(card.get("vin"))
            if not uid:
                raise ServiceError("INVALID_CARD_UID")
        except Exception as exc:
            failures.append({{
                "car_uid": str(card.get("car_uid") or ""),
                "reason": "IDENTITY:" + type(exc).__name__,
            }})
            continue
        try:
            active = _ua116_get(SPEC_DB, uid)
            if active and active.vin_sha256 == _ua116_vin_hash(vin):
                continue
            rows = _ua116_legacy_snapshot(uid)
            visible = len([item for item in rows if item.visible and item.display_value])
            with connect_spec(True) as conn:
                job = conn.execute(
                    "SELECT vin,status,facts_count FROM vin_spec_jobs WHERE car_uid=? "
                    "ORDER BY id DESC LIMIT 1", (uid,)).fetchone()
            bound = bool(
                job
                and str(job["vin"]) == vin
                and str(job["status"]) == "READY"
                and int(job["facts_count"] or 0) >= _UA116_MIN
            )
            if visible >= _UA116_MIN and bound:
                _ua116_activate(
                    SPEC_DB, uid=uid, vin=vin, policy_version=source_policy.POLICY_VERSION,
                    revision_id=_ua116_revision_id(uid, vin, rows), rows=rows,
                    allow_manual_facts=True)
                migrated += 1
                continue
            failures.append({{
                "car_uid": uid,
                "vin": vin,
                "reason": "%d:%s" % (visible, "BOUND" if bound else "UNBOUND"),
            }})
        except Exception as exc:
            failures.append({{
                "car_uid": uid, "vin": vin,
                "reason": "SNAPSHOT:" + type(exc).__name__,
            }})
        try:
            queued = bool(enqueue_card(card, force=True))
            pending.append({{
                "car_uid": uid, "vin": vin,
                "state": "ENQUEUED" if queued else "EXISTING",
            }})
        except Exception as exc:
            failures.append({{
                "car_uid": uid, "vin": vin,
                "reason": "ENQUEUE:" + type(exc).__name__,
            }})
    status = "RECOVERY_PENDING" if pending else ("NEEDS_ATTENTION" if failures else "PASS")
    return {{
        "status": status, "migrated": migrated,
        "pending": pending, "failures": failures,
    }}

def start_worker():
    bootstrap_immutable_revisions()
    import ua116_runtime_bridge as _ua116_runtime
    _ua116_runtime.bootstrap_published_vin_reservations()
    return _UA116_BASE_START_WORKER()

'''
    source = _insert_before_once(
        source, runtime_anchor, runtime_support, "VIN_SERVICE_MAIN_ANCHOR"
    )
    return source


def patch_additional_spec(source: str) -> str:
    if _already_patched(
        "ua_additional_spec.py", source, f"# {MARKER}: ua_additional_spec"
    ):
        return source
    if "def inject_public_spec" not in source or "def fetch_specs" not in source:
        raise RecoveryGuardError("ADDITIONAL_SPEC_API_MISSING")
    support = f'''\n\n# {MARKER}: ua_additional_spec
_UA116_BASE_FETCH_SPECS = fetch_specs
_UA116_BASE_INJECT_PUBLIC_SPEC = inject_public_spec
from recovery_core import PUBLIC_MIN_VISIBLE_SPEC_ROWS as _UA116_MIN_VISIBLE_SPEC_ROWS

def _ua116_spec_db_path():
    # The immutable store belongs to vin_spec_service, not this renderer's
    # legacy CRM DB_PATH. Resolve lazily to avoid an import cycle.
    import vin_spec_service as _ua116_vin_service
    return _ua116_vin_service.SPEC_DB

def _ua116_exact_active(value):
    import spec_revision_store as _ua116_store
    from recovery_core import vin_sha256 as _ua116_vin_sha256
    uid = canonical_uid(value)
    if not uid:
        return None
    current_vin = _car_vin(uid)
    if not current_vin:
        return None
    active = _ua116_store.get_active(_ua116_spec_db_path(), uid)
    if not active or active.vin_sha256 != _ua116_vin_sha256(current_vin):
        return None
    return active

def fetch_specs(value, include_hidden=False):
    try:
        uid = canonical_uid(value)
        active = _ua116_exact_active(uid)
        if active is not None:
            selected = active.facts if include_hidden else active.visible_facts
            return [{{
                "car_uid": uid,
                "field_key": fact.field_key,
                "field_value": fact.display_value,
                "display_value": fact.display_value,
                "label_ru": fact.label_ru,
                "category": fact.category,
                "unit": fact.unit,
                "confidence": fact.confidence,
                "evidence_count": fact.evidence_count,
                "source_domains": list(fact.source_domains),
                "is_manual": int(fact.manual),
                "is_visible": int(fact.visible),
            }} for fact in selected]
    except Exception as exc:
        raise RuntimeError(
            "UA116_SPEC_SNAPSHOT_UNAVAILABLE:%s" % type(exc).__name__)
    # Preserve the legacy view until this exact UID/VIN has a validated ACTIVE
    # revision. Publication still fails closed in inject_public_spec below;
    # this display-only fallback prevents the old specification disappearing
    # during startup/recovery or a source outage.
    try:
        return _UA116_BASE_FETCH_SPECS(value, include_hidden=include_hidden)
    except TypeError:
        return _UA116_BASE_FETCH_SPECS(value)

def inject_public_spec(source, value):
    output = _UA116_BASE_INJECT_PUBLIC_SPEC(source, value)
    try:
        import re as _ua116_re
        from recovery_core import card_identity_errors as _ua116_card_identity_errors
        uid = canonical_uid(value)
        active = _ua116_exact_active(uid)
        if not active:
            raise RuntimeError("UA116_SPEC_EXACT_REVISION_MISSING:" + str(uid))
        rendered = len(_ua116_re.findall(
            r"class\\s*=\\s*(['\\\"])[^'\\\"]*\\bua-addspec-row\\b[^'\\\"]*\\1",
            output or "", _ua116_re.I))
        if (rendered != active.visible_count
                or rendered < _UA116_MIN_VISIBLE_SPEC_ROWS):
            raise RuntimeError(
                "UA116_SPEC_SNAPSHOT_MISMATCH:%s:%d:%d" %
                (uid, rendered, active.visible_count))
        marker = (' data-ua-spec-card="%s" data-ua-spec-revision="%s" '
                  'data-ua-spec-sha256="%s"' %
                  (uid, active.revision_id, active.digest))
        output, changed = _ua116_re.subn(
            r"(<(?:section|details)\\b[^>]*class=['\\\"][^'\\\"]*ua-additional-spec[^'\\\"]*['\\\"][^>]*)>",
            lambda match: match.group(1) + marker + ">", output, count=1, flags=_ua116_re.I)
        if changed != 1:
            raise RuntimeError("UA116_SPEC_SECTION_MARKER_MISSING:" + uid)
        errors = _ua116_card_identity_errors(
            output, uid=uid, vin=_car_vin(uid),
            expected_spec_rows=active.visible_count,
            expected_spec_digest=active.digest,
            expected_spec=active)
        if errors:
            raise RuntimeError(
                "UA116_SPEC_CONTENT_INVALID:%s:%s" % (uid, ";".join(errors)))
        return output
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("UA116_SPEC_REVISION_UNAVAILABLE:%s" % type(exc).__name__)
'''
    return source.rstrip() + support


PATCHES: dict[str, Callable[[str], str]] = {
    "cars_ui.py": patch_cars_ui,
    "konteyner.py": patch_konteyner,
    "source_policy.py": patch_source_policy,
    "vin_spec_service.py": patch_vin_service,
    "ua_additional_spec.py": patch_additional_spec,
}


def patch_bundle(root: str | Path) -> dict[str, Any]:
    requested_root = Path(root)
    if requested_root.is_symlink():
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(requested_root))
    root = requested_root.resolve(strict=True)
    originals: dict[Path, str] = {}
    candidates: dict[Path, str] = {}
    original_modes: dict[Path, int] = {}
    original_identities: dict[Path, tuple[int, int]] = {}
    result: dict[str, Any] = {}
    for name, patcher in PATCHES.items():
        nominal_path = root / name
        if nominal_path.is_symlink():
            raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(nominal_path))
        path = resolved_under(root, nominal_path)
        before, info = _safe_read_text(path)
        after = patcher(before)
        if after != before:
            after = _seal_candidate(name, after)
        compile(after, name, "exec")
        _verify_patch_seal(name, after)
        _verify_module_invariants(name, after)
        originals[path] = before
        candidates[path] = after
        original_modes[path] = stat.S_IMODE(info.st_mode)
        original_identities[path] = (info.st_dev, info.st_ino)
        result[name] = {
            "before_digest": stable_digest(before),
            "after_digest": stable_digest(after),
            "changed": before != after,
            "marker_count": after.count(MARKER),
        }
    replaced: list[Path] = []
    try:
        for path in sorted(candidates, key=lambda item: item.name):
            after = candidates[path]
            if after == originals[path]:
                continue
            current_text, _current = _safe_read_text(
                path, expected_identity=original_identities[path]
            )
            if current_text != originals[path]:
                raise RecoveryGuardError("PATCH_SOURCE_CHANGED_DURING_APPLY", path.name)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix="." + path.name + ".", suffix=".ua116", dir=str(path.parent)
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(after)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary_name, original_modes[path])
                os.replace(temporary_name, path)
                replaced.append(path)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        for path, after in candidates.items():
            readback, _info = _safe_read_text(path)
            if readback != after:
                raise RecoveryGuardError("PATCH_READBACK_MISMATCH", path.name)
    except Exception as apply_error:
        rollback_errors: list[str] = []
        for path in reversed(replaced):
            temporary_name = ""
            try:
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix="." + path.name + ".rollback.", dir=str(path.parent)
                )
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    stream.write(originals[path])
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary_name, original_modes[path])
                os.replace(temporary_name, path)
                directory = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
                readback, _info = _safe_read_text(path)
                if readback != originals[path]:
                    raise RecoveryGuardError("PATCH_ROLLBACK_READBACK_MISMATCH", path.name)
            except Exception as rollback_error:
                rollback_errors.append(
                    path.name + ":" + type(rollback_error).__name__
                )
            finally:
                if temporary_name and os.path.exists(temporary_name):
                    os.unlink(temporary_name)
        if rollback_errors:
            raise RecoveryGuardError(
                "PATCH_ROLLBACK_FAILED", ",".join(rollback_errors)
            ) from apply_error
        raise
    result["bundle_digest"] = stable_digest(result)
    return result


def _write_receipt_under(root: Path, relative_or_absolute: str, text: str) -> Path:
    candidate = Path(relative_or_absolute)
    path = resolved_under(root, candidate if candidate.is_absolute() else root / candidate)
    if path.is_symlink():
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    # Re-resolve after mkdir so a raced parent symlink cannot redirect the write.
    path = resolved_under(root, path)
    if path.exists():
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise RecoveryGuardError("PATCH_RECEIPT_NOT_REGULAR", str(path))
        if info.st_nlink != 1:
            raise RecoveryGuardError("PATCH_RECEIPT_HARDLINK_FORBIDDEN", str(path))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".receipt", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    readback, _info = _safe_read_text(path)
    if readback != text:
        raise RecoveryGuardError("PATCH_RECEIPT_READBACK_MISMATCH", str(path))
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview-root", required=True)
    parser.add_argument("--receipt")
    args = parser.parse_args()
    receipt = patch_bundle(args.preview_root)
    text = json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.receipt:
        preview_root = Path(args.preview_root).resolve(strict=True)
        _write_receipt_under(preview_root, args.receipt, text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
