#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import tempfile
import uuid

import controller as deployment
import remote_installer as target
import rollback_controller as rollback_deployment


def load_source(source: str, filename: str):
    """Load a generated fixture through the standard import loader."""
    with tempfile.TemporaryDirectory() as raw:
        path = pathlib.Path(raw) / filename
        path.write_text(source, encoding="utf-8")
        name = "task115_fixture_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise AssertionError("fixture loader unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        finally:
            sys.modules.pop(name, None)
        return module


GENERATOR_FIXTURE = r'''import re as _ua068_re
_UA068_VIN_START = "<!-- UA-ART-VIN-GUARD-LITE-V1:START -->"
_UA068_VIN_END = "<!-- UA-ART-VIN-GUARD-LITE-V1:END -->"
_UA068_CARHISTORY_URL = "https://www.carhistory.kr/search/carhistory/search.car?lang=ru"

def _ua068_e(value):
    return str(value)

def _ua068_stage(row):
    return int((row or {}).get("stage") or 4)

def _ua068_video_count(kod, row):
    return int((row or {}).get("videos") or 2)

def _ua068_vin_block(kod, row):
    vin = str((row or {}).get("vin") or "")
    css = '<style>.ua-vin-v1-button{display:block}</style>'
    return (_UA068_VIN_START + css
            + '<section><span>Korea CarHistory</span><small>2 200 KRW</small>'
            + '<div>%s</div>' % vin
            + '<a class="ua-vin-v1-button" href="%s">Проверить VIN в CarHistory</a>' % _UA068_CARHISTORY_URL
            + '</section>' + _UA068_VIN_END)

def _ua068_card_errors(source, kod, row):
    errors = []
    if source.count(_UA068_VIN_START) != 1 or source.count(_UA068_VIN_END) != 1:
        errors.append("VIN Guard blocks != 1")
    if len(_ua068_re.findall(r'class=["\\\'][^"\\\']*\\bua-vin-v1-button\\b', source, _ua068_re.I)) != 1:
        errors.append("VIN buttons != 1")
    if source.count(_UA068_CARHISTORY_URL) != 1:
        errors.append("CarHistory target != 1")
    if "navigator.clipboard.writeText" not in source:
        errors.append("VIN copy helper missing")
    vin = str((row or {}).get("vin") or "").strip().upper()
    if not vin or vin not in source:
        errors.append("VIN missing")
    stage = _ua068_stage(row)
    if 'data-ua-stage="%d"' % stage not in source:
        errors.append("stage copy mismatch")
    expected_videos = _ua068_video_count(kod, row)
    if 'data-ua-video-count="%d"' % expected_videos not in source:
        errors.append("video count mismatch")
    return errors
'''


CARS_UI_FIXTURE = r'''class InlineKeyboardButton:
    def __init__(self, text, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

class InlineKeyboardMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows

def client_of(card):
    return None

def card_kb(card, staff):
    cid = card["id"]
    rows = [
        [InlineKeyboardButton("Редактировать данные", callback_data="car_edit:%d" % cid)],
        [InlineKeyboardButton("Комплексная диагностика", callback_data="car_cond:%d" % cid)],
        [InlineKeyboardButton("🇰🇷 Проверить VIN · CarHistory",
                              url="https://www.carhistory.kr/search/carhistory/search.car?lang=ru")],
    ]
    rows.append([InlineKeyboardButton("Как видит покупатель", callback_data="car_preview:%d" % cid)])
    return InlineKeyboardMarkup(rows)

def preview_buttons(card, cid):
    rows = []
    rows.append([InlineKeyboardButton("Задать вопрос", callback_data="car_demo:%d" % cid)])
    if card.get("vin"):
        rows.append([InlineKeyboardButton("Проверить VIN",
                                          callback_data="car_demo:%d" % cid)])
    rows.append([InlineKeyboardButton("Все машины", callback_data="cards_cars")])
    return rows

def register(app):
    _ua110_vin_service.start_worker()
'''


CLIENT_UI_FIXTURE = r'''class InlineKeyboardButton:
    def __init__(self, text, callback_data=None, url=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url

def car_screen(card):
    rows = []
    rows.append([InlineKeyboardButton(
        "Задать вопрос по этой машине", callback_data="c_vopros:%d" % card["id"])])
    if card.get("vin"):
        rows.append([InlineKeyboardButton(
            "Проверить VIN",
            url="https://www.vindecoderz.com/EN/check-lookup/" + str(card["vin"]))])
    rows.append([InlineKeyboardButton("← Все машины", callback_data="c_cars")])
    return rows
'''


VIN_SERVICE_FIXTURE = r'''import threading
_worker = None

def start_worker():
    global _worker
    _worker = threading.Thread(target=lambda: None, daemon=True)
    _worker.start()
    return True

# >>> UA115 VIN AUTOWORKER DISABLED
def start_worker() -> None:
    return None
# <<< UA115 VIN AUTOWORKER DISABLED
'''


PUBLISHER_FIXTURE = r'''def _master(kod):
    return "", None, {}

# >>> UA111 FINAL PUBLIC SPEC NORMALIZER V1
_UA111_BASE_MASTER = _master

def _master(kod):
    html, diag, card = _UA111_BASE_MASTER(kod)
    if isinstance(html, str) and html:
        import ua_additional_spec as _ua111_spec
        html = _ua111_spec.inject_public_spec(html, kod)
    return html, diag, card
# <<< UA111 FINAL PUBLIC SPEC NORMALIZER V1
'''


