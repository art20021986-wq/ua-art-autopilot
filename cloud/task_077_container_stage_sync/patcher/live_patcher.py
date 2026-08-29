"""
TASK 079 - live_patcher.py

This tool is a FAIL-CLOSED, NON-EXECUTING patch preparer. It never writes to
any production path in this delivery. It is designed so that, if ever run by
an authorized operator against a real checkout AFTER separate Gate B owner
approval, it:

  1. Verifies the full-file SHA-256 anchor of each target file against the
     TASK 079 anchors before touching anything.
  2. Locates the named active function definition by AST, computes a hash of
     its exact source block, and compares it against an explicit expected
     hash supplied by the caller. If no expected hash is supplied, or if more
     than one definition of the function exists in the file (duplicate
     definition), it aborts.
  3. Refuses to run at all unless the caller passes the exact owner approval
     token string via the `owner_token` argument AND `allow_write=True`.
     In this repository/delivery, `allow_write` is hardcoded to False at the
     top-level `main()` entrypoint, so no invocation from this codebase can
     ever write to a real file. Direct callers of the internal API must
     explicitly override that, which is out of scope for Gate A.

This file intentionally does NOT embed the actual production source of
db.py / cars_ui.py / konteyner.py / stranica.py / publikaciya.py, since that
would require access this delivery does not have. It only provides the
verification and transplant machinery to be exercised against real files by
an operator with the actual checkout, strictly after Gate B approval.
"""

from __future__ import annotations

import ast
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from eta_release_candidate import LIVE_FULL_FILE_SHA256, AnchorMismatchError, sha256_of_file

OWNER_TOKEN = "CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED"

class PatchAbortedError(RuntimeError):
    pass


@dataclass
class FunctionLocation:
    name: str
    start_line: int
    end_line: int
    source: str
    source_sha256: str


@dataclass(frozen=True)
class PatchSpec:
    anchor_key: str
    function_name: str
    function_sha256: str
    transform: str


PATCH_SPECS = (
    PatchSpec("db.py", "update_card_field",
              "1749f0eef8fc799ed5b08bd6a4482fad3126199d8c40207b76143b263349a1b1",
              "db_bridge"),
    PatchSpec("cars_ui.py", "apply_value",
              "18c8dfc9f7cb6f5d4cf4e41a0fe02dbd07be9b21f142a072e90bfac602f7388b",
              "apply_value"),
    PatchSpec("cars_ui.py", "stage_menu",
              "edf960e645680f758dd3cbfd071410067f6b4be2a94ec4c4ca97793fc9d8d795",
              "stage_menu"),
    PatchSpec("cars_ui.py", "toggle_publish",
              "21c3f452813122f18247359259432bed2a23f12163ac36859bac0ffd594d8682",
              "toggle_publish"),
    PatchSpec("konteyner.py", "prinyat",
              "e82be6158f5f67025b88e5e17f70e77b814e0c239acbfbb23bc4e124baa02ee7",
              "prinyat"),
    PatchSpec("konteyner.py", "_peresobrat",
              "7a71a1fc49424bc849625034441e5931777f3f515c711780df3238b415749c65",
              "peresobrat"),
    PatchSpec("stranica.py", "sobrat_kartochku",
              "56c27f91c60285c32e96929bb913eed8fa1a627bd038bde57ce25a343044b9c5",
              "renderer"),
    PatchSpec("publikaciya.py", "opublikovat",
              "93f130c2542124b820eae2416984705ecbbc80019a298d2b3c40fdf58d93033f",
              "publisher"),
)


def _find_function_definitions(source_text: str, function_name: str) -> List[FunctionLocation]:
    tree = ast.parse(source_text)
    lines = source_text.splitlines(keepends=True)
    found: List[FunctionLocation] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            block = "".join(lines[start:end])
            found.append(
                FunctionLocation(
                    name=function_name,
                    start_line=node.lineno,
                    end_line=end,
                    source=block,
                    source_sha256=hashlib.sha256(block.encode("utf-8")).hexdigest(),
                )
            )
    return found


