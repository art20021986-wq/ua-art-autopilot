#!/usr/bin/env python3
"""Build the private HANDOFF006 writer-fence candidate without exposing inputs.

The builder accepts only the three freshly bound source hashes.  It writes a
new private candidate directory, never edits the input directory, and emits a
hash-only manifest.  The private source bytes and generated source files must
not be committed to Git.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


CONTRACT = "PR114-HANDOFF006-PRIVATE-INTEGRATION-1"
BEFORE_SHA256 = {
    "cars_ui.py": "4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde",
    "stranica.py": "2794f01c00a49f1a55c66f3e6af4657808f857e9167f59a5da84c9b8430d724a",
    "publish_transaction_guard.py": "3d80712290e0881ebe7583231b532de422f808e6f18b5f6a90566d9e1eed3e0d",
}

CARS_MARKER = "# UA-ART-PR114-PUBLICATION-FENCE-HANDOFF006:START"
STRANICA_MARKER = "# UA-ART-PR114-STRANICA-FENCE-HANDOFF006:START"
GUARD_MARKER = "# UA-ART-PR114-SHARED-FENCE-HANDOFF006:START"


CARS_BLOCK = r'''

# UA-ART-PR114-PUBLICATION-FENCE-HANDOFF006:START
import asyncio as _ua114_asyncio
import hashlib as _ua114_hashlib
import shutil as _ua114_shutil
import tempfile as _ua114_tempfile
from publication_fence import publication_fence as _ua114_publication_fence
from publication_fence import require_publication_fence as _ua114_require_fence

_ua114_remove_photo_files_base = _ubrat_fayly_foto
_ua114_remove_video_files_base = _ubrat_fayly_video
_ua114_remove_video_full_base = _ubrat_video_polno
_ua114_rebuild_pages_base = _peresobrat_stranicy


def _ubrat_fayly_foto(nomer):
    _ua114_require_fence()
    return _ua114_remove_photo_files_base(nomer)


def _ubrat_fayly_video(nomer):
    _ua114_require_fence()
    return _ua114_remove_video_files_base(nomer)


def _ubrat_video_polno(nomer):
    _ua114_require_fence()
    return _ua114_remove_video_full_base(nomer)


def _peresobrat_stranicy():
    with _ua114_publication_fence():
        return _ua114_rebuild_pages_base()


def _ua114_file_sha256(path):
    digest = _ua114_hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _ua114_regular_files(root):
    """Return exact regular-file members and refuse symlinked content."""
    if not os.path.isdir(root):
        return []
    result = []
    for current, directories, files in os.walk(root, followlinks=False):
        for name in directories:
            if os.path.islink(os.path.join(current, name)):
                raise RuntimeError("MEDIA_BACKUP_SYMLINK_REFUSED")
        for name in files:
            path = os.path.join(current, name)
            if os.path.islink(path) or not os.path.isfile(path):
                raise RuntimeError("MEDIA_BACKUP_NONREGULAR_REFUSED")
            result.append(path)
    return sorted(result)


def _ua114_backup_exact(paths, root, backup_dir):
    """Copy every destructive target and verify byte hashes before mutation."""
    root = os.path.realpath(root)
    entries = []
    for source in sorted(set(paths)):
        source = os.path.realpath(source)
        if os.path.commonpath((root, source)) != root:
            raise RuntimeError("MEDIA_BACKUP_PATH_ESCAPE")
        relative = os.path.relpath(source, root)
        destination = os.path.join(backup_dir, "exact", relative)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        before_sha256 = _ua114_file_sha256(source)
        _ua114_shutil.copy2(source, destination)
        if _ua114_file_sha256(destination) != before_sha256:
            raise RuntimeError("MEDIA_BACKUP_SHA256_MISMATCH:" + relative)
        entries.append((source, destination, before_sha256, relative))
    if len(entries) != len(set(paths)):
        raise RuntimeError("MEDIA_BACKUP_MEMBER_COUNT_MISMATCH")
    return entries


def _ua114_restore_exact(entries):
    """Restore only missing originals; never overwrite a newer after-image."""
    conflicts = []
    for destination, backup, before_sha256, relative in entries:
        staged = None
        try:
            if os.path.lexists(destination):
                if os.path.islink(destination) or _ua114_file_sha256(destination) != before_sha256:
                    conflicts.append("media:" + relative)
                continue
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            descriptor, staged = _ua114_tempfile.mkstemp(
                prefix=".ua114-restore-", dir=os.path.dirname(destination))
            os.close(descriptor)
            _ua114_shutil.copy2(backup, staged)
            if _ua114_file_sha256(staged) != before_sha256:
                raise RuntimeError("MEDIA_RESTORE_BACKUP_SHA256_MISMATCH")
            # link is atomic and refuses an existing destination, including
            # a file created after the initial check. Never replace it.
            os.link(staged, destination)
        except Exception:
            conflicts.append("media:" + relative)
        finally:
            if staged is not None:
                try:
                    os.unlink(staged)
                except OSError:
                    if "media:" + relative not in conflicts:
                        conflicts.append("media:" + relative)
    return conflicts


def _ua114_restore_fields(cid, actor_id, before, expected):
    """Restore only values still equal to this operation's after-image."""
    conflicts = []
    current = card_of(cid) or {}
    for field, old_value in before.items():
        if current.get(field) != expected.get(field):
            conflicts.append(field)
            continue
        try:
            db.update_card_field("cars", cid, field, old_value, actor_id)
        except Exception:
            conflicts.append(field)
    return conflicts


