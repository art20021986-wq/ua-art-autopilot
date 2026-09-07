from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

try:
    import pytest
except ModuleNotFoundError:  # pragma: no cover - exercised by direct stdlib run
    class _Raises:
        def __init__(self, exception, match=None):
            self.exception = exception
            self.match = match

        def __enter__(self):
            return self

        def __exit__(self, kind, value, traceback):
            if kind is None:
                raise AssertionError(f"{self.exception.__name__} was not raised")
            if not issubclass(kind, self.exception):
                return False
            if self.match and not re.search(self.match, str(value)):
                raise AssertionError(f"{value!s} does not match {self.match!r}")
            return True

    class _PytestFallback:
        @staticmethod
        def raises(exception, match=None):
            return _Raises(exception, match)

    pytest = _PytestFallback()

import preview_release as preview_module
from preview_release import build_preview_release, current_release
from recovery_core import (
    RecoveryGuardError,
    SpecFact,
    activate_candidate,
    build_candidate_revision,
)


# Synthetic/example VIN: never bind a real inventory VIN to the UA-0017 fixture.
VIN = "1HGBH41JXMN109186"
UID = "UA-0017"


def active_spec():
    rows = [
        SpecFact(
            field_key=f"field_{i}",
            label_ru=f"Поле {i}",
            display_value=str(i),
            confidence=0.99,
            evidence_count=2,
            source_domains=("auto-data.net",),
        )
        for i in range(10)
    ]
    candidate = build_candidate_revision(
        UID, VIN, "P1", rows, revision_id="revision-1"
    )
    return activate_candidate(None, candidate)[1]


def page(spec, *, uid: str = UID) -> str:
    rows = "".join(
        '<div class="ua-addspec-row"><dt>%s</dt><dd>%s</dd></div>'
        % (fact.label_ru, fact.display_value)
        for fact in spec.visible_facts
    )
    return (
        f'<html><section class="ua-additional-spec" data-ua-card="{uid}" '
        f'data-ua-spec-sha256="{spec.digest}">{VIN}{rows}</section></html>'
    )


def diag(*, uid: str = UID, vin: str = VIN) -> str:
    return f'<html><main data-ua-card="{uid}">Диагностика {vin}</main></html>'


def listing(*, uid: str = UID, label: str = "card") -> str:
    return f'<html><a href="{uid}.html?v=1">{label}</a></html>'


def foundation() -> dict[str, str]:
    return {
        "templates/card.html": hashlib.sha256(b"immutable card shell").hexdigest(),
        "static/site.css": hashlib.sha256(b"immutable site css").hexdigest(),
    }


def release(root: Path, *, release_id: str = "gateb-001", **changes):
    spec = changes.pop("spec", active_spec())
    values = {
        "uid": UID,
        "vin": VIN,
        "spec": spec,
        "page_html": page(spec),
        "diag_html": diag(),
        "catalog_html": listing(label="catalog"),
        "index_html": listing(label="index"),
        "card_row_digest": "card-digest",
        "foundation_manifest": foundation(),
    }
    values.update(changes)
    return build_preview_release(root, release_id=release_id, **values)


def test_complete_release_switches_pointer_only_after_full_readback(
    tmp_path: Path,
) -> None:
    root = tmp_path / "preview"
    manifest = release(root)
    assert manifest["production_touched"] is False
    assert manifest["production_write_attempts"] == 0
    assert manifest["release_artifacts_readback_verified_before_pointer"] is True
    assert manifest["artifact_count"] == 8
    evidence = manifest["foundation_baseline_evidence"]
    assert evidence["path_sha256"] == foundation()
    assert evidence["source_files_verified"] is False
    assert evidence["source_verification_status"] == "NOT_PERFORMED_BY_PREVIEW_BUILDER"
    assert len(evidence["release_binding_digest"]) == 64

    current = current_release(root)
    assert current and current["release_id"] == "gateb-001"
    assert set(current["artifacts"]) == {
        f"video/{UID}.html",
        f"site/{UID}.html",
        f"video/{UID}-diag.html",
        f"site/{UID}-diag.html",
        "video/katalog.html",
        "site/katalog.html",
        "video/index.html",
        "site/index.html",
    }
    assert (root / f"releases/gateb-001/site/{UID}.html").is_file()


def test_failure_before_pointer_does_not_replace_current(tmp_path: Path) -> None:
    root = tmp_path / "preview"
    release(root)
    before = (root / "current.json").read_bytes()
    with pytest.raises(RuntimeError, match="INJECTED_BEFORE_POINTER"):
        release(
            root,
            release_id="gateb-002",
            card_row_digest="next-digest",
            fault="before_pointer",
        )
    assert (root / "current.json").read_bytes() == before
    assert current_release(root)["release_id"] == "gateb-001"


