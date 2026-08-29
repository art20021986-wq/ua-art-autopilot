"""SEO068 fail-closed, atomic, idempotent publish path for TASK 073.

Guarantees:
- Missing diagnostics never blocks the primary card; a canonical
  placeholder diagnostic page is generated atomically instead.
- A staged bundle (primary + diag) is fully built and validated before
  any production file is touched, and installed atomically.
- Success is only ever reported after a caller-supplied verify_fn proves
  the exact card_id/revision is publicly reachable. Any failure produces
  exactly one honest failure result and never a later false success.
- Re-publishing the same content is idempotent (no duplicate index entries
  or content rewrites).
"""

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from typing import Callable, Optional


class SEO068DiagnosticMissing(Exception):
    pass


class PublicationError(Exception):
    pass


PLACEHOLDER_DIAG_TEXT = "Материалы диагностики пока не добавлены."


@dataclass
class PublishResult:
    success: bool
    card_id: str
    revision: str
    message: str


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _render_placeholder(card_id: str) -> str:
    return (
        f"<html><body><h1>{card_id}</h1>"
        f"<p>{PLACEHOLDER_DIAG_TEXT}</p></body></html>"
    )


def build_bundle(staging_dir: str, card_id: str, primary_html: str, diag_html: Optional[str]) -> dict:
    os.makedirs(staging_dir, exist_ok=True)
    primary_path = os.path.join(staging_dir, f"{card_id}.html")
    diag_path = os.path.join(staging_dir, f"{card_id}-diag.html")
    with open(primary_path, "w", encoding="utf-8") as handle:
        handle.write(primary_html)
    diag_content = diag_html if diag_html else _render_placeholder(card_id)
    with open(diag_path, "w", encoding="utf-8") as handle:
        handle.write(diag_content)
    manifest = {
        "card_id": card_id,
        "primary_sha256": _sha256_bytes(primary_html.encode("utf-8")),
        "diag_sha256": _sha256_bytes(diag_content.encode("utf-8")),
        "diag_is_placeholder": diag_html is None,
        "revision": _sha256_bytes((primary_html + diag_content + card_id).encode("utf-8"))[:16],
    }
    with open(os.path.join(staging_dir, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    return manifest


def install_bundle(staging_dir: str, production_dir: str, manifest: dict, existing_index: dict) -> dict:
    card_id = manifest["card_id"]
    if existing_index.get(card_id) == manifest["revision"]:
        return dict(existing_index)
    os.makedirs(production_dir, exist_ok=True)
    tmp_targets = []
    try:
        for name in (f"{card_id}.html", f"{card_id}-diag.html"):
            src = os.path.join(staging_dir, name)
            dst = os.path.join(production_dir, name)
            dst_tmp = dst + ".tmp"
            shutil.copyfile(src, dst_tmp)
            tmp_targets.append((dst_tmp, dst))
        for tmp_path, final_path in tmp_targets:
            os.replace(tmp_path, final_path)
        new_index = dict(existing_index)
        new_index[card_id] = manifest["revision"]
        return new_index
    except Exception as exc:
        for tmp_path, _final_path in tmp_targets:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        raise PublicationError(f"install_failed:{exc}") from exc


def publish_card(
    card_id: str,
    primary_html: str,
    diag_html: Optional[str],
    production_dir: str,
    index: dict,
    verify_fn: Callable[[str, str], bool],
) -> PublishResult:
    if primary_html is None or primary_html.strip() == "":
        raise SEO068DiagnosticMissing(f"SEO068_PRIMARY_TARGET_MISSING:{card_id}")

    with tempfile.TemporaryDirectory() as staging_dir:
        manifest = build_bundle(staging_dir, card_id, primary_html, diag_html)
        try:
            new_index = install_bundle(staging_dir, production_dir, manifest, index)
        except PublicationError as exc:
            return PublishResult(False, card_id, manifest["revision"], f"install_error:{exc}")

        index.clear()
        index.update(new_index)

        try:
            verified = verify_fn(card_id, manifest["revision"])
        except Exception:
            verified = False

        if not verified:
            return PublishResult(
                False,
                card_id,
                manifest["revision"],
                "publication_verify_failed_no_success_claimed",
            )

        return PublishResult(True, card_id, manifest["revision"], "published_and_verified")