def _ua114_photo_remove_all_mutation(cid, actor_id):
    with _ua114_publication_fence():
        card = card_of(cid) or {}
        if not card:
            return {"ok": False, "error": "CARD_NOT_FOUND", "rollback_conflicts": []}
        code = str(card.get("auto_number") or "").upper()
        before = {"photos": card.get("photos")}
        expected = {"photos": jdump([])}
        if card.get("cover_photo") is not None:
            before["cover_photo"] = card.get("cover_photo")
            expected["cover_photo"] = None
        if "hidden_photos" in card:
            before["hidden_photos"] = card.get("hidden_photos")
            expected["hidden_photos"] = jdump([])
        photo_root = os.path.join("/home/Carix", "video", "foto", code)
        try:
            targets = _ua114_regular_files(photo_root)
            backup_dir = _v142_papka(code, "foto_exact")
            backup_entries = _ua114_backup_exact(targets, photo_root, backup_dir)
        except Exception as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "rollback_conflicts": [],
            }
        backup_count = len(backup_entries)
        removed = 0
        written = {}
        try:
            removed = _ubrat_fayly_foto(code)
            remaining = [path for path in targets if os.path.exists(path)]
            if remaining:
                raise RuntimeError("PHOTO_REMOVE_INCOMPLETE:%d" % len(remaining))
            for field, value in expected.items():
                db.update_card_field("cars", cid, field, value, actor_id)
                written[field] = value
            if not _peresobrat_stranicy():
                raise RuntimeError("PAGE_REBUILD_FAILED")
            return {
                "ok": True,
                "removed": removed,
                "before_count": len(photos_of(card)),
                "backup_count": backup_count,
            }
        except Exception as exc:
            conflicts = _ua114_restore_fields(
                cid, actor_id,
                {field: before[field] for field in written}, written)
            file_conflicts = _ua114_restore_exact(backup_entries)
            conflicts.extend(file_conflicts)
            restored = len(backup_entries) - len(file_conflicts)
            try:
                if not _peresobrat_stranicy():
                    conflicts.append("rebuilt_pages")
            except Exception:
                conflicts.append("rebuilt_pages")
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "removed": removed,
                "restored": restored,
                "rollback_conflicts": sorted(set(conflicts)),
            }


