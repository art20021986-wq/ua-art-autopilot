from __future__ import annotations

import ast
import dataclasses
import json
import os
import sys
import types
from pathlib import Path

import pytest

import integration_patcher
from integration_patcher import MARKER, SEAL_PREFIX, main, patch_bundle
from recovery_core import RecoveryGuardError, SpecFact, build_candidate_revision


CARS_UI = r'''
async def apply_value(card_id, field, raw, actor_id):
    value = (raw or "").strip()
    if field == "vin":
        vin = value.upper().replace(" ", "")
        ok, msg = S.check_vin(vin)
        if not ok:
            return False, "bad"
        set_field(card_id, field, vin, actor_id)
        return True, "Записано: %s" % vin
    return True, "ok"

async def stage_menu(update, context):
    card = {"status": "x"}
    cid = 1
    rows = []
    for number, _name in S.STAGES:
        pair = [InlineKeyboardButton(label, callback_data="car_setstage:%d:%s" % (cid, code))
                for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]
        rows.append(pair)

async def stage_set(update, context):
    q = update.callback_query
    _, cid, code = q.data.split(":")
    cid = int(cid)
    set_field(cid, "status", code, q.from_user.id)

async def toggle_publish(update, context):
    q = update.callback_query
    cid = 1
    card = {"auto_number": "UA-0017"}
    novoe = 1
    db.update_card_field("cars", cid, "published", novoe, q.from_user.id)
    if novoe:
        try:
            import publikaciya
            ok, text = publikaciya.opublikovat(card.get("auto_number"))
            await q.message.reply_text(text)
        except Exception:
            pass

async def preview(update, context):
    q = update.callback_query
    card = {"auto_number": "UA-0017"}
    try:
        import publikaciya as _pub
        _pub.opublikovat(card.get("auto_number"))
    except Exception:
        pass
    raise ApplicationHandlerStop

def register(app):
    pass
'''

KONTEYNER = r'''
async def gde_mashina(update, context):
    rows = []
    for nomer_etapa, _nazv in S.STAGES:
        pary = [InlineKeyboardButton(label)
                for code, (stage_no, label) in S.STATUSES.items()
                if stage_no == nomer_etapa]
        rows.append(pary)
'''

SOURCE_POLICY = r'''
POLICY_VERSION = "UA111-10SRC-V3"
def enrich(profile):
    minimum_facts = 10 if profile else 4
    return minimum_facts
'''

VIN_SERVICE = r'''
def utc_now():
    return "now"
def connect_spec(readonly):
    return None
class source_policy:
    POLICY_VERSION = "P"
def _process_claimed(
    job):
    try:
        uid = "UA-0017"
        vin = "1HGBH41JXMN109186"
        facts = []
        result = {"status": "READY"}
        written = _store_facts(uid, facts)
        status = "READY" if result.get("status") == "READY" and written >= 1 else "NEEDS_REVIEW"
        card = {}
        sync_status, sync_detail = _refresh_published(card) if written >= 1 else ("NOT_REQUIRED", "нет подтверждённых фактов")
        return status
    except Exception:
        return "FAILED"
def process_card_now():
    one = "AND status IN ('NEEDS_REVIEW','FAILED','READY')"
    two = "AND status IN ('NEEDS_REVIEW','FAILED','READY')"
    return one + two
class Stop:
    def is_set(self):
        return True
    def wait(self, seconds):
        return None
_stop_event = Stop()
SCAN_SECONDS = 30
WORKER_NAME = "worker"
def migrate_legacy_once(): pass
def recover_interrupted_jobs(): pass
def scan_new_vins(): pass
def process_one(): pass
def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            migrate_legacy_once()
            recover_interrupted_jobs()
            scan_new_vins()
            process_one()
        except Exception:
            # Deliberately fail the current cycle only; each job keeps its own
            # retry/error state and the CRM bot must remain available.
            pass
        _stop_event.wait(SCAN_SECONDS)
def enqueue_card(card, *, force=False): pass
def start_worker(): pass
if __name__ == "__main__":
    pass
'''

ADDITIONAL = r'''
SPEC_DB = "spec.db"
def canonical_uid(value): return value
def _car_vin(value): return "1HGBH41JXMN109186"
def fetch_specs(value): return []
def inject_public_spec(source, value):
    rows = fetch_specs(value)
    rendered = "".join(
        "<div class='ua-addspec-row'><dt>%s</dt><dd>%s</dd></div>" %
        (row["label_ru"], row["field_value"])
        for row in rows)
    return (
        "<main data-ua-card='%s'>%s"
        "<details class='blok ua-additional-spec'>%s</details></main>" %
        (canonical_uid(value), _car_vin(value), rendered))
'''


