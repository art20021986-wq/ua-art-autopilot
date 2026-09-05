#!/usr/bin/env python3
"""Remove the unsolicited public VIN advertisement and restore specifications."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import fcntl
import gzip
import html
import hashlib
import importlib.util
import json
import os
import pathlib
import re
import sqlite3
import stat
import tempfile
import urllib.parse


TASK_ID = "TASK115-REMOVE-VIN-ADS"
CONTRACT = "UA-ART-NO-VIN-ADS-V1.0"
ROOT = pathlib.Path("/home/Carix")
SAFE = ROOT / "autopilot_inbox/cloud/task_068_ferry_vin"
RECEIPT = SAFE / "task115_receipt.json"
LATEST = SAFE / "task115_latest_backup.txt"
CERTIFIED = SAFE / "task115_certified_backup.json"
BACKUPS = SAFE / "task115_backups"
LOCK = ROOT / ".task115_no_vin_ads.lock"
DB = ROOT / "crm.db"
SPEC_RENDERER = ROOT / "ua_additional_spec.py"
VIN_SERVICE = ROOT / "vin_spec_service.py"
LEGACY_GENERATORS = (
    ROOT / "master_card.py",
    ROOT / "stranica.py",
    ROOT / "yadro.py",
)
CRM_UI = ROOT / "cars_ui.py"
CLIENT_UI = ROOT / "client_ui.py"
PUBLISHER = ROOT / "publikaciya.py"
SOURCE_PATHS = (
    SPEC_RENDERER, VIN_SERVICE, *LEGACY_GENERATORS, CRM_UI, CLIENT_UI, PUBLISHER,
)
PUBLIC_ROOTS = (ROOT / "video", ROOT / "site")
IDS = tuple("UA-%04d" % value for value in range(1, 17))
ADD_START = "<!--UA099_ADD_SPEC_START-->"
ADD_END = "<!--UA099_ADD_SPEC_END-->"
CLEAN_START = "<!--UA099_CLEAN_VIN_START-->"
CLEAN_END = "<!--UA099_CLEAN_VIN_END-->"
OLD_START = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
OLD_END = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
PY_START = "# >>> UA115 NO PUBLIC VIN ADS"
PY_END = "# <<< UA115 NO PUBLIC VIN ADS"
WORKER_START = "# >>> UA115 VIN AUTOWORKER DISABLED"
WORKER_END = "# <<< UA115 VIN AUTOWORKER DISABLED"
FORBIDDEN = re.compile(
    r"carhistory(?:\.kr)?|vindecoderz(?:\.com)?|"
    r"проверить\s+vin|перевірити\s+vin|2\s*200\s*krw",
    re.I,
)
FORBIDDEN_CTA_SOURCE = re.compile(
    r"https?://[^\"']*(?:carhistory(?:\.kr)?|vindecoderz(?:\.com)?)|"
    r"Korea\s+CarHistory|(?:Проверить|Перевірити)\s+VIN",
    re.I,
)
WORKER_REGISTRATION = "_ua110_vin_service.start_worker()"
PUBLISH_NORMALIZER_START = "# >>> UA111 FINAL PUBLIC SPEC NORMALIZER V1"
PUBLISH_NORMALIZER_END = "# <<< UA111 FINAL PUBLIC SPEC NORMALIZER V1"
APPROVED_HOSTS = {
    "www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "telegram.org",
    "maps.app.goo.gl", "ecomm.one-line.com", "schema.org", "www.w3.org",
}
MAX_BYTES = 64 * 1024 * 1024
MIN_SPEC_ROWS = 10


class InstallError(RuntimeError):
    pass


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read(path: pathlib.Path, required: bool = True) -> bytes | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        if required:
            raise InstallError("MISSING:" + str(path))
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise InstallError("UNSAFE_FILE:" + str(path))
    value = path.read_bytes()
    if len(value) > MAX_BYTES:
        raise InstallError("FILE_TOO_LARGE:" + str(path))
    return value


def atomic(path: pathlib.Path, value: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    current = read(path, False)
    actual_mode = mode if mode is not None else (stat.S_IMODE(path.stat().st_mode) if current is not None else 0o600)
    handle = tempfile.NamedTemporaryFile("wb", dir=path.parent, prefix="." + path.name + ".", suffix=".task115", delete=False)
    temporary = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, actual_mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: pathlib.Path, value: dict) -> None:
    atomic(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def car_rows() -> dict[str, str]:
    uri = "file:" + str(DB.resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=30) as conn:
        conn.execute("PRAGMA query_only=ON")
        rows = conn.execute("SELECT auto_number,vin FROM cars WHERE published=1 ORDER BY auto_number").fetchall()
        if conn.total_changes:
            raise InstallError("CRM_WRITE_GUARD")
    result = {str(uid): str(vin or "").strip().upper() for uid, vin in rows}
    if tuple(sorted(result)) != IDS or any(not result[uid] for uid in IDS):
        raise InstallError("CARD_REGISTRY_NOT_16")
    return result


def target_paths() -> list[pathlib.Path]:
    paths = list(SOURCE_PATHS)
    for root in PUBLIC_ROOTS:
        paths.extend(root / (uid + ".html") for uid in IDS)
    return paths


def backup(paths: list[pathlib.Path]) -> pathlib.Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    folder = BACKUPS / dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    (folder / "files").mkdir(parents=True)
    items = []
    for index, path in enumerate(paths):
        value = read(path)
        stored = "files/%04d.gz" % index
        atomic(folder / stored, gzip.compress(value or b"", 9, mtime=0), 0o600)
        items.append({"path": str(path), "sha256": sha(value or b""), "mode": stat.S_IMODE(path.stat().st_mode), "stored": stored})
    atomic_json(folder / "manifest.json", {
        "schema_version": 2,
        "task_id": TASK_ID,
        "files": items,
    })
    return folder


def backup_identity(
        folder: pathlib.Path, expected_sha256: str | None = None,
        require_current_preimage: bool = False) -> tuple[pathlib.Path, dict, str]:
    """Fully validate a task-scoped backup bundle without changing production."""
    try:
        folder_info = folder.lstat()
    except FileNotFoundError as exc:
        raise InstallError("BACKUP_MISSING") from exc
    if stat.S_ISLNK(folder_info.st_mode) or not stat.S_ISDIR(folder_info.st_mode):
        raise InstallError("BACKUP_UNSAFE_DIRECTORY")
    resolved = folder.resolve()
    if resolved.parent != BACKUPS.resolve():
        raise InstallError("BACKUP_SCOPE")
    manifest_bytes = read(resolved / "manifest.json") or b""
    manifest_sha256 = sha(manifest_bytes)
    if expected_sha256 is not None and manifest_sha256 != expected_sha256:
        raise InstallError("BACKUP_MANIFEST_SHA256_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except Exception as exc:
        raise InstallError("BACKUP_MANIFEST_JSON") from exc
    expected_paths = {str(path) for path in target_paths()}
    items = manifest.get("files") or []
    manifest_paths = [str(item.get("path") or "") for item in items if isinstance(item, dict)]
    if (manifest.get("task_id") != TASK_ID or manifest.get("schema_version") != 2
            or len(items) != len(manifest_paths)
            or len(manifest_paths) != len(set(manifest_paths))
            or set(manifest_paths) != expected_paths):
        raise InstallError("BACKUP_MANIFEST_SCOPE")
    files_directory = resolved / "files"
    try:
        files_info = files_directory.lstat()
    except FileNotFoundError as exc:
        raise InstallError("BACKUP_FILES_MISSING") from exc
    if stat.S_ISLNK(files_info.st_mode) or not stat.S_ISDIR(files_info.st_mode):
        raise InstallError("BACKUP_FILES_UNSAFE_DIRECTORY")
    files_root = files_directory.resolve()
    for item in items:
        path = pathlib.Path(str(item["path"]))
        stored = resolved / str(item.get("stored") or "")
        if stored.resolve().parent != files_root:
            raise InstallError("BACKUP_STORED_SCOPE")
        try:
            value = gzip.decompress(read(stored) or b"")
        except Exception as exc:
            raise InstallError("BACKUP_GZIP") from exc
        if sha(value) != item.get("sha256"):
            raise InstallError("BACKUP_HASH")
        try:
            mode = int(item["mode"])
        except Exception as exc:
            raise InstallError("BACKUP_MODE") from exc
        if mode < 0 or mode > 0o7777:
            raise InstallError("BACKUP_MODE")
        if require_current_preimage and read(path) != value:
            raise InstallError("BACKUP_PREIMAGE_CHANGED:" + str(path))
    return resolved, manifest, manifest_sha256


def backup_only() -> dict:
    folder = backup(target_paths())
    resolved, _manifest, manifest_sha256 = backup_identity(
        folder, require_current_preimage=True
    )
    atomic_json(CERTIFIED, {
        "schema_version": 1,
        "task_id": TASK_ID,
        "backup": str(resolved),
        "backup_manifest_sha256": manifest_sha256,
        "certified_at": now(),
    })
    return {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS", "mode": "BACKUP",
            "backup": str(resolved), "backup_manifest_sha256": manifest_sha256,
            "crm_write": False, "media_write": False}


def certified_backup(
        expected_sha256: str, require_current_preimage: bool = True) -> pathlib.Path:
    if not re.fullmatch(r"[0-9a-f]{64}", str(expected_sha256 or "")):
        raise InstallError("EXPECTED_BACKUP_SHA256")
    try:
        pointer = json.loads((read(CERTIFIED) or b"").decode("utf-8"))
    except Exception as exc:
        raise InstallError("CERTIFIED_BACKUP_POINTER") from exc
    if (pointer.get("schema_version") != 1 or pointer.get("task_id") != TASK_ID
            or pointer.get("backup_manifest_sha256") != expected_sha256):
        raise InstallError("CERTIFIED_BACKUP_IDENTITY")
    folder = pathlib.Path(str(pointer.get("backup") or ""))
    resolved, _manifest, _manifest_sha256 = backup_identity(
        folder, expected_sha256,
        require_current_preimage=require_current_preimage,
    )
    return resolved


def seal_backup(folder: pathlib.Path, expected_sha256: str | None = None) -> str:
    """Bind a successful install's exact post-image to its rollback bundle."""
    resolved, manifest, manifest_sha = backup_identity(folder, expected_sha256)
    expected = {str(path) for path in target_paths()}
    items = manifest.get("files") or []
    postimage = []
    for item in items:
        path = pathlib.Path(str(item["path"]))
        current = read(path) or b""
        postimage.append({
            "path": str(path),
            "installed_sha256": sha(current),
            "installed_mode": stat.S_IMODE(path.stat().st_mode),
        })
    atomic_json(resolved / "postimage.json", {
        "schema_version": 1,
        "task_id": TASK_ID,
        "backup_manifest_sha256": manifest_sha,
        "sealed_at": now(),
        "files": postimage,
    })
    atomic(LATEST, (str(resolved) + "\n").encode(), 0o600)
    return manifest_sha


