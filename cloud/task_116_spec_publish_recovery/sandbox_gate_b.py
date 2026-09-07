#!/usr/bin/env python3
"""Dependency-free Gate B runner for the TASK116 preview candidate."""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import importlib.util
import json
import os
import platform
import sqlite3
import sys
import tempfile
import traceback
import types
from pathlib import Path

from preview_release import build_preview_release, current_release
from integration_patcher import MARKER, patch_bundle
from integration_patcher import (
    patch_additional_spec,
    patch_source_policy,
    patch_vin_service,
)
from recovery_core import (
    BaseCandidate,
    PUBLIC_MIN_VISIBLE_SPEC_ROWS,
    RecoveryGuardError,
    SpecFact,
    WorkerHealth,
    activate_candidate,
    build_candidate_revision,
    card_identity_errors,
    classify_stage_callback,
    evidence_envelope,
    exact_catalog_link_count,
    filter_selectable_statuses,
    plan_base_fill,
    publication_preflight,
    stable_digest,
    vin_sha256,
)
from spec_revision_store import (
    backup_sqlite,
    get_active,
    record_rejected_candidate,
    stage_and_activate,
)
from vin_base_spec_service import apply_fill_plan, row_digest
from vin_ingestion import prepare_for_publish
from vin_primary_decoder import decode_primary_candidates


# Synthetic fixtures; neither value is asserted to belong to UA-0017.
VIN = "1HGBH41JXMN109186"
SECOND_VIN = "1M8GDM9AXKP042788"
PACKAGE_ROOT = Path(__file__).resolve().parent


def _facts(count: int, prefix: str = "v") -> list[SpecFact]:
    return [
        SpecFact(
            field_key=f"field_{index:02d}",
            label_ru=f"Поле {index}",
            display_value=f"{prefix}{index}",
            category="engine" if index < 4 else "dimensions",
            confidence=0.95,
            evidence_count=2,
            source_domains=("auto-data.net", "cars-data.com"),
        )
        for index in range(count)
    ]


def _card() -> dict[str, object]:
    return {
        "auto_number": "UA-0017",
        "brand": "Mercedes-Benz",
        "model": "B-Class",
        "year": "2010",
        "vin": VIN,
        "fuel": "бензин",
        "engine_cc": 1700,
        "gearbox": "автомат",
        "drive": "передний",
        "mileage_km": 104000,
        "color": "белая",
    }


def _active():
    candidate = build_candidate_revision(
        "UA-0017",
        VIN,
        "P1",
        _facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS),
        revision_id="gateb-revision-1",
    )
    return activate_candidate(None, candidate)[1]


def _page(spec) -> str:
    rows = "".join(
        '<div class="ua-addspec-row"><dt>%s</dt><dd>%s</dd></div>'
        % (fact.label_ru, fact.display_value)
        for fact in spec.visible_facts
    )
    return (
        '<html><section class="ua-additional-spec" data-ua-card="UA-0017" '
        f'data-ua-spec-sha256="{spec.digest}">{VIN}{rows}</section></html>'
    )


def _diag() -> str:
    return f'<html><main data-ua-card="UA-0017">Диагностика {VIN}</main></html>'


def _listing(label: str) -> str:
    return f'<html><a href="UA-0017.html?v=1">{label}</a></html>'


def _foundation() -> dict[str, str]:
    return {
        "templates/card.html": hashlib.sha256(b"immutable card shell").hexdigest(),
        "static/site.css": hashlib.sha256(b"immutable site css").hexdigest(),
    }


