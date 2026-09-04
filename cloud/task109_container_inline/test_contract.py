#!/usr/bin/env python3
"""Offline contract tests for TASK109."""
from __future__ import annotations

import ast
import pathlib

import controller
import remote_installer as installer


HERE = pathlib.Path(__file__).resolve().parent


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def inspect_python(path: pathlib.Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            require(node.func.id not in {"eval", "exec"}, "denied call")
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
                    require(keyword.value.value is not True, "shell true")


def main() -> int:
    require(installer.self_test() == 0, "installer self-test")
    source = installer.transform_source(installer.source_fixture())
    require(installer.transform_source(source) == source, "source idempotence")
    original = installer.card_fixture()
    transformed, contract = installer.transform_card(original)
    require(installer.transform_card(transformed)[0] == transformed, "card idempotence")
    require(contract["trackable"] is True, "trackable")
    require("ONEYSELGF1046602" in transformed, "container preserved")
    require("Отследить ↗" in transformed, "short russian action")
    require("Відстежити ↗" in transformed, "short ukrainian action")
    require("text-decoration:underline" in transformed, "visible link underline")
    require("flex-wrap:nowrap" in transformed, "single line")
    require('target="_blank"' in transformed, "new tab")
    require('rel="noopener noreferrer"' in transformed, "safe external link")
    require("Отследить контейнер онлайн" not in transformed, "legacy link removed")
    require(transformed.index("ONEYSELGF1046602") < transformed.index("Отследить ↗"), "visual order")
    for path in (HERE / "controller.py", HERE / "remote_installer.py", HERE / "test_contract.py"):
        inspect_python(path)
    browser = controller.mobile_width_contract(require_browser=False)
    require(browser["status"] in {"PASS", "SKIP"}, "browser contract")
    drill = controller.rollback_drill()
    require(drill["status"] == "PASS" and drill["before"] == drill["after"], "rollback drill")
    print("TASK109_CONTRACT_TEST_PASS", browser["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