def restore(
        folder: pathlib.Path, require_installed: bool = False,
        expected_sha256: str | None = None) -> dict:
    resolved, manifest, manifest_sha256 = backup_identity(folder, expected_sha256)
    crm_before = sha(read(DB) or b"")
    restored = []
    allowed = {str(path) for path in target_paths()}
    items = manifest.get("files") or []
    manifest_paths = [str(item.get("path") or "") for item in items]
    if len(manifest_paths) != len(set(manifest_paths)) or set(manifest_paths) != allowed:
        raise InstallError("RESTORE_MANIFEST_SCOPE")
    preimages: dict[pathlib.Path, tuple[bytes, int, str]] = {}
    for item in items:
        path = pathlib.Path(str(item.get("path") or ""))
        if str(path) not in allowed:
            raise InstallError("RESTORE_SCOPE")
        stored = (resolved / str(item["stored"])).resolve()
        if stored.parent != (resolved / "files").resolve():
            raise InstallError("BACKUP_STORED_SCOPE")
        value = gzip.decompress(read(stored) or b"")
        if sha(value) != item.get("sha256"):
            raise InstallError("BACKUP_HASH")
        preimages[path] = (value, int(item["mode"]), str(item["sha256"]))

    current_state = {
        str(path): (sha(read(path) or b""), stat.S_IMODE(path.stat().st_mode))
        for path in preimages
    }
    rollback_allowed_sha256: dict[str, tuple[str, ...]] | None = None
    if require_installed:
        postimage_bytes = read(resolved / "postimage.json", False)
        if postimage_bytes is None:
            # A rollback may be retried after a pre-seal install failure. It is
            # truthful only when nothing remains to restore.
            for path, (_value, preimage_mode, preimage_sha256) in preimages.items():
                if current_state[str(path)] != (preimage_sha256, preimage_mode):
                    raise InstallError("BACKUP_NOT_SEALED")
            rollback_allowed_sha256 = {
                str(path): (preimage_sha256,)
                for path, (_value, _mode, preimage_sha256) in preimages.items()
            }
        else:
            try:
                postimage = json.loads(postimage_bytes.decode("utf-8"))
            except Exception as exc:
                raise InstallError("BACKUP_NOT_SEALED") from exc
            post_items = postimage.get("files") or []
            post_by_path = {
                str(item.get("path") or ""): item
                for item in post_items if isinstance(item, dict)
            }
            if (postimage.get("task_id") != TASK_ID or postimage.get("schema_version") != 1
                    or postimage.get("backup_manifest_sha256") != manifest_sha256
                    or len(post_items) != len(post_by_path) or set(post_by_path) != allowed):
                raise InstallError("BACKUP_NOT_SEALED")
            for path, (_value, _preimage_mode, preimage_sha256) in preimages.items():
                path_text = str(path)
                installed_sha256 = post_by_path[path_text].get("installed_sha256")
                installed_mode = post_by_path[path_text].get("installed_mode")
                if not re.fullmatch(r"[0-9a-f]{64}", str(installed_sha256 or "")):
                    raise InstallError("BACKUP_NOT_SEALED")
                if (type(installed_mode) is not int or installed_mode < 0
                        or installed_mode > 0o7777):
                    raise InstallError("BACKUP_NOT_SEALED")
                # Unknown bytes are a concurrent edit and must never be
                # overwritten. A known image with mode drift is recoverable:
                # the scoped atomic writer restores the certified pre-mode.
                if current_state[path_text][0] not in (installed_sha256, preimage_sha256):
                    raise InstallError("ROLLBACK_CONCURRENT_CHANGE:" + path_text)
            rollback_allowed_sha256 = {
                path_text: (
                    str(post_by_path[path_text]["installed_sha256"]),
                    preimages[pathlib.Path(path_text)][2],
                )
                for path_text in post_by_path
            }

    for path, (value, mode, _preimage_sha256) in preimages.items():
        current_value = read(path) or b""
        if (rollback_allowed_sha256 is not None
                and sha(current_value) not in rollback_allowed_sha256[str(path)]):
            raise InstallError("ROLLBACK_CONCURRENT_CHANGE:" + str(path))
        if current_value != value or stat.S_IMODE(path.stat().st_mode) != mode:
            atomic(path, value, mode)
            restored.append(str(path))
    restored_sha256 = {}
    restored_mode = {}
    for path, (_value, preimage_mode, preimage_sha256) in preimages.items():
        current = sha(read(path) or b"")
        current_mode = stat.S_IMODE(path.stat().st_mode)
        if current != preimage_sha256 or current_mode != preimage_mode:
            raise InstallError("ROLLBACK_READBACK:" + str(path))
        restored_sha256[str(path)] = current
        restored_mode[str(path)] = current_mode
    if sha(read(DB) or b"") != crm_before:
        raise InstallError("CRM_CHANGED")
    return {"status": "PASS", "restored": restored, "backup": str(resolved),
            "backup_manifest_sha256": manifest_sha256,
            "restored_exact": True, "restored_sha256": restored_sha256,
            "restored_mode": restored_mode,
            "crm_unchanged": True, "protected_files_unchanged": True,
            "unexpected_changes": 0}