def test_final_readback_failure_restores_exact_previous_pointer_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "preview"
    first = release(root)
    pointer = root / "current.json"
    exact_previous = (
        "{\n"
        f'  "mode" : "PREVIEW_ONLY",\n  "release_id" : "gateb-001",\n'
        f'  "manifest_digest" : "{first["manifest_digest"]}"\n'
        "}\n"
    ).encode("utf-8")
    pointer.write_bytes(exact_previous)

    original = preview_module.current_release
    preview_module.current_release = lambda _root: (_ for _ in ()).throw(
        RecoveryGuardError("INJECTED_FINAL_READBACK")
    )
    try:
        with pytest.raises(RecoveryGuardError, match="INJECTED_FINAL_READBACK"):
            release(root, release_id="gateb-002")
    finally:
        preview_module.current_release = original

    assert pointer.read_bytes() == exact_previous
    assert current_release(root)["release_id"] == "gateb-001"


def test_final_readback_failure_restores_exact_pointer_absence(tmp_path: Path) -> None:
    root = tmp_path / "preview"
    original = preview_module.current_release
    preview_module.current_release = lambda _root: (_ for _ in ()).throw(
        RecoveryGuardError("INJECTED_FINAL_READBACK")
    )
    try:
        with pytest.raises(RecoveryGuardError, match="INJECTED_FINAL_READBACK"):
            release(root)
    finally:
        preview_module.current_release = original

    assert not (root / "current.json").exists()


def test_root_and_foundation_fail_closed_before_any_mkdir(tmp_path: Path) -> None:
    spec = active_spec()
    forbidden = Path("/home/Carix/task116-must-not-exist")
    assert not forbidden.exists()
    with pytest.raises(RecoveryGuardError, match="PRODUCTION_PATH_FORBIDDEN"):
        build_preview_release(
            forbidden,
            release_id="gateb-001",
            uid=UID,
            vin=VIN,
            spec=spec,
            page_html=page(spec),
            diag_html=diag(),
            catalog_html=listing(label="catalog"),
            index_html=listing(label="index"),
            card_row_digest="a",
            foundation_manifest=foundation(),
        )
    assert not forbidden.exists()

    missing_baseline_root = tmp_path / "missing-foundation"
    with pytest.raises(
        RecoveryGuardError, match="PREVIEW_FOUNDATION_BASELINE_REQUIRED"
    ):
        build_preview_release(
            missing_baseline_root,
            release_id="gateb-001",
            uid=UID,
            vin=VIN,
            spec=spec,
            page_html=page(spec),
            diag_html=diag(),
            catalog_html=listing(label="catalog"),
            index_html=listing(label="index"),
            card_row_digest="a",
        )
    assert not missing_baseline_root.exists()


def test_page_diag_catalog_and_index_semantics_are_all_required(
    tmp_path: Path,
) -> None:
    spec = active_spec()
    with pytest.raises(RecoveryGuardError, match="PREVIEW_CARD_INVALID"):
        release(tmp_path / "bad-page", page_html="<html>Открыть все автомобили</html>")
    with pytest.raises(RecoveryGuardError, match="PREVIEW_DIAG_INVALID"):
        release(tmp_path / "bad-diag", diag_html="<html>generic diagnostics</html>")
    with pytest.raises(RecoveryGuardError, match="PREVIEW_CATALOG_INVALID"):
        release(
            tmp_path / "bad-catalog",
            catalog_html='<a href="UA-00170.html">prefix collision</a>',
        )
    with pytest.raises(RecoveryGuardError, match="PREVIEW_INDEX_INVALID"):
        release(tmp_path / "bad-index", index_html="<html>index without target</html>")

    for candidate in (tmp_path / "bad-page", tmp_path / "bad-diag"):
        assert not candidate.exists()


def test_card_and_diag_reject_identity_and_spec_evidence_only_in_inert_dom(
    tmp_path: Path,
) -> None:
    spec = active_spec()
    valid_page = page(spec)
    hidden_card = (
        f"<!--{valid_page}-->"
        f'<div aria-hidden="true"><section inert>{valid_page}</section></div>'
    )
    with pytest.raises(RecoveryGuardError, match="PREVIEW_CARD_INVALID"):
        release(tmp_path / "hidden-card", page_html=hidden_card)

    card_errors = preview_module._card_hash_identity_errors(
        hidden_card,
        uid=UID,
        expected_vin_hash=spec.vin_sha256,
        expected_spec_rows=spec.visible_count,
        expected_spec_digest=spec.digest,
    )
    assert card_errors
    assert any("IDENTITY" in error for error in card_errors)
    assert any("SPEC_ROW_COUNT" in error for error in card_errors)

    hidden_diag = (
        f"<!--{diag()}-->"
        f'<div style="display: none !important">{diag()}</div>'
    )
    with pytest.raises(RecoveryGuardError, match="PREVIEW_DIAG_INVALID"):
        release(tmp_path / "hidden-diag", diag_html=hidden_diag)
    diag_errors = preview_module._diag_identity_errors(
        hidden_diag, uid=UID, expected_vin_hash=spec.vin_sha256
    )
    assert "DIAG_TARGET_VIN_MISSING" in diag_errors

    # Inert decoys do not create duplicate evidence when one real card/diag is
    # present in the active DOM.
    accepted = release(
        tmp_path / "active-plus-decoys",
        page_html=valid_page + hidden_card,
        diag_html=diag() + hidden_diag,
    )
    assert accepted["release_id"] == "gateb-001"