def _ua114_video_remove_all_mutation(cid, actor_id):
    with _ua114_publication_fence():
        card = card_of(cid) or {}
        if not card:
            return {"ok": False, "error": "CARD_NOT_FOUND", "rollback_conflicts": []}
        before = {name: card.get(name) for name in ("videos", "video_h", "video_v")}
        expected = {"videos": jdump([]), "video_h": None, "video_v": None}
        code = str(card.get("auto_number") or "").upper()
        video_root = os.path.join("/home/Carix", "video")
        try:
            names = sorted(os.listdir(video_root))
        except FileNotFoundError:
            names = []
        except OSError as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "rollback_conflicts": [],
            }
        targets = []
        for name in names:
            primary = name == code + ".mp4" or (
                name.startswith(code + "-") and name.endswith(".mp4"))
            if not primary:
                continue
            path = os.path.join(video_root, name)
            if os.path.islink(path) or not os.path.isfile(path):
                return {
                    "ok": False,
                    "error": "MEDIA_BACKUP_NONREGULAR_REFUSED",
                    "rollback_conflicts": [],
                }
            targets.append(path)
            poster = path + ".poster.jpg"
            if os.path.isfile(poster):
                if os.path.islink(poster):
                    return {
                        "ok": False,
                        "error": "MEDIA_BACKUP_SYMLINK_REFUSED",
                        "rollback_conflicts": [],
                    }
                targets.append(poster)
        try:
            backup_dir = _v142_papka(code, "video_exact")
            backup_entries = _ua114_backup_exact(targets, video_root, backup_dir)
        except Exception as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "rollback_conflicts": [],
            }
        written = {}
        try:
            for field, value in expected.items():
                db.update_card_field("cars", cid, field, value, actor_id)
                written[field] = value
            removed, failures = _ubrat_video_polno(card.get("auto_number"))
            remaining = [path for path in targets if os.path.exists(path)]
            if remaining:
                failures = list(failures) + [
                    "VIDEO_REMOVE_INCOMPLETE:%d" % len(remaining)]
            if failures:
                conflicts = _ua114_restore_fields(
                    cid, actor_id,
                    {field: before[field] for field in written}, written)
                conflicts.extend(_ua114_restore_exact(backup_entries))
                return {
                    "ok": False,
                    "error": "VIDEO_REMOVE_FAILED:" + "; ".join(failures),
                    "removed": removed,
                    "rollback_conflicts": conflicts,
                }
            return {
                "ok": True,
                "removed": removed,
                "before_count": len(videos_of(card)),
            }
        except Exception as exc:
            conflicts = _ua114_restore_fields(
                cid, actor_id,
                {field: before[field] for field in written}, written)
            conflicts.extend(_ua114_restore_exact(backup_entries))
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "removed": 0,
                "rollback_conflicts": conflicts,
            }


def _ua114_diag_directory(code):
    return os.path.join("/home/Carix", "video", "diag", code)


def _ua114_diag_clear_mutation(cid, pole, actor_id):
    if pole not in ("condition_photos", "condition_videos"):
        return {"ok": False, "error": "DIAGNOSTIC_FIELD_REFUSED", "rollback_conflicts": []}
    with _ua114_publication_fence():
        card = card_of(cid) or {}
        if not card:
            return {"ok": False, "error": "CARD_NOT_FOUND", "rollback_conflicts": []}
        code = str(card.get("auto_number") or "").strip()
        if not code:
            code = "UA-%04d" % int(card["id"])
        directory = _ua114_diag_directory(code)
        video = pole == "condition_videos"
        targets = []
        try:
            names = sorted(os.listdir(directory))
        except FileNotFoundError:
            names = []
        except OSError as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "rollback_conflicts": [],
            }
        for name in names:
            path = os.path.join(directory, name)
            if name.endswith(".poster.jpg"):
                continue
            if os.path.islink(path) or not os.path.isfile(path):
                return {
                    "ok": False,
                    "error": "MEDIA_BACKUP_NONREGULAR_REFUSED",
                    "rollback_conflicts": [],
                }
            try:
                with open(path, "rb") as handle:
                    header = handle.read(16)
            except OSError:
                continue
            if (header[4:8] == b"ftyp") == video:
                targets.append(path)
                if os.path.isfile(path + ".poster.jpg"):
                    targets.append(path + ".poster.jpg")
        try:
            backup_dir = _v142_papka(code, "diag_" + pole)
            backup_entries = _ua114_backup_exact(targets, directory, backup_dir)
        except Exception as exc:
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "rollback_conflicts": [],
            }
        backup_count = len(backup_entries)
        before = {pole: card.get(pole)}
        expected = {pole: "[]"}
        written = {}
        removed = 0
        try:
            db.update_card_field("cars", int(cid), pole, "[]", actor_id)
            written[pole] = "[]"
            for path in targets:
                os.remove(path)
                removed += 1
            if not _peresobrat_stranicy():
                raise RuntimeError("PAGE_REBUILD_FAILED")
            return {
                "ok": True,
                "removed": removed,
                "before_count": len(jload(card.get(pole))),
                "backup_count": backup_count,
            }
        except Exception as exc:
            conflicts = _ua114_restore_fields(
                int(cid), actor_id,
                {field: before[field] for field in written}, written)
            conflicts.extend(_ua114_restore_exact(backup_entries))
            try:
                if not _peresobrat_stranicy():
                    conflicts.append("rebuilt_pages")
            except Exception:
                conflicts.append("rebuilt_pages")
            return {
                "ok": False,
                "error": type(exc).__name__ + ":" + str(exc),
                "removed": removed,
                "rollback_conflicts": sorted(set(conflicts)),
            }