def _make_crm(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE cars (id INTEGER PRIMARY KEY, auto_number TEXT, vin TEXT, "
            "brand TEXT, model TEXT, year TEXT, fuel TEXT, engine_cc INTEGER, "
            "gearbox TEXT, drive TEXT, mileage_km INTEGER, color TEXT)"
        )
        con.execute(
            "CREATE TABLE audit (id INTEGER PRIMARY KEY, actor_id INTEGER, action TEXT, "
            "entity_type TEXT, entity_id INTEGER, field TEXT, old_value TEXT, "
            "new_value TEXT, created_at TEXT)"
        )
        con.execute(
            "INSERT INTO cars(id,auto_number,vin,brand,model,color) "
            "VALUES(1,'UA-0017',?,'Mercedes-Benz','','белая')",
            (VIN,),
        )


def _row(path: Path) -> dict[str, object]:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        return dict(con.execute("SELECT * FROM cars WHERE id=1").fetchone())
    finally:
        con.close()


def case_shared_threshold() -> None:
    for count in (0, 4, PUBLIC_MIN_VISIBLE_SPEC_ROWS - 1):
        try:
            build_candidate_revision(
                "UA-0017", VIN, "P1", _facts(count), revision_id=f"r-{count}"
            )
        except RecoveryGuardError as exc:
            assert exc.code == "SPEC_NOT_READY"
        else:
            raise AssertionError(f"{count} rows unexpectedly became READY")
    assert _active().visible_count == PUBLIC_MIN_VISIBLE_SPEC_ROWS


def case_revision_immutability(root: Path) -> None:
    spec_db = root / "spec.db"
    first = stage_and_activate(
        spec_db,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-old",
        rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, "old"),
    )
    second = stage_and_activate(
        spec_db,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="rev-refresh",
        rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, "changed"),
    )
    assert second["status"] == "UNCHANGED"
    assert first["active_digest"] == second["active_digest"]
    before = get_active(spec_db, "UA-0017")
    record_rejected_candidate(
        spec_db,
        uid="UA-0017",
        vin="WDDMH0BBXDV171918",
        policy_version="P1",
        revision_id="rev-partial",
        visible_count=PUBLIC_MIN_VISIBLE_SPEC_ROWS - 1,
        reject_code="SPEC_NOT_READY",
    )
    after = get_active(spec_db, "UA-0017")
    assert before and after and before.digest == after.digest
    try:
        stage_and_activate(
            spec_db,
            uid="UA-0017",
            vin="WDDMH0BBXDV171918",
            policy_version="P1",
            revision_id="rev-fault",
            rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, "new-vin"),
            fault="after_activation",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("fault injection did not abort")
    assert get_active(spec_db, "UA-0017").revision_id == "rev-old"


def case_store_tamper_and_backup(root: Path) -> None:
    spec_db = root / "tamper-spec.db"
    stage_and_activate(
        spec_db,
        uid="UA-0017",
        vin=VIN,
        policy_version="P1",
        revision_id="tamper-source",
        rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, "sealed"),
    )
    before = get_active(spec_db, "UA-0017")
    assert before is not None

    with sqlite3.connect(spec_db) as con:
        try:
            con.execute(
                "UPDATE ua116_spec_fact SET display_value='forged' "
                "WHERE revision_id=? AND field_key='field_00'",
                (before.revision_id,),
            )
        except sqlite3.IntegrityError as exc:
            assert "UA116_SPEC_FACT_IMMUTABLE" in str(exc)
        else:
            raise AssertionError("active fact mutation was not rejected")
    after = get_active(spec_db, "UA-0017")
    assert after and after.digest == before.digest and after.facts == before.facts

    backup = root / "tamper-spec.backup.db"
    receipt = backup_sqlite(spec_db, backup)
    assert receipt["status"] == "PASS" and receipt["quick_check"] == "ok"
    with sqlite3.connect(backup) as con:
        assert con.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    restored = get_active(backup, "UA-0017")
    assert restored and restored.digest == before.digest and restored.facts == before.facts