def without_block(source: str, start: str, end: str) -> str:
    while start in source or end in source:
        left = source.find(start)
        right = source.find(end, max(0, left + len(start)))
        if left >= 0 and right >= 0:
            source = source[:left] + source[right + len(end):]
        else:
            source = source.replace(start, "").replace(end, "")
    return source


def without_style(source: str) -> str:
    return re.sub(r"<style\b[^>]*id=['\"]ua099-additional-spec-style['\"][^>]*>[\s\S]*?</style>", "", source, flags=re.I)


def canonical(source: str) -> str:
    for start, end in ((ADD_START, ADD_END), (CLEAN_START, CLEAN_END), (OLD_START, OLD_END)):
        source = without_block(source, start, end)
    return without_style(source)


def load_spec():
    spec = importlib.util.spec_from_file_location("ua_additional_spec", ROOT / "ua_additional_spec.py")
    if spec is None or spec.loader is None:
        raise InstallError("SPEC_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compact_vin(uid: str, vin: str) -> str:
    import html
    return (CLEAN_START + "<div class='blok ua-clean-vin' data-ua-clean-vin='1' data-ua-card='%s'>"
            "<div class='zag'>VIN</div><div class='ua-vin-value'>%s</div></div>" %
            (html.escape(uid), html.escape(vin)) + CLEAN_END)


def external_hosts(source: str) -> set[str]:
    """Return every statically named external host in public HTML/CSS/JS.

    The policy is deliberately broader than clickable anchors: advertisements
    can also arrive through media attributes, form targets, meta refreshes,
    CSS URLs, or a literal URL consumed by inline JavaScript.
    """
    decoded = html.unescape(str(source or ""))
    candidates: list[str] = []

    attribute = re.compile(
        r"\b(?:href|src|action|formaction)\s*=\s*"
        r"(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
        re.I,
    )
    for match in attribute.finditer(decoded):
        candidates.append(next(value for value in match.groups() if value is not None))

    for tag in re.findall(r"<meta\b[^>]*>", decoded, re.I | re.S):
        content = re.search(
            r"\bcontent\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
            tag,
            re.I,
        )
        if not content:
            continue
        value = next(item for item in content.groups() if item is not None)
        refresh = re.search(r"\burl\s*=\s*([^;\s]+|['\"][^'\"]+['\"])", value, re.I)
        if refresh:
            candidates.append(refresh.group(1).strip("'\""))

    candidates.extend(
        match.group(1).strip().strip("'\"")
        for match in re.finditer(r"\burl\(\s*([^)]*?)\s*\)", decoded, re.I)
    )
    candidates.extend(
        next(value for value in match.groups() if value is not None)
        for match in re.finditer(
            r"@import\s+(?:url\(\s*)?(?:\"([^\"]+)\"|'([^']+)'|([^\s;\)]+))",
            decoded,
            re.I,
        )
    )
    candidates.extend(re.findall(
        r"(?i)(?<![:A-Za-z0-9+.-])(?:(?:https?|ftp|wss?):)?//"
        r"(?:(?:[a-z0-9-]+\.)+[a-z0-9-]{2,63}|"
        r"\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-f:]+\])(?::\d+)?"
        r"(?:[/?#][^\s\"'<>`{}|\\^]*)?",
        decoded,
    ))

    result = set()
    for candidate in candidates:
        value = candidate.strip().rstrip(",.;)}]")
        if value.startswith("//"):
            value = "https:" + value
        host = (urllib.parse.urlsplit(value).hostname or "").casefold().rstrip(".")
        if host:
            result.add(host)
    return result


def transform(source: str, uid: str, vin: str, helper) -> str:
    before = canonical(source)
    cleaned = source
    for start, end in ((ADD_START, ADD_END), (CLEAN_START, CLEAN_END), (OLD_START, OLD_END)):
        cleaned = without_block(cleaned, start, end)
    cleaned = without_style(cleaned)
    block = helper.render_public_block(uid) + compact_vin(uid, vin)
    anchor = "<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->"
    position = cleaned.find(anchor)
    if position < 0:
        raise InstallError("STAGE_ANCHOR:" + uid)
    cleaned = cleaned[:position] + block + cleaned[position:]
    cleaned = re.sub(r"</head>", helper._css() + "</head>", cleaned, count=1, flags=re.I)
    if canonical(cleaned) != before:
        raise InstallError("OUTSIDE_TARGET_CHANGED:" + uid)
    if FORBIDDEN.search(cleaned):
        raise InstallError("VIN_AD_REMAINS:" + uid)
    unknown = external_hosts(cleaned) - APPROVED_HOSTS
    if unknown:
        raise InstallError("UNAPPROVED_EXTERNAL_HOST:" + uid + ":" + ",".join(sorted(unknown)))
    if cleaned.count(ADD_START) != 1 or cleaned.count(CLEAN_START) != 1 or vin not in cleaned:
        raise InstallError("PUBLIC_CONTRACT:" + uid)
    return cleaned


def append_block(source: str, start: str, end: str, block: str) -> str:
    source = re.sub(r"(?:\n|^)" + re.escape(start) + r"[\s\S]*?" + re.escape(end) + r"\s*", "\n", source)
    return source.rstrip() + "\n\n" + block.strip() + "\n"


LEGACY_VIN_RENDERER = r'''def _ua068_vin_block(kod, row):
    """Render VIN as vehicle data only; external VIN offers are forbidden."""
    vin = str((row or {}).get("vin") or "").strip().upper()
    stage = _ua068_stage(row)
    video_count = _ua068_video_count(kod, row)
    return (
        _UA068_VIN_START
        + '<div class="blok ua-clean-vin" data-ua-clean-vin="1" data-ua-card="%s" '
          'data-ua-stage="%d" data-ua-video-count="%d">'
          '<div class="zag">VIN</div><div class="ua-vin-value">%s</div></div>'
          % (_ua068_e(kod), stage, video_count, _ua068_e(vin))
        + _UA068_VIN_END
    )
'''


def _line_offsets(source: str) -> list[int]:
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _top_level_function(source: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise InstallError("SOURCE_SYNTAX:%s" % name) from exc
    matches = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(matches) != 1:
        raise InstallError("FUNCTION_COUNT:%s:%d" % (name, len(matches)))
    return matches[0]


def _replace_function(source: str, name: str, replacement: str) -> str:
    node = _top_level_function(source, name)
    offsets = _line_offsets(source)
    first = min([node.lineno] + [item.lineno for item in node.decorator_list])
    start = offsets[first - 1]
    end = offsets[int(node.end_lineno)]
    return source[:start] + replacement.rstrip() + "\n" + source[end:]


def _patch_legacy_validator(source: str) -> str:
    node = _top_level_function(source, "_ua068_card_errors")
    offsets = _line_offsets(source)
    removable = []
    assignment = None
    positive_tokens = ("ua-vin-v1-button", "_UA068_CARHISTORY_URL", "navigator.clipboard.writeText")
    for statement in node.body:
        fragment = ast.get_source_segment(source, statement) or ""
        if isinstance(statement, ast.If) and any(token in fragment for token in positive_tokens):
            removable.append(statement)
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            if any(isinstance(target, ast.Name) and target.id == "errors" for target in targets):
                assignment = statement
    if assignment is None:
        raise InstallError("VALIDATOR_ERRORS_ASSIGNMENT")
    if len(removable) != 3:
        raise InstallError("LEGACY_POSITIVE_VALIDATORS:%d" % len(removable))
    guard = (
        "    if _ua068_re.search(\n"
        "            r\"carhistory(?:\\.kr)?|проверить\\s+vin|перевірити\\s+vin|2\\s*200\\s*krw\",\n"
        "            source, _ua068_re.I):\n"
        "        errors.append(\"VIN advertisement forbidden\")\n"
    )
    edits: list[tuple[int, int, str]] = [
        (offsets[int(assignment.end_lineno)], offsets[int(assignment.end_lineno)], guard)
    ]
    edits.extend(
        (offsets[item.lineno - 1], offsets[int(item.end_lineno)], "") for item in removable
    )
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def patch_legacy_generator(source: str, filename: str) -> str:
    """Replace the public VIN offer and invert its legacy positive validator."""
    current_validator = ast.get_source_segment(
        source, _top_level_function(source, "_ua068_card_errors")
    ) or ""
    if "VIN advertisement forbidden" not in current_validator:
        source = _replace_function(source, "_ua068_vin_block", LEGACY_VIN_RENDERER)
        source = _patch_legacy_validator(source)
    source = re.sub(
        r"(?m)^(?P<indent>\s*)_UA068_CARHISTORY_URL\s*=\s*[^\n]+$",
        r'\g<indent>_UA068_CARHISTORY_URL = ""  # UA115: external VIN advertising disabled',
        source,
    )
    validate_legacy_generator(source, filename)
    return source


def validate_legacy_generator(source: str, filename: str) -> None:
    compile(source, filename, "exec")
    renderer = ast.get_source_segment(source, _top_level_function(source, "_ua068_vin_block")) or ""
    validator = ast.get_source_segment(source, _top_level_function(source, "_ua068_card_errors")) or ""
    if FORBIDDEN_CTA_SOURCE.search(renderer):
        raise InstallError("GENERATOR_VIN_CTA:" + filename)
    if "ua-clean-vin" not in renderer or "VIN" not in renderer:
        raise InstallError("GENERATOR_VIN_TEXT_MISSING:" + filename)
    if "VIN advertisement forbidden" not in validator:
        raise InstallError("GENERATOR_FORBIDDEN_VALIDATOR_MISSING:" + filename)
    for legacy in ("VIN buttons != 1", "CarHistory target != 1", "VIN copy helper missing"):
        if legacy in validator:
            raise InstallError("GENERATOR_POSITIVE_VALIDATOR_REMAINS:" + filename)
    if FORBIDDEN_CTA_SOURCE.search(source):
        raise InstallError("GENERATOR_CTA_SOURCE_REMAINS:" + filename)


CRM_CARHISTORY_ROW = re.compile(
    r"\n[ \t]*\[\s*InlineKeyboardButton\(\s*"
    r"(?P<quote>['\"])[^'\"]*(?:Проверить\s+VIN|Перевірити\s+VIN|CarHistory)[^'\"]*(?P=quote)\s*,\s*"
    r"url\s*=\s*(?P<urlquote>['\"])[^'\"]*carhistory(?:\.kr)?[^'\"]*(?P=urlquote)\s*\)\s*\]\s*,?",
    re.I,
)


def _remove_vin_cta_nodes(source: str) -> str:
    """Remove the outer statement that adds a VIN-check keyboard action."""
    tree = ast.parse(source)
    offsets = _line_offsets(source)
    candidates = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.If, ast.Expr)) or not hasattr(node, "end_lineno"):
            continue
        fragment = ast.get_source_segment(source, node) or ""
        if ("InlineKeyboardButton" in fragment
                and re.search(r"(?:Проверить|Перевірити)\s+VIN", fragment, re.I)):
            candidates.append(node)
    outermost = []
    for node in sorted(candidates, key=lambda item: (item.lineno, -int(item.end_lineno))):
        if any(parent.lineno <= node.lineno and int(parent.end_lineno) >= int(node.end_lineno)
               for parent in outermost):
            continue
        outermost.append(node)
    for node in sorted(outermost, key=lambda item: item.lineno, reverse=True):
        source = source[:offsets[node.lineno - 1]] + source[offsets[int(node.end_lineno)]:]
    return source


