#!/usr/bin/env python3
"""Dependency-free local checks for the guarded atomic publisher candidate.

All writes target temporary directories.  Passing this runner is evidence only
for ``B_LOCAL_CANDIDATE`` and can never issue a full Gate B receipt.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import sqlite3
import sys
import tempfile
import traceback
import types
from pathlib import Path
from typing import Callable


PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

import atomic_publish as atomic_module
import integration_patcher
import spec_revision_store
from atomic_publish import atomic_publish
from recovery_core import (
    BASE_SHA,
    CONTRACT_ID,
    CONTRACT_VERSION,
    RecoveryGuardError,
    SpecFact,
    activate_candidate,
    build_candidate_revision,
    stable_digest,
)


UID = "UA-0017"
SYNTHETIC_VIN = "1HGBH41JXMN109186"
ARTIFACT_DIGEST = stable_digest("reviewed-stdlib-adapter-artifact-v1")


def _active_spec():
    facts = [
        SpecFact(
            field_key=f"field_{index:02d}",
            label_ru=f"Поле {index}",
            display_value=f"Значение {index}",
            confidence=1.0,
            evidence_count=1,
            source_domains=("official.example",),
        )
        for index in range(10)
    ]
    candidate = build_candidate_revision(
        UID,
        SYNTHETIC_VIN,
        "STDLIB-P1",
        facts,
        revision_id="stdlib-revision-1",
    )
    return activate_candidate(None, candidate)[1]


class _Controller:
    def __init__(self) -> None:
        self.consumed: set[str] = set()

    @staticmethod
    def verify(receipt) -> bool:
        return bool(
            receipt.get("trusted_signature") == "stdlib-controller-signature"
            and receipt.get("publisher_artifact_sha256") == ARTIFACT_DIGEST
        )

    def consume(self, nonce: str) -> bool:
        if nonce in self.consumed:
            return False
        self.consumed.add(nonce)
        return True


class _Harness:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.roots = (root / "mirror-a", root / "mirror-b")
        self.spec = _active_spec()
        for mirror in self.roots:
            mirror.mkdir()
            (mirror / "index.html").write_text(
                '<a href="UA-0001.html">old index</a>', encoding="utf-8"
            )
            (mirror / "katalog.html").write_text(
                '<a href="UA-0001.html">old catalog</a>', encoding="utf-8"
            )
            (mirror / "foundation.html").write_text(
                "immutable foundation", encoding="utf-8"
            )

    def adapter(self, publisher: Callable, adapter_id: str = "stdlib-adapter-v1"):
        return atomic_module.trusted_legacy_publisher(
            adapter_id,
            publisher,
            adapter_artifact_sha256=ARTIFACT_DIGEST,
        )

    def snapshot(self):
        return atomic_module._snapshot_roots(tuple(root.resolve() for root in self.roots))

    def page(self, *, extra: bool = False) -> str:
        rows = "".join(
            f'<div class="ua-addspec-row"><dt>{fact.label_ru}</dt>'
            f'<dd>{fact.display_value}{" WRONGUNIT" if extra else ""}</dd>'
            f'{"<span>EXTRA</span>" if extra else ""}</div>'
            for fact in self.spec.visible_facts
        )
        return (
            f'<html data-ua-card="{UID}"><section class="ua-additional-spec" '
            f'data-ua-spec-card="{UID}" '
            f'data-ua-spec-revision="{self.spec.revision_id}" '
            f'data-ua-spec-sha256="{self.spec.digest}">'
            f"{SYNTHETIC_VIN}{rows}</section></html>"
        )

    def write_valid(self) -> None:
        for mirror in self.roots:
            (mirror / f"{UID}.html").write_text(self.page(), encoding="utf-8")
            (mirror / f"{UID}-diag.html").write_text(
                f'<html data-ua-card="{UID}">{SYNTHETIC_VIN} diagnostic</html>',
                encoding="utf-8",
            )
            for name in ("index.html", "katalog.html"):
                old = (mirror / name).read_text(encoding="utf-8")
                (mirror / name).write_text(
                    old + f'<a href="{UID}.html">new card</a>', encoding="utf-8"
                )

    def gate_receipt(self, adapter, *, nonce: str) -> dict[str, object]:
        roots = tuple(root.resolve() for root in self.roots)
        now = dt.datetime.now(dt.timezone.utc)
        value: dict[str, object] = {
            "contract_id": CONTRACT_ID,
            "contract_version": CONTRACT_VERSION,
            "gate": "B",
            "status": "PASS",
            "production_touched": False,
            "production_write_attempts": 0,
            "target_uid": UID,
            "target_vin_sha256": self.spec.vin_sha256,
            "spec_digest": self.spec.digest,
            "spec_revision_id": self.spec.revision_id,
            "base_sha": BASE_SHA,
            "atomic_publish_code_sha256": atomic_module.atomic_publish_code_sha256(),
            "roots_before_digest": atomic_module._roots_digest(
                atomic_module._snapshot_roots(roots)
            ),
            "site_root_fingerprints": list(
                atomic_module._site_root_fingerprints(roots)
            ),
            "publisher_adapter_id": adapter.adapter_id,
            "publisher_artifact_sha256": adapter.adapter_artifact_sha256,
            "publisher_code_object_sha256": adapter.code_object_sha256,
            "publisher_side_effect_scope": adapter.side_effect_scope,
            "legacy_kwargs": {},
            "nonce": nonce,
            "issued_at": now.isoformat(),
            "expires_at": (now + dt.timedelta(minutes=5)).isoformat(),
            "trusted_signature": "stdlib-controller-signature",
        }
        value["evidence_digest"] = stable_digest(value)
        return value

    def invoke(
        self,
        adapter,
        controller: _Controller,
        *,
        nonce: str = "stdlib-nonce-00000001",
        receipt: dict[str, object] | None = None,
    ):
        return atomic_publish(
            self.roots,
            uid=UID,
            vin=SYNTHETIC_VIN,
            spec=self.spec,
            base_publish=adapter,
            verify_gate_b=controller.verify,
            consume_gate_nonce=controller.consume,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt=receipt or self.gate_receipt(adapter, nonce=nonce),
        )


def _expect_code(expected: str, callback: Callable[[], object]) -> RecoveryGuardError:
    try:
        callback()
    except RecoveryGuardError as exc:
        if exc.code != expected:
            raise AssertionError(f"expected {expected}, got {exc.code}: {exc}") from exc
        return exc
    raise AssertionError(f"expected guard {expected}")


def _case_deny_without_gates(root: Path) -> None:
    harness = _Harness(root)
    calls: list[str] = []

    def publisher(uid, **_kwargs):
        calls.append(uid)
        return True, "unexpected"

    adapter = harness.adapter(publisher)
    _expect_code(
        "PRODUCTION_EXPLICIT_ALLOW_REQUIRED",
        lambda: atomic_publish(
            harness.roots,
            uid=UID,
            vin=SYNTHETIC_VIN,
            spec=harness.spec,
            base_publish=adapter,
            verify_gate_b=lambda _receipt: False,
            consume_gate_nonce=lambda _nonce: False,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
        ),
    )
    assert not calls


def _case_trusted_gate_and_one_time_nonce(root: Path) -> None:
    harness = _Harness(root)
    controller = _Controller()
    calls: list[str] = []

    def publisher(uid, *, ua116_site_roots):
        calls.append(uid)
        harness.write_valid()
        return True, "ok"

    adapter = harness.adapter(publisher)
    receipt = harness.gate_receipt(adapter, nonce="one-time-nonce-0001")
    forged_controller = _Controller()
    _expect_code(
        "GATE_B_NOT_AUTHENTICATED",
        lambda: atomic_publish(
            harness.roots,
            uid=UID,
            vin=SYNTHETIC_VIN,
            spec=harness.spec,
            base_publish=adapter,
            verify_gate_b=lambda _receipt: False,
            consume_gate_nonce=forged_controller.consume,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt=receipt,
        ),
    )
    harness.invoke(adapter, controller, nonce="one-time-nonce-0001", receipt=receipt)
    second = harness.gate_receipt(adapter, nonce="one-time-nonce-0001")
    _expect_code(
        "GATE_NONCE_ALREADY_USED_OR_REJECTED",
        lambda: harness.invoke(
            adapter, controller, nonce="one-time-nonce-0001", receipt=second
        ),
    )
    assert calls == [UID]


def _case_valid_mirror_publish(root: Path) -> None:
    harness = _Harness(root)

    def publisher(uid, *, ua116_site_roots):
        assert tuple(ua116_site_roots) == tuple(
            str(mirror.resolve()) for mirror in harness.roots
        )
        harness.write_valid()
        return True, "published"

    adapter = harness.adapter(publisher)
    result = harness.invoke(adapter, _Controller())
    assert result.outcome == "PUBLISHED"
    assert result.publisher_artifact_sha256 == ARTIFACT_DIGEST
    final = harness.snapshot()
    assert final[0][f"{UID}.html"] == final[1][f"{UID}.html"]
    assert final[0]["foundation.html"] == final[1]["foundation.html"]


def _render_real_task099_page(
    harness: _Harness, crm_database: Path, spec_database: Path
) -> str:
    assert crm_database != spec_database
    spec_revision_store.stage_and_activate(
        spec_database,
        uid=UID,
        vin=SYNTHETIC_VIN,
        policy_version=harness.spec.policy_version,
        revision_id=harness.spec.revision_id,
        rows=harness.spec.facts,
    )
    with sqlite3.connect(crm_database) as connection:
        connection.execute(
            "CREATE TABLE cars("
            "auto_number TEXT PRIMARY KEY,vin TEXT,status TEXT,mileage_km INTEGER)"
        )
        connection.execute(
            "INSERT INTO cars(auto_number,vin,status,mileage_km) VALUES(?,?,?,?)",
            (UID, SYNTHETIC_VIN, "kr_bought", 12345),
        )
        connection.commit()

    source_path = (
        PACKAGE.parent / "task_099_site_crm_repair" / "ua_additional_spec.py"
    )
    patched_source = integration_patcher.patch_additional_spec(
        source_path.read_text(encoding="utf-8")
    )
    previous_database = os.environ.get("UA_ART_CRM_DB")
    previous_service = sys.modules.get("vin_spec_service")
    service = types.ModuleType("vin_spec_service")
    service.SPEC_DB = spec_database
    sys.modules["vin_spec_service"] = service
    os.environ["UA_ART_CRM_DB"] = str(crm_database)
    try:
        namespace = {
            "__name__": "ua099_atomic_publish_stdlib_fixture",
            "__file__": str(source_path),
        }
        exec(compile(patched_source, str(source_path), "exec"), namespace)
        assert Path(namespace["DB_PATH"]) == crm_database
        assert Path(namespace["_ua116_spec_db_path"]()) == spec_database

        # This intentionally has no artificial data-ua-card ancestor.  The
        # real Task099 output places the revision-bound disclosure immediately
        # before a sibling .ua-clean-vin[data-ua-card] block.
        base = (
            "<!doctype html><html><head></head><body><div class='page'>"
            f"<a href='{UID}-diag.html'>Диагностика</a>"
            "<a class='kn_kupit' data-ua-primary-action='1'>Задаток 500 $</a>"
            "<!--UA099_STAGE_START--><section data-ua-stage='1'>stage</section>"
            "<!--UA099_STAGE_END--></div></body></html>"
        )
        output = namespace["inject_public_spec"](base, UID)
    finally:
        if previous_database is None:
            os.environ.pop("UA_ART_CRM_DB", None)
        else:
            os.environ["UA_ART_CRM_DB"] = previous_database
        if previous_service is None:
            sys.modules.pop("vin_spec_service", None)
        else:
            sys.modules["vin_spec_service"] = previous_service
    assert "<details class='blok ua-additional-spec'" in output
    assert "<details class='blok ua-additional-spec' open" not in output
    assert f'data-ua-spec-card="{UID}"' in output
    assert output.index("ua-additional-spec") < output.index("ua-clean-vin")
    assert output.count("data-ua-card=") == 1
    return output


def _case_real_task099_disclosure(root: Path) -> None:
    harness = _Harness(root)
    rendered = _render_real_task099_page(
        harness,
        root / "realistic-crm.sqlite3",
        root / "realistic-spec.sqlite3",
    )

    def publish_real(uid, *, ua116_site_roots):
        for mirror in harness.roots:
            (mirror / f"{UID}.html").write_text(rendered, encoding="utf-8")
            (mirror / f"{UID}-diag.html").write_text(
                f'<html data-ua-card="{UID}">{SYNTHETIC_VIN} diagnostic</html>',
                encoding="utf-8",
            )
            for name in ("index.html", "katalog.html"):
                old = (mirror / name).read_text(encoding="utf-8")
                (mirror / name).write_text(
                    old + f'<a href="{UID}.html">new card</a>', encoding="utf-8"
                )
        return True, "real Task099 render"

    result = harness.invoke(
        harness.adapter(publish_real, "stdlib-real-task099-adapter"),
        _Controller(),
        nonce="stdlib-real-task099-nonce",
    )
    assert result.outcome == "PUBLISHED"
    valid_snapshot = harness.snapshot()

    hidden_mutations = (
        ("summary", "<summary>", "<summary aria-hidden='true'>"),
        (
            "body",
            "<div class='ua-addspec-body'>",
            "<div class='ua-addspec-body' style='display:none'>",
        ),
    )
    for number, (name, old, new) in enumerate(hidden_mutations, start=1):
        def hide_disclosure(uid, *, ua116_site_roots, _old=old, _new=new):
            forged = rendered.replace(_old, _new, 1)
            assert forged != rendered
            for mirror in harness.roots:
                (mirror / f"{UID}.html").write_text(forged, encoding="utf-8")
            return True, "hidden disclosure"

        _expect_code(
            "ATOMIC_PUBLISH_ROLLED_BACK",
            lambda: harness.invoke(
                harness.adapter(
                    hide_disclosure,
                    f"stdlib-real-task099-hidden-{number:02d}-adapter",
                ),
                _Controller(),
                nonce=f"stdlib-real-task099-hidden-nonce-{number:02d}",
            ),
        )
        assert harness.snapshot() == valid_snapshot


def _case_spec_integrity_before_publisher(root: Path) -> None:
    harness = _Harness(root)
    calls: list[str] = []
    gate_calls: list[str] = []

    def publisher(uid, *, ua116_site_roots):
        calls.append(uid)
        return True

    adapter = harness.adapter(publisher, "stdlib-integrity-adapter")
    corruptions = (
        (
            "SPEC_DIGEST_MISMATCH",
            dataclasses.replace(harness.spec, digest="0" * 64),
        ),
        (
            "SPEC_VISIBLE_COUNT_MISMATCH",
            dataclasses.replace(
                harness.spec,
                declared_visible_count=harness.spec.visible_count + 1,
            ),
        ),
        (
            "SPEC_FACTS_NONCANONICAL",
            dataclasses.replace(harness.spec, facts=tuple(reversed(harness.spec.facts))),
        ),
    )
    for expected, corrupted in corruptions:
        _expect_code(
            expected,
            lambda _spec=corrupted: atomic_publish(
                harness.roots,
                uid=UID,
                vin=SYNTHETIC_VIN,
                spec=_spec,
                base_publish=adapter,
                verify_gate_b=lambda _receipt: gate_calls.append("verify") or True,
                consume_gate_nonce=lambda _nonce: gate_calls.append("consume") or True,
                allow_production=True,
                owner_command="ПУБЛИКОВАТЬ UA-0017",
                gate_b_receipt={},
            ),
        )
    assert calls == []
    assert gate_calls == []


def _case_hidden_link_bypass(root: Path) -> None:
    harness = _Harness(root)
    before = harness.snapshot()

    def publisher(uid, *, ua116_site_roots):
        harness.write_valid()
        for mirror in harness.roots:
            (mirror / "katalog.html").write_text(
                '<!--<a href="UA-0001.html">old catalog</a>-->'
                f'<a href="{UID}.html">new</a>',
                encoding="utf-8",
            )
        return True, "bad"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(harness.adapter(publisher), _Controller()),
    )
    assert harness.snapshot() == before

    def external_target(uid, *, ua116_site_roots):
        harness.write_valid()
        for mirror in harness.roots:
            (mirror / "katalog.html").write_text(
                '<a href="UA-0001.html">old catalog</a>'
                f'<a href="https://evil.invalid/{UID}.html">new</a>',
                encoding="utf-8",
            )
        return True, "external target is not a local card link"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(
            harness.adapter(external_target, "stdlib-external-link-adapter"),
            _Controller(), nonce="stdlib-external-link-nonce",
        ),
    )
    assert harness.snapshot() == before

    def closed_details(uid, *, ua116_site_roots):
        harness.write_valid()
        for mirror in harness.roots:
            (mirror / "katalog.html").write_text(
                '<details><a href="UA-0001.html">old catalog</a>'
                f'<a href="{UID}.html">new</a></details>',
                encoding="utf-8",
            )
        return True, "links hidden in closed details"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(
            harness.adapter(closed_details, "stdlib-closed-details-adapter"),
            _Controller(),
            nonce="stdlib-closed-details-nonce",
        ),
    )
    assert harness.snapshot() == before


def _case_forged_spec_content(root: Path) -> None:
    harness = _Harness(root)
    before = harness.snapshot()

    def publisher(uid, *, ua116_site_roots):
        harness.write_valid()
        for mirror in harness.roots:
            (mirror / f"{UID}.html").write_text(
                harness.page(extra=True), encoding="utf-8"
            )
        return True, "bad"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(harness.adapter(publisher), _Controller()),
    )
    assert harness.snapshot() == before

    def wrong_spec_card(uid, *, ua116_site_roots):
        harness.write_valid()
        forged = harness.page().replace(
            f'data-ua-spec-card="{UID}"',
            'data-ua-spec-card="UA-00170"',
            1,
        )
        for mirror in harness.roots:
            (mirror / f"{UID}.html").write_text(forged, encoding="utf-8")
        return True, "wrong spec owner"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(
            harness.adapter(wrong_spec_card, "stdlib-wrong-spec-card-adapter"),
            _Controller(),
            nonce="stdlib-wrong-spec-card-nonce",
        ),
    )
    assert harness.snapshot() == before

    duplicate_attributes = (
        (
            "card",
            f'<html data-ua-card="{UID}"',
            f'<html data-ua-card="UA-00170" data-ua-card="{UID}"',
        ),
        (
            "style",
            '<section class="ua-additional-spec"',
            '<section style="display:none" style="" class="ua-additional-spec"',
        ),
    )
    for number, (name, old, new) in enumerate(duplicate_attributes, start=1):
        def duplicate_security_attr(
            uid, *, ua116_site_roots, _old=old, _new=new
        ):
            harness.write_valid()
            forged = harness.page().replace(_old, _new, 1)
            assert forged != harness.page()
            for mirror in harness.roots:
                (mirror / f"{UID}.html").write_text(forged, encoding="utf-8")
            return True, "browser/parser attribute differential"

        _expect_code(
            "ATOMIC_PUBLISH_ROLLED_BACK",
            lambda: harness.invoke(
                harness.adapter(
                    duplicate_security_attr,
                    f"stdlib-duplicate-attribute-{number:02d}-adapter",
                ),
                _Controller(),
                nonce=f"stdlib-duplicate-attribute-nonce-{number:02d}",
            ),
        )
        assert harness.snapshot() == before

    hidden_wrappers = (
        ("hidden-attribute", '<div hidden>{section}</div>'),
        ("aria-hidden", '<div aria-hidden="true">{section}</div>'),
        ("inert-ancestor", '<div inert>{section}</div>'),
        ("display-none", '<div style="display: none">{section}</div>'),
        ("visibility-hidden", '<div style="visibility: hidden">{section}</div>'),
        ("opacity-zero", '<div style="opacity: 0">{section}</div>'),
        ("closed-details", '<details>{section}</details>'),
    )
    for number, (name, wrapper) in enumerate(hidden_wrappers, start=1):
        def hidden_section(
            uid,
            *,
            ua116_site_roots,
            _wrapper=wrapper,
        ):
            harness.write_valid()
            page = harness.page()
            prefix = f'<html data-ua-card="{UID}">' 
            section = page[len(prefix) : -len("</html>")]
            hidden = (
                prefix
                + f"<p>{SYNTHETIC_VIN}</p>"
                + _wrapper.format(section=section)
                + "</html>"
            )
            # Both mirrors contain the exact same forged page, so rejection
            # proves visible-section validation rather than mirror divergence.
            for mirror in harness.roots:
                (mirror / f"{UID}.html").write_text(hidden, encoding="utf-8")
            return True, "hidden forged spec"

        _expect_code(
            "ATOMIC_PUBLISH_ROLLED_BACK",
            lambda: harness.invoke(
                harness.adapter(
                    hidden_section, f"stdlib-hidden-spec-{number:02d}-adapter"
                ),
                _Controller(),
                nonce=f"stdlib-hidden-spec-nonce-{number:02d}",
            ),
        )
        assert harness.snapshot() == before


def _case_publisher_exception_and_false_tuple(root: Path) -> None:
    harness = _Harness(root)
    before = harness.snapshot()

    def crashing(uid, *, ua116_site_roots):
        (harness.roots[0] / f"{UID}.html").write_text("partial", encoding="utf-8")
        raise RuntimeError("injected legacy exception")

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(harness.adapter(crashing), _Controller()),
    )
    assert harness.snapshot() == before

    def false_tuple(uid, *, ua116_site_roots):
        (harness.roots[0] / f"{UID}.html").write_text("partial", encoding="utf-8")
        return False, "legacy failure"

    _expect_code(
        "ATOMIC_PUBLISH_ROLLED_BACK",
        lambda: harness.invoke(
            harness.adapter(false_tuple, "stdlib-false-adapter"), _Controller()
        ),
    )
    assert harness.snapshot() == before


def _case_unsafe_post_snapshot_bounded_rollback(root: Path) -> None:
    harness = _Harness(root)
    before = harness.snapshot()
    outside = root / "outside.html"
    outside.write_text("outside unchanged", encoding="utf-8")

    def unsafe(uid, *, ua116_site_roots):
        (harness.roots[0] / f"{UID}.html").symlink_to(outside)
        return True, "unsafe"

    _expect_code(
        "POST_PUBLISH_SNAPSHOT_FAILED_ALLOWED_ARTIFACTS_ROLLED_BACK",
        lambda: harness.invoke(harness.adapter(unsafe), _Controller()),
    )
    assert harness.snapshot() == before
    assert outside.read_text(encoding="utf-8") == "outside unchanged"


def _case_untrusted_adapter_rejected(root: Path) -> None:
    harness = _Harness(root)
    calls: list[str] = []

    def raw(uid, **_kwargs):
        calls.append(uid)
        return True

    _expect_code(
        "UNTRUSTED_LEGACY_PUBLISHER",
        lambda: atomic_publish(
            harness.roots,
            uid=UID,
            vin=SYNTHETIC_VIN,
            spec=harness.spec,
            base_publish=raw,
            verify_gate_b=lambda _receipt: True,
            consume_gate_nonce=lambda _nonce: True,
            allow_production=True,
            owner_command="ПУБЛИКОВАТЬ UA-0017",
            gate_b_receipt={},
        ),
    )
    assert not calls


def run() -> dict[str, object]:
    checks: list[dict[str, str]] = []
    cases = (
        ("deny_without_gates", _case_deny_without_gates),
        ("trusted_verifier_and_one_time_nonce", _case_trusted_gate_and_one_time_nonce),
        ("valid_mirror_publish_from_snapshot", _case_valid_mirror_publish),
        ("real_task099_closed_disclosure_publish", _case_real_task099_disclosure),
        ("spec_integrity_before_publisher", _case_spec_integrity_before_publisher),
        ("comment_hidden_link_bypass_rejected", _case_hidden_link_bypass),
        ("forged_spec_extra_content_rejected", _case_forged_spec_content),
        ("publisher_exception_and_false_tuple_rollback", _case_publisher_exception_and_false_tuple),
        ("unsafe_post_snapshot_bounded_rollback", _case_unsafe_post_snapshot_bounded_rollback),
        ("untrusted_adapter_rejected", _case_untrusted_adapter_rejected),
    )
    with tempfile.TemporaryDirectory(prefix="ua116-atomic-stdlib-") as temporary:
        suite_root = Path(temporary)
        for index, (name, callback) in enumerate(cases):
            case_root = suite_root / f"case-{index:02d}"
            case_root.mkdir()
            try:
                callback(case_root)
            except Exception as exc:
                checks.append(
                    {
                        "name": name,
                        "status": "FAIL",
                        "error": type(exc).__name__ + ":" + str(exc),
                        "traceback": traceback.format_exc(limit=5),
                    }
                )
            else:
                checks.append({"name": name, "status": "PASS"})
    passed = sum(item["status"] == "PASS" for item in checks)
    result: dict[str, object] = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "gate": "B_LOCAL_CANDIDATE",
        "status": "PASS" if passed == len(checks) else "FAIL",
        "passed": passed,
        "total": len(checks),
        "checks": checks,
        "production_touched": False,
        "production_write_attempts": 0,
        "note": "Temporary roots only; not a full Gate B or Production authorization.",
    }
    result["evidence_digest"] = stable_digest(result)
    return result


if __name__ == "__main__":
    outcome = run()
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if outcome["status"] == "PASS" else 1)