def test_legacy_generators() -> None:
    for filename in ("master_card.py", "stranica.py", "yadro.py"):
        patched = target.patch_legacy_generator(GENERATOR_FIXTURE, filename)
        assert patched == target.patch_legacy_generator(patched, filename)
        assert not target.FORBIDDEN_CTA_SOURCE.search(patched)
        module = load_source(patched, filename)
        row = {"vin": "WDD2452322J561014", "stage": 4, "videos": 2}
        rendered = module._ua068_vin_block("UA-0017", row)
        assert "WDD2452322J561014" in rendered
        assert "ua-clean-vin" in rendered
        assert 'data-ua-stage="4"' in rendered
        assert 'data-ua-video-count="2"' in rendered
        assert not target.FORBIDDEN.search(rendered)
        assert module._ua068_card_errors(rendered, "UA-0017", row) == []
        contaminated = rendered.replace("</div>", "Проверить VIN в CarHistory</div>", 1)
        assert "VIN advertisement forbidden" in module._ua068_card_errors(
            contaminated, "UA-0017", row
        )
        future = module._ua068_vin_block("UA-0017", row)
        assert "UA-0017" in future and not target.FORBIDDEN.search(future)
        assert module._ua068_card_errors(future, "UA-0017", row) == []


def test_cars_ui() -> None:
    patched = target.patch_cars_ui(CARS_UI_FIXTURE)
    assert patched == target.patch_cars_ui(patched)
    assert not target.FORBIDDEN_CTA_SOURCE.search(patched)
    module = load_source(patched, "cars_ui.py")
    markup = module.card_kb({"id": 7}, None)
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [button.text for button in buttons] == [
        "Редактировать данные", "Комплексная диагностика", "Как видит покупатель"
    ]
    assert not any(button.url for button in buttons)
    assert patched.count(target.WORKER_REGISTRATION) == 1
    preview = module.preview_buttons({"vin": "WDD2452322J561014"}, 7)
    assert [button.text for row in preview for button in row] == ["Задать вопрос", "Все машины"]


def test_client_ui() -> None:
    patched = target.patch_client_ui(CLIENT_UI_FIXTURE)
    assert patched == target.patch_client_ui(patched)
    assert "vindecoderz" not in patched.casefold()
    assert not target.FORBIDDEN_CTA_SOURCE.search(patched)
    module = load_source(patched, "client_ui.py")
    rows = module.car_screen({
        "id": 7,
        "vin": "WDD2452322J561014",
    })
    buttons = [button for row in rows for button in row]
    assert [button.text for button in buttons] == [
        "Задать вопрос по этой машине", "← Все машины",
    ]
    assert not any(button.url for button in buttons)


def test_external_url_guard() -> None:
    allowed = (
        "<script src='https://telegram.org/js/telegram-web-app.js'></script>"
        "<a href=https://wa.me/380992222002>x</a>"
        "<script>// this is an ordinary JavaScript comment</script>"
        "https://schema.org"
    )
    assert not (target.external_hosts(allowed) - target.APPROVED_HOSTS)
    vectors = {
        "href": "<a href='https://ads.example/a'>x</a>",
        "src": "<iframe src=//ads.example/frame></iframe>",
        "action": "<form action='https://ads.example/post'></form>",
        "formaction": "<button formaction=https://ads.example/buy>x</button>",
        "meta": "<meta http-equiv='refresh' content='0; url=https://ads.example/go'>",
        "css": "<style>x{background:url(https://ads.example/pixel)}</style>",
        "plain": "<script>const offer = 'https://ads.example/vin';</script>",
    }
    for name, value in vectors.items():
        assert target.external_hosts(value) - target.APPROVED_HOSTS == {"ads.example"}, name

    preamble = r'''from typing import Any
import html
import re
VIN_START = "<!--VIN_START-->"
VIN_END = "<!--VIN_END-->"
def canonical_uid(_value): return "UA-0017"
def _car_vin(_uid): return "WDD2452322J561014"
def _stage_number(_uid): return 4
_SPEC_COUNT = 10
def fetch_specs(_uid): return [{} for _ in range(_SPEC_COUNT)]
def inject_public_spec(source, _value): return source
'''
    module = load_source(preamble + target.PY_BLOCK, "ua115_embedded_guard.py")
    spec_rows = "".join(
        "<div class='ua-addspec-row'><dt>x</dt><dd>y</dd></div>"
        for _ in range(10)
    )
    clean = "<!--VIN_START--><div>old</div><!--VIN_END-->" + spec_rows + allowed
    rendered = module.inject_public_spec(clean, "UA-0017")
    assert "WDD2452322J561014" in rendered
    assert rendered.count("<!--VIN_START-->") == 1
    assert rendered.count("<!--VIN_END-->") == 1
    module._SPEC_COUNT = 0
    try:
        module.inject_public_spec("<!--VIN_START--><div>old</div><!--VIN_END-->", "UA-0017")
    except RuntimeError as exc:
        assert str(exc).startswith("UA115_ADDITIONAL_SPEC_INCOMPLETE:")
    else:
        raise AssertionError("future publisher accepted zero specification rows")
    module._SPEC_COUNT = 11
    try:
        module.inject_public_spec(clean, "UA-0017")
    except RuntimeError as exc:
        assert str(exc).startswith("UA115_ADDITIONAL_SPEC_INCOMPLETE:")
    else:
        raise AssertionError("future publisher accepted truncated specification rows")
    module._SPEC_COUNT = 10
    try:
        module.inject_public_spec(spec_rows, "UA-0017")
    except RuntimeError as exc:
        assert str(exc).startswith("UA115_VIN_BLOCK_COUNT:")
    else:
        raise AssertionError("future publisher accepted a missing VIN block")
    double_vin = (
        "<!--VIN_START--><div>one</div><!--VIN_END-->"
        "<!--VIN_START--><div>two</div><!--VIN_END-->" + spec_rows
    )
    try:
        module.inject_public_spec(double_vin, "UA-0017")
    except RuntimeError as exc:
        assert str(exc).startswith("UA115_VIN_BLOCK_COUNT:")
    else:
        raise AssertionError("future publisher accepted duplicate VIN blocks")
    for name, value in vectors.items():
        contaminated = "<!--VIN_START--><div>old</div><!--VIN_END-->" + spec_rows + value
        try:
            module.inject_public_spec(contaminated, "UA-0017")
        except RuntimeError as exc:
            assert str(exc).startswith("UA115_UNAPPROVED_EXTERNAL_HOST:"), name
        else:
            raise AssertionError("embedded guard missed " + name)


