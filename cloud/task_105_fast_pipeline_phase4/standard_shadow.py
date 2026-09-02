#!/usr/bin/env python3
"""Deterministic Phase 4 STANDARD shadow matrix for TASK105."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
ORCHESTRATOR = ROOT / "automation/task_orchestrator.py"
OUT = pathlib.Path(__file__).resolve().parent / "standard_shadow_results.json"


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("task105_orchestrator_phase4", ORCHESTRATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("ORCHESTRATOR_SPEC")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CASES: list[dict[str, Any]] = [
    {
        "task_id": "STD-01-FORM",
        "title": "Update selection form validation",
        "description": "deterministic form validation and backup",
        "changed_paths": ["src/forms/selection.py"],
        "production_required": True,
        "complexity": 2,
        "expected_ai": "NO_AI",
    },
    {
        "task_id": "STD-02-CATALOG",
        "title": "Update catalog rendering rule",
        "description": "catalog rendering logic",
        "changed_paths": ["src/catalog/renderer.py"],
        "production_required": True,
        "complexity": 3,
        "expected_ai": "GPT_PRIMARY",
    },
    {
        "task_id": "STD-03-COUNTER",
        "title": "Fix stage counter",
        "description": "counter update with deterministic checksum",
        "changed_paths": ["src/counters/stages.py"],
        "production_required": True,
        "complexity": 2,
        "expected_ai": "NO_AI",
    },
    {
        "task_id": "STD-04-PUBLISH",
        "title": "Repair publication worker",
        "description": "publication worker change",
        "changed_paths": ["src/publication/worker.py"],
        "production_required": True,
        "complexity": 3,
        "expected_ai": "GPT_PRIMARY",
    },
    {
        "task_id": "STD-05-VOICE",
        "title": "Voice parser guard",
        "description": "voice parser regression fix",
        "changed_paths": ["src/voice/parser.py"],
        "production_required": True,
        "complexity": 4,
        "expected_ai": "CLAUDE_REVIEW",
    },
    {
        "task_id": "STD-06-CARD",
        "title": "Single card template rule",
        "description": "card template deterministic static check",
        "changed_paths": ["src/cards/template.py"],
        "production_required": True,
        "complexity": 2,
        "expected_ai": "NO_AI",
    },
    {
        "task_id": "STD-07-PHOTO",
        "title": "Photo path normalizer",
        "description": "photo path normalizer",
        "changed_paths": ["src/media/photo_paths.py"],
        "production_required": True,
        "complexity": 3,
        "expected_ai": "GPT_PRIMARY",
    },
    {
        "task_id": "STD-08-GENERATOR",
        "title": "Generator schema validation",
        "description": "generator schema validation and checksum",
        "changed_paths": ["src/generator/schema.py"],
        "production_required": True,
        "complexity": 2,
        "expected_ai": "NO_AI",
    },
    {
        "task_id": "STD-09-CRM-READONLY",
        "title": "CRM read-only diagnostics",
        "description": "crm diagnostics without database mutation",
        "changed_paths": ["src/crm/diagnostics.py"],
        "production_required": False,
        "read_only": True,
        "complexity": 3,
        "expected_ai": "GPT_PRIMARY",
    },
    {
        "task_id": "STD-10-MULTIFILE",
        "title": "Multi-file form fixture",
        "description": "replace exact form fixtures, backup, rollback and http 200",
        "changed_paths": [
            "video/task105-standard-canary-a.txt",
            "video/task105-standard-canary-b.txt",
            "video/task105-standard-canary-c.txt",
        ],
        "production_required": True,
        "complexity": 2,
        "expected_ai": "NO_AI",
    },
]


def main() -> int:
    module = load_orchestrator()
    results = []
    failures = []
    for source in CASES:
        raw = dict(source)
        expected_ai = raw.pop("expected_ai")
        request = module.TaskRequest.from_mapping(raw)
        plan = module.build_plan(request).to_dict()
        passed = plan["task_class"] == "STANDARD" and plan["ai_route"] == expected_ai
        row = {
            "task_id": source["task_id"],
            "expected_class": "STANDARD",
            "actual_class": plan["task_class"],
            "expected_ai": expected_ai,
            "actual_ai": plan["ai_route"],
            "locks": plan["resource_locks"],
            "status": "PASS" if passed else "FAIL",
        }
        results.append(row)
        if not passed:
            failures.append(row)
    payload = {
        "status": "PASS" if not failures else "FAIL",
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": len(failures),
        "results": results,
    }
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if not failures and len(results) == 10 else 1


if __name__ == "__main__":
    raise SystemExit(main())