def write_fixture(root: Path) -> None:
    values = {
        "cars_ui.py": CARS_UI,
        "konteyner.py": KONTEYNER,
        "source_policy.py": SOURCE_POLICY,
        "vin_spec_service.py": VIN_SERVICE,
        "ua_additional_spec.py": ADDITIONAL,
    }
    for name, value in values.items():
        (root / name).write_text(value, encoding="utf-8")


def test_fresh_source_patch_is_compilable_idempotent_and_scoped(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    receipt = patch_bundle(tmp_path)
    assert all(receipt[name]["changed"] for name in receipt if name.endswith(".py"))
    for name in ("cars_ui.py", "konteyner.py", "source_policy.py", "vin_spec_service.py", "ua_additional_spec.py"):
        value = (tmp_path / name).read_text(encoding="utf-8")
        compile(value, name, "exec")
        assert MARKER in value
        assert value.rstrip().splitlines()[-1].startswith(SEAL_PREFIX)
    cars = (tmp_path / "cars_ui.py").read_text(encoding="utf-8")
    assert ".opublikovat" not in cars
    assert "доверенным TASK116 release-controller" in cars
    assert "await _ua116_asyncio.wait_for(" in cars
    assert "prepare_for_publish_async" in cars
    assert "group=-10" in cars
    assert "code not in _UA116_HIDDEN_STATUS_CODES" in cars
    assert "set_field(cid, \"status\", code" in cars  # schema behavior preserved for allowed codes
    service = (tmp_path / "vin_spec_service.py").read_text(encoding="utf-8")
    assert "visible >= PUBLIC_MIN_VISIBLE_SPEC_ROWS" in service
    assert "last_cycle_error" in service

    second = patch_bundle(tmp_path)
    assert not any(second[name]["changed"] for name in second if name.endswith(".py"))


def test_no_production_path_or_launch_marker_is_created(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    patch_bundle(tmp_path)
    values = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.py"))
    assert "/home/Carix" not in values
    assert "AUTO-TASK116" not in values


def test_marker_or_content_tamper_fails_closed_without_touching_other_files(
    tmp_path: Path,
) -> None:
    write_fixture(tmp_path)
    patch_bundle(tmp_path)
    baseline = {path.name: path.read_bytes() for path in tmp_path.glob("*.py")}

    cars = tmp_path / "cars_ui.py"
    cars.write_text(
        cars.read_text(encoding="utf-8").replace(
            "prepare_for_publish_async(card)", "prepare_for_publish_async_tampered(card)"
        ),
        encoding="utf-8",
    )
    tampered = cars.read_bytes()

    with pytest.raises(RecoveryGuardError) as error:
        patch_bundle(tmp_path)
    assert error.value.code == "PATCH_SEAL_MISMATCH"
    assert cars.read_bytes() == tampered
    for name, value in baseline.items():
        if name != "cars_ui.py":
            assert (tmp_path / name).read_bytes() == value


def test_incomplete_marker_and_late_candidate_failure_write_nothing(
    tmp_path: Path,
) -> None:
    write_fixture(tmp_path)
    source_policy = tmp_path / "source_policy.py"
    source_policy.write_text(
        source_policy.read_text(encoding="utf-8")
        + f"\n# {MARKER}: source_policy\n",
        encoding="utf-8",
    )
    baseline = {path.name: path.read_bytes() for path in tmp_path.glob("*.py")}
    with pytest.raises(RecoveryGuardError) as marker_error:
        patch_bundle(tmp_path)
    assert marker_error.value.code == "PATCH_SEAL_MISSING_OR_MISPLACED"
    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.py")} == baseline

    write_fixture(tmp_path)
    vin_service = tmp_path / "vin_spec_service.py"
    vin_service.write_text(
        vin_service.read_text(encoding="utf-8").replace(
            "written = _store_facts(uid, facts)", "written = 1"
        ),
        encoding="utf-8",
    )
    baseline = {path.name: path.read_bytes() for path in tmp_path.glob("*.py")}
    with pytest.raises(RecoveryGuardError):
        patch_bundle(tmp_path)
    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.py")} == baseline


def test_readback_failure_rolls_back_every_replaced_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fixture(tmp_path)
    baseline = {path.name: path.read_bytes() for path in tmp_path.glob("*.py")}
    real_safe_read = integration_patcher._safe_read_text
    saw_sealed_readback = False

    def mismatching_safe_read(path: Path, *args, **kwargs):
        nonlocal saw_sealed_readback
        value, info = real_safe_read(path, *args, **kwargs)
        if path.name == "source_policy.py" and SEAL_PREFIX in value and not saw_sealed_readback:
            saw_sealed_readback = True
            return value + "# simulated readback corruption\n", info
        return value, info

    monkeypatch.setattr(integration_patcher, "_safe_read_text", mismatching_safe_read)
    with pytest.raises(RecoveryGuardError) as error:
        patch_bundle(tmp_path)
    assert error.value.code == "PATCH_READBACK_MISMATCH"
    assert saw_sealed_readback
    assert {path.name: path.read_bytes() for path in tmp_path.glob("*.py")} == baseline


def test_symlink_and_hardlink_sources_are_rejected(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    real = tmp_path / "outside.py"
    real.write_text(CARS_UI, encoding="utf-8")
    (tmp_path / "cars_ui.py").unlink()
    (tmp_path / "cars_ui.py").symlink_to(real)
    with pytest.raises(RecoveryGuardError) as symlink_error:
        patch_bundle(tmp_path)
    assert symlink_error.value.code == "PREVIEW_SYMLINK_FORBIDDEN"

    (tmp_path / "cars_ui.py").unlink()
    os.link(real, tmp_path / "cars_ui.py")
    with pytest.raises(RecoveryGuardError) as hardlink_error:
        patch_bundle(tmp_path)
    assert hardlink_error.value.code == "PATCH_SOURCE_HARDLINK_FORBIDDEN"


def _active_spec():
    facts = tuple(
        SpecFact(
            field_key="field_%02d" % index,
            label_ru="Параметр %02d" % index,
            display_value="Значение %02d" % index,
            confidence=1.0,
            evidence_count=1,
            visible=True,
            manual=True,
        )
        for index in range(10)
    )
    candidate = build_candidate_revision(
        "UA-0017", "1HGBH41JXMN109186", "TEST", facts,
        revision_id="synthetic-revision",
        allow_manual_facts=True,
    )
    return dataclasses.replace(candidate, status="ACTIVE")


def test_generated_renderer_binds_exact_active_fact_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fixture(tmp_path)
    patch_bundle(tmp_path)
    active = _active_spec()
    store = types.ModuleType("spec_revision_store")
    store.get_active = lambda _path, _uid: active
    monkeypatch.setitem(sys.modules, "spec_revision_store", store)
    service = types.ModuleType("vin_spec_service")
    service.SPEC_DB = tmp_path / "spec.db"
    monkeypatch.setitem(sys.modules, "vin_spec_service", service)

    namespace = {"__name__": "ua116_synthetic_renderer"}
    source = (tmp_path / "ua_additional_spec.py").read_text(encoding="utf-8")
    exec(compile(source, "ua_additional_spec.py", "exec"), namespace)
    output = namespace["inject_public_spec"]("<html></html>", "UA-0017")
    assert 'data-ua-spec-revision="synthetic-revision"' in output
    assert "Параметр 00" in output and "Значение 00" in output

    legacy_renderer = namespace["_UA116_BASE_INJECT_PUBLIC_SPEC"]
    namespace["_UA116_BASE_INJECT_PUBLIC_SPEC"] = (
        lambda html, uid: legacy_renderer(html, uid).replace("Значение 00", "ПОДМЕНЕНО")
    )
    with pytest.raises(RuntimeError, match="UA116_SPEC_CONTENT_INVALID"):
        namespace["inject_public_spec"]("<html></html>", "UA-0017")


def test_generated_renderer_preserves_legacy_display_until_active_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fixture(tmp_path)
    patch_bundle(tmp_path)
    store = types.ModuleType("spec_revision_store")
    store.get_active = lambda _path, _uid: None
    monkeypatch.setitem(sys.modules, "spec_revision_store", store)
    service = types.ModuleType("vin_spec_service")
    service.SPEC_DB = tmp_path / "immutable-spec.db"
    monkeypatch.setitem(sys.modules, "vin_spec_service", service)
    namespace = {"__name__": "ua116_legacy_display_fixture"}
    source = (tmp_path / "ua_additional_spec.py").read_text(encoding="utf-8")
    exec(compile(source, "ua_additional_spec.py", "exec"), namespace)
    legacy = [{"field_key": "legacy", "field_value": "Сохранено"}]
    namespace["_UA116_BASE_FETCH_SPECS"] = lambda _value, **_kwargs: legacy
    assert namespace["fetch_specs"]("UA-0017") == legacy
    with pytest.raises(RuntimeError, match="UA116_SPEC_EXACT_REVISION_MISSING"):
        namespace["inject_public_spec"]("<html>old page</html>", "UA-0017")


def test_bootstrap_queues_incomplete_published_card_and_starts_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fixture(tmp_path)
    patch_bundle(tmp_path)
    namespace = {"__name__": "ua116_synthetic_service", "json": json}
    service_source = (tmp_path / "vin_spec_service.py").read_text(encoding="utf-8")
    exec(compile(service_source, "vin_spec_service.py", "exec"), namespace)

    valid_vin = "1HGBH41JXMN109186"
    pending_vin = "1M8GDM9AXKP042788"
    valid_rows = list(_active_spec().facts)
    short_rows = valid_rows[:3]
    cards = [
        {"car_uid": "UA-0017", "vin": valid_vin, "published": 1},
        {"car_uid": "UA-0018", "vin": pending_vin, "published": 1},
    ]
    namespace.update({
        "SPEC_DB": tmp_path / "spec.db",
        "canonical_uid": lambda value: str(value),
        "read_cards": lambda: cards,
        "ensure_schema": lambda: None,
        "_ua116_legacy_snapshot": (
            lambda uid: valid_rows if uid == "UA-0017" else short_rows
        ),
    })
    namespace["source_policy"].normalize_vin = staticmethod(lambda value: str(value))

    jobs = {
        "UA-0017": {"vin": valid_vin, "status": "READY", "facts_count": 10},
        "UA-0018": None,
    }

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, _query, params):
            self.uid = params[0]
            return self
        def fetchone(self): return jobs[self.uid]

    namespace["connect_spec"] = lambda _readonly: Connection()
    activated = []
    queued = []
    store = types.ModuleType("spec_revision_store")
    store.initialize = lambda _path: None
    store.get_active = lambda _path, _uid: None
    store.stage_and_activate = lambda _path, **kwargs: activated.append(kwargs) or {}
    monkeypatch.setitem(sys.modules, "spec_revision_store", store)
    namespace["enqueue_card"] = (
        lambda card, force=False: queued.append((card["car_uid"], force)) or True
    )

    result = namespace["bootstrap_immutable_revisions"]()
    assert result["status"] == "RECOVERY_PENDING"
    assert result["migrated"] == 1
    assert [item["car_uid"] for item in result["pending"]] == ["UA-0018"]
    assert queued == [("UA-0018", True)]
    assert len(activated) == 1

    runtime = types.ModuleType("ua116_runtime_bridge")
    runtime.bootstrap_published_vin_reservations = lambda: {"status": "PASS"}
    monkeypatch.setitem(sys.modules, "ua116_runtime_bridge", runtime)
    namespace["bootstrap_immutable_revisions"] = lambda: result
    namespace["_UA116_BASE_START_WORKER"] = lambda: "STARTED"
    assert namespace["start_worker"]() == "STARTED"


def test_cli_relative_receipt_is_written_below_preview_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    preview = tmp_path / "preview"
    preview.mkdir()
    write_fixture(preview)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["integration_patcher.py", "--preview-root", str(preview),
         "--receipt", "evidence/patch-receipt.json"],
    )
    assert main() == 0
    capsys.readouterr()
    receipt = preview / "evidence" / "patch-receipt.json"
    assert receipt.is_file()
    assert json.loads(receipt.read_text(encoding="utf-8"))["bundle_digest"]
    assert not (tmp_path / "evidence" / "patch-receipt.json").exists()


def _assigned_string(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("missing assignment: " + name)


def test_realistic_task111_task115_candidates_compile(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    cloud = Path(__file__).resolve().parents[2]
    (tmp_path / "source_policy.py").write_text(
        (cloud / "task_111_vin_spec_10src" / "source_policy.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "vin_spec_service.py").write_text(
        (cloud / "task_111_vin_spec_10src" / "vin_spec_service.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    renderer = (cloud / "task_099_site_crm_repair" / "ua_additional_spec.py").read_text(
        encoding="utf-8"
    )
    task115_installer = (cloud / "task115_remove_vin_ads" / "remote_installer.py").read_text(
        encoding="utf-8"
    )
    renderer += "\n" + _assigned_string(task115_installer, "PY_BLOCK").strip() + "\n"
    (tmp_path / "ua_additional_spec.py").write_text(renderer, encoding="utf-8")

    patch_bundle(tmp_path)
    for name in integration_patcher.PATCHES:
        compile((tmp_path / name).read_text(encoding="utf-8"), name, "exec")