def verify_target_file_anchor(path: str, anchor_key: str) -> None:
    expected = LIVE_FULL_FILE_SHA256.get(anchor_key)
    if expected is None:
        raise PatchAbortedError(f"No registered anchor for {anchor_key}")
    actual = sha256_of_file(path)
    if actual != expected:
        raise PatchAbortedError(
            f"ABORT: {anchor_key} full-file hash mismatch (expected {expected}, got {actual}). "
            "No write performed."
        )


def verify_function_anchor(
    path: str, function_name: str, expected_function_sha256: Optional[str]
) -> FunctionLocation:
    if not expected_function_sha256:
        raise PatchAbortedError(
            f"ABORT: no expected function-source hash supplied for {function_name}. "
            "Refusing generic search-and-replace."
        )
    with open(path, "r", encoding="utf-8") as f:
        source_text = f.read()
    matches = _find_function_definitions(source_text, function_name)
    if len(matches) == 0:
        raise PatchAbortedError(f"ABORT: function {function_name} not found in {path}")
    exact = [item for item in matches
             if item.source_sha256 == expected_function_sha256]
    if len(exact) > 1:
        raise PatchAbortedError(
            f"ABORT: multiple definitions of {function_name} match the approved "
            "source hash; refusing."
        )
    if not exact:
        raise PatchAbortedError(
            f"ABORT: {function_name} source hash mismatch (expected "
            f"{expected_function_sha256}, found "
            f"{','.join(item.source_sha256 for item in matches)}). No write performed."
        )
    return exact[0]


def prepare_patch(
    path: str,
    anchor_key: str,
    function_name: str,
    expected_function_sha256: Optional[str],
    replacement_source: str,
) -> str:
    """Returns the fully patched file text WITHOUT writing it anywhere.
    Raises PatchAbortedError on any anchor mismatch.
    """
    verify_target_file_anchor(path, anchor_key)
    match = verify_function_anchor(path, function_name, expected_function_sha256)

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not replacement_source.endswith("\n"):
        replacement_source += "\n"
    new_lines = lines[: match.start_line - 1] + [replacement_source] + lines[match.end_line :]
    return "".join(new_lines)


def _rename_definition(source: str, old: str, new: str) -> str:
    for prefix in ("async def ", "def "):
        needle = prefix + old + "("
        if needle in source:
            return source.replace(needle, prefix + new + "(", 1)
    raise PatchAbortedError("approved function definition header not found")


