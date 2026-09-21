#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("probe", HERE / "controller.py")
if spec is None or spec.loader is None:
    raise SystemExit("SPEC")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)

sample = b"""<html><body><span>File storage: 20.6% full \xe2\x80\x93 7.21 GiB of your 35.0 GiB quota</span></body></html>"""
value = mod.parse_quota(sample, "https://www.pythonanywhere.com/user/Carix/files/home/Carix/", 200)
assert value["target_environment"] == "production"
assert value["read_only"] is True
assert value["total_bytes"] == int(round(35.0 * 1024**3))
assert value["used_bytes"] == int(round(7.21 * 1024**3))
assert value["free_bytes"] == value["total_bytes"] - value["used_bytes"]

try:
    mod.parse_quota(sample, "https://www.pythonanywhere.com/login/", 200)
except RuntimeError as exc:
    assert "NOT_AUTHENTICATED" in str(exc)
else:
    raise AssertionError("login redirect accepted")

print("PASS")