def patch_cars_ui(source: str) -> str:
    """Remove every legacy VIN-check action from CRM/customer-preview keyboards."""
    source, count = CRM_CARHISTORY_ROW.subn("", source)
    if count not in (0, 1):
        raise InstallError("CRM_VIN_CTA_COUNT:%d" % count)
    source = _remove_vin_cta_nodes(source)
    validate_cars_ui(source)
    return source


def validate_cars_ui(source: str) -> None:
    compile(source, "cars_ui.py", "exec")
    if FORBIDDEN_CTA_SOURCE.search(source) or re.search(
            r"InlineKeyboardButton\([\s\S]{0,240}?(?:Проверить|Перевірити)\s+VIN", source, re.I):
        raise InstallError("CRM_VIN_CTA_REMAINS")
    if source.count(WORKER_REGISTRATION) != 1:
        raise InstallError("VIN_AUTOWORKER_REGISTRATION")


def patch_client_ui(source: str) -> str:
    """Remove the customer-bot VIN decoder link, including VIN-in-URL leaks."""
    source = _remove_vin_cta_nodes(source)
    validate_client_ui(source)
    return source


def validate_client_ui(source: str) -> None:
    compile(source, "client_ui.py", "exec")
    if FORBIDDEN_CTA_SOURCE.search(source) or re.search(
            r"InlineKeyboardButton\([\s\S]{0,240}?(?:Проверить|Перевірити)\s+VIN", source, re.I):
        raise InstallError("CLIENT_VIN_CTA_REMAINS")