def test_vin_service_stays_active() -> None:
    patched = target.enable_vin_service(VIN_SERVICE_FIXTURE)
    assert patched == target.enable_vin_service(patched)
    assert target.WORKER_START not in patched and target.WORKER_END not in patched
    assert patched.count("def start_worker") == 1
    assert "threading.Thread" in patched and "_worker.start()" in patched


def test_final_publisher_boundary_is_required() -> None:
    target.validate_publisher(PUBLISHER_FIXTURE)
    try:
        target.validate_publisher("def _master(kod): return '', None, {}\n")
    except target.InstallError as exc:
        assert str(exc) == "FINAL_PUBLIC_SPEC_NORMALIZER_MISSING"
    else:
        raise AssertionError("future-card spec boundary falsely accepted")


def test_legacy_vin_ad_triggers_are_removed() -> None:
    class FakeAPI(deployment.API):
        def __init__(self) -> None:
            self.tasks = {
                "always_on": [
                    {"id": 1, "enabled": True,
                     "command": "python3.10 /home/Carix/start_safe.py"},
                    {"id": 2, "enabled": True,
                     "command": "cd /home/Carix/autopilot_inbox/cloud/task_068_ferry_vin && "
                                "python3.10 task068_ferry_vin_repair.py"},
                ],
                "schedule": [
                    {"id": 3, "enabled": True,
                     "command": "python3.10 task068_ferry_vin_repair.py --rollback"},
                    {"id": 4, "enabled": False,
                     "command": "python3.10 task068_ferry_vin_repair.py"},
                    {"id": 5, "enabled": True,
                     "command": "python3.10 harmless_maintenance.py"},
                ],
            }

        def request(self, method, url, data=None, headers=None, allowed=(200,)):
            del data, headers, allowed
            kind = "always_on" if "/always_on/" in url else "schedule"
            if method == "GET":
                return 200, ("{\"results\":" + __import__("json").dumps(self.tasks[kind]) + "}").encode()
            if method == "DELETE":
                identifier = int(url.rstrip("/").rsplit("/", 1)[-1])
                self.tasks[kind] = [item for item in self.tasks[kind] if item["id"] != identifier]
                return 204, b""
            raise AssertionError((method, url))

    api = FakeAPI()
    audit: dict[str, object] = {}
    result = api.remove_legacy_vin_ad_triggers(audit)
    assert result is audit
    assert result["status"] == "PASS" and result["remaining"] == 0
    assert result["operation"] == "IRREVERSIBLE_SAFETY_QUARANTINE"
    assert result["irreversible"] is True
    assert result["rollback_policy"] == "NEVER_RESTORE_OWNER_FORBIDDEN_VIN_AD_TRIGGER"
    assert result["candidate_count"] == 3 and result["removed_count"] == 3
    assert len(result["candidate_inventory_sha256"]) == 64
    assert {item["id"] for item in result["removed"]} == {2, 3, 4}
    assert {item["id"] for item in api.tasks["always_on"]} == {1}
    assert {item["id"] for item in api.tasks["schedule"]} == {5}

    class PartialFailureAPI(FakeAPI):
        def delete_trigger(self, trigger):
            if trigger == ("schedule", 3):
                raise deployment.ControllerError("SIMULATED_DELETE_FAILURE")
            super().delete_trigger(trigger)

    partial = PartialFailureAPI()
    partial_audit: dict[str, object] = {}
    try:
        partial.remove_legacy_vin_ad_triggers(partial_audit)
    except deployment.ControllerError as exc:
        assert str(exc) == "SIMULATED_DELETE_FAILURE"
    else:
        raise AssertionError("partial quarantine failure was hidden")
    assert partial_audit["status"] == "FAIL"
    assert partial_audit["irreversible"] is True
    assert partial_audit["rollback_policy"] == "NEVER_RESTORE_OWNER_FORBIDDEN_VIN_AD_TRIGGER"
    assert partial_audit["candidate_count"] == 3
    assert partial_audit["removed_count"] == 1
    assert partial_audit["removed"][0]["id"] == 2

    clean = FakeAPI()
    clean.tasks = {
        "always_on": [{"id": 1, "enabled": True,
                       "command": "python3.10 /home/Carix/start_safe.py"}],
        "schedule": [{"id": 5, "enabled": False,
                      "command": "python3.10 harmless_maintenance.py"}],
    }
    clean_audit = clean.remove_legacy_vin_ad_triggers({})
    assert clean_audit["candidate_count"] == 0
    assert clean_audit["removed_count"] == 0
    assert clean_audit["remaining"] == 0