def concrete_replacement(spec: PatchSpec, source: str) -> str:
    """Return a complete, reviewable replacement for an approved source block."""
    if spec.transform == "db_bridge":
        return source + (
            "\ndef update_eta_days_atomic(card_id, days, actor_id):\n"
            "    from eta_sync_guard import apply_eta_days_live\n"
            "    return apply_eta_days_live(int(card_id), days, actor_id)\n"
        )
    if spec.transform == "apply_value":
        original = _rename_definition(source, "apply_value", "_task077_original_apply_value")
        return original + '''
def apply_value(card_id, field, raw, actor_id):
    if field != "eta_days":
        return _task077_original_apply_value(card_id, field, raw, actor_id)
    from eta_sync_guard import apply_eta_days_live
    return apply_eta_days_live(int(card_id), raw, actor_id)
'''
    if spec.transform == "stage_menu":
        needle = "if stage_no == number]"
        if source.count(needle) != 1:
            raise PatchAbortedError("stage_menu callback anchor is not unique")
        return source.replace(
            needle, 'if stage_no == number and code != "sea_transit"]', 1)
    if spec.transform == "toggle_publish":
        return '''async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    card = card_of(cid)
    preimage = int(bool(card.get("published")))
    desired = 0 if preimage else 1
    if desired:
        miss = S.missing_required(card)
        if miss:
            await q.message.reply_text("Для показа клиентам не хватает: %s" % ", ".join(miss))
            raise ApplicationHandlerStop
    db.update_card_field("cars", cid, "published", desired, q.from_user.id)
    if desired:
        try:
            import asyncio as _task077_asyncio
            import publikaciya as _task077_publisher
            ok, detail = await _task077_asyncio.to_thread(
                _task077_publisher.opublikovat, card.get("auto_number"))
        except Exception as exc:
            ok, detail = False, "Публикация не подтверждена: %s" % exc
        if not ok:
            db.update_card_field("cars", cid, "published", preimage, q.from_user.id)
            await q.message.reply_text(detail or "Публикация не подтверждена. Изменение отменено.")
            raise ApplicationHandlerStop
        await q.message.reply_text("Машина видна клиентам в каталоге.")
    else:
        await q.message.reply_text("Машина скрыта от клиентов.")
    raise ApplicationHandlerStop
'''
    if spec.transform == "prinyat":
        original = _rename_definition(source, "prinyat", "_task077_original_prinyat")
        return original + r'''
async def prinyat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wait = context.user_data.get("cont_wait")
    if not wait or wait.get("field") != "eta_manual":
        return await _task077_original_prinyat(update, context)
    msg = update.effective_message
    if not msg or not msg.text:
        return
    raw = msg.text.strip()
    if not re.fullmatch(r"\d{1,3}", raw):
        await msg.reply_text("Пришлите целое число дней от 0 до 400.")
        raise ApplicationHandlerStop
    days = int(raw)
    if days > 400:
        await msg.reply_text("Пришлите целое число дней от 0 до 400.")
        raise ApplicationHandlerStop
    import asyncio as _task077_asyncio
    from eta_sync_guard import apply_eta_days_live
    ok, detail = await _task077_asyncio.to_thread(
        apply_eta_days_live, int(wait["card_id"]), days, update.effective_user.id)
    context.user_data.pop("cont_wait", None)
    await msg.reply_text(detail)
    raise ApplicationHandlerStop
'''
    if spec.transform == "peresobrat":
        return '''def _peresobrat():
    """Synchronous bounded rebuild; callers receive a real boolean result."""
    try:
        result = subprocess.run(
            ["python3.10", "-c",
             "import sys; sys.path.insert(0, '/home/Carix'); import stranica; stranica.main()"],
            cwd="/home/Carix", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=180, check=False)
        return result.returncode == 0
    except Exception as exc:
        log.warning("konteyner: пересборка не подтверждена: %s", exc)
        return False
'''
    if spec.transform == "renderer":
        needle = "        html = _ishodnaya(m, kadry, sredn)"
        if source.count(needle) != 1:
            raise PatchAbortedError("active renderer call anchor is not unique")
        injected = (
            "        from eta_sync_guard import sanitize_stale_arrival_sentence\n"
            "        m = dict(m or {})\n"
            "        for _task077_field in ('condition_text', 'description'):\n"
            "            if m.get(_task077_field):\n"
            "                m[_task077_field] = sanitize_stale_arrival_sentence(str(m[_task077_field]))\n"
            + needle
        )
        return source.replace(needle, injected, 1)
    if spec.transform == "publisher":
        master = "        html, diag, m = _master(kod)"
        if source.count(master) != 1:
            raise PatchAbortedError("publisher master anchor is not unique")
        source = source.replace(
            master,
            master + "\n        if not diag:\n"
            "            from eta_sync_guard import diagnostic_placeholder_html\n"
            "            diag = diagnostic_placeholder_html(kod)",
            1,
        )
        before = "    stalo = dict((put, _sha(put)) for put in celi)"
        if source.count(before) != 1:
            raise PatchAbortedError("publisher completion anchor is not unique")
        catalog = '''    try:
        from eta_sync_guard import rebuild_catalogs_live
        _task077_catalog_ok, _task077_catalog_text = rebuild_catalogs_live()
    except Exception as _task077_catalog_exc:
        _task077_catalog_ok = False
        _task077_catalog_text = str(_task077_catalog_exc)
    if not _task077_catalog_ok:
        _otkat(papka_rez, celi)
        return False, "Публикация отменена: каталоги не подтверждены (%s)." % _task077_catalog_text

'''
        return source.replace(before, catalog + before, 1)
    raise PatchAbortedError("unknown concrete transform " + spec.transform)