def test_card_rejects_all_supported_hidden_ancestor_forms(tmp_path: Path) -> None:
    spec = active_spec()
    wrappers = (
        ("hidden", '<div hidden>{}</div>'),
        ("inert", '<div inert>{}</div>'),
        ("aria", '<div aria-hidden="true">{}</div>'),
        ("display", '<div style="display:none">{}</div>'),
        ("visibility", '<div style="visibility: hidden">{}</div>'),
        ("content", '<div style="content-visibility:hidden">{}</div>'),
        ("opacity", '<div style="opacity: 0">{}</div>'),
    )
    for name, wrapper in wrappers:
        with pytest.raises(RecoveryGuardError, match="PREVIEW_CARD_INVALID"):
            release(
                tmp_path / f"hidden-card-{name}",
                page_html=wrapper.format(page(spec)),
            )


def test_catalog_and_index_count_only_active_html_anchors(tmp_path: Path) -> None:
    inert_and_active = f"""
        <!-- <a href="{UID}.html">comment</a> -->
        <script>const fake = '<a href="{UID}.html">script</a>';</script>
        <template><a href="{UID}.html">template</a></template>
        <a href="{UID}.html" aria-disabled="true">disabled</a>
        <a href="{UID}.html?v=1">active</a>
    """
    result = release(
        tmp_path / "active-anchor",
        catalog_html=inert_and_active,
        index_html=inert_and_active,
    )
    assert result["release_id"] == "gateb-001"

    inert_only = f"""
        <!-- <a href="{UID}.html">comment</a> -->
        <script>const fake = '<a href="{UID}.html">script</a>';</script>
    """
    with pytest.raises(RecoveryGuardError, match="PREVIEW_CATALOG_INVALID"):
        release(tmp_path / "inert-only", catalog_html=inert_only)

    for name, href in (
        ("external", f"https://evil.invalid/{UID}.html"),
        ("absolute", f"/video/{UID}.html"),
        ("traversal", f"../video/{UID}.html"),
    ):
        with pytest.raises(RecoveryGuardError, match="PREVIEW_CATALOG_INVALID"):
            release(tmp_path / name, catalog_html=f'<a href="{href}">target</a>')


def test_preview_rejects_duplicate_security_attributes(tmp_path: Path) -> None:
    with pytest.raises(RecoveryGuardError, match="PREVIEW_CATALOG_INVALID"):
        release(
            tmp_path / "duplicate-href",
            catalog_html=f'<a href="WRONG.html" href="{UID}.html">forged</a>',
        )
    with pytest.raises(RecoveryGuardError, match="PREVIEW_INDEX_INVALID"):
        release(
            tmp_path / "duplicate-style",
            index_html=(
                f'<div style="display:none" style=""><a href="{UID}.html">'
                "forged</a></div>"
            ),
        )


def test_listing_rejects_hidden_closed_or_disabled_ancestor_links(
    tmp_path: Path,
) -> None:
    anchor = f'<a href="{UID}.html">target</a>'
    wrappers = (
        ("hidden", '<div hidden>{}</div>'),
        ("inert", '<section inert>{}</section>'),
        ("aria-hidden", '<div aria-hidden="true">{}</div>'),
        ("display", '<div style="display: none !important">{}</div>'),
        ("visibility", '<div style="visibility:collapse">{}</div>'),
        ("content", '<div style="content-visibility: hidden">{}</div>'),
        ("opacity", '<div style="opacity:0">{}</div>'),
        ("closed-details", '<details>{}</details>'),
        ("disabled", '<fieldset disabled>{}</fieldset>'),
        ("aria-disabled", '<div aria-disabled="1">{}</div>'),
        ("pointer-events", '<div style="pointer-events:none">{}</div>'),
    )
    for name, wrapper in wrappers:
        with pytest.raises(RecoveryGuardError, match="PREVIEW_CATALOG_INVALID"):
            release(
                tmp_path / f"inactive-link-{name}",
                catalog_html=wrapper.format(anchor),
            )

    decoys = "".join(wrapper.format(anchor) for _name, wrapper in wrappers)
    accepted = release(
        tmp_path / "one-active-many-inactive",
        catalog_html=decoys + anchor,
        index_html=f"<details open>{anchor}</details>" + decoys,
    )
    assert accepted["release_id"] == "gateb-001"

    with pytest.raises(RecoveryGuardError, match="PREVIEW_INDEX_INVALID"):
        release(
            tmp_path / "inactive-index",
            catalog_html=anchor,
            index_html=decoys,
        )