def test_legacy_vin_ad_remote_files_are_removed() -> None:
    class FakeAPI(deployment.API):
        def __init__(self) -> None:
            self.files = {
                path: ("print('legacy VIN ad source: %s')\n" % path).encode()
                for path in deployment.LEGACY_VIN_AD_REMOTE_FILES
            }

        def read(self, path, missing=False):
            del missing
            return self.files.get(path)

        def delete_file(self, path):
            self.files.pop(path, None)

    api = FakeAPI()
    audit = api.remove_legacy_vin_ad_remote_files({})
    assert audit["status"] == "PASS"
    assert audit["candidate_count"] == len(deployment.LEGACY_VIN_AD_REMOTE_FILES)
    assert audit["removed_count"] == len(deployment.LEGACY_VIN_AD_REMOTE_FILES)
    assert audit["remaining"] == 0
    assert len(audit["candidate_inventory_sha256"]) == 64
    assert api.files == {}

    clean = api.remove_legacy_vin_ad_remote_files({})
    assert clean["status"] == "PASS"
    assert clean["candidate_count"] == 0
    assert clean["removed_count"] == 0
    assert clean["remaining"] == 0


def test_rollback_is_bound_to_the_installed_postimage() -> None:
    saved = {
        "BACKUPS": target.BACKUPS,
        "LATEST": target.LATEST,
        "CERTIFIED": target.CERTIFIED,
        "LOCK": target.LOCK,
        "DB": target.DB,
        "SOURCE_PATHS": target.SOURCE_PATHS,
        "PUBLIC_ROOTS": target.PUBLIC_ROOTS,
        "IDS": target.IDS,
    }
    try:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source = root / "generator.py"
            public = root / "video"
            page = public / "UA-0001.html"
            public.mkdir()
            source.write_text("before-source", encoding="utf-8")
            page.write_text("before-page", encoding="utf-8")
            source.chmod(0o640)
            page.chmod(0o644)
            target.BACKUPS = root / "backups"
            target.LATEST = root / "latest.txt"
            target.CERTIFIED = root / "certified.json"
            target.LOCK = root / "task.lock"
            target.DB = root / "crm.db"
            target.DB.write_bytes(b"crm-unchanged")
            target.SOURCE_PATHS = (source,)
            target.PUBLIC_ROOTS = (public,)
            target.IDS = ("UA-0001",)

            folder = target.backup(target.target_paths())
            manifest_sha = target.sha(target.read(folder / "manifest.json") or b"")
            target.atomic_json(target.CERTIFIED, {
                "schema_version": 1,
                "task_id": target.TASK_ID,
                "backup": str(folder),
                "backup_manifest_sha256": manifest_sha,
                "certified_at": target.now(),
            })
            assert not target.LATEST.exists(), "a backup-only run must not retarget rollback"
            source.write_text("installed-source", encoding="utf-8")
            page.write_text("installed-page", encoding="utf-8")
            assert target.seal_backup(folder) == manifest_sha
            assert manifest_sha == target.sha(target.read(folder / "manifest.json") or b"")

            page.write_text("newer-legitimate-page", encoding="utf-8")
            try:
                target.restore(folder, require_installed=True)
            except target.InstallError as exc:
                assert str(exc).startswith("ROLLBACK_CONCURRENT_CHANGE:")
            else:
                raise AssertionError("rollback overwrote a concurrent change")
            assert source.read_text(encoding="utf-8") == "installed-source"
            assert page.read_text(encoding="utf-8") == "newer-legitimate-page"

            page.write_text("installed-page", encoding="utf-8")
            restored = target.restore(folder, require_installed=True)
            assert restored["status"] == "PASS"
            assert restored["restored_exact"] is True
            assert restored["crm_unchanged"] is True
            assert restored["protected_files_unchanged"] is True
            assert restored["unexpected_changes"] == 0
            assert restored["restored_sha256"] == {
                str(source): target.sha(b"before-source"),
                str(page): target.sha(b"before-page"),
            }
            assert restored["restored_mode"] == {
                str(source): 0o640,
                str(page): 0o644,
            }
            assert source.read_text(encoding="utf-8") == "before-source"
            assert page.read_text(encoding="utf-8") == "before-page"

            # Known content with chmod drift is restored to the certified
            # preimage mode, and then another rollback is a truthful no-op.
            page.chmod(0o600)
            mode_fixed = target.restore(folder, require_installed=True)
            assert mode_fixed["restored"] == [str(page)]
            assert target.stat.S_IMODE(page.stat().st_mode) == 0o644
            again = target.restore(folder, require_installed=True)
            assert again["status"] == "PASS" and again["restored"] == []
            assert again["restored_exact"] is True

            # Remote rollback resolves the certified pointer, not the mutable
            # legacy LATEST pointer.
            target.LATEST.write_text(str(root / "wrong-backup") + "\n", encoding="utf-8")
            via_run = target.run("rollback", manifest_sha)
            assert via_run["status"] == "PASS" and via_run["restored_exact"] is True

            # Without a postimage, rollback can only report PASS when every
            # target is already the exact preimage.
            unsealed = target.backup(target.target_paths())
            unsealed_sha = target.sha(target.read(unsealed / "manifest.json") or b"")
            exact = target.restore(
                unsealed, require_installed=True, expected_sha256=unsealed_sha
            )
            assert exact["restored_exact"] is True and exact["restored"] == []
            page.chmod(0o600)
            try:
                target.restore(
                    unsealed, require_installed=True,
                    expected_sha256=unsealed_sha,
                )
            except target.InstallError as exc:
                assert str(exc) == "BACKUP_NOT_SEALED"
            else:
                raise AssertionError("unsealed rollback rewrote unknown chmod drift")
            assert target.stat.S_IMODE(page.stat().st_mode) == 0o600
            page.chmod(0o644)
            page.write_text("unknown-without-postimage", encoding="utf-8")
            try:
                target.restore(
                    unsealed, require_installed=True,
                    expected_sha256=unsealed_sha,
                )
            except target.InstallError as exc:
                assert str(exc) == "BACKUP_NOT_SEALED"
            else:
                raise AssertionError("unsealed rollback rewrote an unknown state")
            assert page.read_text(encoding="utf-8") == "unknown-without-postimage"
    finally:
        for name, value in saved.items():
            setattr(target, name, value)


