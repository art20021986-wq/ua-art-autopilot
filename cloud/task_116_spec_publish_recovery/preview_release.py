#!/usr/bin/env python3
"""Versioned, preview-only release builder.

Unlike the historical ``opublikovat(..., proba=True)``, this module has no live
path fallback. A release is assembled below an explicitly validated preview
root, read back and validated in full, and only then exposed through the small
``current.json`` pointer.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from urllib.parse import urlsplit

from recovery_core import (
    CONTRACT_ID,
    CONTRACT_VERSION,
    MODE,
    PUBLIC_MIN_VISIBLE_SPEC_ROWS,
    RecoveryGuardError,
    SpecRevision,
    canonical_uid,
    card_identity_errors,
    rendered_spec_pairs,
    resolved_under,
    stable_digest,
    visible_html_evidence,
    vin_sha256,
)


_PRODUCTION_ROOT = Path("/home/Carix")
_RELEASE_ID_RE = re.compile(r"[A-Za-z0-9_.-]{6,80}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_VIN_TOKEN_RE = re.compile(r"(?<![A-Z0-9])[A-HJ-NPR-Z0-9]{17}(?![A-Z0-9])")
_INERT_DOM_TAGS = frozenset({"script", "style", "template", "noscript"})
_VOID_DOM_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


@dataclass(frozen=True)
class _FileState:
    device: int
    inode: int
    size: int
    modified_ns: int
    sha256: str
    data: bytes


@dataclass(frozen=True)
class _DirectoryState:
    device: int
    inode: int
    size: int
    modified_ns: int
    links: int


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_under(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def _validated_preview_root(
    preview_root: str | Path, *, must_exist: bool
) -> Path:
    """Validate a preview root without creating anything.

    Both the lexical path and its resolved destination are checked before the
    first ``mkdir``. Existing symlinks in the path are rejected rather than
    followed, closing the easy alias-to-Production escape.
    """

    raw_text = os.fspath(preview_root)
    if not str(raw_text).strip():
        raise RecoveryGuardError("PREVIEW_ROOT_REQUIRED")
    raw = Path(raw_text).expanduser()
    lexical = Path(os.path.abspath(os.fspath(raw)))
    production = _PRODUCTION_ROOT.resolve(strict=False)
    if _is_under(lexical, _PRODUCTION_ROOT):
        raise RecoveryGuardError("PRODUCTION_PATH_FORBIDDEN", str(lexical))

    current = Path(lexical.anchor)
    parts = lexical.parts[1:] if lexical.is_absolute() else lexical.parts
    for index, part in enumerate(parts):
        current = current / part
        if not os.path.lexists(current):
            break
        info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode):
            raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(current))
        if index < len(parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise RecoveryGuardError("PREVIEW_ROOT_PARENT_NOT_DIRECTORY", str(current))

    resolved = lexical.resolve(strict=False)
    if _is_under(resolved, production):
        raise RecoveryGuardError("PRODUCTION_PATH_FORBIDDEN", str(resolved))
    if must_exist and not resolved.is_dir():
        raise RecoveryGuardError("PREVIEW_ROOT_MISSING", str(resolved))
    if resolved.exists() and not resolved.is_dir():
        raise RecoveryGuardError("PREVIEW_ROOT_NOT_DIRECTORY", str(resolved))
    return resolved


def _directory_state(path: Path, *, missing_code: str) -> _DirectoryState:
    try:
        info = os.lstat(path)
    except FileNotFoundError as exc:
        raise RecoveryGuardError(missing_code, str(path)) from exc
    if stat.S_ISLNK(info.st_mode):
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
    if not stat.S_ISDIR(info.st_mode):
        raise RecoveryGuardError("PREVIEW_DIRECTORY_REQUIRED", str(path))
    return _DirectoryState(
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_nlink,
    )


def _assert_directory_state(path: Path, expected: _DirectoryState) -> None:
    actual = _directory_state(path, missing_code="PREVIEW_DIRECTORY_RACE")
    if actual != expected:
        raise RecoveryGuardError("PREVIEW_DIRECTORY_RACE", str(path))


def _assert_directory_identity(path: Path, expected: _DirectoryState) -> None:
    actual = _directory_state(path, missing_code="PREVIEW_DIRECTORY_RACE")
    if (actual.device, actual.inode) != (expected.device, expected.inode):
        raise RecoveryGuardError("PREVIEW_DIRECTORY_RACE", str(path))


def _read_regular_state(
    path: Path,
    *,
    missing_code: str,
    allow_missing: bool = False,
) -> _FileState | None:
    """Read a regular single-link file while detecting entry replacement."""

    try:
        before = os.lstat(path)
    except FileNotFoundError as exc:
        if allow_missing:
            return None
        raise RecoveryGuardError(missing_code, str(path)) from exc
    if stat.S_ISLNK(before.st_mode):
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
    if not stat.S_ISREG(before.st_mode):
        raise RecoveryGuardError("PREVIEW_REGULAR_FILE_REQUIRED", str(path))
    if before.st_nlink != 1:
        raise RecoveryGuardError("PREVIEW_HARDLINK_FORBIDDEN", str(path))

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path)) from exc
    except OSError as exc:
        raise RecoveryGuardError("PREVIEW_FILE_OPEN_FAILED", str(path)) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path))
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
    finally:
        os.close(descriptor)

    try:
        after = os.lstat(path)
    except FileNotFoundError as exc:
        raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path)) from exc
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_nlink,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_nlink,
    )
    identity_opened = (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
        opened.st_mtime_ns,
        opened.st_nlink,
    )
    if (
        stat.S_ISLNK(after.st_mode)
        or not stat.S_ISREG(after.st_mode)
        or identity_before != identity_opened
        or identity_opened != identity_after
        or len(data) != opened.st_size
    ):
        raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path))
    return _FileState(
        device=opened.st_dev,
        inode=opened.st_ino,
        size=opened.st_size,
        modified_ns=opened.st_mtime_ns,
        sha256=_sha_bytes(data),
        data=data,
    )


def _assert_file_state(path: Path, expected: _FileState | None) -> None:
    actual = _read_regular_state(
        path, missing_code="PREVIEW_PATH_RACE", allow_missing=expected is None
    )
    if actual != expected:
        raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path))


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _fsync_directory(path: Path, expected: _DirectoryState) -> None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (opened.st_dev, opened.st_ino) != (expected.device, expected.inode)
        ):
            raise RecoveryGuardError("PREVIEW_DIRECTORY_RACE", str(path))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write_bytes(
    path: Path,
    data: bytes,
    *,
    expected_previous: _FileState | None,
    parent_state: _DirectoryState,
) -> _FileState:
    """Atomically replace ``path`` only after a same-entry state check."""

    _assert_directory_identity(path.parent, parent_state)
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_state = _read_regular_state(
            temporary, missing_code="PREVIEW_TEMPORARY_MISSING"
        )
        if temporary_state is None or temporary_state.data != data:
            raise RecoveryGuardError("PREVIEW_TEMPORARY_READBACK_MISMATCH")
        _assert_directory_identity(path.parent, parent_state)
        _assert_file_state(path, expected_previous)
        os.replace(temporary, path)
        _fsync_directory(path.parent, parent_state)
        _assert_directory_identity(path.parent, parent_state)
        written = _read_regular_state(path, missing_code="PREVIEW_ATOMIC_WRITE_MISSING")
        if written is None or written.data != data:
            raise RecoveryGuardError("PREVIEW_ATOMIC_WRITE_MISMATCH", str(path))
        return written
    finally:
        if os.path.lexists(temporary):
            info = os.lstat(temporary)
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                raise RecoveryGuardError("PREVIEW_TEMPORARY_PATH_RACE", str(temporary))
            os.unlink(temporary)


def _remove_exact_file(
    path: Path, *, expected: _FileState, parent_state: _DirectoryState
) -> None:
    _assert_directory_identity(path.parent, parent_state)
    _assert_file_state(path, expected)
    os.unlink(path)
    _fsync_directory(path.parent, parent_state)
    _assert_directory_identity(path.parent, parent_state)
    _assert_file_state(path, None)


def _assert_path_absent(path: Path, *, exists_code: str) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
    if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
        raise RecoveryGuardError("PREVIEW_HARDLINK_FORBIDDEN", str(path))
    raise RecoveryGuardError(exists_code, str(path))


def _rollback_pointer(
    pointer_path: Path,
    *,
    previous: _FileState | None,
    installed: _FileState,
    root_state: _DirectoryState,
) -> None:
    """Restore the exact previous pointer bytes, or its exact absence."""

    try:
        if previous is None:
            _remove_exact_file(
                pointer_path, expected=installed, parent_state=root_state
            )
            return
        restored = _atomic_write_bytes(
            pointer_path,
            previous.data,
            expected_previous=installed,
            parent_state=root_state,
        )
        if restored.data != previous.data:
            raise RecoveryGuardError("CURRENT_POINTER_ROLLBACK_MISMATCH")
    except Exception as exc:
        raise RecoveryGuardError(
            "CURRENT_POINTER_ROLLBACK_FAILED", type(exc).__name__
        ) from exc


def _canonical_foundation_manifest(
    value: Mapping[str, str] | None,
) -> dict[str, str]:
    """Normalize caller-supplied hashes; source files are not read or verified."""

    if not isinstance(value, Mapping) or not value:
        raise RecoveryGuardError("PREVIEW_FOUNDATION_BASELINE_REQUIRED")
    result: dict[str, str] = {}
    for raw_path, raw_digest in value.items():
        name = str(raw_path or "").strip().replace("\\", "/")
        candidate = Path(name)
        if (
            not name
            or candidate.is_absolute()
            or name.startswith("/")
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise RecoveryGuardError("INVALID_FOUNDATION_PATH", name)
        digest = str(raw_digest or "").strip().lower()
        if not _SHA256_RE.fullmatch(digest):
            raise RecoveryGuardError("INVALID_FOUNDATION_DIGEST", name)
        if name in result:
            raise RecoveryGuardError("DUPLICATE_FOUNDATION_PATH", name)
        result[name] = digest
    return dict(sorted(result.items()))


def _foundation_binding_payload(
    *,
    release_id: str,
    uid: str,
    vin_hash: str,
    card_row_digest: str,
    spec_revision_id: str,
    spec_digest: str,
    rendered_spec_content_digest: str,
    caller_manifest_digest: str,
) -> dict[str, str]:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "release_id": release_id,
        "target_uid": uid,
        "target_vin_sha256": vin_hash,
        "card_row_digest": card_row_digest,
        "spec_revision_id": spec_revision_id,
        "spec_digest": spec_digest,
        "rendered_spec_content_digest": rendered_spec_content_digest,
        "caller_manifest_digest": caller_manifest_digest,
    }


def _write_new(path: Path, value: str) -> None:
    if not isinstance(value, str):
        raise RecoveryGuardError("PREVIEW_ARTIFACT_TEXT_REQUIRED", str(path))
    payload = value.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    parent_state = _directory_state(
        path.parent, missing_code="PREVIEW_ARTIFACT_PARENT_MISSING"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        # Inspecting through the strict reader supplies a precise symlink or
        # hardlink error when possible; otherwise this is a duplicate path.
        try:
            _read_regular_state(path, missing_code="PREVIEW_ARTIFACT_ALREADY_EXISTS")
        except RecoveryGuardError:
            raise
        raise RecoveryGuardError("PREVIEW_ARTIFACT_ALREADY_EXISTS", str(path)) from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        # The enclosing private staging directory is removed on failure. Do
        # not unlink this pathname here: it may have been replaced in a race.
        raise
    _assert_directory_identity(path.parent, parent_state)
    state = _read_regular_state(path, missing_code="PREVIEW_ARTIFACT_MISSING")
    if state is None or state.data != payload:
        raise RecoveryGuardError("PREVIEW_ARTIFACT_READBACK_MISMATCH", str(path))


def _atomic_json(
    path: Path, value: Mapping[str, Any], *, must_be_absent: bool = False
) -> _FileState:
    path.parent.mkdir(parents=True, exist_ok=True)
    parent_state = _directory_state(path.parent, missing_code="PREVIEW_JSON_PARENT_MISSING")
    previous = _read_regular_state(
        path, missing_code="PREVIEW_JSON_MISSING", allow_missing=True
    )
    if must_be_absent and previous is not None:
        raise RecoveryGuardError("PREVIEW_JSON_ALREADY_EXISTS", str(path))
    return _atomic_write_bytes(
        path,
        _json_bytes(value),
        expected_previous=previous,
        parent_state=parent_state,
    )


def _contains_vin_hash(visible_text: str, expected_hash: str) -> bool:
    for token in _VIN_TOKEN_RE.findall(str(visible_text or "").upper()):
        try:
            if vin_sha256(token) == expected_hash:
                return True
        except RecoveryGuardError:
            continue
    return False


def _diag_identity_errors(
    html: str, *, uid: str, expected_vin_hash: str
) -> tuple[str, ...]:
    try:
        evidence = visible_html_evidence(str(html or ""))
    except RecoveryGuardError as exc:
        return ("DIAG_" + exc.code,)
    errors: list[str] = []
    if evidence.duplicate_security_attributes:
        errors.append(
            "DIAG_DUPLICATE_SECURITY_ATTRIBUTE:"
            + ",".join(evidence.duplicate_security_attributes)
        )
    matching_markers = [value for value in evidence.card_markers if value == uid]
    other_markers = [value for value in evidence.card_markers if value != uid]
    if len(matching_markers) != 1 or other_markers:
        errors.append(
            "DIAG_IDENTITY_MARKER_COUNT:"
            f"{len(matching_markers)}:OTHER:{len(other_markers)}"
        )
    target_text = " ".join(
        text for owner, text in evidence.owned_text_chunks if owner == uid
    )
    if not _contains_vin_hash(target_text, expected_vin_hash):
        errors.append("DIAG_TARGET_VIN_MISSING")
    if "ОТКРЫТЬ ВСЕ АВТОМОБИЛИ" in evidence.visible_text.upper() and not matching_markers:
        errors.append("DIAG_GENERIC_FALLBACK_PAGE")
    return tuple(errors)


def _card_hash_identity_errors(
    html: str,
    *,
    uid: str,
    expected_vin_hash: str,
    expected_spec_rows: int,
    expected_spec_digest: str,
) -> tuple[str, ...]:
    try:
        evidence = visible_html_evidence(str(html or ""))
    except RecoveryGuardError as exc:
        return (exc.code,)
    errors: list[str] = []
    if evidence.duplicate_security_attributes:
        errors.append(
            "HTML_DUPLICATE_SECURITY_ATTRIBUTE:"
            + ",".join(evidence.duplicate_security_attributes)
        )
    matching_markers = [value for value in evidence.card_markers if value == uid]
    other_markers = [value for value in evidence.card_markers if value != uid]
    if len(matching_markers) != 1 or other_markers:
        errors.append(
            f"TARGET_IDENTITY_MARKER_COUNT:{len(matching_markers)}:"
            f"OTHER:{len(other_markers)}"
        )
    target_text = " ".join(
        text for owner, text in evidence.owned_text_chunks if owner == uid
    )
    if not _contains_vin_hash(target_text, expected_vin_hash):
        errors.append("TARGET_VIN_MISSING")
    if evidence.spec_section_count != 1:
        errors.append(f"SPEC_SECTION_COUNT_MISMATCH:{evidence.spec_section_count}:1")
    if evidence.spec_section_owners != (uid,):
        errors.append("SPEC_SECTION_OUTSIDE_TARGET_CARD")
    if evidence.spec_rows_outside_section:
        errors.append(f"SPEC_ROWS_OUTSIDE_SECTION:{evidence.spec_rows_outside_section}")
    if any(owner != uid for owner in evidence.spec_row_owners):
        errors.append("SPEC_ROW_OUTSIDE_TARGET_CARD")
    errors.extend(evidence.spec_row_shape_errors)
    rendered = len(evidence.spec_pairs)
    if rendered != expected_spec_rows:
        errors.append(f"SPEC_ROW_COUNT_MISMATCH:{rendered}:{expected_spec_rows}")
    normalized_digest = expected_spec_digest.lower()
    matching_digests = [
        value for value in evidence.spec_digest_markers if value == normalized_digest
    ]
    other_digests = [
        value for value in evidence.spec_digest_markers if value != normalized_digest
    ]
    if len(matching_digests) != 1 or other_digests:
        errors.append(
            f"SPEC_DIGEST_MARKER_COUNT:{len(matching_digests)}:"
            f"OTHER:{len(other_digests)}"
        )
    if "ОТКРЫТЬ ВСЕ АВТОМОБИЛИ" in evidence.visible_text.upper() and not matching_markers:
        errors.append("GENERIC_FALLBACK_PAGE")
    return tuple(errors)


def _is_exact_local_card_href(href: str, uid: str) -> bool:
    value = str(href or "").strip()
    if not value or "\\" in value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
        return False
    if ".." in PurePosixPath(parsed.path).parts:
        return False
    basename = parsed.path.rsplit("/", 1)[-1]
    return basename.casefold() == f"{uid}.html".casefold()


def _inactive_dom_element(tag: str, attrs: Mapping[str, str | None]) -> bool:
    lowered = {str(name).casefold(): value for name, value in attrs.items()}
    classes = set(str(lowered.get("class") or "").casefold().split())
    normalized_tag = str(tag).casefold()
    if normalized_tag in _INERT_DOM_TAGS:
        return True
    if normalized_tag == "details" and "open" not in lowered:
        return True
    if "hidden" in lowered or "inert" in lowered or "disabled" in lowered:
        return True
    if "disabled" in classes:
        return True
    if str(lowered.get("aria-hidden") or "").strip().casefold() in {"true", "1"}:
        return True
    if str(lowered.get("aria-disabled") or "").strip().casefold() in {"true", "1"}:
        return True
    style = str(lowered.get("style") or "")
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        name = re.sub(r"\s+", "", name).casefold()
        value = re.sub(
            r"\s+|!important", "", value, flags=re.IGNORECASE
        ).casefold()
        if name == "display" and value == "none":
            return True
        if name == "visibility" and value in {"hidden", "collapse"}:
            return True
        if name == "content-visibility" and value == "hidden":
            return True
        if name == "pointer-events" and value == "none":
            return True
        if name == "opacity":
            try:
                if float(value) <= 0.0:
                    return True
            except ValueError:
                pass
    return False


class _ActiveAnchorParser(HTMLParser):
    """Count navigable anchors from the active DOM only."""

    def __init__(self, uid: str) -> None:
        super().__init__(convert_charrefs=True)
        self.uid = uid
        self.count = 0
        self.stack: list[dict[str, Any]] = []
        self.duplicate_security_attributes: list[str] = []

    def _start(
        self,
        tag: str,
        attrs_list: list[tuple[str, str | None]],
        *,
        push: bool,
    ) -> None:
        lowered = str(tag).casefold()
        security_names = {
            "class", "style", "hidden", "inert", "disabled",
            "aria-hidden", "aria-disabled", "open", "href",
        }
        names = [str(name).casefold() for name, _value in attrs_list]
        for name in security_names:
            if names.count(name) > 1:
                self.duplicate_security_attributes.append(lowered + ":" + name)
        attrs = {str(name).casefold(): value for name, value in attrs_list}
        parent_inactive = bool(self.stack and self.stack[-1]["inactive"])
        inactive = parent_inactive or _inactive_dom_element(lowered, attrs)
        if lowered == "a" and not inactive:
            href = attrs.get("href")
            if href is not None and _is_exact_local_card_href(href, self.uid):
                self.count += 1
        if push and lowered not in _VOID_DOM_TAGS:
            self.stack.append({"tag": lowered, "inactive": inactive})

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._start(tag, attrs, push=True)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._start(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        lowered = str(tag).casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == lowered:
                del self.stack[index:]
                return


def _listing_errors(html: str, *, uid: str, role: str) -> tuple[str, ...]:
    parser = _ActiveAnchorParser(uid)
    try:
        parser.feed(str(html or ""))
        parser.close()
    except Exception as exc:
        return (f"{role.upper()}_HTML_PARSE_FAILED:{type(exc).__name__}",)
    if parser.duplicate_security_attributes:
        return (
            f"{role.upper()}_DUPLICATE_SECURITY_ATTRIBUTE:"
            + ",".join(parser.duplicate_security_attributes),
        )
    count = parser.count
    if count != 1:
        return (f"{role.upper()}_TARGET_LINK_COUNT:{uid}:{count}",)
    return ()


def _artifact_texts(
    *,
    uid: str,
    page_html: str,
    diag_html: str,
    catalog_html: str,
    index_html: str,
) -> dict[str, str]:
    return {
        f"video/{uid}.html": page_html,
        f"site/{uid}.html": page_html,
        f"video/{uid}-diag.html": diag_html,
        f"site/{uid}-diag.html": diag_html,
        "video/katalog.html": catalog_html,
        "site/katalog.html": catalog_html,
        "video/index.html": index_html,
        "site/index.html": index_html,
    }


def _expected_artifact_paths(uid: str) -> frozenset[str]:
    return frozenset(
        _artifact_texts(
            uid=uid,
            page_html="",
            diag_html="",
            catalog_html="",
            index_html="",
        )
    )


def _read_json_regular_with_state(
    path: Path, *, missing_code: str
) -> tuple[dict[str, Any], _FileState]:
    state = _read_regular_state(path, missing_code=missing_code)
    if state is None:
        raise RecoveryGuardError(missing_code, str(path))
    try:
        value = json.loads(state.data.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecoveryGuardError("PREVIEW_JSON_INVALID", str(path)) from exc
    if not isinstance(value, dict):
        raise RecoveryGuardError("PREVIEW_JSON_INVALID", str(path))
    return value, state


def _verify_release_directory(
    root: Path,
    release_dir: Path,
    *,
    expected_pointer_digest: str = "",
    require_directory_name: bool = True,
) -> dict[str, Any]:
    root_state = _directory_state(root, missing_code="PREVIEW_ROOT_MISSING")
    if os.path.lexists(release_dir) and stat.S_ISLNK(os.lstat(release_dir).st_mode):
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(release_dir))
    release_dir = resolved_under(root, release_dir)
    release_state = _directory_state(
        release_dir, missing_code="CURRENT_RELEASE_MISSING"
    )

    manifest_path = release_dir / "release.json"
    manifest, manifest_state = _read_json_regular_with_state(
        release_dir / "release.json", missing_code="CURRENT_RELEASE_MISSING"
    )
    if manifest.get("contract_id") != CONTRACT_ID:
        raise RecoveryGuardError("RELEASE_CONTRACT_MISMATCH")
    if manifest.get("contract_version") != CONTRACT_VERSION:
        raise RecoveryGuardError("RELEASE_CONTRACT_VERSION_MISMATCH")
    if manifest.get("mode") != MODE:
        raise RecoveryGuardError("RELEASE_MODE_MISMATCH")
    if manifest.get("production_touched") is not False:
        raise RecoveryGuardError("RELEASE_PRODUCTION_FLAG_INVALID")
    if manifest.get("production_write_attempts") != 0:
        raise RecoveryGuardError("RELEASE_PRODUCTION_WRITES_INVALID")

    recorded_digest = manifest.get("manifest_digest")
    unsigned = dict(manifest)
    unsigned.pop("manifest_digest", None)
    if not isinstance(recorded_digest, str) or recorded_digest != stable_digest(unsigned):
        raise RecoveryGuardError("RELEASE_MANIFEST_TAMPERED")
    if expected_pointer_digest and recorded_digest != expected_pointer_digest:
        raise RecoveryGuardError("CURRENT_RELEASE_DIGEST_MISMATCH")

    release_id = str(manifest.get("release_id") or "")
    if not _RELEASE_ID_RE.fullmatch(release_id) or (
        require_directory_name and release_dir.name != release_id
    ):
        raise RecoveryGuardError("RELEASE_ID_MISMATCH")
    uid = canonical_uid(manifest.get("target_uid"))
    vin_hash = str(manifest.get("target_vin_sha256") or "")
    spec_digest = str(manifest.get("spec_digest") or "")
    spec_content_digest = str(manifest.get("rendered_spec_content_digest") or "")
    if not _SHA256_RE.fullmatch(vin_hash) or not _SHA256_RE.fullmatch(spec_digest):
        raise RecoveryGuardError("RELEASE_IDENTITY_DIGEST_INVALID")
    if not _SHA256_RE.fullmatch(spec_content_digest):
        raise RecoveryGuardError("RELEASE_SPEC_CONTENT_DIGEST_INVALID")
    try:
        spec_rows = int(manifest.get("visible_spec_rows"))
    except (TypeError, ValueError) as exc:
        raise RecoveryGuardError("RELEASE_SPEC_ROWS_INVALID") from exc
    if spec_rows < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
        raise RecoveryGuardError(
            "RELEASE_SPEC_ROWS_INVALID",
            f"{spec_rows}/{PUBLIC_MIN_VISIBLE_SPEC_ROWS}",
        )

    foundation_evidence = manifest.get("foundation_baseline_evidence")
    if not isinstance(foundation_evidence, dict):
        raise RecoveryGuardError("FOUNDATION_BASELINE_EVIDENCE_MISSING")
    if foundation_evidence.get("kind") != "CALLER_SUPPLIED_PATH_SHA256":
        raise RecoveryGuardError("FOUNDATION_BASELINE_KIND_INVALID")
    if foundation_evidence.get("source_files_verified") is not False:
        raise RecoveryGuardError("FOUNDATION_SOURCE_VERIFICATION_CLAIM_INVALID")
    if (
        foundation_evidence.get("source_verification_status")
        != "NOT_PERFORMED_BY_PREVIEW_BUILDER"
    ):
        raise RecoveryGuardError("FOUNDATION_SOURCE_VERIFICATION_CLAIM_INVALID")
    foundation = _canonical_foundation_manifest(
        foundation_evidence.get("path_sha256")
    )
    caller_manifest_digest = str(
        foundation_evidence.get("caller_manifest_digest") or ""
    )
    if caller_manifest_digest != stable_digest(foundation):
        raise RecoveryGuardError("FOUNDATION_MANIFEST_DIGEST_MISMATCH")
    binding_payload = _foundation_binding_payload(
        release_id=release_id,
        uid=uid,
        vin_hash=vin_hash,
        card_row_digest=str(manifest.get("card_row_digest") or ""),
        spec_revision_id=str(manifest.get("spec_revision_id") or ""),
        spec_digest=spec_digest,
        rendered_spec_content_digest=spec_content_digest,
        caller_manifest_digest=caller_manifest_digest,
    )
    if foundation_evidence.get("release_binding_digest") != stable_digest(
        binding_payload
    ):
        raise RecoveryGuardError("FOUNDATION_RELEASE_BINDING_MISMATCH")

    recorded_artifacts = manifest.get("artifacts")
    if not isinstance(recorded_artifacts, dict):
        raise RecoveryGuardError("RELEASE_ARTIFACT_MANIFEST_INVALID")
    expected_paths = _expected_artifact_paths(uid)
    if set(recorded_artifacts) != expected_paths:
        raise RecoveryGuardError("RELEASE_ARTIFACT_SET_MISMATCH")
    if manifest.get("artifact_count") != len(expected_paths):
        raise RecoveryGuardError("RELEASE_ARTIFACT_COUNT_MISMATCH")
    if manifest.get("artifact_set_digest") != stable_digest(recorded_artifacts):
        raise RecoveryGuardError("RELEASE_ARTIFACT_DIGEST_MISMATCH")

    present: set[str] = set()
    paths_by_name: dict[str, Path] = {}
    states_by_name: dict[str, _FileState] = {}
    directory_states: dict[Path, _DirectoryState] = {}
    for path in sorted(release_dir.rglob("*")):
        try:
            info = os.lstat(path)
        except FileNotFoundError as exc:
            raise RecoveryGuardError("PREVIEW_PATH_RACE", str(path)) from exc
        if stat.S_ISLNK(info.st_mode):
            raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
        if stat.S_ISDIR(info.st_mode):
            directory_states[path] = _directory_state(
                path, missing_code="PREVIEW_DIRECTORY_RACE"
            )
            continue
        if not stat.S_ISREG(info.st_mode):
            raise RecoveryGuardError("PREVIEW_REGULAR_FILE_REQUIRED", str(path))
        relative = path.relative_to(release_dir).as_posix()
        if relative == "release.json":
            continue
        present.add(relative)
        paths_by_name[relative] = path
        state = _read_regular_state(path, missing_code="RELEASE_ARTIFACT_MISSING")
        if state is None:
            raise RecoveryGuardError("RELEASE_ARTIFACT_MISSING", relative)
        states_by_name[relative] = state
    if present != expected_paths:
        raise RecoveryGuardError("RELEASE_ARTIFACT_SET_MISMATCH")

    texts: dict[str, str] = {}
    for relative in sorted(expected_paths):
        expected_hash = str(recorded_artifacts.get(relative) or "")
        if not _SHA256_RE.fullmatch(expected_hash):
            raise RecoveryGuardError("RELEASE_ARTIFACT_HASH_INVALID", relative)
        state = states_by_name[relative]
        if state.sha256 != expected_hash:
            raise RecoveryGuardError("RELEASE_ARTIFACT_HASH_MISMATCH", relative)
        try:
            texts[relative] = state.data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecoveryGuardError("RELEASE_ARTIFACT_ENCODING_INVALID", relative) from exc

    page_paths = (f"video/{uid}.html", f"site/{uid}.html")
    diag_paths = (f"video/{uid}-diag.html", f"site/{uid}-diag.html")
    catalog_paths = ("video/katalog.html", "site/katalog.html")
    index_paths = ("video/index.html", "site/index.html")
    for role, paths in (
        ("CARD", page_paths),
        ("DIAG", diag_paths),
        ("CATALOG", catalog_paths),
        ("INDEX", index_paths),
    ):
        if texts[paths[0]] != texts[paths[1]]:
            raise RecoveryGuardError(f"{role}_SITE_VIDEO_DIVERGENCE")

    for path in page_paths:
        errors = _card_hash_identity_errors(
            texts[path],
            uid=uid,
            expected_vin_hash=vin_hash,
            expected_spec_rows=spec_rows,
            expected_spec_digest=spec_digest,
        )
        if errors:
            raise RecoveryGuardError("PREVIEW_CARD_INVALID", f"{path}:" + ";".join(errors))
        if stable_digest(rendered_spec_pairs(texts[path])) != spec_content_digest:
            raise RecoveryGuardError("PREVIEW_SPEC_CONTENT_MISMATCH", path)
    for path in diag_paths:
        errors = _diag_identity_errors(
            texts[path], uid=uid, expected_vin_hash=vin_hash
        )
        if errors:
            raise RecoveryGuardError("PREVIEW_DIAG_INVALID", f"{path}:" + ";".join(errors))
    for path in catalog_paths:
        errors = _listing_errors(texts[path], uid=uid, role="catalog")
        if errors:
            raise RecoveryGuardError("PREVIEW_CATALOG_INVALID", f"{path}:" + ";".join(errors))
    for path in index_paths:
        errors = _listing_errors(texts[path], uid=uid, role="index")
        if errors:
            raise RecoveryGuardError("PREVIEW_INDEX_INVALID", f"{path}:" + ";".join(errors))

    for relative, state in states_by_name.items():
        _assert_file_state(paths_by_name[relative], state)
    _assert_file_state(manifest_path, manifest_state)
    for path, state in directory_states.items():
        _assert_directory_state(path, state)
    _assert_directory_state(release_dir, release_state)
    _assert_directory_state(root, root_state)
    return manifest


def build_preview_release(
    preview_root: str | Path,
    *,
    release_id: str,
    uid: str,
    vin: str,
    spec: SpecRevision,
    page_html: str,
    diag_html: str,
    catalog_html: str,
    index_html: str,
    card_row_digest: str,
    foundation_manifest: Mapping[str, str] | None = None,
    fault: str = "",
) -> dict[str, Any]:
    """Build one preview release from validated, caller-supplied inputs.

    ``foundation_manifest`` is bound into the signed release evidence, but this
    function deliberately does not claim that those hashes were verified
    against a source tree. The caller must produce that separate evidence.
    """
    # This check is deliberately first and performs no writes. A caller cannot
    # make ``/home/Carix`` (or a symlink to it) the target even momentarily.
    root = _validated_preview_root(preview_root, must_exist=False)
    uid = canonical_uid(uid)
    release_id = str(release_id).strip()
    if not _RELEASE_ID_RE.fullmatch(release_id):
        raise RecoveryGuardError("INVALID_RELEASE_ID")
    foundation = _canonical_foundation_manifest(foundation_manifest)
    normalized_vin_hash = vin_sha256(vin)
    if spec.uid != uid or spec.vin_sha256 != normalized_vin_hash or spec.status != "ACTIVE":
        raise RecoveryGuardError("SPEC_RELEASE_BINDING_MISMATCH")

    errors = card_identity_errors(
        page_html,
        uid=uid,
        vin=vin,
        expected_spec_rows=spec.visible_count,
        expected_spec_digest=spec.digest,
        expected_spec=spec,
    )
    if errors:
        raise RecoveryGuardError("PREVIEW_CARD_INVALID", ";".join(errors))
    errors = _diag_identity_errors(
        diag_html, uid=uid, expected_vin_hash=normalized_vin_hash
    )
    if errors:
        raise RecoveryGuardError("PREVIEW_DIAG_INVALID", ";".join(errors))
    errors = _listing_errors(catalog_html, uid=uid, role="catalog")
    if errors:
        raise RecoveryGuardError("PREVIEW_CATALOG_INVALID", ";".join(errors))
    errors = _listing_errors(index_html, uid=uid, role="index")
    if errors:
        raise RecoveryGuardError("PREVIEW_INDEX_INVALID", ";".join(errors))

    normalized_card_row_digest = str(card_row_digest)
    rendered_content_digest = stable_digest(rendered_spec_pairs(page_html))
    caller_foundation_digest = stable_digest(foundation)
    foundation_binding = _foundation_binding_payload(
        release_id=release_id,
        uid=uid,
        vin_hash=normalized_vin_hash,
        card_row_digest=normalized_card_row_digest,
        spec_revision_id=spec.revision_id,
        spec_digest=spec.digest,
        rendered_spec_content_digest=rendered_content_digest,
        caller_manifest_digest=caller_foundation_digest,
    )

    # No directories are created before all fail-closed path and input checks.
    root.mkdir(parents=True, exist_ok=True)
    root = _validated_preview_root(root, must_exist=True)
    root_state = _directory_state(root, missing_code="PREVIEW_ROOT_MISSING")
    releases = root / "releases"
    if os.path.lexists(releases) and stat.S_ISLNK(os.lstat(releases).st_mode):
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(releases))
    releases = resolved_under(root, releases)
    releases.mkdir(exist_ok=True)
    releases_state = _directory_state(
        releases, missing_code="PREVIEW_RELEASES_DIRECTORY_MISSING"
    )
    # Creating ``releases`` may legitimately change the root mtime. Capture the
    # stable identity/state used by the pointer compare-and-swap afterwards.
    root_state = _directory_state(root, missing_code="PREVIEW_ROOT_MISSING")
    pointer_path = root / "current.json"
    previous_pointer = _read_regular_state(
        pointer_path, missing_code="CURRENT_POINTER_MISSING", allow_missing=True
    )
    target = releases / release_id
    _assert_path_absent(target, exists_code="RELEASE_ID_EXISTS")
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=str(releases)))
    artifacts = _artifact_texts(
        uid=uid,
        page_html=page_html,
        diag_html=diag_html,
        catalog_html=catalog_html,
        index_html=index_html,
    )
    try:
        hashes: dict[str, str] = {}
        for relative, text in artifacts.items():
            destination = resolved_under(root, staging / relative)
            _write_new(destination, text)
            hashes[relative] = _sha_bytes(destination.read_bytes())
        manifest: dict[str, Any] = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "mode": MODE,
            "release_id": release_id,
            "target_uid": uid,
            "target_vin_sha256": normalized_vin_hash,
            "card_row_digest": normalized_card_row_digest,
            "spec_revision_id": spec.revision_id,
            "spec_digest": spec.digest,
            "visible_spec_rows": spec.visible_count,
            "rendered_spec_content_digest": rendered_content_digest,
            "foundation_baseline_evidence": {
                "kind": "CALLER_SUPPLIED_PATH_SHA256",
                "source_files_verified": False,
                "source_verification_status": "NOT_PERFORMED_BY_PREVIEW_BUILDER",
                "path_sha256": foundation,
                "caller_manifest_digest": caller_foundation_digest,
                "release_binding_digest": stable_digest(foundation_binding),
            },
            "artifacts": hashes,
            "artifact_count": len(hashes),
            "artifact_set_digest": stable_digest(hashes),
            "release_artifacts_readback_verified_before_pointer": True,
            "production_touched": False,
            "production_write_attempts": 0,
        }
        manifest["manifest_digest"] = stable_digest(manifest)
        _atomic_json(staging / "release.json", manifest, must_be_absent=True)
        # Verify the bytes that were actually written, including both site and
        # video copies, before a release directory or pointer can become live.
        _verify_release_directory(root, staging, require_directory_name=False)
        if fault == "before_release_move":
            raise RuntimeError("INJECTED_BEFORE_RELEASE_MOVE")
        staging_state = _directory_state(
            staging, missing_code="PREVIEW_STAGING_DIRECTORY_MISSING"
        )
        _assert_directory_identity(root, root_state)
        _assert_directory_identity(releases, releases_state)
        _assert_path_absent(target, exists_code="RELEASE_ID_RACE")
        os.replace(staging, target)
        _fsync_directory(releases, releases_state)
        _assert_directory_identity(releases, releases_state)
        target_state = _directory_state(
            target, missing_code="PREVIEW_RELEASE_MOVE_MISSING"
        )
        if (target_state.device, target_state.inode) != (
            staging_state.device,
            staging_state.inode,
        ):
            raise RecoveryGuardError("PREVIEW_RELEASE_MOVE_RACE", str(target))
        _verify_release_directory(root, target)
        if fault == "before_pointer":
            raise RuntimeError("INJECTED_BEFORE_POINTER")
        pointer = {
            "release_id": release_id,
            "manifest_digest": manifest["manifest_digest"],
            "mode": MODE,
        }
        installed_pointer = _atomic_write_bytes(
            pointer_path,
            _json_bytes(pointer),
            expected_previous=previous_pointer,
            parent_state=root_state,
        )
        try:
            if fault == "after_pointer_write":
                raise RuntimeError("INJECTED_AFTER_POINTER_WRITE")
            # Return only after the pointer and every referenced artifact have
            # been read back under the strict verifier used on future reads.
            current = current_release(root)
            if current is None:
                raise RecoveryGuardError("CURRENT_RELEASE_MISSING")
            return current
        except Exception as readback_error:
            try:
                _rollback_pointer(
                    pointer_path,
                    previous=previous_pointer,
                    installed=installed_pointer,
                    root_state=root_state,
                )
            except Exception as rollback_error:
                raise rollback_error from readback_error
            raise
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        # A fully validated release may remain after an injected crash between
        # directory move and pointer switch. It is not current and is safe to
        # inspect or garbage-collect later.
        raise


def current_release(preview_root: str | Path) -> dict[str, Any] | None:
    root = _validated_preview_root(preview_root, must_exist=True)
    root_state = _directory_state(root, missing_code="PREVIEW_ROOT_MISSING")
    pointer_path = root / "current.json"
    if not os.path.lexists(pointer_path):
        _assert_directory_state(root, root_state)
        if os.path.lexists(pointer_path):
            raise RecoveryGuardError("PREVIEW_PATH_RACE", str(pointer_path))
        return None
    pointer, pointer_state = _read_json_regular_with_state(
        pointer_path, missing_code="CURRENT_POINTER_MISSING"
    )
    if pointer.get("mode") != MODE:
        raise RecoveryGuardError("CURRENT_POINTER_MODE_MISMATCH")
    release_id = str(pointer.get("release_id") or "")
    if not _RELEASE_ID_RE.fullmatch(release_id):
        raise RecoveryGuardError("CURRENT_RELEASE_ID_INVALID")
    pointer_digest = str(pointer.get("manifest_digest") or "")
    if not _SHA256_RE.fullmatch(pointer_digest):
        raise RecoveryGuardError("CURRENT_RELEASE_DIGEST_INVALID")
    releases = root / "releases"
    releases_state = _directory_state(
        releases, missing_code="CURRENT_RELEASES_DIRECTORY_MISSING"
    )
    release = releases / release_id
    result = _verify_release_directory(
        root, release, expected_pointer_digest=pointer_digest
    )
    _assert_file_state(pointer_path, pointer_state)
    _assert_directory_state(releases, releases_state)
    _assert_directory_state(root, root_state)
    return result