def case_specs_survive_unrelated_changes(root: Path) -> None:
    """Old and new immutable snapshots do not follow mutable CRM/site state."""

    spec_db = root / "preservation-spec.db"
    snapshots = {
        "UA-0002": (VIN, "legacy", "old-card-revision"),
        "UA-0017": (SECOND_VIN, "new", "new-card-revision"),
    }
    for uid, (vin, prefix, revision_id) in snapshots.items():
        stage_and_activate(
            spec_db,
            uid=uid,
            vin=vin,
            policy_version="P1",
            revision_id=revision_id,
            rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, prefix),
        )
    before = {uid: get_active(spec_db, uid) for uid in snapshots}

    crm = root / "unrelated-crm.db"
    with sqlite3.connect(crm) as con:
        con.execute(
            "CREATE TABLE cards(uid TEXT PRIMARY KEY, price INTEGER, status TEXT, theme TEXT)"
        )
        con.executemany(
            "INSERT INTO cards VALUES(?,?,?,?)",
            (("UA-0002", 8000, "ge_waiting", "dark"), ("UA-0017", 9000, "ua_arrived", "dark")),
        )
        con.execute("UPDATE cards SET price=price+500, status='sold', theme='light'")
    (root / "site-shell.html").write_text(
        "<html><body>new navigation and palette</body></html>", encoding="utf-8"
    )

    # A repeated same-VIN enrichment with different output must also remain a no-op.
    repeat = stage_and_activate(
        spec_db,
        uid="UA-0017",
        vin=SECOND_VIN,
        policy_version="P2",
        revision_id="new-card-refresh",
        rows=_facts(PUBLIC_MIN_VISIBLE_SPEC_ROWS, "replacement"),
    )
    assert repeat["status"] == "UNCHANGED"
    after = {uid: get_active(spec_db, uid) for uid in snapshots}
    for uid in snapshots:
        assert before[uid] and after[uid]
        assert after[uid].revision_id == before[uid].revision_id
        assert after[uid].digest == before[uid].digest
        assert after[uid].facts == before[uid].facts