def test_backup_phase_certifies_the_exact_install_preimage() -> None:
    saved = {
        "BACKUPS": target.BACKUPS,
        "LATEST": target.LATEST,
        "CERTIFIED": target.CERTIFIED,
        "SOURCE_PATHS": target.SOURCE_PATHS,
        "PUBLIC_ROOTS": target.PUBLIC_ROOTS,
        "IDS": target.IDS,
        "DB": target.DB,
        "backup": target.backup,
        "certified_backup": target.certified_backup,
        "car_rows": target.car_rows,
        "patch_source_files": target.patch_source_files,
        "load_spec": target.load_spec,
        "transform": target.transform,
        "verify": target.verify,
        "seal_backup": target.seal_backup,
    }
    try:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            source = root / "source.py"
            public = root / "video"
            page = public / "UA-0001.html"
            public.mkdir()
            source.write_text("source-a", encoding="utf-8")
            page.write_text("page-a", encoding="utf-8")
            target.BACKUPS = root / "backups"
            target.LATEST = root / "latest.txt"
            target.CERTIFIED = root / "certified.json"
            target.SOURCE_PATHS = (source,)
            target.PUBLIC_ROOTS = (public,)
            target.IDS = ("UA-0001",)

            first = target.backup_only()
            first_sha = first["backup_manifest_sha256"]
            pointer = json.loads(target.CERTIFIED.read_text(encoding="utf-8"))
            assert pointer["backup"] == first["backup"]
            assert pointer["backup_manifest_sha256"] == first_sha
            assert target.certified_backup(first_sha) == pathlib.Path(first["backup"])
            assert not target.LATEST.exists(), "backup certification must not arm rollback"

            source.write_text("source-b", encoding="utf-8")
            second = target.backup_only()
            second_sha = second["backup_manifest_sha256"]
            assert second_sha != first_sha
            source.write_text("source-a", encoding="utf-8")
            try:
                target.certified_backup(first_sha)
            except target.InstallError as exc:
                assert str(exc) == "CERTIFIED_BACKUP_IDENTITY"
            else:
                raise AssertionError("install accepted a superseded backup pointer")

            source.write_text("source-b", encoding="utf-8")
            assert target.certified_backup(second_sha) == pathlib.Path(second["backup"])

            events = []
            original_certified = target.certified_backup
            target.certified_backup = lambda expected: events.append(
                ("certified", expected)
            ) or original_certified(expected)

            def forbidden_backup(_paths):
                raise AssertionError("install created an unauthorized second backup")

            target.backup = forbidden_backup
            database = root / "crm.db"
            database.write_bytes(b"database-unchanged")
            target.DB = database
            target.car_rows = lambda: {"UA-0001": "VIN-EXAMPLE"}
            target.patch_source_files = lambda: {source: b"source-installed"}
            target.load_spec = lambda: object()
            target.transform = lambda original, uid, vin, helper: (
                "page-installed:" + uid + ":" + vin
            )
            target.verify = lambda rows: {
                "status": "PASS", "page_count": 2, "card_count": 1,
                "ua0009": "PASS", "sha256": {}, "source_sha256": {},
                "specification_rows": {"UA-0001": target.MIN_SPEC_ROWS},
                "specification_min_rows": target.MIN_SPEC_ROWS,
            }

            def seal_exact(folder, expected_sha256=None):
                assert folder == pathlib.Path(second["backup"])
                assert expected_sha256 == second_sha
                return second_sha

            target.seal_backup = seal_exact
            installed = target.install(second_sha)
            assert installed["backup_manifest_sha256"] == second_sha
            assert source.read_bytes() == b"source-installed"
            assert page.read_text(encoding="utf-8") == "page-installed:UA-0001:VIN-EXAMPLE"
            assert events == [("certified", second_sha)]
    finally:
        for name, value in saved.items():
            setattr(target, name, value)


