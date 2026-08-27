"""Shared constants and helpers for the UA cards unified pipeline (Gate A only).

SAFETY (TASK 014 / TASK 017 / TASK 018):
- Gate A only. No production writes. No PythonAnywhere execution.
- Banned synthetic placeholder IDs UA-0001..UA-0008 must NEVER be treated
  as real cards, anywhere in the pipeline.
- Any single card failure blocks progression to AWAITING_GATE_B; the
  pipeline instead reports BLOCKED.
- Gate B (production application) is never triggered by any file in this
  package. It always requires explicit, separate owner approval.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "data" / "input_cards"
OUTPUT_DIR = BASE_DIR / "output"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
PREFLIGHT_REPORT_PATH = OUTPUT_DIR / "preflight_report.json"
RUN_LOG_PATH = OUTPUT_DIR / "run_log.json"

# UA-0001 .. UA-0008 are forbidden synthetic/placeholder test IDs.
BANNED_SYNTHETIC_IDS = {f"UA-{i:04d}" for i in range(1, 9)}

FORBIDDEN_ENV_MARKERS = [
    "PYTHONANYWHERE_DOMAIN",
    "PYTHONANYWHERE_SITE",
    "PA_API_TOKEN",
    "PRODUCTION_DB_URL",
]

REQUIRED_CARD_FIELDS = ["card_id", "title", "payload"]


class GateStatus:
    BLOCKED = "BLOCKED"
    AWAITING_GATE_B = "AWAITING_GATE_B"
    NOT_RUN = "NOT_RUN"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json_cards(input_dir: Path = None) -> List[Dict[str, Any]]:
    """Load *.json card files from input_dir (defaults to module INPUT_DIR).

    Read-only: never modifies source files.
    """
    directory = input_dir if input_dir is not None else INPUT_DIR
    cards: List[Dict[str, Any]] = []
    if not directory.exists():
        return cards
    for path in sorted(directory.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            cards.append({
                "card_id": path.stem,
                "_load_error": str(exc),
                "_source_file": str(path),
            })
            continue
        if isinstance(data, dict):
            data["_source_file"] = str(path)
        cards.append(data)
    return cards


def is_banned_synthetic(card_id: str) -> bool:
    return card_id in BANNED_SYNTHETIC_IDS


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