def case_primary_cas(root: Path) -> None:
    db_path = root / "crm.db"
    _make_crm(db_path)
    before = _row(db_path)
    candidates = [
        BaseCandidate("brand", "Other", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("engine_cc", "1700", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("mileage_km", "999", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN)),
        BaseCandidate("mileage_km", "104000", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
        BaseCandidate("color", "чёрная", "same_vin_crm", "crm:same-vin", 0.99, vin_sha256(VIN)),
    ]
    plan = plan_base_fill(before, candidates, expected_vin=VIN)
    receipt = apply_fill_plan(
        db_path,
        card_id=1,
        uid="UA-0017",
        expected_vin=VIN,
        plan=plan,
        actor_id=7,
        expected_row_digest=row_digest(before),
        preview_root=root,
    )
    after = _row(db_path)
    assert after["brand"] == "Mercedes-Benz" and after["color"] == "белая"
    assert after["model"] == "B-Class" and after["mileage_km"] == 104000
    assert receipt["written_fields"] == ["engine_cc", "mileage_km", "model"]
    with sqlite3.connect(db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 3

    rollback_path = root / "crm-rollback.db"
    _make_crm(rollback_path)
    old = _row(rollback_path)
    rollback_plan = plan_base_fill(
        old,
        [BaseCandidate("model", "B-Class", "vin_decoder", "vpic.nhtsa.dot.gov", 0.99, vin_sha256(VIN))],
        expected_vin=VIN,
    )
    try:
        apply_fill_plan(
            rollback_path,
            card_id=1,
            uid="UA-0017",
            expected_vin=VIN,
            plan=rollback_plan,
            actor_id=7,
            expected_row_digest=row_digest(old),
            preview_root=root,
            fault="after_audit",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("CRM fault injection did not abort")
    assert _row(rollback_path)["model"] == ""
    with sqlite3.connect(rollback_path) as con:
        assert con.execute("SELECT COUNT(*) FROM audit").fetchone()[0] == 0


def case_preflight_and_identity() -> None:
    spec = _active()
    now = dt.datetime.now(dt.timezone.utc)
    health = WorkerHealth("gateb", now.isoformat(), now.isoformat())
    result = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=_card(),
        active_spec=spec,
        worker_health=health,
        now=now,
    )
    assert result.ok
    duplicate = publication_preflight(
        uid="UA-0017",
        vin=VIN,
        card=_card(),
        active_spec=spec,
        worker_health=health,
        duplicate_active_uids=("UA-0002",),
        now=now,
    )
    assert duplicate.codes == ("DUPLICATE_ACTIVE_VIN:UA-0002",)
    generic = card_identity_errors(
        "<html>Открыть все автомобили</html>",
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=10,
    )
    assert "GENERIC_FALLBACK_PAGE" in generic
    assert exact_catalog_link_count(
        '<a href="UA-00170.html">bad</a><a href="UA-0017.html?v=1">ok</a>',
        "UA-0017",
    ) == 1

    # A copied digest/count marker must not hide forged visible values.
    forged_page = _page(spec).replace(
        "<dd>v0</dd>", "<dd>forged</dd>", 1
    )
    content_errors = card_identity_errors(
        forged_page,
        uid="UA-0017",
        vin=VIN,
        expected_spec_rows=spec.visible_count,
        expected_spec_digest=spec.digest,
        expected_spec=spec,
    )
    assert "SPEC_FACT_CONTENT_MISSING:field_00" in content_errors
    assert "SPEC_FACT_CONTENT_UNEXPECTED:1" in content_errors


class _VpicResponse:
    status = 200

    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return (
            "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
            + VIN
            + "?format=json"
        )

    def read(self, _limit):
        return json.dumps(self.payload).encode("utf-8")


def _vpic_opener(payload: dict[str, object]):
    def opener(_request, timeout):
        assert timeout > 0
        return _VpicResponse(payload)

    return opener


def case_vpic_exact_identity_and_outage() -> None:
    exact = {
        "Results": [
            {
                "VIN": VIN,
                "ErrorCode": "0",
                "Make": "Mercedes-Benz",
                "Model": "B-Class",
            }
        ]
    }
    candidates = decode_primary_candidates(VIN, opener=_vpic_opener(exact))
    assert [(item.field, item.value) for item in candidates] == [
        ("brand", "Mercedes-Benz"),
        ("model", "B-Class"),
    ]

    mismatch = json.loads(json.dumps(exact))
    mismatch["Results"][0]["VIN"] = SECOND_VIN
    try:
        decode_primary_candidates(VIN, opener=_vpic_opener(mismatch))
    except RuntimeError as exc:
        assert str(exc) == "VPIC_VIN_MISMATCH"
    else:
        raise AssertionError("vPIC VIN mismatch was not rejected")

    def outage(_request, timeout):
        assert timeout > 0
        raise OSError("simulated network outage")

    try:
        decode_primary_candidates(VIN, opener=outage)
    except OSError as exc:
        assert "simulated network outage" in str(exc)
    else:
        raise AssertionError("vPIC outage unexpectedly produced candidates")


def case_status_dedupe() -> None:
    statuses = {
        "kr_bought": (1, "Выкуплено, на нашей парковке"),
        "sea_loaded": (2, "Загружено в контейнер"),
        "sea_transit": (2, "В пути"),
        "ge_waiting": (3, "Авто в Грузии"),
        "ua_arrived": (4, "В Киеве"),
        "ua_handed": (4, "Передано клиенту"),
        "sold": (4, "Продано"),
        "archive": (4, "Архив"),
    }
    selectable = filter_selectable_statuses(statuses)
    assert set(selectable) == {"ge_waiting", "ua_arrived", "sold", "archive"}
    for code in ("kr_bought", "sea_loaded", "sea_transit", "ua_handed"):
        assert classify_stage_callback(f"car_setstage:17:{code}")[0] == "BLOCKED_LEGACY_STATUS"
    assert "ua_handed" in statuses  # historical schema/data is intentionally retained


def case_versioned_preview(root: Path) -> None:
    spec = _active()
    preview = root / "preview"
    first = build_preview_release(
        preview,
        release_id="gateb-release-001",
        uid="UA-0017",
        vin=VIN,
        spec=spec,
        page_html=_page(spec),
        diag_html=_diag(),
        catalog_html=_listing("catalog"),
        index_html=_listing("index"),
        card_row_digest="card-row",
        foundation_manifest=_foundation(),
    )
    assert first["production_touched"] is False
    pointer_before = (preview / "current.json").read_bytes()
    try:
        build_preview_release(
            preview,
            release_id="gateb-release-002",
            uid="UA-0017",
            vin=VIN,
            spec=spec,
            page_html=_page(spec),
            diag_html=_diag(),
            catalog_html=_listing("catalog-2"),
            index_html=_listing("index-2"),
            card_row_digest="card-row-2",
            foundation_manifest=_foundation(),
            fault="before_pointer",
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("preview fault injection did not abort")
    assert (preview / "current.json").read_bytes() == pointer_before
    assert current_release(preview)["release_id"] == "gateb-release-001"

    try:
        build_preview_release(
            root / "forged-preview",
            release_id="gateb-forged-001",
            uid="UA-0017",
            vin=VIN,
            spec=spec,
            page_html=_page(spec).replace("<dd>v0</dd>", "<dd>forged</dd>", 1),
            diag_html=_diag(),
            catalog_html=_listing("catalog"),
            index_html=_listing("index"),
            card_row_digest="card-row-forged",
            foundation_manifest=_foundation(),
        )
    except RecoveryGuardError as exc:
        assert exc.code == "PREVIEW_CARD_INVALID"
        assert "SPEC_FACT_CONTENT_MISSING:field_00" in exc.detail
    else:
        raise AssertionError("forged specification content became a preview release")


def case_fresh_source_patcher(root: Path) -> None:
    patch_root = root / "fresh-sources"
    patch_root.mkdir()
    cars_ui = '''\
async def apply_value(card_id, field, raw, actor_id):
    value = (raw or "").strip()
    if field == "vin":
        vin = value.upper().replace(" ", "")
        ok, msg = S.check_vin(vin)
        if not ok:
            return False, "bad"
        set_field(card_id, field, vin, actor_id)
        return True, "Записано: %s" % vin
async def stage_menu(update, context):
    for number, _name in S.STAGES:
        pair = [InlineKeyboardButton(label) for code, (stage_no, label) in S.STATUSES.items() if stage_no == number]
async def stage_set(update, context):
    q = update.callback_query
    _, cid, code = q.data.split(":")
    cid = int(cid)
    set_field(cid, "status", code, q.from_user.id)
async def toggle_publish(update, context):
    q = update.callback_query
    cid, novoe, card = 1, 1, {}
    db.update_card_field("cars", cid, "published", novoe, q.from_user.id)
    if novoe:
        try:
            import publikaciya as p
            ok, text = p.opublikovat(card.get("auto_number"))
            await q.message.reply_text(text)
        except Exception:
            pass
async def preview(update, context):
    q, card = update.callback_query, {}
    try:
        import publikaciya as p
        p.opublikovat(card.get("auto_number"))
    except Exception:
        pass
def register(app):
    pass
'''
    konteyner = '''\
async def gde_mashina(update, context):
    for nomer_etapa, _nazv in S.STAGES:
        pary = [InlineKeyboardButton(label) for code, (stage_no, label) in S.STATUSES.items()
                if stage_no == nomer_etapa]
async def _ekran(update, context):
    rows = []
    rows.append([InlineKeyboardButton("В пути", callback_data="car_setstage:1:sea_transit")])
    rows.append([InlineKeyboardButton("В Киеве", callback_data="car_setstage:1:ua_arrived")])
'''
    source_policy = '''\
POLICY_VERSION = "UA111-10SRC-V3"
def enrich(profile):
    minimum_facts = 10 if profile else 4
    return minimum_facts
'''
    service = '''\
def utc_now(): return "now"
def connect_spec(value): return None
class source_policy: POLICY_VERSION = "P"
def _process_claimed(
    job):
    try:
        uid, vin, result, facts = "UA-0017", "1HGBH41JXMN109186", {"status": "READY"}, []
        written = _store_facts(uid, facts)
        status = "READY" if result.get("status") == "READY" and written >= 1 else "NEEDS_REVIEW"
        card = {}
        sync_status, sync_detail = _refresh_published(card) if written >= 1 else ("NOT_REQUIRED", "нет подтверждённых фактов")
        return status
    except Exception:
        return "FAILED"
def claim():
    a = "AND status IN ('NEEDS_REVIEW','FAILED','READY')"
    b = "AND status IN ('NEEDS_REVIEW','FAILED','READY')"
class Stop:
    def is_set(self): return True
    def wait(self, value): pass
_stop_event, SCAN_SECONDS, WORKER_NAME = Stop(), 30, "worker"
def migrate_legacy_once(): pass
def recover_interrupted_jobs(): pass
def scan_new_vins(): pass
def process_one(): pass
def enqueue_card(card, *, force=False): return False
def start_worker(): return None
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
if __name__ == "__main__":
    pass
'''
    additional = '''\
SPEC_DB = "spec.db"
def canonical_uid(value): return value
def _car_vin(value): return "1HGBH41JXMN109186"
def fetch_specs(value): return []
def inject_public_spec(source, value): return source
'''
    values = {
        "cars_ui.py": cars_ui,
        "konteyner.py": konteyner,
        "source_policy.py": source_policy,
        "vin_spec_service.py": service,
        "ua_additional_spec.py": additional,
    }
    for name, value in values.items():
        (patch_root / name).write_text(value, encoding="utf-8")
    first = patch_bundle(patch_root)
    assert all(first[name]["changed"] for name in values)
    for name in values:
        changed = (patch_root / name).read_text(encoding="utf-8")
        compile(changed, name, "exec")
        assert MARKER in changed
    patched_cars = (patch_root / "cars_ui.py").read_text()
    assert "p.opublikovat" not in patched_cars
    assert ".opublikovat" not in patched_cars
    assert "доверенным TASK116 release-controller" in patched_cars
    assert "group=-10" in patched_cars
    patched_policy = (patch_root / "source_policy.py").read_text()
    assert "minimum_facts = PUBLIC_MIN_VISIBLE_SPEC_ROWS" in patched_policy

    # During cutover/source outage, old rows remain visible in CRM but cannot
    # be published until an exact immutable ACTIVE revision exists.
    patched_additional = (patch_root / "ua_additional_spec.py").read_text()
    previous_store = sys.modules.get("spec_revision_store")
    previous_service = sys.modules.get("vin_spec_service")
    store_stub = types.ModuleType("spec_revision_store")
    store_stub.get_active = lambda _path, _uid: None
    service_stub = types.ModuleType("vin_spec_service")
    service_stub.SPEC_DB = patch_root / "immutable-spec.db"
    sys.modules["spec_revision_store"] = store_stub
    sys.modules["vin_spec_service"] = service_stub
    try:
        namespace = {"__name__": "ua116_sandbox_legacy_fallback"}
        exec(compile(patched_additional, "ua_additional_spec.py", "exec"), namespace)
        legacy = [{"field_key": "legacy", "field_value": "Сохранено"}]
        namespace["_UA116_BASE_FETCH_SPECS"] = lambda _value, **_kwargs: legacy
        assert namespace["fetch_specs"]("UA-0017") == legacy
        try:
            namespace["inject_public_spec"]("<html>old</html>", "UA-0017")
        except RuntimeError as exc:
            assert "UA116_SPEC_EXACT_REVISION_MISSING" in str(exc)
        else:
            raise AssertionError("legacy fallback was allowed to publish")
    finally:
        if previous_store is None:
            sys.modules.pop("spec_revision_store", None)
        else:
            sys.modules["spec_revision_store"] = previous_store
        if previous_service is None:
            sys.modules.pop("vin_spec_service", None)
        else:
            sys.modules["vin_spec_service"] = previous_service
    second = patch_bundle(patch_root)
    assert not any(second[name]["changed"] for name in values)


def case_saved_source_candidate_compatibility() -> None:
    """Compile against the latest repository-held TASK111/TASK115 sources.

    These are not a substitute for a fresh remote Gate A snapshot, but they
    catch drift that synthetic fixtures cannot reveal.
    """

    repository_root = PACKAGE_ROOT.parents[1]
    policy_path = repository_root / "cloud/task_111_vin_spec_10src/source_policy.py"
    service_path = repository_root / "cloud/task_111_vin_spec_10src/vin_spec_service.py"
    spec_path = repository_root / "cloud/task_099_site_crm_repair/ua_additional_spec.py"
    task115_path = repository_root / "cloud/task115_remove_vin_ads/remote_installer.py"
    required = (policy_path, service_path, spec_path, task115_path)
    missing = [str(path.relative_to(repository_root)) for path in required if not path.is_file()]
    if missing:
        raise AssertionError("saved source candidate missing: " + ",".join(missing))

    policy = patch_source_policy(policy_path.read_text(encoding="utf-8"))
    service = patch_vin_service(service_path.read_text(encoding="utf-8"))
    compile(policy, "saved-source-policy.py", "exec")
    compile(service, "saved-vin-service.py", "exec")

    installer_tree = ast.parse(task115_path.read_text(encoding="utf-8"))
    task115_block = None
    for node in installer_tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "PY_BLOCK" for target in targets):
            task115_block = ast.literal_eval(node.value)
            break
    if not isinstance(task115_block, str) or "UA115 NO PUBLIC VIN ADS" not in task115_block:
        raise AssertionError("TASK115 specification guard block unavailable")
    task115_spec = (
        spec_path.read_text(encoding="utf-8").rstrip()
        + "\n\n"
        + task115_block.strip()
        + "\n"
    )
    patched_spec = patch_additional_spec(task115_spec)
    compile(patched_spec, "saved-task115-additional-spec.py", "exec")


class _Backend:
    def __init__(self):
        self.job = {"id": 1, "status": "NOT_QUEUED", "attempts": 0}
        self.spec = None
        self.process_calls = 0

    def load_card(self, uid): return _card()
    def enqueue_exact(self, uid, vin):
        if self.job["status"] == "NOT_QUEUED":
            self.job = {"id": 1, "status": "PENDING", "attempts": 0}
        return dict(self.job)
    def process_exact(self, uid, vin):
        self.process_calls += 1
        self.job = {"id": 1, "status": "READY", "attempts": 1}
        self.spec = _active()
        return dict(self.job)
    def job_state(self, uid, vin): return dict(self.job)
    def active_spec(self, uid): return self.spec
    def worker_health(self):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        return WorkerHealth("gateb", now, now)
    def duplicate_active_uids(self, uid, vin): return ()


def case_immediate_publish_bridge() -> None:
    backend = _Backend()
    first = prepare_for_publish(backend, uid="UA-0017", expected_vin=VIN)
    assert first.ready and backend.process_calls == 1
    second = prepare_for_publish(backend, uid="UA-0017", expected_vin=VIN)
    assert second.ready and backend.process_calls == 1


def case_runtime_bridge_stdlib() -> None:
    runner_path = PACKAGE_ROOT / "tests/runtime_bridge_stdlib.py"
    spec = importlib.util.spec_from_file_location(
        "ua116_runtime_bridge_stdlib", runner_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("runtime bridge stdlib runner unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outcome = module.run()
    if outcome.get("status") != "PASS":
        raise AssertionError(
            "runtime bridge stdlib failed: "
            + json.dumps(outcome, ensure_ascii=False, sort_keys=True)
        )
    assert outcome.get("passed") == outcome.get("total") == 6


def case_atomic_publish_stdlib() -> None:
    runner_path = PACKAGE_ROOT / "tests/atomic_publish_stdlib.py"
    spec = importlib.util.spec_from_file_location(
        "ua116_atomic_publish_stdlib", runner_path
    )
    if spec is None or spec.loader is None:
        raise AssertionError("atomic publish stdlib runner unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outcome = module.run()
    if outcome.get("status") != "PASS":
        raise AssertionError(
            "atomic publish stdlib failed: "
            + json.dumps(outcome, ensure_ascii=False, sort_keys=True)
        )
    assert outcome.get("gate") == "B_LOCAL_CANDIDATE"
    assert outcome.get("production_touched") is False
    assert outcome.get("passed") == outcome.get("total") == 10


def run() -> dict[str, object]:
    checks = []
    with tempfile.TemporaryDirectory(prefix="uaart-task116-gateb-") as temporary:
        root = Path(temporary)
        cases = (
            ("shared_minimum_threshold", lambda: case_shared_threshold()),
            ("revision_immutability", lambda: case_revision_immutability(root)),
            ("store_tamper_and_backup_quick_check", lambda: case_store_tamper_and_backup(root)),
            ("old_and_new_specs_survive_unrelated_changes", lambda: case_specs_survive_unrelated_changes(root)),
            ("primary_empty_only_cas", lambda: case_primary_cas(root)),
            ("preflight_identity_duplicate_and_content", lambda: case_preflight_and_identity()),
            ("vpic_exact_identity_mismatch_and_outage", lambda: case_vpic_exact_identity_and_outage()),
            ("status_buttons_and_stale_callbacks", lambda: case_status_dedupe()),
            ("versioned_preview_atomicity_and_content", lambda: case_versioned_preview(root)),
            ("fresh_source_patcher", lambda: case_fresh_source_patcher(root)),
            (
                "saved_task111_task115_source_candidate_compatibility",
                lambda: case_saved_source_candidate_compatibility(),
            ),
            ("vin_immediate_publish_bridge", lambda: case_immediate_publish_bridge()),
            ("runtime_bridge_temp_sqlite_stdlib", lambda: case_runtime_bridge_stdlib()),
            ("atomic_publish_temp_roots_stdlib", lambda: case_atomic_publish_stdlib()),
        )
        for name, callback in cases:
            try:
                callback()
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
    status = "PASS" if passed == len(checks) else "FAIL"
    candidate_files = sorted(
        path for path in PACKAGE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    candidate_manifest = {
        path.relative_to(PACKAGE_ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in candidate_files
    }
    return evidence_envelope(
        gate="B_LOCAL_CANDIDATE",
        status=status,
        passed=passed,
        total=len(checks),
        checks=checks,
        test_matrix_digest=stable_digest(checks),
        expected_branch="codex/ua-art-crm-spec-publish-recovery-001",
        expected_base_sha="c0244c51c846a6370de943eb247496935125e677",
        candidate_file_sha256=candidate_manifest,
        candidate_manifest_digest=stable_digest(candidate_manifest),
        python_version=platform.python_version(),
        platform=platform.platform(),
        gate_b_eligible=False,
        production_eligible=False,
        release_authorization="BLOCKED",
        publication_state="UNKNOWN_REMOTE_NOT_OBSERVED",
        known_blockers=[
            "AUTHORITATIVE_REMOTE_GATE_A_NOT_RUN",
            "REMOTE_DERIVED_GATE_B_COPIES_NOT_AVAILABLE",
            "EXTERNAL_TRUSTED_RELEASE_CONTROLLER_NOT_INSTALLED",
            "DURABLE_ONE_TIME_OWNER_NONCE_NOT_INSTALLED",
            "OS_PROCESS_WRITE_ALLOWLIST_NOT_ENFORCED",
            "CRASH_DURABLE_SNAPSHOT_AND_RECOVERY_NOT_PROVEN",
            "BROWSER_COMPUTED_CSS_VISIBILITY_NOT_PROVEN",
        ],
        note=(
            "Local candidate checks only. No Production URL, path, database, "
            "service or publisher was called. Remote Gate B was not executed."
        ),
    )


def _validated_output_path(value: str) -> Path:
    raw = Path(value)
    lexical = raw if raw.is_absolute() else Path.cwd() / raw
    if lexical.is_symlink():
        raise RecoveryGuardError("GATE_OUTPUT_SYMLINK_FORBIDDEN", str(lexical))
    try:
        parent = lexical.parent.resolve(strict=True)
    except OSError as exc:
        raise RecoveryGuardError("GATE_OUTPUT_PARENT_INVALID", str(lexical.parent)) from exc
    target = parent / lexical.name
    if target != PACKAGE_ROOT and PACKAGE_ROOT not in target.parents:
        raise RecoveryGuardError("GATE_OUTPUT_OUTSIDE_TASK_PACKAGE", str(target))
    if target.exists():
        stat = os.stat(target, follow_symlinks=False)
        if not target.is_file() or stat.st_nlink != 1:
            raise RecoveryGuardError("GATE_OUTPUT_TARGET_INVALID", str(target))
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    args = parser.parse_args()
    result = run()
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        _validated_output_path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