def test_controller_binds_remote_commands_and_results_to_backup() -> None:
    expected = "a" * 64

    class FakeAPI(deployment.API):
        def __init__(self):
            self.commands = []
            self.deleted = []

        def delete_file(self, path):
            self.deleted.append(path)

        def create_trigger(self, command):
            self.commands.append(command)
            return "always_on", 91

        def read(self, _path, missing=False):
            del missing
            return json.dumps({
                "task_id": deployment.TASK_ID,
                "contract_id": deployment.CONTRACT,
                "status": "PASS",
                "mode": "INSTALL",
                "backup_manifest_sha256": expected,
            }).encode("utf-8")

        def delete_trigger(self, trigger):
            self.deleted.append(trigger)

    api = FakeAPI()
    result = api.run("install", timeout=1, backup_manifest_sha256=expected)
    assert result["backup_manifest_sha256"] == expected
    assert api.commands == [
        "cd %s && python3.10 task115_remove_vin_ads.py --mode install "
        "--backup-manifest-sha256 %s" % (deployment.REMOTE, expected)
    ]
    assert api.deleted[-1] == ("always_on", 91)

    before = (list(api.commands), list(api.deleted))
    try:
        api.run("install; touch /tmp/injected", timeout=1)
    except deployment.ControllerError as exc:
        assert str(exc) == "REMOTE_MODE"
    else:
        raise AssertionError("unlisted mode reached the remote shell")
    assert (api.commands, api.deleted) == before

    try:
        api.run("install", timeout=1, backup_manifest_sha256="x; touch /tmp/bad")
    except deployment.ControllerError as exc:
        assert str(exc) == "BACKUP_MANIFEST_SHA256_REQUIRED"
    else:
        raise AssertionError("unsafe backup identity reached the remote shell")

    valid = {
        "task_id": deployment.TASK_ID,
        "contract_id": deployment.CONTRACT,
        "status": "PASS",
        "mode": "INSTALL",
        "crm_write": False,
        "media_write": False,
        "backup_manifest_sha256": expected,
        "card_count": 16,
        "page_count": 32,
        "vin_ad_count": 0,
        "ua0009": "PASS",
        "autoworker_enabled": True,
        "specification_min_rows": target.MIN_SPEC_ROWS,
    }
    deployment.validate_remote(valid, "install", expected)
    stale_mode = dict(valid)
    stale_mode["mode"] = "VERIFY"
    try:
        deployment.validate_remote(stale_mode, "install", expected)
    except deployment.ControllerError as exc:
        assert str(exc).startswith("REMOTE_INSTALL_FAIL:")
    else:
        raise AssertionError("stale remote mode was accepted")
    try:
        deployment.validate_remote(valid, "install", "b" * 64)
    except deployment.ControllerError as exc:
        assert str(exc) == "REMOTE_BACKUP_MANIFEST_SHA256_MISMATCH"
    else:
        raise AssertionError("controller accepted the wrong installed backup")

    rollback_hashes = {
        path: deployment.sha(path.encode("utf-8"))
        for path in rollback_deployment.ROLLBACK_TARGET_PATHS
    }
    rollback_modes = {
        path: 0o640 for path in rollback_deployment.ROLLBACK_TARGET_PATHS
    }
    rollback_value = {
        "task_id": deployment.TASK_ID,
        "contract_id": deployment.CONTRACT,
        "mode": "ROLLBACK",
        "status": "PASS",
        "crm_write": False,
        "media_write": False,
        "backup_manifest_sha256": expected,
        "restored_exact": True,
        "restored_sha256": rollback_hashes,
        "restored_mode": rollback_modes,
        "protected_files_unchanged": True,
        "crm_unchanged": True,
        "unexpected_changes": 0,
    }
    assert rollback_deployment.validate_rollback_backup(
        rollback_value, expected
    ) == rollback_hashes
    try:
        rollback_deployment.validate_rollback_backup(
            {**rollback_value, "backup_manifest_sha256": "b" * 64}, expected
        )
    except RuntimeError as exc:
        assert str(exc) == "REMOTE_ROLLBACK_BACKUP_MISMATCH"
    else:
        raise AssertionError("rollback receipt accepted the wrong backup")
    try:
        rollback_deployment.validate_rollback_backup(
            {key: value for key, value in rollback_value.items()
             if key != "backup_manifest_sha256"}, expected
        )
    except RuntimeError as exc:
        assert str(exc) == "REMOTE_ROLLBACK_BACKUP_MISMATCH"
    else:
        raise AssertionError("rollback receipt accepted a missing backup identity")

    for key in (
            "restored_exact", "restored_sha256", "restored_mode",
            "protected_files_unchanged",
            "crm_unchanged", "unexpected_changes"):
        incomplete = dict(rollback_value)
        incomplete.pop(key)
        try:
            rollback_deployment.validate_rollback_backup(incomplete, expected)
        except RuntimeError:
            pass
        else:
            raise AssertionError("rollback accepted missing proof flag: " + key)
    bad_hash_scope = dict(rollback_value)
    bad_hash_scope["restored_sha256"] = dict(rollback_hashes)
    bad_hash_scope["restored_sha256"].pop(next(iter(rollback_hashes)))
    try:
        rollback_deployment.validate_rollback_backup(bad_hash_scope, expected)
    except RuntimeError as exc:
        assert str(exc) == "REMOTE_ROLLBACK_HASHES_INVALID"
    else:
        raise AssertionError("rollback accepted an incomplete target hash set")
    bad_mode = dict(rollback_value)
    bad_mode["restored_mode"] = dict(rollback_modes)
    bad_mode["restored_mode"][next(iter(rollback_modes))] = True
    try:
        rollback_deployment.validate_rollback_backup(bad_mode, expected)
    except RuntimeError as exc:
        assert str(exc) == "REMOTE_ROLLBACK_MODES_INVALID"
    else:
        raise AssertionError("rollback accepted a non-integer exact mode")