def _replace_in_text(source_text: str, spec: PatchSpec, path_label: str) -> str:
    matches = _find_function_definitions(source_text, spec.function_name)
    exact = [m for m in matches if m.source_sha256 == spec.function_sha256]
    if len(exact) != 1:
        raise PatchAbortedError(
            f"ABORT: {path_label}:{spec.function_name} expected one approved "
            f"definition, got {len(exact)}")
    match = exact[0]
    replacement = concrete_replacement(spec, match.source)
    lines = source_text.splitlines(keepends=True)
    if not replacement.endswith("\n"):
        replacement += "\n"
    return "".join(lines[:match.start_line - 1] + [replacement] + lines[match.end_line:])


def prepare_patch_bundle(root: str) -> Dict[str, str]:
    """Verify the exact audited preimage once, then apply all eight transforms in memory."""
    grouped: Dict[str, List[PatchSpec]] = {}
    for spec in PATCH_SPECS:
        grouped.setdefault(spec.anchor_key, []).append(spec)
    result: Dict[str, str] = {}
    for anchor_key, specs in grouped.items():
        path = os.path.join(root, anchor_key)
        verify_target_file_anchor(path, anchor_key)
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
        for spec in specs:
            source = _replace_in_text(source, spec, path)
        compile(source, path, "exec")
        result[path] = source
    return result


def main(
    targets: Dict[str, str],
    owner_token: str,
    allow_write: bool = False,
) -> None:
    """Legacy verification-only entry point kept for callers."""
    if owner_token != OWNER_TOKEN:
        raise PatchAbortedError("ABORT: owner token missing or incorrect. No action taken.")

    if not allow_write:
        raise PatchAbortedError(
            "ABORT: explicit allow_write=True is required. No file was modified."
        )

    # Unreachable in this delivery by construction.
    for anchor_key, path in targets.items():
        verify_target_file_anchor(path, anchor_key)


def apply_patch_bundle(root: str, backup_dir: str, owner_token: str,
                       apply: bool = False) -> Dict[str, str]:
    """Gate B entry point. It is inert unless all three independent gates pass."""
    if owner_token != OWNER_TOKEN:
        raise PatchAbortedError("ABORT: exact owner token missing")
    if apply is not True:
        raise PatchAbortedError("ABORT: explicit apply=True missing")
    root = os.path.abspath(root)
    backup_dir = os.path.abspath(backup_dir)
    if not backup_dir or backup_dir == root or backup_dir.startswith(root + os.sep):
        raise PatchAbortedError("ABORT: backup_dir must be outside the live root")
    patched = prepare_patch_bundle(root)
    os.makedirs(backup_dir, exist_ok=False)
    guard_source_path = os.path.join(os.path.dirname(__file__), "eta_release_candidate.py")
    guard_target = os.path.join(root, "eta_sync_guard.py")
    engine_source_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "task_076_eta_sync", "eta_engine.py"))
    engine_target = os.path.join(root, "eta_engine.py")
    originals: Dict[str, Optional[bytes]] = {}
    for path in list(patched) + [guard_target, engine_target]:
        originals[path] = open(path, "rb").read() if os.path.exists(path) else None
        if originals[path] is not None:
            shutil.copy2(path, os.path.join(backup_dir, os.path.basename(path)))
    try:
        writes = dict(patched)
        writes[guard_target] = open(guard_source_path, encoding="utf-8").read()
        writes[engine_target] = open(engine_source_path, encoding="utf-8").read()
        for path, source in writes.items():
            compile(source, path, "exec")
            fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path))
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(source)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        return {path: hashlib.sha256(text.encode("utf-8")).hexdigest()
                for path, text in writes.items()}
    except Exception:
        for path, content in originals.items():
            if content is None:
                if os.path.exists(path):
                    os.remove(path)
            else:
                fd, temporary = tempfile.mkstemp(dir=os.path.dirname(path))
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
        raise


if __name__ == "__main__":
    raise SystemExit(
        "live_patcher.py is a library for Gate B tooling only. It performs no "
        "action when run directly, by design, in this delivery."
    )