def validate_publisher(source: str) -> None:
    """Require the final boundary used by every present and future publish."""
    compile(source, "publikaciya.py", "exec")
    if (source.count(PUBLISH_NORMALIZER_START) != 1
            or source.count(PUBLISH_NORMALIZER_END) != 1
            or "_ua111_spec.inject_public_spec(html, kod)" not in source):
        raise InstallError("FINAL_PUBLIC_SPEC_NORMALIZER_MISSING")


def patch_source_files() -> dict[pathlib.Path, bytes]:
    originals = {path: read(path) or b"" for path in SOURCE_PATHS}
    spec_new = append_block(originals[SPEC_RENDERER].decode("utf-8"), PY_START, PY_END, PY_BLOCK)
    service_new = enable_vin_service(originals[VIN_SERVICE].decode("utf-8"))
    compile(spec_new, SPEC_RENDERER.name, "exec")
    compile(service_new, VIN_SERVICE.name, "exec")
    patched: dict[pathlib.Path, bytes] = {
        SPEC_RENDERER: spec_new.encode(),
        VIN_SERVICE: service_new.encode(),
        CRM_UI: patch_cars_ui(originals[CRM_UI].decode("utf-8")).encode(),
        CLIENT_UI: patch_client_ui(originals[CLIENT_UI].decode("utf-8")).encode(),
    }
    for path in LEGACY_GENERATORS:
        patched[path] = patch_legacy_generator(originals[path].decode("utf-8"), path.name).encode()
    return patched