async def photo_remove_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    result = await _ua114_asyncio.to_thread(
        _ua114_photo_remove_all_mutation, cid, q.from_user.id)
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← К карточке", callback_data="car_open:%d" % cid)]])
    if not result.get("ok"):
        suffix = ""
        if result.get("rollback_conflicts"):
            suffix = "\nТребуется ручная сверка: " + ", ".join(result["rollback_conflicts"])
        await q.message.reply_text(
            "Фото не изменены либо выполнен ограниченный откат.%s" % suffix,
            reply_markup=back)
        raise ApplicationHandlerStop
    await q.message.reply_text(
        "Удалено фото: %d.\nСтраница покупателя пересобрана.\n\n"
        "Теперь пришлите новые кадры одним альбомом." % result["before_count"],
        reply_markup=back)
    raise ApplicationHandlerStop


async def video_remove_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    cid = int(q.data.split(":")[-1])
    result = await _ua114_asyncio.to_thread(
        _ua114_video_remove_all_mutation, cid, q.from_user.id)
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← К карточке", callback_data="car_open:%d" % cid)]])
    if not result.get("ok"):
        suffix = ""
        if result.get("rollback_conflicts"):
            suffix = "\nТребуется ручная сверка: " + ", ".join(result["rollback_conflicts"])
        await q.message.reply_text(
            "Видео убрать полностью не вышло; выполнен ограниченный откат.%s" % suffix,
            reply_markup=back)
        raise ApplicationHandlerStop
    await q.message.reply_text(
        "Удалено видео: %d. Файлов с сайта убрано: %d.\n"
        "Фото и материалы диагностики не тронуты." % (
            result["before_count"], result["removed"]),
        reply_markup=back)
    raise ApplicationHandlerStop


async def diag_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await _v168_ack(q,)
    try:
        _, cid, pole = (q.data or "").split(":", 2)
    except ValueError:
        raise ApplicationHandlerStop
    result = await _ua114_asyncio.to_thread(
        _ua114_diag_clear_mutation, int(cid), pole, q.from_user.id)
    back = InlineKeyboardMarkup([[InlineKeyboardButton(
        "← К диагностике", callback_data="car_cond:%s" % cid)]])
    if not result.get("ok"):
        suffix = ""
        if result.get("rollback_conflicts"):
            suffix = "\nТребуется ручная сверка: " + ", ".join(result["rollback_conflicts"])
        await q.message.reply_text(
            "Материалы диагностики не изменены либо выполнен ограниченный откат.%s" % suffix,
            reply_markup=back)
        raise ApplicationHandlerStop
    label = "Фото" if pole == "condition_photos" else "Видео"
    await q.message.reply_text(
        "%s проверки убраны: %d.\nСтраница пересобрана." % (
            label, result["before_count"]),
        reply_markup=back)
    raise ApplicationHandlerStop
# UA-ART-PR114-PUBLICATION-FENCE-HANDOFF006:END
'''


STRANICA_BLOCK = r'''

# UA-ART-PR114-STRANICA-FENCE-HANDOFF006:START
from publication_fence import publication_fence as _ua114_publication_fence

_ua114_zapisat_base = zapisat
_ua114_obnovit_etalon_base = obnovit_etalon
_ua114_main_base = main


def zapisat(*args, **kwargs):
    with _ua114_publication_fence():
        return _ua114_zapisat_base(*args, **kwargs)


def obnovit_etalon(*args, **kwargs):
    with _ua114_publication_fence():
        return _ua114_obnovit_etalon_base(*args, **kwargs)


def main(*args, **kwargs):
    # Covers generation, spec84 nested writes, validation and fallback restore.
    with _ua114_publication_fence():
        return _ua114_main_base(*args, **kwargs)
# UA-ART-PR114-STRANICA-FENCE-HANDOFF006:END
'''


GUARD_BLOCK = r'''

# UA-ART-PR114-SHARED-FENCE-HANDOFF006:START
from publication_fence import publication_fence as _ua114_publication_fence


def _exclusive_lock():
    """Use the shared reentrant registry; never open a second flock inode."""
    return _ua114_publication_fence(timeout=WAIT_SECONDS)
