#!/usr/bin/env python3
"""Dependency-free contract tests for TASK 083."""
from __future__ import annotations

import importlib.util
import pathlib
import tempfile


HERE = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


installer = load("task083_remote_installer_test", HERE / "remote_installer.py")
guard = load("task083_guard_test", HERE / "publish_transaction_guard.py")


def test_publisher_patch_is_idempotent():
    source = """
def opublikovat(kod, proba=False):
    return True, 'old'

_UA9_BASE_PUBLISH = opublikovat

def _ua9_sobrat_katalog():
    return '<html></html>', []
"""
    first = installer.patch_publisher(source)
    second = installer.patch_publisher(first)
    assert first == second
    assert first.count(installer.PUB_START) == 1
    assert "_UA083_BASE_PUBLISH = _UA9_BASE_PUBLISH" in first
    assert "publish_one" in first and "rebuild_catalog" in first


def test_cars_ui_patch_is_idempotent_and_single_result():
    source = """
class ApplicationHandlerStop(Exception): pass
async def toggle_publish(update, context):
    return None
def register(app):
    app.add_handler(CallbackQueryHandler(toggle_publish, pattern=r'^car_pub:'))
"""
    first = installer.patch_cars_ui(source)
    second = installer.patch_cars_ui(first)
    assert first == second
    assert first.count(installer.UI_START) == 1
    wrapper = installer.ui_wrapper()
    assert "if ok is not True" in wrapper
    assert wrapper.count("Машина видна клиентам в каталоге.") == 1
    assert "_ua083_restore_publish_preimage" in wrapper
    for field in ("published", "status", "publish_pending"):
        assert field in wrapper


def test_stage_and_catalog_contract():
    rows = {
        "UA-0012": {"auto_number": "UA-0012", "status": "sea_transit"},
        "UA-0013": {"auto_number": "UA-0013", "status": "sea_loaded"},
    }
    filler = "x" * 5200
    source = (
        "<html><body>" + filler
        + '<a href="UA-0012.html?v=1" data-ua-stage-tile="2">На пароме</a>'
        + '<a href="UA-0013.html?v=1" data-ua-stage-tile="2">На пароме</a>'
        + "</body></html>"
    )
    audit = guard._validate_catalog(source, rows)
    assert audit["count"] == 2
    assert audit["cards"]["UA-0012"]["stage"] == 2
    assert audit["cards"]["UA-0013"]["category"] == "more"


def test_snapshot_rollback_restores_and_removes_new_files():
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory).resolve()
        video, site = root / "video", root / "site"
        video.mkdir(); site.mkdir()
        (video / "katalog.html").write_text("before-video", encoding="utf-8")
        (site / "katalog.html").write_text("before-site", encoding="utf-8")
        old_values = {
            "ROOT": guard.ROOT, "VIDEO": guard.VIDEO, "SITE": guard.SITE,
            "DB": guard.DB, "LOCK": guard.LOCK, "BACKUPS": guard.BACKUPS,
            "LOG": guard.LOG, "ROOTS": guard.ROOTS,
        }
        try:
            guard.ROOT = root; guard.VIDEO = video; guard.SITE = site
            guard.DB = root / "crm.db"; guard.LOCK = root / ".lock"
            guard.BACKUPS = root / "backups"; guard.LOG = root / "log"
            guard.ROOTS = (video, site)
            snapshot = guard.Snapshot(["UA-0012"])
            (video / "katalog.html").write_text("after", encoding="utf-8")
            (video / "UA-0012.html").write_text("new", encoding="utf-8")
            value = snapshot.restore()
            assert value["backup_root"] == str(snapshot.root)
            assert (video / "katalog.html").read_text() == "before-video"
            assert (site / "katalog.html").read_text() == "before-site"
            assert not (video / "UA-0012.html").exists()
        finally:
            for name, value in old_values.items():
                setattr(guard, name, value)


def main():
    tests = sorted((name, value) for name, value in globals().items()
                   if name.startswith("test_") and callable(value))
    for name, test in tests:
        test()
        print("PASS", name)
    print("TASK083_CONTRACT_TESTS_PASS")


if __name__ == "__main__":
    main()