def verify_source_files() -> dict[str, str]:
    hashes = {}
    for path in LEGACY_GENERATORS:
        source = (read(path) or b"").decode("utf-8")
        validate_legacy_generator(source, path.name)
        hashes[str(path)] = sha(source.encode())
    cars_ui = (read(CRM_UI) or b"").decode("utf-8")
    validate_cars_ui(cars_ui)
    hashes[str(CRM_UI)] = sha(cars_ui.encode())
    client_ui = (read(CLIENT_UI) or b"").decode("utf-8")
    validate_client_ui(client_ui)
    hashes[str(CLIENT_UI)] = sha(client_ui.encode())
    publisher = (read(PUBLISHER) or b"").decode("utf-8")
    validate_publisher(publisher)
    hashes[str(PUBLISHER)] = sha(publisher.encode())
    spec = (read(SPEC_RENDERER) or b"").decode("utf-8")
    compile(spec, SPEC_RENDERER.name, "exec")
    if spec.count(PY_START) != 1 or spec.count(PY_END) != 1 or "render_public_block" not in spec:
        raise InstallError("ADDITIONAL_SPEC_GUARD_MISSING")
    hashes[str(SPEC_RENDERER)] = sha(spec.encode())
    service = (read(VIN_SERVICE) or b"").decode("utf-8")
    enable_vin_service(service)
    if WORKER_START in service or WORKER_END in service:
        raise InstallError("VIN_AUTOWORKER_DISABLED")
    hashes[str(VIN_SERVICE)] = sha(service.encode())
    return hashes