def test_remote_api_scope_is_canonical_and_closed() -> None:
    valid = [
        deployment.REMOTE + "/nested/file.py",
        deployment.REMOTE_SCRIPT,
        deployment.REMOTE_RECEIPT,
        *deployment.LEGACY_VIN_AD_REMOTE_FILES,
    ]
    for path in valid:
        url = deployment.API.file_url(path)
        assert url.startswith(deployment.BASE + "files/path/home/Carix/")

    invalid = [
        deployment.REMOTE,
        deployment.REMOTE + "/../task_067/installer.py",
        deployment.REMOTE + "/nested/../file.py",
        deployment.REMOTE + "/./file.py",
        deployment.REMOTE + "//file.py",
        deployment.REMOTE + "/file.py/",
        deployment.REMOTE + "-sibling/file.py",
        "/home/Carix/unapproved.py",
        "home/Carix/relative.py",
        deployment.REMOTE + "/bad\\name.py",
        deployment.REMOTE + "/bad\x00name.py",
    ]
    for path in invalid:
        try:
            deployment.API.file_url(path)
        except deployment.ControllerError as exc:
            assert str(exc) == "REMOTE_SCOPE", repr(path)
        else:
            raise AssertionError("remote path alias escaped scope: " + repr(path))


def test_rollback_live_bytes_match_certified_preimage_hashes() -> None:
    saved_urlopen = rollback_deployment.urllib.request.urlopen
    bodies = {
        uid: ("preimage:" + uid).encode("utf-8") for uid in deployment.IDS
    }
    restored_sha256 = {
        "/home/Carix/video/" + uid + ".html": deployment.sha(body)
        for uid, body in bodies.items()
    }

    class Response:
        status = 200

        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return self.body

    def fake_urlopen(request, timeout=0):
        assert timeout == 30
        uid = request.full_url.split("/")[-1].split(".html", 1)[0]
        return Response(bodies[uid])

    try:
        rollback_deployment.urllib.request.urlopen = fake_urlopen
        assert rollback_deployment.live_integrity(restored_sha256)
        wrong = dict(restored_sha256)
        wrong["/home/Carix/video/UA-0009.html"] = "0" * 64
        assert not rollback_deployment.live_integrity(wrong)
    finally:
        rollback_deployment.urllib.request.urlopen = saved_urlopen


def test_controller_delayed_proof_and_workflow_owned_rollback() -> None:
    saved = {
        "ROOT": deployment.ROOT,
        "HERE": deployment.HERE,
        "API": deployment.API,
        "required": deployment.required,
        "live_verify": deployment.live_verify,
        "sleep": deployment.time.sleep,
    }
    expected_backup = "a" * 64
    specification_rows = {uid: target.MIN_SPEC_ROWS for uid in deployment.IDS}

    def proof(mode):
        return {
            "task_id": deployment.TASK_ID,
            "contract_id": deployment.CONTRACT,
            "status": "PASS",
            "mode": mode,
            "crm_write": False,
            "media_write": False,
            "backup_manifest_sha256": expected_backup,
            "backup": "/remote/certified-a",
            "card_count": 16,
            "page_count": 32,
            "vin_ad_count": 0,
            "ua0009": "PASS",
            "autoworker_enabled": True,
            "specification_rows": dict(specification_rows),
            "specification_min_rows": target.MIN_SPEC_ROWS,
        }

    def values():
        return {
            "PYTHONANYWHERE_API_TOKEN": "token",
            "UAART_REQUEST_PATH": "tasks/requests/request.json",
            "UAART_REQUEST_SHA256": "b" * 64,
            "UAART_TASK_ID": deployment.TASK_ID,
            "UAART_TASK_CLASS": "CRITICAL",
            "UAART_RUN_ID": "123",
            "UAART_RECEIPT_PATH": deployment.RECEIPT_REL,
            "UAART_BACKUP_MANIFEST_SHA256": expected_backup,
        }

    class BaseFakeAPI:
        last = None

        def __init__(self, _token):
            type(self).last = self
            self.calls = []

        @staticmethod
        def _quarantine(audit):
            audit.update({
                "status": "PASS", "candidate_count": 0, "removed_count": 0,
                "remaining": 0, "candidate_inventory_sha256": "c" * 64,
            })
            return audit

        def remove_legacy_vin_ad_triggers(self, audit):
            return self._quarantine(audit)

        def remove_legacy_vin_ad_remote_files(self, audit):
            return self._quarantine(audit)

        def upload(self, _path, _script):
            return None

        def run(self, mode, timeout=1200, backup_manifest_sha256=None):
            del timeout
            self.calls.append((mode, backup_manifest_sha256))
            if mode == "install":
                return proof("INSTALL")
            if mode == "verify":
                return proof("VERIFY")
            raise AssertionError("controller attempted its own rollback: " + mode)

    try:
        with tempfile.TemporaryDirectory() as raw:
            root = pathlib.Path(raw)
            package = root / "cloud/task115_remove_vin_ads"
            package.mkdir(parents=True)
            (package / "remote_installer.py").write_text("VALUE = 1\n", encoding="utf-8")
            deployment.ROOT = root
            deployment.HERE = package
            deployment.required = lambda _environment: values()
            deployment.live_verify = lambda: {
                "status": "PASS", "card_count": 16, "vin_ad_count": 0,
                "ua0009": "PASS", "sha256": {},
                "specification_rows": dict(specification_rows),
                "specification_min_rows": target.MIN_SPEC_ROWS,
            }
            deployment.time.sleep = lambda _seconds: None

            class SuccessAPI(BaseFakeAPI):
                def restart(self):
                    return None

            deployment.API = SuccessAPI
            result = deployment.execute({})
            assert result["status"] == "PASS"
            assert SuccessAPI.last.calls == [
                ("install", expected_backup), ("verify", None), ("verify", None),
            ]
            assert result["remote_delayed_verify"]["page_count"] == 32
            receipt = json.loads((root / deployment.RECEIPT_REL).read_text(encoding="utf-8"))
            assert receipt["specification_min_rows"] == target.MIN_SPEC_ROWS

            class RestartFailureAPI(BaseFakeAPI):
                def restart(self):
                    raise RuntimeError("SIMULATED_RESTART_FAILURE")

            deployment.API = RestartFailureAPI
            failed = deployment.execute({})
            assert failed["status"] == "FAIL"
            assert failed["rollback"] == "DEFERRED"
            assert failed["rollback_owner"] == "GENERIC_CRITICAL_WORKFLOW"
            assert RestartFailureAPI.last.calls == [("install", expected_backup)]

            drift = proof("VERIFY")
            drift["specification_rows"] = dict(specification_rows)
            drift["specification_rows"]["UA-0009"] += 1
            try:
                deployment.validate_specification_proofs(proof("INSTALL"), drift)
            except deployment.ControllerError as exc:
                assert str(exc) == "SPECIFICATION_PROOF_DRIFT"
            else:
                raise AssertionError("controller accepted delayed specification drift")
    finally:
        deployment.ROOT = saved["ROOT"]
        deployment.HERE = saved["HERE"]
        deployment.API = saved["API"]
        deployment.required = saved["required"]
        deployment.live_verify = saved["live_verify"]
        deployment.time.sleep = saved["sleep"]


