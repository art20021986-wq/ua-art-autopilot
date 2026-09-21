#!/usr/bin/env python3
from __future__ import annotations
import ast
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
controller = (HERE / "controller.py").read_text(encoding="utf-8")
remote = (HERE / "remote_probe.py").read_text(encoding="utf-8")
ast.parse(controller)
ast.parse(remote)

assert "/home/Carix/uploads/seo_daily_storage_probe_20260921.py" in controller
assert "/home/Carix/uploads/seo_daily_storage_probe_20260921.json" in controller
assert "/home/Carix/video" not in controller
assert "crm.db" not in controller
assert "python3.10 seo_daily_storage_probe_20260921.py" in controller
assert "du -s -B 1 /tmp /home/Carix /var/www" in remote
assert 'TOTAL_BYTES = 37580963840' in remote
assert '"task_id": "SEO-DAILY-PODBOR-CANONICAL-20260921"' in remote
assert "/home/Carix/video" not in remote
assert "crm.db" not in remote
print("PASS")
