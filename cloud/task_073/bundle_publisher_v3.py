"""
TASK_073 ROUND 4 - bundle_publisher_v3.py

Generic, per-card unified publisher used by:
  * gate_a_v3.py for a fully offline dry-run (proba=True/False on a temp fs)
  * gate_b_controller_v3.py for the real, owner-approved production canary

The publisher never touches crm.db. It stages primary + diagnostics/placeholder
+ catalog for exactly one auto card, validates the staged bundle, then
atomically installs the bounded write-set with a per-target backup and full
rollback on any failure.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional


class PublishGuardError(RuntimeError):
    pass


DIAG_PLACEHOLDER_TEXT = "Материалы диагностики пока не добавлены."


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class CardTargets:
    auto_number: str
    primary_path: str
    diag_path: str
    catalog_path: str
    has_diag_material: bool = False


@dataclass
class PublishResult:
    ok: bool
    message: str
    changed_paths: List[str] = field(default_factory=list)
    backups: Dict[str, Optional[str]] = field(default_factory=dict)


def render_primary_html(auto_number: str) -> str:
    return (
        "<!doctype html><html><head><title>{a}</title></head>"
        "<body><h1>{a}</h1>"
        '<a class="diag-cta" href="{a}-diag.html">Диагностика</a>'
        "</body></html>"
    ).format(a=auto_number)


def render_diag_placeholder_html(auto_number: str) -> str:
    return (
        "<!doctype html><html><head><title>{a} diagnostics</title></head>"
        "<body><h1>{a}</h1><p>{ph}</p></body></html>"
    ).format(a=auto_number, ph=DIAG_PLACEHOLDER_TEXT)


def rebuild_catalog(existing_catalog_text: str, all_auto_numbers: List[str]) -> str:
    """Rebuild the catalog card list section deterministically from the
    authoritative list of published auto numbers, keeping any surrounding
    document markup byte-identical."""
    seen: List[str] = []
    for number in all_auto_numbers:
        if number not in seen:
            seen.append(number)
    items = "".join('<li><a href="{n}.html">{n}</a></li>'.format(n=n) for n in seen)
    block = '<ul id="ua-catalog-cards">{items}</ul>'.format(items=items)
    pattern = re.compile(r'<ul id="ua-catalog-cards">.*?</ul>', re.DOTALL)
    if pattern.search(existing_catalog_text):
        return pattern.sub(block, existing_catalog_text, count=1)
    return existing_catalog_text + block


def validate_bundle(auto_number: str, primary_text: str, diag_text: str, catalog_text: str) -> None:
    if auto_number not in primary_text:
        raise PublishGuardError("primary bundle missing card identity")
    expected_cta = 'href="{}-diag.html"'.format(auto_number)
    if expected_cta not in primary_text:
        raise PublishGuardError("primary bundle missing exact diagnostics CTA")
    if auto_number not in diag_text:
        raise PublishGuardError("diagnostics bundle missing card identity")
    expected_href = 'href="{}.html"'.format(auto_number)
    occurrences = catalog_text.count(expected_href)
    if occurrences != 1:
        raise PublishGuardError(
            "catalog must contain exact href {} once, found {}".format(expected_href, occurrences)
        )


def _backup_target(path: str, backup_dir: str) -> Optional[str]:
    if not os.path.isfile(path):
        return None
    backup_path = os.path.join(backup_dir, hashlib.sha256(path.encode("utf-8")).hexdigest() + ".bak")
    shutil.copy2(path, backup_path)
    return backup_path


def _atomic_write(path: str, content: str) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".task073_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def publish_card(
    targets: CardTargets,
    all_auto_numbers: List[str],
    existing_diag_text: Optional[str],
    proba: bool = True,
) -> PublishResult:
    """Build, validate, and (unless proba) atomically install primary + diag
    (real material or canonical placeholder) + catalog for exactly one card.
    Any staging or install failure triggers a full rollback of every target
    that was touched."""
    primary_text = render_primary_html(targets.auto_number)
    if targets.has_diag_material and existing_diag_text:
        diag_text = existing_diag_text
    else:
        diag_text = render_diag_placeholder_html(targets.auto_number)

    if os.path.isfile(targets.catalog_path):
        with open(targets.catalog_path, "r", encoding="utf-8") as fh:
            existing_catalog_text = fh.read()
    else:
        existing_catalog_text = (
            '<!doctype html><html><body><ul id="ua-catalog-cards"></ul></body></html>'
        )
    catalog_text = rebuild_catalog(existing_catalog_text, all_auto_numbers)

    try:
        validate_bundle(targets.auto_number, primary_text, diag_text, catalog_text)
    except PublishGuardError as exc:
        return PublishResult(False, "SEO068_VALIDATION_FAILED:{}".format(exc))

    if proba:
        return PublishResult(
            True,
            "DRY_RUN_PASS",
            changed_paths=[targets.primary_path, targets.diag_path, targets.catalog_path],
        )

    backup_dir = tempfile.mkdtemp(prefix="task073_backup_")
    write_plan = [
        (targets.primary_path, primary_text),
        (targets.diag_path, diag_text),
        (targets.catalog_path, catalog_text),
    ]
    backups: Dict[str, Optional[str]] = {}
    written: List[str] = []
    try:
        for path, _content in write_plan:
            backups[path] = _backup_target(path, backup_dir)
        for path, content in write_plan:
            _atomic_write(path, content)
            written.append(path)

        for path, content in write_plan:
            with open(path, "r", encoding="utf-8") as fh:
                on_disk = fh.read()
            if sha256_text(on_disk) != sha256_text(content):
                raise PublishGuardError("read-back mismatch for {}".format(path))

        return PublishResult(True, "PUBLISH_COMMIT_PASS", changed_paths=written, backups=backups)
    except Exception as exc:  # noqa: BLE001 - fail closed, always roll back
        for path in written:
            backup_path = backups.get(path)
            if backup_path is not None:
                shutil.copy2(backup_path, path)
            elif os.path.exists(path):
                os.remove(path)
        return PublishResult(False, "PUBLISH_FAILED_ROLLED_BACK:{}".format(exc))
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)