def test_specification_must_be_nonempty_and_complete() -> None:
    saved = {
        "PUBLIC_ROOTS": target.PUBLIC_ROOTS,
        "IDS": target.IDS,
        "load_spec": target.load_spec,
        "verify_source_files": target.verify_source_files,
    }
    try:
        with tempfile.TemporaryDirectory() as raw:
            public = pathlib.Path(raw) / "video"
            public.mkdir()
            target.PUBLIC_ROOTS = (public,)
            target.IDS = ("UA-0001",)
            target.verify_source_files = lambda: {}

            class FakeSpec:
                count = target.MIN_SPEC_ROWS - 1

                @classmethod
                def fetch_specs(cls, _uid):
                    return [{} for _ in range(cls.count)]

            target.load_spec = lambda: FakeSpec

            def page(row_count: int) -> str:
                rows = "".join(
                    "<div class='ua-addspec-row'><dt>x</dt><dd>y</dd></div>"
                    for _ in range(row_count)
                )
                return (target.ADD_START + rows + target.ADD_END + target.CLEAN_START
                        + "<div>VIN-EXAMPLE</div>" + target.CLEAN_END)

            card = public / "UA-0001.html"
            card.write_text(page(FakeSpec.count), encoding="utf-8")
            try:
                target.verify({"UA-0001": "VIN-EXAMPLE"})
            except target.InstallError as exc:
                assert str(exc).startswith("ADDITIONAL_SPEC_INCOMPLETE:")
            else:
                raise AssertionError("empty/incomplete specification falsely passed")

            FakeSpec.count = target.MIN_SPEC_ROWS
            card.write_text(page(FakeSpec.count), encoding="utf-8")
            result = target.verify({"UA-0001": "VIN-EXAMPLE"})
            assert result["specification_min_rows"] == target.MIN_SPEC_ROWS

            card.write_text(page(FakeSpec.count - 1), encoding="utf-8")
            try:
                target.verify({"UA-0001": "VIN-EXAMPLE"})
            except target.InstallError as exc:
                assert str(exc).startswith("VERIFY:")
            else:
                raise AssertionError("truncated rendered specification falsely passed")
    finally:
        for name, value in saved.items():
            setattr(target, name, value)


def main() -> int:
    target.self_test()
    assert target.external_hosts("<a href='https://wa.me/1'>x</a>") == {"wa.me"}
    assert not (target.external_hosts("<a href='/video/UA-0001.html'>x</a>") - target.APPROVED_HOSTS)
    assert target.external_hosts("<a href='https://ads.example/x'>x</a>") - target.APPROVED_HOSTS == {"ads.example"}
    fixture = "A" + target.ADD_START + "SPEC" + target.ADD_END + "B"
    assert target.canonical(fixture) == "AB"
    test_legacy_generators()
    test_cars_ui()
    test_client_ui()
    test_external_url_guard()
    test_vin_service_stays_active()
    test_final_publisher_boundary_is_required()
    test_legacy_vin_ad_triggers_are_removed()
    test_legacy_vin_ad_remote_files_are_removed()
    test_rollback_is_bound_to_the_installed_postimage()
    test_backup_phase_certifies_the_exact_install_preimage()
    test_controller_binds_remote_commands_and_results_to_backup()
    test_remote_api_scope_is_canonical_and_closed()
    test_rollback_live_bytes_match_certified_preimage_hashes()
    test_controller_delayed_proof_and_workflow_owned_rollback()
    test_specification_must_be_nonempty_and_complete()
    expected_sources = {
        "ua_additional_spec.py", "vin_spec_service.py", "master_card.py",
        "stranica.py", "yadro.py", "cars_ui.py", "client_ui.py", "publikaciya.py",
    }
    assert {path.name for path in target.SOURCE_PATHS} == expected_sources
    for path in (
        pathlib.Path(__file__).with_name("remote_installer.py"),
        pathlib.Path(__file__).with_name("controller.py"),
        pathlib.Path(__file__).with_name("backup_controller.py"),
        pathlib.Path(__file__).with_name("rollback_controller.py"),
    ):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    print("TASK115_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
