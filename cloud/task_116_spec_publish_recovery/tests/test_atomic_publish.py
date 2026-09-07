from __future__ import annotations

import dataclasses
import datetime as dt
import inspect
from pathlib import Path

import pytest

import atomic_publish as atomic_module
from atomic_publish import atomic_publish
from recovery_core import (
    RecoveryGuardError,
    SpecFact,
    activate_candidate,
    build_candidate_revision,
    stable_digest,
)


VIN = "1HGBH41JXMN109186"
UID = "UA-0017"
UNIT_ADAPTER_ARTIFACT_SHA256 = stable_digest("reviewed-unit-adapter-artifact-v1")


def adapter_for(publisher, adapter_id: str = "unit-adapter-v1"):
    return atomic_module.trusted_legacy_publisher(
        adapter_id,
        publisher,
        adapter_artifact_sha256=UNIT_ADAPTER_ARTIFACT_SHA256,
    )


def active_spec():
    rows = [
        SpecFact(
            field_key=f"field_{number}",
            label_ru=f"Поле {number}",
            display_value=str(number),
            confidence=1.0,
            evidence_count=1,
            source_domains=("official.example",),
        )
        for number in range(10)
    ]
    candidate = build_candidate_revision(
        UID, VIN, "P1", rows, revision_id="revision-production-1"
    )
    return activate_candidate(None, candidate)[1]


def valid_page(spec, uid: str = UID) -> str:
    rows = "".join(
        f'<div class="ua-addspec-row"><dt>{fact.label_ru}</dt>'
        f'<dd>{fact.display_value}</dd></div>'
        for fact in spec.visible_facts
    )
    return (
        f'<html data-ua-card="{uid}"><section class="ua-additional-spec" '
        f'data-ua-spec-card="{uid}" '
        f'data-ua-spec-revision="{spec.revision_id}" '
        f'data-ua-spec-sha256="{spec.digest}">{VIN}{rows}</section></html>'
    )


def seed_roots(tmp_path: Path) -> tuple[Path, Path]:
    roots = (tmp_path / "mirror-a", tmp_path / "mirror-b")
    for root in roots:
        root.mkdir()
        (root / "index.html").write_text(
            '<a href="UA-0001.html">old index</a>', encoding="utf-8"
        )
        (root / "katalog.html").write_text(
            '<a href="UA-0001.html">old catalog</a>', encoding="utf-8"
        )
        (root / "unrelated.html").write_text("foundation", encoding="utf-8")
    return roots


def snapshot_bytes(roots: tuple[Path, Path]):
    return {
        (number, path.relative_to(root).as_posix()): path.read_bytes()
        for number, root in enumerate(roots)
        for path in root.rglob("*.html")
    }


def write_valid_release(roots: tuple[Path, Path], spec) -> None:
    for root in roots:
        (root / f"{UID}.html").write_text(valid_page(spec), encoding="utf-8")
        (root / f"{UID}-diag.html").write_text(
            f'<html data-ua-card="{UID}">{VIN} diagnostic</html>',
            encoding="utf-8",
        )
        for name in ("katalog.html", "index.html"):
            old = (root / name).read_text(encoding="utf-8")
            (root / name).write_text(
                old + f'<a href="{UID}.html?v=1">card</a>', encoding="utf-8"
            )


def gate_b_receipt(roots, spec, adapter, legacy_kwargs=None):
    resolved = tuple(root.resolve() for root in roots)
    snapshots = atomic_module._snapshot_roots(resolved)
    now = dt.datetime.now(dt.timezone.utc)
    value = {
        "contract_id": "UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001",
        "contract_version": "1.0",
        "gate": "B",
        "status": "PASS",
        "production_touched": False,
        "production_write_attempts": 0,
        "target_uid": UID,
        "target_vin_sha256": spec.vin_sha256,
        "spec_digest": spec.digest,
        "spec_revision_id": spec.revision_id,
        "base_sha": atomic_module.BASE_SHA,
        "atomic_publish_code_sha256": atomic_module.atomic_publish_code_sha256(),
        "roots_before_digest": atomic_module._roots_digest(snapshots),
        "site_root_fingerprints": list(
            atomic_module._site_root_fingerprints(resolved)
        ),
        "publisher_adapter_id": adapter.adapter_id,
        "publisher_artifact_sha256": adapter.adapter_artifact_sha256,
        "publisher_code_object_sha256": adapter.code_object_sha256,
        "publisher_side_effect_scope": adapter.side_effect_scope,
        "legacy_kwargs": dict(legacy_kwargs or {}),
        "nonce": "test-nonce-00000001",
        "issued_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(minutes=5)).isoformat(),
        "trusted_signature": "unit-controller-signature",
    }
    value["evidence_digest"] = stable_digest(value)
    return value