# UA-ART-PR114-SHARED-FENCE-HANDOFF006:END
'''


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes, name: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("UTF8_REQUIRED:" + name) from exc


def _require_defs(source: str, name: str, required: set[str]) -> None:
    tree = ast.parse(source, filename=name)
    found = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    missing = sorted(required - found)
    if missing:
        raise RuntimeError("PRIVATE_SOURCE_SHAPE_MISMATCH:%s:%s" % (name, ",".join(missing)))


def _integrate_cars_text(source: str) -> str:
    if CARS_MARKER in source:
        raise RuntimeError("CARS_ALREADY_INTEGRATED")
    _require_defs(source, "cars_ui.py", {
        "photo_remove_all", "video_remove_all", "diag_clear", "_ubrat_fayly_foto",
        "_ubrat_fayly_video", "_ubrat_video_polno", "_peresobrat_stranicy",
        "register",
    })
    return source.rstrip() + CARS_BLOCK + "\n"


def _integrate_stranica_text(source: str) -> str:
    if STRANICA_MARKER in source:
        raise RuntimeError("STRANICA_ALREADY_INTEGRATED")
    _require_defs(source, "stranica.py", {"zapisat", "obnovit_etalon", "main"})
    anchor = 'if __name__ == "__main__":\n    main()'
    if source.count(anchor) != 1:
        raise RuntimeError("STRANICA_MAIN_ANCHOR_MISMATCH")
    return source.replace(anchor, STRANICA_BLOCK.strip("\n") + "\n\n" + anchor)


def _integrate_guard_text(source: str) -> str:
    if GUARD_MARKER in source:
        raise RuntimeError("GUARD_ALREADY_INTEGRATED")
    _require_defs(source, "publish_transaction_guard.py", {
        "_exclusive_lock", "publish_batch", "publish_one", "rebuild_catalog",
        "verify_bundle", "rollback_backup",
    })
    return source.rstrip() + GUARD_BLOCK + "\n"


def _atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    temp = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def build(source_dir: Path, output_dir: Path, fence_source: Path) -> dict[str, object]:
    source_dir = source_dir.resolve()
    output_dir = output_dir.resolve()
    if source_dir == output_dir:
        raise RuntimeError("IN_PLACE_PRIVATE_SOURCE_EDIT_FORBIDDEN")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError("NONEMPTY_OUTPUT_DIR_FORBIDDEN")

    original: dict[str, bytes] = {}
    for name, expected in BEFORE_SHA256.items():
        data = (source_dir / name).read_bytes()
        if _sha(data) != expected:
            raise RuntimeError("PRIVATE_SOURCE_SHA256_MISMATCH:" + name)
        original[name] = data

    integrated = {
        "cars_ui.py": _integrate_cars_text(_decode(original["cars_ui.py"], "cars_ui.py")),
        "stranica.py": _integrate_stranica_text(
            _decode(original["stranica.py"], "stranica.py")),
        "publish_transaction_guard.py": _integrate_guard_text(
            _decode(original["publish_transaction_guard.py"], "publish_transaction_guard.py")),
    }
    for name, source in integrated.items():
        compile(source, name, "exec")

    output_dir.mkdir(parents=True, exist_ok=True)
    after: dict[str, dict[str, object]] = {}
    for name, source in integrated.items():
        data = source.encode("utf-8")
        _atomic_write(output_dir / name, data, (source_dir / name).stat().st_mode & 0o777)
        after[name] = {"sha256": _sha(data), "bytes": len(data)}

    fence_data = fence_source.read_bytes()
    compile(_decode(fence_data, "publication_fence.py"), "publication_fence.py", "exec")
    _atomic_write(output_dir / "publication_fence.py", fence_data, 0o644)
    after["publication_fence.py"] = {"sha256": _sha(fence_data), "bytes": len(fence_data)}

    manifest: dict[str, object] = {
        "contract": CONTRACT,
        "production_authority": False,
        "installed": False,
        "writer_gate_pass": False,
        "private_sources_committed": False,
        "before_sha256": BEFORE_SHA256,
        "candidate": after,
        "lock_path": "/home/Carix/.ua_art_publish_transaction.lock",
        "lock_order": ["publication_fence", "sqlite", "spec84"],
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    _atomic_write(output_dir / "PRIVATE_CANDIDATE_MANIFEST.json", manifest_data, 0o600)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--fence-source", type=Path,
        default=Path(__file__).with_name("publication_fence.py"),
    )
    args = parser.parse_args()
    manifest = build(args.source_dir, args.output_dir, args.fence_source)
    print(json.dumps({
        "contract": manifest["contract"],
        "status": "PASS",
        "candidate": manifest["candidate"],
        "installed": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