PY_BLOCK = r'''
# >>> UA115 NO PUBLIC VIN ADS
_UA115_BASE_INJECT_PUBLIC_SPEC = inject_public_spec
_UA115_APPROVED_HOSTS = {
    "www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "telegram.org",
    "maps.app.goo.gl", "ecomm.one-line.com", "schema.org", "www.w3.org",
}
_UA115_MIN_SPEC_ROWS = 10

def _ua115_external_hosts(source: str) -> set[str]:
    import html as _ua115_html
    import urllib.parse as _ua115_urlparse
    decoded = _ua115_html.unescape(str(source or ""))
    candidates = []
    attribute = re.compile(
        r"\b(?:href|src|action|formaction)\s*=\s*"
        r"(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
        re.I,
    )
    for match in attribute.finditer(decoded):
        candidates.append(next(item for item in match.groups() if item is not None))
    for tag in re.findall(r"<meta\b[^>]*>", decoded, re.I | re.S):
        content = re.search(
            r"\bcontent\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'`=<>]+))",
            tag,
            re.I,
        )
        if content:
            value = next(item for item in content.groups() if item is not None)
            refresh = re.search(r"\burl\s*=\s*([^;\s]+|['\"][^'\"]+['\"])", value, re.I)
            if refresh:
                candidates.append(refresh.group(1).strip("'\""))
    candidates.extend(
        match.group(1).strip().strip("'\"")
        for match in re.finditer(r"\burl\(\s*([^)]*?)\s*\)", decoded, re.I)
    )
    candidates.extend(
        next(item for item in match.groups() if item is not None)
        for match in re.finditer(
            r"@import\s+(?:url\(\s*)?(?:\"([^\"]+)\"|'([^']+)'|([^\s;\)]+))",
            decoded,
            re.I,
        )
    )
    candidates.extend(re.findall(
        r"(?i)(?<![:A-Za-z0-9+.-])(?:(?:https?|ftp|wss?):)?//"
        r"(?:(?:[a-z0-9-]+\.)+[a-z0-9-]{2,63}|"
        r"\d{1,3}(?:\.\d{1,3}){3}|\[[0-9a-f:]+\])(?::\d+)?"
        r"(?:[/?#][^\s\"'<>`{}|\\^]*)?",
        decoded,
    ))
    result = set()
    for candidate in candidates:
        value = candidate.strip().rstrip(",.;)}]")
        if value.startswith("//"):
            value = "https:" + value
        host = (_ua115_urlparse.urlsplit(value).hostname or "").casefold().rstrip(".")
        if host:
            result.add(host)
    return result

def inject_public_spec(source: str, value: Any) -> str:
    output = _UA115_BASE_INJECT_PUBLIC_SPEC(source, value)
    uid = canonical_uid(value)
    if not output or not uid:
        return output
    vin = _car_vin(uid)
    stage = _stage_number(uid)
    videos = len(re.findall(r"<video\b", output, re.I))
    compact = (VIN_START + "<div class='blok ua-clean-vin' data-ua-clean-vin='1' "
               "data-ua-card='%s' data-ua-stage='%d' data-ua-video-count='%d'>"
               "<div class='zag'>VIN</div>"
               "<div class='ua-vin-value'>%s</div></div>" %
               (html.escape(uid), stage, videos, html.escape(vin)) + VIN_END)
    output = re.sub(re.escape(VIN_START) + r"[\s\S]*?" + re.escape(VIN_END), compact, output)
    expected_spec_rows = len(fetch_specs(uid))
    rendered_spec_rows = len(re.findall(
        r"<div\b[^>]*class=['\"][^'\"]*\bua-addspec-row\b[^'\"]*['\"]",
        output, re.I,
    ))
    if (expected_spec_rows < _UA115_MIN_SPEC_ROWS
            or rendered_spec_rows != expected_spec_rows):
        raise RuntimeError(
            "UA115_ADDITIONAL_SPEC_INCOMPLETE:%s:%d:%d" %
            (uid, rendered_spec_rows, expected_spec_rows)
        )
    if output.count(VIN_START) != 1 or output.count(VIN_END) != 1:
        raise RuntimeError("UA115_VIN_BLOCK_COUNT:" + uid)
    if re.search(
            r"carhistory(?:\.kr)?|vindecoderz(?:\.com)?|"
            r"проверить\s+vin|перевірити\s+vin|2\s*200\s*krw",
            output, re.I):
        raise RuntimeError("UA115_PUBLIC_VIN_AD_GUARD:" + uid)
    _ua115_unknown = _ua115_external_hosts(output) - _UA115_APPROVED_HOSTS
    if _ua115_unknown:
        raise RuntimeError("UA115_UNAPPROVED_EXTERNAL_HOST:" + uid + ":" + ",".join(sorted(_ua115_unknown)))
    return output
# <<< UA115 NO PUBLIC VIN ADS
'''


def enable_vin_service(source: str) -> str:
    """Remove only an earlier TASK115 disable override; keep the real worker intact."""
    source = re.sub(
        r"(?:\n|^)" + re.escape(WORKER_START) + r"[\s\S]*?" + re.escape(WORKER_END) + r"\s*",
        "\n", source,
    ).rstrip() + "\n"
    compile(source, VIN_SERVICE.name, "exec")
    worker = ast.get_source_segment(source, _top_level_function(source, "start_worker")) or ""
    if "threading.Thread" not in worker or "_worker.start()" not in worker:
        raise InstallError("VIN_AUTOWORKER_NOT_ACTIVE")
    return source