def call(roots, tmp_path, spec, publisher, **overrides):
    adapter = (
        publisher
        if type(publisher) is atomic_module.TrustedLegacyPublisher
        else adapter_for(publisher)
    )
    used_nonces = set()

    def consume(nonce):
        if nonce in used_nonces:
            return False
        used_nonces.add(nonce)
        return True

    values = {
        "uid": UID,
        "vin": VIN,
        "spec": spec,
        "base_publish": adapter,
        "verify_gate_b": lambda receipt: (
            receipt.get("trusted_signature") == "unit-controller-signature"
            and receipt.get("publisher_artifact_sha256")
            == UNIT_ADAPTER_ARTIFACT_SHA256
        ),
        "consume_gate_nonce": consume,
        "allow_production": True,
        # U+2011 exercises the exact owner's non-breaking-hyphen spelling.
        "owner_command": "ПУБЛИКОВАТЬ UA‑0017",
        "gate_b_receipt": gate_b_receipt(roots, spec, adapter),
    }
    values.update(overrides)
    return atomic_publish(roots, **values)


def test_default_deny_does_not_invoke_legacy_publisher(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    called = []
    with pytest.raises(RecoveryGuardError, match="PRODUCTION_EXPLICIT_ALLOW_REQUIRED"):
        atomic_publish(
            roots,
            uid=UID,
            vin=VIN,
            spec=active_spec(),
            base_publish=lambda uid, **kwargs: called.append(uid),
            verify_gate_b=lambda receipt: False,
            consume_gate_nonce=lambda nonce: False,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
        )
    assert called == []


@pytest.mark.parametrize(
    ("expected", "corrupt"),
    [
        ("SPEC_DIGEST_MISMATCH", "digest"),
        ("SPEC_VISIBLE_COUNT_MISMATCH", "count"),
        ("SPEC_FACTS_NONCANONICAL", "facts"),
    ],
)
def test_spec_integrity_is_checked_before_gate_or_publisher(
    tmp_path: Path, expected: str, corrupt: str
) -> None:
    roots = seed_roots(tmp_path)
    original = active_spec()
    if corrupt == "digest":
        spec = dataclasses.replace(original, digest="0" * 64)
    elif corrupt == "count":
        spec = dataclasses.replace(
            original, declared_visible_count=original.visible_count + 1
        )
    else:
        spec = dataclasses.replace(original, facts=tuple(reversed(original.facts)))
    calls: list[str] = []

    def publisher(uid, **kwargs):
        calls.append("publisher")
        return True

    with pytest.raises(RecoveryGuardError, match=expected):
        atomic_publish(
            roots,
            uid=UID,
            vin=VIN,
            spec=spec,
            base_publish=adapter_for(publisher),
            verify_gate_b=lambda receipt: calls.append("verify") or True,
            consume_gate_nonce=lambda nonce: calls.append("consume") or True,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt={},
        )
    assert calls == []


def test_exact_owner_command_and_proba_are_fail_closed(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    called = []
    with pytest.raises(RecoveryGuardError, match="OWNER_PUBLISH_COMMAND_REQUIRED"):
        call(
            roots,
            tmp_path,
            spec,
            lambda uid, **kwargs: called.append(uid),
            owner_command="publish",
        )
    with pytest.raises(RecoveryGuardError, match="PROBA_MODE_FORBIDDEN"):
        call(
            roots,
            tmp_path,
            spec,
            lambda uid, **kwargs: called.append(uid),
            legacy_kwargs={"proba": True},
        )
    def unsafe_default(uid, *, ua116_site_roots, proba=True):
        called.append(uid)

    partial = adapter_for(unsafe_default, "unsafe-proba-adapter")
    with pytest.raises(RecoveryGuardError, match="PROBA_MODE_FORBIDDEN"):
        call(roots, tmp_path, spec, partial)
    assert called == []


def test_local_or_tampered_gate_b_cannot_unlock_production(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    called = []

    def publisher(uid, **kwargs):
        called.append(uid)

    adapter = adapter_for(publisher)
    local = gate_b_receipt(roots, spec, adapter)
    local["gate"] = "B_LOCAL_SANDBOX"
    local["evidence_digest"] = stable_digest(
        {key: value for key, value in local.items() if key != "evidence_digest"}
    )
    with pytest.raises(RecoveryGuardError, match="GATE_B_RECEIPT_MISMATCH"):
        call(
            roots,
            tmp_path,
            spec,
            adapter,
            gate_b_receipt=local,
        )
    tampered = gate_b_receipt(roots, spec, adapter)
    tampered["spec_digest"] = "0" * 64
    with pytest.raises(RecoveryGuardError, match="GATE_B_EVIDENCE_DIGEST_INVALID"):
        call(
            roots,
            tmp_path,
            spec,
            adapter,
            gate_b_receipt=tampered,
        )
    assert called == []


def test_production_downgrade_and_path_controls_are_not_exposed() -> None:
    parameters = inspect.signature(atomic_publish).parameters
    assert "target_relative_path" not in parameters
    assert "diagnostic_relative_path" not in parameters
    assert "catalog_relative_path" not in parameters
    assert "index_relative_path" not in parameters
    assert "require_mirror_equality" not in parameters
    assert "minimum_listing_size_ratio" not in parameters
    assert "lock_path" not in parameters


def test_valid_publication_checks_both_roots_and_preserves_foundation(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    assert atomic_module.canonical_publish_lock(roots) == atomic_module.canonical_publish_lock(
        tuple(reversed(roots))
    )

    def publisher(uid, *, ua116_site_roots):
        assert tuple(ua116_site_roots) == tuple(str(root.resolve()) for root in roots)
        write_valid_release(roots, spec)
        return True, "ok"

    receipt = call(roots, tmp_path, spec, publisher)
    assert receipt.target_uid == UID
    assert receipt.outcome == "PUBLISHED"
    assert receipt.spec_digest == spec.digest
    assert receipt.production_write_attempts == 1
    assert all((root / "unrelated.html").read_text() == "foundation" for root in roots)
    assert all(f"root{number}:{UID}.html" in receipt.changed_html for number in (1, 2))


@pytest.mark.parametrize(
    "failure_kind",
    [
        "prefix",
        "identity",
        "stale_rows",
        "extra_spec_text",
        "wrong_spec_card",
        "duplicate_card_attribute",
        "duplicate_style_attribute",
        "hidden_spec_section",
        "catalog_wipe",
        "hidden_catalog",
        "closed_details_catalog",
        "bad_diagnostic",
        "comment_diagnostic",
        "executable_mode",
        "world_writable_mode",
        "second_root",
    ],
)
def test_any_validation_failure_rolls_back_both_complete_trees(
    tmp_path: Path, failure_kind: str
) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    before = snapshot_bytes(roots)

    def broken(_uid, *, ua116_site_roots):
        write_valid_release(roots, spec)
        if failure_kind == "prefix":
            # Must never be accepted as an artifact for UA-0017.
            (roots[0] / "UA-00170.html").write_text("collision", encoding="utf-8")
        elif failure_kind == "identity":
            (roots[0] / f"{UID}.html").write_text(
                "<html>Открыть все автомобили</html>", encoding="utf-8"
            )
        elif failure_kind == "stale_rows":
            rows = '<div class="ua-addspec-row">stale</div>' * 10
            (roots[0] / f"{UID}.html").write_text(
                f'<main data-ua-card="{UID}" '
                f'data-ua-spec-revision="{spec.revision_id}" '
                f'data-ua-spec-sha256="{spec.digest}">{VIN}{rows}</main>',
                encoding="utf-8",
            )
        elif failure_kind == "extra_spec_text":
            rows = "".join(
                f'<div class="ua-addspec-row"><dt>{fact.label_ru}</dt>'
                f'<dd>{fact.display_value} WRONGUNIT</dd><span>EXTRA</span></div>'
                for fact in spec.visible_facts
            )
            for root in roots:
                (root / f"{UID}.html").write_text(
                    f'<html data-ua-card="{UID}"><section class="ua-additional-spec" '
                    f'data-ua-spec-card="{UID}" '
                    f'data-ua-spec-revision="{spec.revision_id}" '
                    f'data-ua-spec-sha256="{spec.digest}">{VIN}{rows}</section></html>',
                    encoding="utf-8",
                )
        elif failure_kind == "hidden_spec_section":
            hidden = valid_page(spec).replace(
                f'<html data-ua-card="{UID}"><section class="ua-additional-spec"',
                f'<html data-ua-card="{UID}"><p>{VIN}</p>'
                '<section aria-hidden="true" class="ua-additional-spec"',
                1,
            )
            for root in roots:
                (root / f"{UID}.html").write_text(hidden, encoding="utf-8")
        elif failure_kind == "wrong_spec_card":
            forged = valid_page(spec).replace(
                f'data-ua-spec-card="{UID}"',
                'data-ua-spec-card="UA-00170"',
                1,
            )
            for root in roots:
                (root / f"{UID}.html").write_text(forged, encoding="utf-8")
        elif failure_kind == "duplicate_card_attribute":
            forged = valid_page(spec).replace(
                f'<html data-ua-card="{UID}"',
                f'<html data-ua-card="UA-00170" data-ua-card="{UID}"',
                1,
            )
            for root in roots:
                (root / f"{UID}.html").write_text(forged, encoding="utf-8")
        elif failure_kind == "duplicate_style_attribute":
            forged = valid_page(spec).replace(
                '<section class="ua-additional-spec"',
                '<section style="display:none" style="" class="ua-additional-spec"',
                1,
            )
            for root in roots:
                (root / f"{UID}.html").write_text(forged, encoding="utf-8")
        elif failure_kind == "catalog_wipe":
            (roots[0] / "katalog.html").write_text(
                f'<a href="{UID}.html">only target remains</a>', encoding="utf-8"
            )
        elif failure_kind == "hidden_catalog":
            for root in roots:
                (root / "katalog.html").write_text(
                    '<!--<a href="UA-0001.html">old catalog</a>-->'
                    f'<a href="{UID}.html">target</a>',
                    encoding="utf-8",
                )
        elif failure_kind == "closed_details_catalog":
            for root in roots:
                (root / "katalog.html").write_text(
                    '<details><a href="UA-0001.html">old catalog</a>'
                    f'<a href="{UID}.html">target</a></details>',
                    encoding="utf-8",
                )
        elif failure_kind == "bad_diagnostic":
            (roots[0] / f"{UID}-diag.html").write_text(
                '<html data-ua-card="UA-00170">wrong</html>', encoding="utf-8"
            )
        elif failure_kind == "comment_diagnostic":
            (roots[0] / f"{UID}-diag.html").write_text(
                f'<!--<main data-ua-card="{UID}">{VIN}</main>--><html></html>',
                encoding="utf-8",
            )
        elif failure_kind == "executable_mode":
            (roots[0] / f"{UID}.html").chmod(0o755)
        elif failure_kind == "world_writable_mode":
            (roots[0] / f"{UID}.html").chmod(0o646)
        else:
            (roots[1] / "katalog.html").write_text(
                '<a href="UA-00170.html">wrong</a>', encoding="utf-8"
            )
        return True, "ok"

    with pytest.raises(RecoveryGuardError, match="ATOMIC_PUBLISH_ROLLED_BACK"):
        call(roots, tmp_path, spec, broken)
    assert snapshot_bytes(roots) == before
    assert not (roots[0] / "UA-00170.html").exists()


def test_legacy_exception_rolls_back_partial_output(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    before = snapshot_bytes(roots)

    def crashes(_uid, *, ua116_site_roots):
        (roots[0] / f"{UID}.html").write_text("partial", encoding="utf-8")
        (roots[1] / "index.html").write_text("partial", encoding="utf-8")
        raise RuntimeError("legacy crash")

    with pytest.raises(RecoveryGuardError, match="ATOMIC_PUBLISH_ROLLED_BACK"):
        call(roots, tmp_path, spec, crashes)
    assert snapshot_bytes(roots) == before


def test_legacy_false_tuple_is_failure_and_rolls_back(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    before = snapshot_bytes(roots)

    def reports_failure(_uid, *, ua116_site_roots):
        (roots[0] / f"{UID}.html").write_text("partial", encoding="utf-8")
        return False, "legacy error"

    with pytest.raises(RecoveryGuardError, match="ATOMIC_PUBLISH_ROLLED_BACK"):
        call(roots, tmp_path, spec, reports_failure)
    assert snapshot_bytes(roots) == before


def test_rollback_cas_refuses_to_clobber_noncooperating_writer(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    resolved = tuple(root.resolve() for root in roots)
    before = atomic_module._snapshot_roots(resolved)
    (roots[0] / "index.html").write_text("publisher value", encoding="utf-8")
    captured_after = atomic_module._snapshot_roots(resolved)
    (roots[0] / "index.html").write_text("concurrent value", encoding="utf-8")
    with pytest.raises(RecoveryGuardError, match="ROLLBACK_CONCURRENT_CHANGE_DETECTED"):
        atomic_module._restore_snapshots(resolved, before, captured_after)
    assert (roots[0] / "index.html").read_text() == "concurrent value"


def test_html_hardlink_is_rejected_before_legacy_call(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    outside = tmp_path / "outside.html"
    outside.write_text("outside", encoding="utf-8")
    (roots[0] / "linked.html").hardlink_to(outside)
    called = []

    def publisher(uid, **kwargs):
        called.append(uid)

    with pytest.raises(RecoveryGuardError, match="HTML_HARDLINK_FORBIDDEN"):
        atomic_publish(
            roots,
            uid=UID,
            vin=VIN,
            spec=active_spec(),
            base_publish=adapter_for(publisher),
            verify_gate_b=lambda receipt: True,
            consume_gate_nonce=lambda nonce: True,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt={},
        )
    assert called == []


def test_unsafe_post_snapshot_attempts_bounded_allowed_rollback(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    outside = tmp_path / "outside-target.html"
    outside.write_text("outside stays untouched", encoding="utf-8")
    before = snapshot_bytes(roots)

    def creates_symlink(uid, *, ua116_site_roots):
        (roots[0] / f"{uid}.html").symlink_to(outside)
        return True, "unsafe output"

    with pytest.raises(
        RecoveryGuardError,
        match="POST_PUBLISH_SNAPSHOT_FAILED_ALLOWED_ARTIFACTS_ROLLED_BACK",
    ):
        call(roots, tmp_path, spec, creates_symlink)
    assert snapshot_bytes(roots) == before
    assert not (roots[0] / f"{UID}.html").exists()
    assert outside.read_text(encoding="utf-8") == "outside stays untouched"


def test_trusted_verifier_and_nonce_consumer_are_enforced(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    called = []

    def publisher(uid, **kwargs):
        called.append(uid)

    with pytest.raises(RecoveryGuardError, match="GATE_B_NOT_AUTHENTICATED"):
        call(
            roots,
            tmp_path,
            spec,
            publisher,
            verify_gate_b=lambda receipt: False,
        )
    with pytest.raises(RecoveryGuardError, match="GATE_NONCE_ALREADY_USED_OR_REJECTED"):
        call(
            roots,
            tmp_path,
            spec,
            publisher,
            consume_gate_nonce=lambda nonce: False,
        )
    assert called == []


def test_raw_callable_is_not_a_trusted_adapter(tmp_path: Path) -> None:
    roots = seed_roots(tmp_path)
    spec = active_spec()
    called = []
    with pytest.raises(RecoveryGuardError, match="UNTRUSTED_LEGACY_PUBLISHER"):
        atomic_publish(
            roots,
            uid=UID,
            vin=VIN,
            spec=spec,
            base_publish=lambda uid, **kwargs: called.append(uid),
            verify_gate_b=lambda receipt: True,
            consume_gate_nonce=lambda nonce: True,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt={},
        )
    assert called == []
