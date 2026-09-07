#!/usr/bin/env python3
"""Fail-closed wrapper around the legacy Production publisher.

This module is a *candidate* Production adapter.  Merely importing it cannot
publish anything.  A call is accepted only when ``allow_production``, a fresh
target/root/build-bound full Gate B receipt, and the exact owner command are
all supplied.  The injected legacy adapter receives the canonical roots and is
then executed while an advisory ``flock`` is held and while every HTML file
below both roots is covered by a byte-for-byte rollback snapshot.

The historical ``proba=True`` path is intentionally unavailable: that mode
writes into the live tree before attempting to restore it.  Preview releases
must use :mod:`preview_release` instead.
"""
from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import inspect
import marshal
import os
import re
import stat
import tempfile
import types
import unicodedata
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator, Mapping, Sequence
from urllib.parse import urlsplit

from recovery_core import (
    BASE_SHA,
    CONTRACT_ID,
    CONTRACT_VERSION,
    PUBLIC_MIN_VISIBLE_SPEC_ROWS,
    RecoveryGuardError,
    SpecRevision,
    assert_spec_revision_integrity,
    canonical_uid,
    card_identity_errors,
    stable_digest,
    vin_sha256,
)


PRODUCTION_MODE = "PRODUCTION_EXPLICIT_OWNER_GATE"
_DASHES_RE = re.compile(r"[\u2010-\u2015\u2212\ufe58\ufe63\uff0d]")
CATALOG_PATH = "katalog.html"
INDEX_PATH = "index.html"
MINIMUM_LISTING_SIZE_RATIO = 0.85
ALLOWED_LEGACY_KWARGS = frozenset()
ADAPTER_SIDE_EFFECT_SCOPE = "EXACT_HTML_ARTIFACTS_IN_TWO_BOUND_ROOTS_ONLY"


@dataclasses.dataclass(frozen=True)
class HtmlSnapshotEntry:
    """One rollback unit.

    Contents are retained only in memory.  Receipts expose digests, never the
    bytes themselves.
    """

    content: bytes
    mode: int
    sha256: str


def publisher_code_object_sha256(publisher: Callable[..., Any]) -> str:
    code = getattr(publisher, "__code__", None)
    if code is None:
        raise RecoveryGuardError("PUBLISHER_PYTHON_CODE_REQUIRED")
    return hashlib.sha256(marshal.dumps(code)).hexdigest()


@dataclasses.dataclass(frozen=True)
class TrustedLegacyPublisher:
    """Explicit adapter boundary; this is not an OS process sandbox.

    The trusted controller must review this adapter and bind the digest of its
    installed artifact in Gate B; the code-object digest is only supplemental
    evidence and does not cover globals/defaults/closures.  The callable
    contract is ``publisher(uid, ua116_site_roots=...)``
    and permits writes only to the four canonical HTML artifacts in each root.
    Out-of-root enforcement requires an external process sandbox and therefore
    remains a blocker before this candidate may be called in Production.
    """

    adapter_id: str
    publisher: Callable[..., Any]
    adapter_artifact_sha256: str
    code_object_sha256: str
    side_effect_scope: str = ADAPTER_SIDE_EFFECT_SCOPE

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{6,80}", self.adapter_id):
            raise RecoveryGuardError("PUBLISHER_ADAPTER_ID_INVALID")
        if self.side_effect_scope != ADAPTER_SIDE_EFFECT_SCOPE:
            raise RecoveryGuardError("PUBLISHER_SCOPE_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", self.adapter_artifact_sha256):
            raise RecoveryGuardError("PUBLISHER_ARTIFACT_DIGEST_INVALID")
        actual = publisher_code_object_sha256(self.publisher)
        if self.code_object_sha256 != actual:
            raise RecoveryGuardError("PUBLISHER_CODE_OBJECT_DIGEST_MISMATCH")


def trusted_legacy_publisher(
    adapter_id: str,
    publisher: Callable[..., Any],
    *,
    adapter_artifact_sha256: str,
) -> TrustedLegacyPublisher:
    return TrustedLegacyPublisher(
        adapter_id=str(adapter_id),
        publisher=publisher,
        adapter_artifact_sha256=str(adapter_artifact_sha256),
        code_object_sha256=publisher_code_object_sha256(publisher),
    )


@dataclasses.dataclass(frozen=True)
class AtomicPublishReceipt:
    contract_id: str
    contract_version: str
    mode: str
    outcome: str
    target_uid: str
    target_vin_sha256: str
    spec_revision_id: str
    spec_digest: str
    visible_spec_rows: int
    changed_html: tuple[str, ...]
    roots_before_digest: str
    roots_after_digest: str
    lock_path: str
    gate_b_evidence_digest: str
    gate_nonce: str
    publisher_adapter_id: str
    publisher_artifact_sha256: str
    publisher_code_object_sha256: str
    rendered_facts_digest: str
    site_root_fingerprints: tuple[Mapping[str, Any], ...]
    production_write_attempts: int = 1
    rolled_back: bool = False

    @property
    def receipt_digest(self) -> str:
        return stable_digest(dataclasses.asdict(self))

    def as_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["receipt_digest"] = self.receipt_digest
        return result


def _owner_command(value: Any) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    normalized = _DASHES_RE.sub("-", normalized)
    return re.sub(r"\s+", " ", normalized)


def required_owner_command(uid: Any) -> str:
    return f"ПУБЛИКОВАТЬ {canonical_uid(uid)}"


def _require_owner_gate(*, uid: str, allow_production: bool, owner_command: Any) -> None:
    if allow_production is not True:
        raise RecoveryGuardError("PRODUCTION_EXPLICIT_ALLOW_REQUIRED", uid)
    expected = required_owner_command(uid)
    if _owner_command(owner_command) != expected:
        raise RecoveryGuardError("OWNER_PUBLISH_COMMAND_REQUIRED", expected)