def test_current_release_reads_back_every_artifact_hash(tmp_path: Path) -> None:
    root = tmp_path / "preview"
    release(root)
    site_page = root / f"releases/gateb-001/site/{UID}.html"
    site_page.write_text(site_page.read_text() + "tampered", encoding="utf-8")
    with pytest.raises(RecoveryGuardError, match="RELEASE_ARTIFACT_HASH_MISMATCH"):
        current_release(root)


def test_current_release_rejects_missing_or_extra_artifacts(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"
    release(missing_root)
    (missing_root / "releases/gateb-001/site/index.html").unlink()
    with pytest.raises(RecoveryGuardError, match="RELEASE_ARTIFACT_SET_MISMATCH"):
        current_release(missing_root)

    extra_root = tmp_path / "extra"
    release(extra_root)
    extra = extra_root / "releases/gateb-001/site/unexpected.html"
    extra.write_text("unexpected", encoding="utf-8")
    with pytest.raises(RecoveryGuardError, match="RELEASE_ARTIFACT_SET_MISMATCH"):
        current_release(extra_root)


def test_release_and_pointer_symlinks_and_hardlinks_are_rejected(
    tmp_path: Path,
) -> None:
    pointer_root = tmp_path / "pointer-hardlink"
    release(pointer_root)
    pointer = pointer_root / "current.json"
    pointer_hardlink = pointer_root / "current-copy.json"
    pointer_hardlink.hardlink_to(pointer)
    with pytest.raises(RecoveryGuardError, match="PREVIEW_HARDLINK_FORBIDDEN"):
        release(pointer_root, release_id="gateb-002")

    pointer_symlink_root = tmp_path / "pointer-symlink"
    release(pointer_symlink_root)
    pointer_symlink = pointer_symlink_root / "current.json"
    saved_pointer = tmp_path / "saved-pointer.json"
    pointer_symlink.replace(saved_pointer)
    pointer_symlink.symlink_to(saved_pointer)
    with pytest.raises(RecoveryGuardError, match="PREVIEW_SYMLINK_FORBIDDEN"):
        release(pointer_symlink_root, release_id="gateb-002")

    symlink_root = tmp_path / "release-symlink"
    releases = symlink_root / "releases"
    releases.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (releases / "gateb-001").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RecoveryGuardError, match="PREVIEW_SYMLINK_FORBIDDEN"):
        release(symlink_root)

    artifact_root = tmp_path / "artifact-symlink"
    release(artifact_root)
    site_page = artifact_root / f"releases/gateb-001/site/{UID}.html"
    video_page = artifact_root / f"releases/gateb-001/video/{UID}.html"
    site_page.unlink()
    site_page.symlink_to(video_page)
    with pytest.raises(RecoveryGuardError, match="PREVIEW_SYMLINK_FORBIDDEN"):
        current_release(artifact_root)

    hardlink_root = tmp_path / "artifact-hardlink"
    release(hardlink_root)
    video_page = hardlink_root / f"releases/gateb-001/video/{UID}.html"
    (hardlink_root / "releases/gateb-001/video/card-copy.html").hardlink_to(
        video_page
    )
    with pytest.raises(RecoveryGuardError, match="PREVIEW_HARDLINK_FORBIDDEN"):
        current_release(hardlink_root)


def test_foundation_manifest_paths_and_hashes_are_strict(tmp_path: Path) -> None:
    with pytest.raises(RecoveryGuardError, match="INVALID_FOUNDATION_PATH"):
        release(tmp_path / "bad-foundation-path", foundation_manifest={"../x": "0" * 64})
    with pytest.raises(RecoveryGuardError, match="INVALID_FOUNDATION_DIGEST"):
        release(
            tmp_path / "bad-foundation-digest",
            foundation_manifest={"static/site.css": "not-a-sha256"},
        )


if __name__ == "__main__":
    direct_tests = sorted(
        (name, callback)
        for name, callback in globals().items()
        if name.startswith("test_") and callable(callback)
    )
    for name, callback in direct_tests:
        with tempfile.TemporaryDirectory(prefix="ua116-preview-test-") as temporary:
            callback(Path(temporary))
        print(f"{name}: PASS")
    print(f"preview dependency-free tests: PASS {len(direct_tests)}/{len(direct_tests)}")