def verify(rows: dict[str, str]) -> dict:
    result = {}
    helper = load_spec()
    spec_counts = {uid: len(helper.fetch_specs(uid)) for uid in IDS}
    incomplete = [uid for uid, count in spec_counts.items() if count < MIN_SPEC_ROWS]
    if incomplete:
        raise InstallError("ADDITIONAL_SPEC_INCOMPLETE:" + ",".join(incomplete))
    for root in PUBLIC_ROOTS:
        for uid in IDS:
            text = (read(root / (uid + ".html")) or b"").decode("utf-8")
            rendered_rows = len(re.findall(
                r"<div\b[^>]*class=['\"][^'\"]*\bua-addspec-row\b[^'\"]*['\"]",
                text, re.I,
            ))
            unknown_hosts = external_hosts(text) - APPROVED_HOSTS
            if (FORBIDDEN.search(text) or text.count(ADD_START) != 1
                    or text.count(ADD_END) != 1 or text.count(CLEAN_START) != 1
                    or text.count(CLEAN_END) != 1 or rows[uid] not in text
                    or rendered_rows != spec_counts[uid] or unknown_hosts):
                raise InstallError("VERIFY:" + str(root) + ":" + uid)
            result[str(root / (uid + ".html"))] = sha(text.encode())
    return {"status": "PASS", "page_count": len(result), "card_count": len(IDS),
            "ua0009": "PASS", "sha256": result, "source_sha256": verify_source_files(),
            "specification_rows": spec_counts,
            "specification_min_rows": min(spec_counts.values())}


def install(expected_backup_sha256: str) -> dict:
    # Resolve, hash, scope-check, decompress-check, and compare the certified
    # preimage before any source or public page can be written.
    folder = certified_backup(expected_backup_sha256)
    rows = car_rows()
    crm_before = sha(read(DB) or b"")
    writes_started = False
    try:
        patched_sources = patch_source_files()
        changed = []
        for path, value in patched_sources.items():
            if read(path) != value:
                writes_started = True
                atomic(path, value)
                changed.append(str(path))
        helper = load_spec()
        for root in PUBLIC_ROOTS:
            for uid in IDS:
                path = root / (uid + ".html")
                original = (read(path) or b"").decode("utf-8")
                updated = transform(original, uid, rows[uid], helper)
                if updated != original:
                    writes_started = True
                    atomic(path, updated.encode())
                    changed.append(str(path))
        checked = verify(rows)
        if sha(read(DB) or b"") != crm_before:
            raise InstallError("CRM_CHANGED")
        backup_manifest_sha256 = seal_backup(folder, expected_backup_sha256)
        if backup_manifest_sha256 != expected_backup_sha256:
            raise InstallError("INSTALLED_BACKUP_SHA256_MISMATCH")
        return {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "PASS", "mode": "INSTALL",
                "backup": str(folder), "changed": changed, "crm_write": False, "media_write": False,
                "backup_manifest_sha256": backup_manifest_sha256,
                "autoworker_enabled": True, "vin_ad_count": 0,
                "legacy_generators_guarded": len(LEGACY_GENERATORS), "crm_vin_cta_removed": True,
                "client_vin_cta_removed": True,
                **checked}
    except Exception:
        if writes_started:
            restore(folder, expected_sha256=expected_backup_sha256)
        raise


def run(mode: str, expected_backup_sha256: str | None = None) -> dict:
    with open(LOCK, "a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if mode == "install":
            if expected_backup_sha256 is None:
                raise InstallError("EXPECTED_BACKUP_SHA256_REQUIRED")
            return install(expected_backup_sha256)
        if mode == "backup":
            if expected_backup_sha256 is not None:
                raise InstallError("UNEXPECTED_BACKUP_SHA256")
            return backup_only()
        if mode == "verify":
            if expected_backup_sha256 is not None:
                raise InstallError("UNEXPECTED_BACKUP_SHA256")
            value = verify(car_rows())
            return {"task_id": TASK_ID, "contract_id": CONTRACT, "mode": "VERIFY", "crm_write": False,
                    "media_write": False, "autoworker_enabled": True, "vin_ad_count": 0, **value}
        if mode == "rollback":
            if expected_backup_sha256 is None:
                raise InstallError("EXPECTED_BACKUP_SHA256_REQUIRED")
            path = certified_backup(
                expected_backup_sha256, require_current_preimage=False
            )
            return {"task_id": TASK_ID, "contract_id": CONTRACT, "mode": "ROLLBACK",
                    "crm_write": False, "media_write": False,
                    **restore(path, require_installed=True,
                              expected_sha256=expected_backup_sha256)}
        raise InstallError("MODE")


def self_test() -> None:
    fixture = "A" + OLD_START + "AD" + OLD_END + "B"
    assert canonical(fixture) == "AB"
    assert without_block(fixture, OLD_START, OLD_END) == "AB"
    assert FORBIDDEN.search("Перевірити VIN")
    assert FORBIDDEN.search("https://www.vindecoderz.com/EN/check-lookup/VIN")
    assert tuple(path.name for path in LEGACY_GENERATORS) == ("master_card.py", "stranica.py", "yadro.py")
    assert CRM_UI.name == "cars_ui.py"
    assert CLIENT_UI.name == "client_ui.py"
    assert PUBLISHER.name == "publikaciya.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("backup", "install", "verify", "rollback"))
    parser.add_argument("--backup-manifest-sha256")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("TASK115_SELFTEST_PASS")
        return 0
    try:
        value = run(str(args.mode), args.backup_manifest_sha256)
    except Exception as exc:
        value = {"task_id": TASK_ID, "contract_id": CONTRACT, "status": "FAIL", "mode": str(args.mode).upper(),
                 "errors": [type(exc).__name__ + ":" + str(exc)], "finished_at": now()}
    atomic_json(RECEIPT, value)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