def _require_gate_b(
    receipt: Mapping[str, Any] | None,
    *,
    verify_gate_b: Callable[[Mapping[str, Any]], bool],
    uid: str,
    vin: Any,
    spec: SpecRevision,
    publisher: TrustedLegacyPublisher,
    legacy_kwargs: Mapping[str, Any],
    roots_before_digest: str,
    site_root_fingerprints: Sequence[Mapping[str, Any]],
    now: dt.datetime | None = None,
) -> str:
    """Accept only a digest-valid, target-bound full Gate B receipt.

    ``B_LOCAL_SANDBOX`` is useful development evidence but deliberately cannot
    unlock Production.  The deploy workflow must issue a full ``gate == B``
    receipt after its fresh-source, isolated-root checks.
    """

    if not isinstance(receipt, Mapping):
        raise RecoveryGuardError("FULL_GATE_B_RECEIPT_REQUIRED")
    if not callable(verify_gate_b):
        raise RecoveryGuardError("TRUSTED_GATE_B_VERIFIER_REQUIRED")
    authenticated = types.MappingProxyType(dict(receipt))
    try:
        verified = verify_gate_b(authenticated)
    except Exception as exc:
        raise RecoveryGuardError("TRUSTED_GATE_B_VERIFIER_FAILED") from exc
    if verified is not True:
        raise RecoveryGuardError("GATE_B_NOT_AUTHENTICATED")
    value = dict(receipt)
    recorded = str(value.pop("evidence_digest", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", recorded) or recorded != stable_digest(value):
        raise RecoveryGuardError("GATE_B_EVIDENCE_DIGEST_INVALID")
    expected = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "gate": "B",
        "status": "PASS",
        "production_touched": False,
        "production_write_attempts": 0,
        "target_uid": uid,
        "target_vin_sha256": vin_sha256(vin),
        "spec_digest": spec.digest,
        "spec_revision_id": spec.revision_id,
        "base_sha": BASE_SHA,
        "atomic_publish_code_sha256": atomic_publish_code_sha256(),
        "roots_before_digest": roots_before_digest,
        "site_root_fingerprints": list(site_root_fingerprints),
        "publisher_adapter_id": publisher.adapter_id,
        "publisher_artifact_sha256": publisher.adapter_artifact_sha256,
        "publisher_code_object_sha256": publisher.code_object_sha256,
        "publisher_side_effect_scope": publisher.side_effect_scope,
        "legacy_kwargs": dict(legacy_kwargs),
    }
    mismatches = [
        key for key, expected_value in expected.items() if value.get(key) != expected_value
    ]
    if mismatches:
        raise RecoveryGuardError("GATE_B_RECEIPT_MISMATCH", ",".join(mismatches))
    nonce = str(value.get("nonce") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{16,128}", nonce):
        raise RecoveryGuardError("GATE_B_NONCE_INVALID")
    try:
        issued = dt.datetime.fromisoformat(
            str(value.get("issued_at") or "").replace("Z", "+00:00")
        )
        expires = dt.datetime.fromisoformat(
            str(value.get("expires_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RecoveryGuardError("GATE_B_TIME_INVALID") from exc
    if issued.tzinfo is None or expires.tzinfo is None:
        raise RecoveryGuardError("GATE_B_TIME_INVALID")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    current = current.astimezone(dt.timezone.utc)
    issued = issued.astimezone(dt.timezone.utc)
    expires = expires.astimezone(dt.timezone.utc)
    age = (current - issued).total_seconds()
    if (
        age < -5
        or age > 600
        or expires <= current
        or expires > issued + dt.timedelta(minutes=30)
    ):
        raise RecoveryGuardError("GATE_B_RECEIPT_EXPIRED_OR_FUTURE")
    return recorded


def atomic_publish_code_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _safe_relative_html(value: str) -> str:
    raw = str(value or "").replace("\\", "/")
    path = PurePosixPath(raw)
    if (
        not raw
        or path.is_absolute()
        or ".." in path.parts
        or path.suffix.lower() != ".html"
        or str(path) != raw
    ):
        raise RecoveryGuardError("INVALID_HTML_RELATIVE_PATH", raw)
    return raw


def _validate_roots(site_roots: Sequence[str | Path]) -> tuple[Path, Path]:
    if len(site_roots) != 2:
        raise RecoveryGuardError("TWO_SITE_ROOTS_REQUIRED", str(len(site_roots)))
    roots: list[Path] = []
    for raw in site_roots:
        supplied = Path(raw)
        if supplied.is_symlink():
            raise RecoveryGuardError("SITE_ROOT_SYMLINK_FORBIDDEN", str(supplied))
        root = supplied.resolve(strict=True)
        if not root.is_dir():
            raise RecoveryGuardError("SITE_ROOT_NOT_DIRECTORY", str(root))
        roots.append(root)
    if roots[0] == roots[1]:
        raise RecoveryGuardError("SITE_ROOTS_NOT_DISTINCT", str(roots[0]))
    if roots[0] in roots[1].parents or roots[1] in roots[0].parents:
        raise RecoveryGuardError("SITE_ROOTS_OVERLAP")
    return roots[0], roots[1]


def _site_root_fingerprints(roots: Sequence[Path]) -> tuple[Mapping[str, Any], ...]:
    result: list[Mapping[str, Any]] = []
    for root in roots:
        metadata = root.stat()
        result.append(
            {
                "path": str(root),
                "device": int(metadata.st_dev),
                "inode": int(metadata.st_ino),
            }
        )
    return tuple(result)


def _assert_root_fingerprints(
    roots: Sequence[Path], expected: Sequence[Mapping[str, Any]]
) -> None:
    if any(root.is_symlink() for root in roots):
        raise RecoveryGuardError("SITE_ROOT_REPLACED")
    if tuple(_site_root_fingerprints(roots)) != tuple(expected):
        raise RecoveryGuardError("SITE_ROOT_REPLACED")


def canonical_publish_lock(site_roots: Sequence[str | Path]) -> Path:
    """Return the sole lock name for this exact pair of directory inodes."""

    roots = _validate_roots(site_roots)
    fingerprints = sorted(_site_root_fingerprints(roots), key=lambda item: str(item["path"]))
    identity = stable_digest(fingerprints)[:24]
    return Path("/tmp").resolve(strict=True) / f"ua116-publish-{identity}.lock"


def _path_below(root: Path, relative: str) -> Path:
    relative = _safe_relative_html(relative)
    path = root.joinpath(*PurePosixPath(relative).parts)
    resolved_parent = path.parent.resolve(strict=False)
    try:
        resolved_parent.relative_to(root)
    except ValueError as exc:
        raise RecoveryGuardError("HTML_PATH_ESCAPES_ROOT", str(path)) from exc
    if path.is_symlink():
        raise RecoveryGuardError("HTML_SYMLINK_FORBIDDEN", str(path))
    return path


def _snapshot_root(root: Path) -> dict[str, HtmlSnapshotEntry]:
    result: dict[str, HtmlSnapshotEntry] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            # A linked directory could conceal HTML outside the rollback set.
            # Non-HTML file links do not affect the HTML foundation, but linked
            # directories and linked HTML files make the snapshot ambiguous.
            if path.suffix.lower() == ".html" or path.is_dir():
                relative = path.relative_to(root).as_posix()
                raise RecoveryGuardError("HTML_SYMLINK_FORBIDDEN", f"{root}:{relative}")
            continue
        if path.suffix.lower() != ".html":
            continue
        relative = path.relative_to(root).as_posix()
        try:
            metadata = path.stat()
        except FileNotFoundError as exc:
            raise RecoveryGuardError("HTML_SNAPSHOT_RACE", f"{root}:{relative}") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise RecoveryGuardError("HTML_NOT_REGULAR_FILE", f"{root}:{relative}")
        if metadata.st_nlink != 1:
            raise RecoveryGuardError("HTML_HARDLINK_FORBIDDEN", f"{root}:{relative}")
        content = path.read_bytes()
        # A writer replacing the file between stat/read is detected wherever
        # the platform exposes stable inode/mtime metadata.
        try:
            after = path.stat()
        except FileNotFoundError as exc:
            raise RecoveryGuardError("HTML_SNAPSHOT_RACE", f"{root}:{relative}") from exc
        if (
            metadata.st_ino != after.st_ino
            or metadata.st_size != after.st_size
            or metadata.st_mtime_ns != after.st_mtime_ns
        ):
            raise RecoveryGuardError("HTML_SNAPSHOT_RACE", f"{root}:{relative}")
        result[relative] = HtmlSnapshotEntry(
            content=content,
            mode=stat.S_IMODE(metadata.st_mode),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    return result


def _snapshot_roots(roots: Sequence[Path]) -> tuple[dict[str, HtmlSnapshotEntry], ...]:
    return tuple(_snapshot_root(root) for root in roots)


def _manifest(snapshot: Mapping[str, HtmlSnapshotEntry]) -> dict[str, Mapping[str, Any]]:
    return {
        relative: {"sha256": value.sha256, "mode": value.mode}
        for relative, value in sorted(snapshot.items())
    }


def _roots_digest(snapshots: Sequence[Mapping[str, HtmlSnapshotEntry]]) -> str:
    return stable_digest(
        {str(index): _manifest(snapshot) for index, snapshot in enumerate(snapshots)}
    )


def _changed_paths(
    before: Mapping[str, HtmlSnapshotEntry],
    after: Mapping[str, HtmlSnapshotEntry],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            relative
            for relative in set(before) | set(after)
            if before.get(relative) != after.get(relative)
        )
    )


def _same_snapshots(
    left: Sequence[Mapping[str, HtmlSnapshotEntry]],
    right: Sequence[Mapping[str, HtmlSnapshotEntry]],
) -> bool:
    return tuple(left) == tuple(right)


def _atomic_restore_file(path: Path, entry: HtmlSnapshotEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise RecoveryGuardError("ROLLBACK_SYMLINK_CONFLICT", str(path))
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.ua116-rollback-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(entry.content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, entry.mode)
        os.replace(temporary, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        except OSError:
            directory_fd = -1
        if directory_fd >= 0:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _assert_path_matches_entry(
    path: Path, expected: HtmlSnapshotEntry | None
) -> None:
    if expected is None:
        if path.exists() or path.is_symlink():
            raise RecoveryGuardError("ROLLBACK_CONCURRENT_CHANGE_DETECTED", str(path))
        return
    if path.is_symlink() or not path.is_file():
        raise RecoveryGuardError("ROLLBACK_CONCURRENT_CHANGE_DETECTED", str(path))
    metadata = path.stat()
    content = path.read_bytes()
    if (
        hashlib.sha256(content).hexdigest() != expected.sha256
        or stat.S_IMODE(metadata.st_mode) != expected.mode
    ):
        raise RecoveryGuardError("ROLLBACK_CONCURRENT_CHANGE_DETECTED", str(path))


def _restore_snapshots(
    roots: Sequence[Path],
    before: Sequence[Mapping[str, HtmlSnapshotEntry]],
    captured_after: Sequence[Mapping[str, HtmlSnapshotEntry]],
) -> None:
    """Restore only if the tree still equals the captured post-publish state.

    This is the filesystem equivalent of an empty-only/CAS write.  It avoids
    overwriting a concurrent writer that does not cooperate with our flock.
    Cooperative publishers serialize on the lock and cannot reach this race.
    """

    current = _snapshot_roots(roots)
    if not _same_snapshots(current, captured_after):
        raise RecoveryGuardError("ROLLBACK_CONCURRENT_CHANGE_DETECTED")

    for root, old, new in zip(roots, before, captured_after):
        changed = _changed_paths(old, new)
        # Restore previously existing files first via atomic replace.
        for relative in changed:
            entry = old.get(relative)
            if entry is not None:
                path = _path_below(root, relative)
                _assert_path_matches_entry(path, new.get(relative))
                _atomic_restore_file(path, entry)
        # Files created by the failed publication did not exist before.
        for relative in changed:
            if relative in old:
                continue
            path = _path_below(root, relative)
            _assert_path_matches_entry(path, new.get(relative))
            path.unlink()

    restored = _snapshot_roots(roots)
    if not _same_snapshots(restored, before):
        raise RecoveryGuardError("ROLLBACK_VERIFICATION_FAILED")


@dataclasses.dataclass(frozen=True)
class _ArtifactState:
    kind: str
    device: int = 0
    inode: int = 0
    mode: int = 0
    size: int = 0
    mtime_ns: int = 0
    digest: str = ""


def _capture_artifact_state(path: Path) -> _ArtifactState:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return _ArtifactState("missing")
    common = {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
        "mode": stat.S_IMODE(metadata.st_mode),
        "size": int(metadata.st_size),
        "mtime_ns": int(metadata.st_mtime_ns),
    }
    if stat.S_ISLNK(metadata.st_mode):
        return _ArtifactState(
            "symlink",
            digest=hashlib.sha256(os.readlink(path).encode("utf-8")).hexdigest(),
            **common,
        )
    if stat.S_ISREG(metadata.st_mode):
        content = path.read_bytes()
        after = path.lstat()
        if (
            metadata.st_ino != after.st_ino
            or metadata.st_size != after.st_size
            or metadata.st_mtime_ns != after.st_mtime_ns
        ):
            raise RecoveryGuardError("BOUNDED_ROLLBACK_CAPTURE_RACE", str(path))
        kind = "regular" if metadata.st_nlink == 1 else "hardlink"
        return _ArtifactState(
            kind, digest=hashlib.sha256(content).hexdigest(), **common
        )
    return _ArtifactState("other", **common)


def _bounded_allowed_rollback(
    roots: Sequence[Path],
    before: Sequence[Mapping[str, HtmlSnapshotEntry]],
    allowed: Sequence[str],
    root_fingerprints: Sequence[Mapping[str, Any]],
) -> None:
    """Rollback only four known artifacts when a full post snapshot is unsafe."""

    _assert_root_fingerprints(roots, root_fingerprints)
    paths = [
        (root_index, relative, root / relative)
        for root_index, root in enumerate(roots)
        for relative in allowed
    ]
    captured = {
        (root_index, relative): _capture_artifact_state(path)
        for root_index, relative, path in paths
    }
    # Preflight every operation before the first mutation.  A second read is a
    # bounded CAS check against a non-cooperating writer.
    for root_index, relative, path in paths:
        if _capture_artifact_state(path) != captured[(root_index, relative)]:
            raise RecoveryGuardError("BOUNDED_ROLLBACK_CONCURRENT_CHANGE", str(path))
    for root_index, relative, path in paths:
        old = before[root_index].get(relative)
        state = captured[(root_index, relative)]
        if old is None:
            if state.kind == "missing":
                continue
            if state.kind == "other" and path.is_dir():
                raise RecoveryGuardError("BOUNDED_ROLLBACK_DIRECTORY_CONFLICT", str(path))
            path.unlink()
            continue
        if (
            state.kind == "regular"
            and state.digest == old.sha256
            and state.mode == old.mode
        ):
            continue
        if state.kind in {"symlink", "hardlink", "other"}:
            if state.kind == "other" and path.is_dir():
                raise RecoveryGuardError("BOUNDED_ROLLBACK_DIRECTORY_CONFLICT", str(path))
            path.unlink()
        _atomic_restore_file(path, old)
    _assert_root_fingerprints(roots, root_fingerprints)
    for root_index, relative, path in paths:
        old = before[root_index].get(relative)
        if old is None:
            if _capture_artifact_state(path).kind != "missing":
                raise RecoveryGuardError("BOUNDED_ROLLBACK_VERIFICATION_FAILED", str(path))
        else:
            _assert_path_matches_entry(path, old)


@contextlib.contextmanager
def _exclusive_lock(lock_path: str | Path) -> Iterator[Path]:
    path = Path(lock_path)
    if not path.is_absolute():
        path = path.resolve(strict=False)
    parent = path.parent.resolve(strict=True)
    path = parent / path.name
    if path.exists() and path.is_symlink():
        raise RecoveryGuardError("PUBLISH_LOCK_SYMLINK_FORBIDDEN", str(path))
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RecoveryGuardError("PUBLISH_LOCK_NOT_REGULAR", str(path))
        if metadata.st_nlink != 1:
            raise RecoveryGuardError("PUBLISH_LOCK_HARDLINK_FORBIDDEN", str(path))
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield path
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _assert_no_hidden_proba(
    base_publish: Callable[..., Any], legacy_kwargs: Mapping[str, Any]
) -> None:
    if any(str(key).casefold() == "proba" for key in legacy_kwargs):
        raise RecoveryGuardError("PROBA_MODE_FORBIDDEN")
    # functools.partial and similar callables commonly expose pre-bound kwargs.
    bound = getattr(base_publish, "keywords", None)
    if isinstance(bound, Mapping) and any(str(key).casefold() == "proba" for key in bound):
        raise RecoveryGuardError("PROBA_MODE_FORBIDDEN")
    try:
        signature = inspect.signature(base_publish)
    except (TypeError, ValueError):
        return
    parameter = signature.parameters.get("proba")
    if parameter is not None and parameter.default is True:
        raise RecoveryGuardError("PROBA_MODE_FORBIDDEN")


def _assert_legacy_success(result: Any) -> None:
    if result is True:
        return
    if isinstance(result, (tuple, list)) and result and result[0] is True:
        return
    raise RecoveryGuardError("LEGACY_BASE_PUBLISH_NOT_SUCCESS", repr(result)[:300])


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


_VOID_TAGS = frozenset(
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
_INERT_TAGS = frozenset({"script", "style", "template", "noscript"})
_HIDDEN_CLASSES = frozenset({"hidden", "d-none", "display-none"})
_SECURITY_RELEVANT_ATTRIBUTES = frozenset(
    {
        "aria-hidden",
        "class",
        "data-ua-additional-spec",
        "data-ua-card",
        "data-ua-spec-card",
        "data-ua-spec-revision",
        "data-ua-spec-sha256",
        "hidden",
        "href",
        "id",
        "inert",
        "open",
        "style",
    }
)


def _duplicate_security_attributes(
    attrs: Sequence[tuple[str, str | None]],
) -> tuple[str, ...]:
    counts = Counter(str(key).casefold() for key, _value in attrs)
    return tuple(
        sorted(
            name
            for name, count in counts.items()
            if count > 1 and name in _SECURITY_RELEVANT_ATTRIBUTES
        )
    )


def _inline_style_hidden(value: str) -> bool:
    for declaration in str(value or "").split(";"):
        if ":" not in declaration:
            continue
        name, raw_value = declaration.split(":", 1)
        name = re.sub(r"\s+", "", name).casefold()
        normalized = re.sub(
            r"\s+|!important", "", raw_value, flags=re.IGNORECASE
        ).casefold()
        if name == "display" and normalized == "none":
            return True
        if name == "visibility" and normalized in {"hidden", "collapse"}:
            return True
        if name == "content-visibility" and normalized == "hidden":
            return True
        if name == "opacity":
            try:
                if float(normalized) <= 0.0:
                    return True
            except ValueError:
                pass
    return False


def _element_hidden(
    tag: str,
    attrs: Sequence[tuple[str, str | None]],
    parent_hidden: bool,
    *,
    closed_details_hidden: bool = True,
) -> bool:
    values = {str(key).lower(): str(value or "") for key, value in attrs}
    classes = set(values.get("class", "").lower().split())
    return (
        parent_hidden
        or tag.lower() in _INERT_TAGS
        or (
            closed_details_hidden
            and tag.lower() == "details"
            and "open" not in values
        )
        or "hidden" in values
        or "inert" in values
        or values.get("aria-hidden", "").strip().lower() in {"true", "1"}
        or bool(classes & _HIDDEN_CLASSES)
        or _inline_style_hidden(values.get("style", ""))
    )


class _AdditionalSpecParser(HTMLParser):
    """Extract exact dt/dd pairs from one additional-spec section only."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.section_count = 0
        self.active_section_count = 0
        self.hidden_section_count = 0
        self.hidden_row_count = 0
        self.hidden_content_count = 0
        self.invalid_disclosure_count = 0
        self.disclosure_details_count = 0
        self.direct_child_tags: list[str] = []
        self.summary_count = 0
        self.hidden_summary_count = 0
        self.duplicate_security_attrs: list[str] = []
        self.section_attrs: dict[str, str] = {}
        self.rows: list[tuple[str, str, str]] = []
        self._section_depth = 0
        self._row_depth = 0
        self._row_tag = ""
        self._all_chunks: list[str] = []
        self._dt_chunks: list[str] = []
        self._dd_chunks: list[str] = []
        self._dt_count = 0
        self._dd_count = 0
        self._capture = ""
        self._capture_depth = 0
        self._capture_tag = ""
        self._hidden_stack: list[bool] = []

    @staticmethod
    def _attrs(attrs: Sequence[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).lower(): str(value or "") for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.duplicate_security_attrs.extend(_duplicate_security_attributes(attrs))
        values = self._attrs(attrs)
        classes = values.get("class", "").split()
        parent_hidden = self._hidden_stack[-1] if self._hidden_stack else False
        is_spec_container = (
            tag in {"section", "details"} and "ua-additional-spec" in classes
        )
        # A closed Task099 additional-spec <details> is deliberately available
        # to the user via its summary.  This exception is local to the strict
        # spec parser.  Catalog/identity parsing still treats arbitrary closed
        # <details> descendants as hidden.
        designated_disclosure = (
            is_spec_container
            and tag == "details"
            and values.get("data-ua-additional-spec") == "1"
        )
        hidden = _element_hidden(
            tag,
            attrs,
            parent_hidden,
            closed_details_hidden=not designated_disclosure,
        )
        if tag not in _VOID_TAGS:
            self._hidden_stack.append(hidden)
        if is_spec_container:
            self.section_count += 1
            if tag == "details":
                self.disclosure_details_count += 1
                if not designated_disclosure:
                    self.invalid_disclosure_count += 1
            if hidden:
                self.hidden_section_count += 1
                return
            self.active_section_count += 1
            if self._section_depth == 0:
                self.section_attrs = values
                self._section_depth = 1
            else:
                self._section_depth += 1
            return
        if self._section_depth == 0:
            return
        direct_child = self._section_depth == 1
        if direct_child:
            self.direct_child_tags.append(tag)
        if self.disclosure_details_count and tag == "summary" and direct_child:
            self.summary_count += 1
            if hidden:
                self.hidden_summary_count += 1
        if tag not in _VOID_TAGS:
            self._section_depth += 1
        if hidden:
            # Hidden rows, hidden summary content and inert/inline-hidden
            # descendants all invalidate the disclosure.  A copied digest may
            # never authenticate facts that a buyer cannot reveal and read.
            self.hidden_content_count += 1
        if "ua-addspec-row" in classes:
            if hidden:
                self.hidden_row_count += 1
                return
            if self._row_depth:
                self.rows.append(("", "", "NESTED_ROW"))
            self._row_depth = self._section_depth
            self._row_tag = tag
            self._all_chunks = []
            self._dt_chunks = []
            self._dd_chunks = []
            self._dt_count = 0
            self._dd_count = 0
        elif self._row_depth and hidden:
            self.hidden_content_count += 1
        if self._row_depth and tag in {"dt", "dd"}:
            if hidden:
                return
            if self._capture:
                self.rows.append(("", "", "NESTED_DT_DD"))
            self._capture = tag
            self._capture_tag = tag
            self._capture_depth = self._section_depth
            if tag == "dt":
                self._dt_count += 1
            else:
                self._dd_count += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.duplicate_security_attrs.extend(_duplicate_security_attributes(attrs))
        values = self._attrs(attrs)
        parent_hidden = self._hidden_stack[-1] if self._hidden_stack else False
        hidden = _element_hidden(tag.lower(), attrs, parent_hidden)
        if self._section_depth == 1:
            self.direct_child_tags.append(tag.lower())
        if self._section_depth and hidden:
            self.hidden_content_count += 1
        if self._section_depth and "ua-addspec-row" in values.get("class", "").split():
            if hidden:
                self.hidden_row_count += 1
            else:
                self.rows.append(("", "", "EMPTY_ROW"))

    def handle_data(self, data: str) -> None:
        if (
            not self._row_depth
            or (self._hidden_stack and self._hidden_stack[-1])
            or not _clean_text(data)
        ):
            return
        self._all_chunks.append(data)
        if self._capture == "dt":
            self._dt_chunks.append(data)
        elif self._capture == "dd":
            self._dd_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._section_depth == 0:
            if tag not in _VOID_TAGS and self._hidden_stack:
                self._hidden_stack.pop()
            return
        if (
            self._capture
            and tag == self._capture_tag
            and self._section_depth == self._capture_depth
        ):
            self._capture = ""
            self._capture_tag = ""
            self._capture_depth = 0
        if (
            self._row_depth
            and tag == self._row_tag
            and self._section_depth == self._row_depth
        ):
            label = _clean_text(" ".join(self._dt_chunks))
            value = _clean_text(" ".join(self._dd_chunks))
            all_text = _clean_text(" ".join(self._all_chunks))
            if self._dt_count != 1:
                label = ""
            if self._dd_count != 1:
                value = ""
            self.rows.append((label, value, all_text))
            self._row_depth = 0
            self._row_tag = ""
            self._capture = ""
        if tag not in _VOID_TAGS:
            self._section_depth -= 1
        if tag not in _VOID_TAGS and self._hidden_stack:
            self._hidden_stack.pop()


def _rendered_facts_digest(spec: SpecRevision) -> str:
    return stable_digest(
        [
            {
                "field_key": fact.field_key,
                "label_ru": _clean_text(fact.label_ru),
                "display_value": _clean_text(fact.display_value),
                "unit": _clean_text(fact.unit),
            }
            for fact in spec.visible_facts
        ]
    )


def _assert_rendered_facts(page: str, spec: SpecRevision) -> None:
    parser = _AdditionalSpecParser()
    parser.feed(page)
    parser.close()
    if parser.duplicate_security_attrs:
        raise RecoveryGuardError(
            "DUPLICATE_SECURITY_ATTRIBUTE",
            ",".join(sorted(set(parser.duplicate_security_attrs))),
        )
    if (
        parser.section_count != 1
        or parser.active_section_count != 1
        or parser.hidden_section_count
    ):
        raise RecoveryGuardError(
            "ADDITIONAL_SPEC_ACTIVE_SECTION_COUNT",
            f"total={parser.section_count};active={parser.active_section_count};"
            f"hidden={parser.hidden_section_count}",
        )
    if parser.hidden_row_count or parser.hidden_content_count:
        raise RecoveryGuardError(
            "ADDITIONAL_SPEC_HIDDEN_CONTENT",
            f"rows={parser.hidden_row_count};content={parser.hidden_content_count}",
        )
    if parser.disclosure_details_count:
        if (
            parser.disclosure_details_count != 1
            or parser.invalid_disclosure_count
            or parser.summary_count != 1
            or parser.hidden_summary_count
            or not parser.direct_child_tags
            or parser.direct_child_tags[0] != "summary"
        ):
            raise RecoveryGuardError(
                "ADDITIONAL_SPEC_DISCLOSURE_INVALID",
                f"details={parser.disclosure_details_count};"
                f"invalid={parser.invalid_disclosure_count};"
                f"summary={parser.summary_count};"
                f"hidden_summary={parser.hidden_summary_count}",
            )
    if parser.section_attrs.get("data-ua-spec-revision") != spec.revision_id:
        raise RecoveryGuardError("SPEC_REVISION_MARKER_MISSING")
    if parser.section_attrs.get("data-ua-spec-sha256") != spec.digest:
        raise RecoveryGuardError("SPEC_DIGEST_MARKER_MISSING")
    if parser.section_attrs.get("data-ua-spec-card", "").strip() != spec.uid:
        raise RecoveryGuardError("SPEC_CARD_MARKER_MISSING_OR_MISMATCH")
    if len(parser.rows) != spec.visible_count:
        raise RecoveryGuardError(
            "RENDERED_SPEC_ROW_COUNT_MISMATCH",
            f"{len(parser.rows)}:{spec.visible_count}",
        )
    for fact, (label, value, all_text) in zip(spec.visible_facts, parser.rows):
        expected_label = _clean_text(fact.label_ru)
        expected_value = _clean_text(fact.display_value)
        expected_with_unit = _clean_text(
            expected_value + ((" " + _clean_text(fact.unit)) if fact.unit else "")
        )
        if label != expected_label:
            raise RecoveryGuardError("RENDERED_SPEC_LABEL_MISMATCH", fact.field_key)
        if value not in {expected_value, expected_with_unit}:
            raise RecoveryGuardError("RENDERED_SPEC_VALUE_MISMATCH", fact.field_key)
        if all_text != _clean_text(label + " " + value):
            raise RecoveryGuardError("RENDERED_SPEC_EXTRA_TEXT", fact.field_key)


class _VisibleDocumentParser(HTMLParser):
    """Collect live anchors/text; comments, scripts and hidden trees are inert."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.text: list[str] = []
        self.visible_chunks: list[str] = []
        self.card_markers: list[str] = []
        self.duplicate_security_attrs: list[str] = []
        self._hidden_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        self.duplicate_security_attrs.extend(_duplicate_security_attributes(attrs))
        parent = self._hidden_stack[-1] if self._hidden_stack else False
        hidden = _element_hidden(tag, attrs, parent)
        if tag not in _VOID_TAGS:
            self._hidden_stack.append(hidden)
        if not hidden:
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            if "data-ua-card" in values:
                self.card_markers.append(values["data-ua-card"].strip().upper())
            if tag == "a":
                href = values.get("href", "").strip()
                if href:
                    self.hrefs.append(href)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.duplicate_security_attrs.extend(_duplicate_security_attributes(attrs))
        parent = self._hidden_stack[-1] if self._hidden_stack else False
        hidden = _element_hidden(tag.lower(), attrs, parent)
        if not hidden and tag.lower() == "a":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            href = values.get("href", "").strip()
            if href:
                self.hrefs.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in _VOID_TAGS and self._hidden_stack:
            self._hidden_stack.pop()

    def handle_data(self, data: str) -> None:
        if not (self._hidden_stack and self._hidden_stack[-1]) and _clean_text(data):
            self.visible_chunks.append(data)
            self.text.extend(re.findall(r"[\w-]+", data.casefold(), re.UNICODE))


def _visible_document(html: str) -> tuple[Counter[str], Counter[str]]:
    parser = _VisibleDocumentParser()
    parser.feed(html)
    parser.close()
    if parser.duplicate_security_attrs:
        raise RecoveryGuardError(
            "DUPLICATE_SECURITY_ATTRIBUTE",
            ",".join(sorted(set(parser.duplicate_security_attrs))),
        )
    return Counter(parser.hrefs), Counter(parser.text)


def _href_uid(href: str) -> str | None:
    raw = str(href or "").strip()
    if not raw or "\\" in raw:
        return None
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
        return None
    pure = PurePosixPath(parsed.path)
    if ".." in pure.parts:
        return None
    path = parsed.path
    name = path.rsplit("/", 1)[-1]
    match = re.fullmatch(r"(UA-\d{4,5})\.html", name, re.IGNORECASE)
    return canonical_uid(match.group(1)) if match else None


def _decode_html(value: bytes, *, path: str) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RecoveryGuardError("PUBLISHED_HTML_NOT_UTF8", path) from exc


def _assert_listing_preserved(
    before: bytes,
    after: bytes,
    *,
    uid: str,
    path: str,
    minimum_size_ratio: float,
) -> None:
    old_html = _decode_html(before, path=path + ":before") if before else ""
    new_html = _decode_html(after, path=path + ":after")
    old_hrefs, old_text = _visible_document(old_html)
    new_hrefs, new_text = _visible_document(new_html)
    old_target_hrefs = Counter(
        {href: count for href, count in old_hrefs.items() if _href_uid(href) == uid}
    )
    new_target_hrefs = Counter(
        {href: count for href, count in new_hrefs.items() if _href_uid(href) == uid}
    )
    old_target_count = sum(old_target_hrefs.values())
    new_target_count = sum(new_target_hrefs.values())
    old_hrefs.subtract(old_target_hrefs)
    new_hrefs.subtract(new_target_hrefs)
    old_hrefs += Counter()
    new_hrefs += Counter()
    if old_target_count not in (0, 1):
        raise RecoveryGuardError("PREEXISTING_CATALOG_LINK_COUNT", f"{path}:{old_target_count}")
    if new_target_count != 1:
        raise RecoveryGuardError(
            "PUBLISHED_CATALOG_LINK_COUNT", f"{path}:{uid}:{new_target_count}"
        )
    if old_hrefs != new_hrefs:
        raise RecoveryGuardError("EXISTING_CATALOG_LINKS_CHANGED", path)
    if any(new_text[token] < count for token, count in old_text.items()):
        raise RecoveryGuardError("VISIBLE_CATALOG_FOUNDATION_CHANGED", path)
    if old_target_count == 1:
        if before != after:
            raise RecoveryGuardError("EXISTING_TARGET_LISTING_CHANGED", path)
    elif not _bytes_are_subsequence(before, after):
        # Publishing a new card may insert bytes, but no byte belonging to the
        # old catalog foundation may be deleted or rewritten.
        raise RecoveryGuardError("CATALOG_FOUNDATION_REWRITTEN", path)
    if before and len(after) < int(len(before) * minimum_size_ratio):
        raise RecoveryGuardError("CATALOG_FOUNDATION_SHRANK", path)


def _bytes_are_subsequence(before: bytes, after: bytes) -> bool:
    if not before:
        return True
    cursor = 0
    for value in after:
        if value == before[cursor]:
            cursor += 1
            if cursor == len(before):
                return True
    return False


def _snapshot_entry(
    snapshot: Mapping[str, HtmlSnapshotEntry],
    relative: str,
    *,
    missing_code: str,
    root: Path,
) -> HtmlSnapshotEntry:
    entry = snapshot.get(relative)
    if entry is None:
        raise RecoveryGuardError(missing_code, f"{root}:{relative}")
    if entry.mode & 0o111:
        raise RecoveryGuardError("PUBLISHED_HTML_EXECUTABLE_MODE", f"{root}:{relative}")
    if entry.mode & 0o002:
        raise RecoveryGuardError("PUBLISHED_HTML_WORLD_WRITABLE", f"{root}:{relative}")
    return entry


def _document_identity_errors(source: str, *, uid: str, vin: str) -> tuple[str, ...]:
    errors: list[str] = []
    parser = _VisibleDocumentParser()
    parser.feed(source)
    parser.close()
    if parser.duplicate_security_attrs:
        errors.append(
            "DUPLICATE_SECURITY_ATTRIBUTE:"
            + ",".join(sorted(set(parser.duplicate_security_attrs)))
        )
    uid_markers = [value for value in parser.card_markers if value == uid]
    other_markers = [value for value in parser.card_markers if value != uid]
    if len(uid_markers) != 1 or other_markers:
        errors.append(
            f"TARGET_IDENTITY_MARKER_COUNT:{len(uid_markers)}:OTHER:{len(other_markers)}"
        )
    visible_text = _clean_text(" ".join(parser.visible_chunks)).upper()
    vin_count = len(
        re.findall(
            r"(?<![A-Z0-9])" + re.escape(vin) + r"(?![A-Z0-9])",
            visible_text,
        )
    )
    if vin_count < 1:
        errors.append("TARGET_VIN_MISSING")
    if "ОТКРЫТЬ ВСЕ АВТОМОБИЛИ" in visible_text and not uid_markers:
        errors.append("GENERIC_FALLBACK_PAGE")
    return tuple(errors)


def _validate_after_publish(
    roots: Sequence[Path],
    before: Sequence[Mapping[str, HtmlSnapshotEntry]],
    after: Sequence[Mapping[str, HtmlSnapshotEntry]],
    *,
    uid: str,
    vin: str,
    spec: SpecRevision,
) -> None:
    target_relative_path = f"{uid}.html"
    diagnostic_relative_path = f"{uid}-diag.html"
    catalog_relative_path = CATALOG_PATH
    index_relative_path = INDEX_PATH
    mirror_artifacts: list[dict[str, tuple[bytes, int]]] = []
    for root_index, root in enumerate(roots):
        current = after[root_index]
        page_entry = _snapshot_entry(
            current,
            target_relative_path,
            missing_code="PUBLISHED_TARGET_MISSING",
            root=root,
        )
        diagnostic_entry = _snapshot_entry(
            current,
            diagnostic_relative_path,
            missing_code="PUBLISHED_DIAGNOSTIC_MISSING",
            root=root,
        )
        catalog_entry = _snapshot_entry(
            current,
            catalog_relative_path,
            missing_code="PUBLISHED_CATALOG_MISSING",
            root=root,
        )
        index_entry = _snapshot_entry(
            current,
            index_relative_path,
            missing_code="PUBLISHED_INDEX_MISSING",
            root=root,
        )
        page_bytes = page_entry.content
        diagnostic_bytes = diagnostic_entry.content
        catalog_bytes = catalog_entry.content
        index_bytes = index_entry.content
        page = _decode_html(page_bytes, path=f"{root}:{target_relative_path}")
        errors = card_identity_errors(
            page,
            uid=uid,
            vin=vin,
            expected_spec_rows=spec.visible_count,
            expected_spec_digest=spec.digest,
            expected_spec=spec,
        )
        errors = tuple(errors) + _document_identity_errors(page, uid=uid, vin=vin)
        if errors:
            raise RecoveryGuardError("PUBLISHED_CARD_INVALID", f"{root}:" + ";".join(errors))
        _assert_rendered_facts(page, spec)
        diagnostic_html = _decode_html(
            diagnostic_bytes, path=f"{root}:{diagnostic_relative_path}"
        )
        diagnostic_errors = _document_identity_errors(
            diagnostic_html, uid=uid, vin=vin
        )
        if diagnostic_errors:
            raise RecoveryGuardError(
                "PUBLISHED_DIAGNOSTIC_INVALID",
                f"{root}:" + ";".join(diagnostic_errors),
            )
        for relative, new_bytes in (
            (catalog_relative_path, catalog_bytes),
            (index_relative_path, index_bytes),
        ):
            old_entry = before[root_index].get(relative)
            _assert_listing_preserved(
                old_entry.content if old_entry else b"",
                new_bytes,
                uid=uid,
                path=f"{root}:{relative}",
                minimum_size_ratio=MINIMUM_LISTING_SIZE_RATIO,
            )
        mirror_artifacts.append(
            {
                target_relative_path: (page_bytes, page_entry.mode),
                diagnostic_relative_path: (diagnostic_bytes, diagnostic_entry.mode),
                catalog_relative_path: (catalog_bytes, catalog_entry.mode),
                index_relative_path: (index_bytes, index_entry.mode),
            }
        )
    if mirror_artifacts[0] != mirror_artifacts[1]:
        raise RecoveryGuardError("PUBLISHED_ROOTS_DIVERGED")


def atomic_publish(
    site_roots: Sequence[str | Path],
    *,
    uid: Any,
    vin: Any,
    spec: SpecRevision,
    base_publish: TrustedLegacyPublisher,
    verify_gate_b: Callable[[Mapping[str, Any]], bool],
    consume_gate_nonce: Callable[[str], bool],
    allow_production: bool = False,
    owner_command: str = "",
    gate_b_receipt: Mapping[str, Any] | None = None,
    legacy_kwargs: Mapping[str, Any] | None = None,
) -> AtomicPublishReceipt:
    """Run the legacy publisher under a guarded, reversible HTML transaction.

    The wrapper cannot make a process crash atomic; a SIGKILL during the legacy
    call may still require the persisted platform backup/release mechanism.
    For ordinary exceptions and validation failures it restores both HTML trees
    byte-for-byte.  A non-cooperating concurrent change is detected before
    rollback and is never silently overwritten.
    """

    normalized_uid = canonical_uid(uid)
    _require_owner_gate(
        uid=normalized_uid,
        allow_production=allow_production,
        owner_command=owner_command,
    )
    # This must happen before roots/Gate/nonce and, most importantly, before
    # the injected publisher can perform any write.  Post-render validation is
    # too late to discover a forged digest, count or fact tuple.
    assert_spec_revision_integrity(spec)
    if spec.uid != normalized_uid or spec.vin_sha256 != vin_sha256(vin):
        raise RecoveryGuardError("SPEC_PUBLISH_BINDING_MISMATCH")
    if spec.status != "ACTIVE":
        raise RecoveryGuardError("SPEC_REVISION_NOT_ACTIVE")
    if spec.visible_count < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
        raise RecoveryGuardError(
            "SPEC_NOT_READY",
            f"{spec.visible_count}/{PUBLIC_MIN_VISIBLE_SPEC_ROWS}",
        )
    if type(base_publish) is not TrustedLegacyPublisher:
        raise RecoveryGuardError("UNTRUSTED_LEGACY_PUBLISHER")
    kwargs = dict(legacy_kwargs or {})
    if "ua116_site_roots" in kwargs:
        raise RecoveryGuardError("RESERVED_PUBLISH_ARGUMENT", "ua116_site_roots")
    _assert_no_hidden_proba(base_publish.publisher, kwargs)
    unknown_kwargs = sorted(set(kwargs) - ALLOWED_LEGACY_KWARGS)
    if unknown_kwargs:
        raise RecoveryGuardError(
            "LEGACY_ARGUMENT_NOT_ALLOWLISTED", ",".join(unknown_kwargs)
        )

    target = f"{normalized_uid}.html"
    diagnostic = f"{normalized_uid}-diag.html"
    catalog = CATALOG_PATH
    index = INDEX_PATH
    allowed = (target, diagnostic, catalog, index)
    roots = _validate_roots(site_roots)
    expected_lock = canonical_publish_lock(roots)
    prelock_fingerprints = _site_root_fingerprints(roots)

    with _exclusive_lock(expected_lock) as locked:
        _assert_root_fingerprints(roots, prelock_fingerprints)
        root_fingerprints = _site_root_fingerprints(roots)
        before = _snapshot_roots(roots)
        before_digest = _roots_digest(before)
        gate_b_digest = _require_gate_b(
            gate_b_receipt,
            verify_gate_b=verify_gate_b,
            uid=normalized_uid,
            vin=vin,
            spec=spec,
            publisher=base_publish,
            legacy_kwargs=kwargs,
            roots_before_digest=before_digest,
            site_root_fingerprints=root_fingerprints,
        )
        if not callable(consume_gate_nonce):
            raise RecoveryGuardError("GATE_NONCE_CONSUMER_REQUIRED")
        gate_nonce = str((gate_b_receipt or {}).get("nonce") or "")
        try:
            nonce_consumed = consume_gate_nonce(gate_nonce)
        except Exception as exc:
            raise RecoveryGuardError("GATE_NONCE_CONSUMER_FAILED") from exc
        if nonce_consumed is not True:
            raise RecoveryGuardError("GATE_NONCE_ALREADY_USED_OR_REJECTED")

        failure: BaseException | None = None
        result: Any = None
        try:
            result = base_publish.publisher(
                normalized_uid,
                ua116_site_roots=tuple(str(root) for root in roots),
                **kwargs,
            )
            if inspect.isawaitable(result):
                close = getattr(result, "close", None)
                if callable(close):
                    close()
                raise RecoveryGuardError("ASYNC_LEGACY_PUBLISHER_UNSUPPORTED")
            _assert_legacy_success(result)
        except BaseException as exc:  # rollback must also cover legacy exceptions
            failure = exc

        try:
            _assert_root_fingerprints(roots, root_fingerprints)
            after = _snapshot_roots(roots)
        except BaseException as snapshot_exc:
            try:
                _bounded_allowed_rollback(
                    roots, before, allowed, root_fingerprints
                )
            except BaseException as rollback_exc:
                raise RecoveryGuardError(
                    "POST_PUBLISH_SNAPSHOT_AND_BOUNDED_ROLLBACK_FAILED",
                    f"snapshot={snapshot_exc!r};rollback={rollback_exc!r}",
                ) from rollback_exc
            raise RecoveryGuardError(
                "POST_PUBLISH_SNAPSHOT_FAILED_ALLOWED_ARTIFACTS_ROLLED_BACK",
                repr(snapshot_exc),
            ) from snapshot_exc

        try:
            if failure is not None:
                raise failure
            changed_labeled: list[str] = []
            for index_number, (old, new) in enumerate(zip(before, after), start=1):
                changed = _changed_paths(old, new)
                outside = tuple(path for path in changed if path not in allowed)
                if outside:
                    raise RecoveryGuardError(
                        "SITE_FOUNDATION_CHANGED",
                        f"root{index_number}:" + ",".join(outside),
                    )
                changed_labeled.extend(f"root{index_number}:{path}" for path in changed)
            _validate_after_publish(
                roots,
                before,
                after,
                uid=normalized_uid,
                vin=vin,
                spec=spec,
            )
            _assert_root_fingerprints(roots, root_fingerprints)
            final_snapshot = _snapshot_roots(roots)
            if not _same_snapshots(final_snapshot, after):
                raise RecoveryGuardError("POST_VALIDATION_CONCURRENT_CHANGE")
            return AtomicPublishReceipt(
                contract_id=CONTRACT_ID,
                contract_version=CONTRACT_VERSION,
                mode=PRODUCTION_MODE,
                outcome="PUBLISHED" if changed_labeled else "ALREADY_VALID",
                target_uid=normalized_uid,
                target_vin_sha256=vin_sha256(vin),
                spec_revision_id=spec.revision_id,
                spec_digest=spec.digest,
                visible_spec_rows=spec.visible_count,
                changed_html=tuple(changed_labeled),
                roots_before_digest=before_digest,
                roots_after_digest=_roots_digest(after),
                lock_path=str(locked),
                gate_b_evidence_digest=gate_b_digest,
                gate_nonce=gate_nonce,
                publisher_adapter_id=base_publish.adapter_id,
                publisher_artifact_sha256=base_publish.adapter_artifact_sha256,
                publisher_code_object_sha256=base_publish.code_object_sha256,
                rendered_facts_digest=_rendered_facts_digest(spec),
                site_root_fingerprints=tuple(root_fingerprints),
            )
        except BaseException as publish_error:
            try:
                _restore_snapshots(roots, before, after)
            except BaseException as rollback_error:
                raise RecoveryGuardError(
                    "ATOMIC_ROLLBACK_FAILED",
                    f"publish={publish_error!r};rollback={rollback_error!r}",
                ) from rollback_error
            raise RecoveryGuardError(
                "ATOMIC_PUBLISH_ROLLED_BACK", repr(publish_error)
            ) from publish_error


__all__ = [
    "AtomicPublishReceipt",
    "HtmlSnapshotEntry",
    "PRODUCTION_MODE",
    "TrustedLegacyPublisher",
    "atomic_publish_code_sha256",
    "atomic_publish",
    "canonical_publish_lock",
    "publisher_code_object_sha256",
    "required_owner_command",
    "trusted_legacy_publisher",
]
