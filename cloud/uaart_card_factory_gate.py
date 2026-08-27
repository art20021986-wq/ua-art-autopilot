#!/usr/bin/env python3
"""
UA ART CARD FACTORY GATE
=========================

Purpose:
    Read-only inspection gate for the UA ART "card factory" pipeline.
    This tool inspects a single target card record (e.g. UA-0009) and
    reports whether it is structurally ready to be produced, WITHOUT
    ever writing to production data, CRM records, WSGI/site files, or
    triggering a webapp reload.

Safety model (STRICT, DO NOT WEAKEN):
    - This script NEVER opens production database/CRM connections in
      write mode. All DB/API access must be explicitly read-only.
    - This script NEVER modifies files outside its own sandbox/report
      directory (SANDBOX_DIR below).
    - This script NEVER reloads, restarts, or touches any WSGI process.
    - This script refuses to run against any card id that is in the
      PROTECTED_CARD_IDS set unless --allow-protected-readonly-inspect
      is passed, and even then it will only ever READ that record, not
      alter it.
    - No secrets/tokens are read from environment and echoed to output.
      Any credential-shaped string is redacted before logging.

Compatibility:
    Python 3.10+. No third-party dependencies required for the core
    inspection path (stdlib only), so it can run in constrained
    PythonAnywhere free-tier environments without extra installs.

This file is produced under TASK 009 via the Claude API worker /
GitHub bridge. It performs no network calls to PythonAnywhere and no
installation. Any downstream transfer/installation is handled solely
by the separate "PythonAnywhere Inbox Sync" GitHub workflow, which is
responsible for producing its own installation/verification receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Constants / safety boundaries
# ---------------------------------------------------------------------------

GATE_VERSION = "2.0.0"

# Cards UA-0001..UA-0008 are protected and must never be mutated by this
# tool. UA-0009 is the current inspection subject for TASK 009.
PROTECTED_CARD_IDS = {
    "UA-0001", "UA-0002", "UA-0003", "UA-0004",
    "UA-0005", "UA-0006", "UA-0007", "UA-0008",
}

# The only directory this script is allowed to write into. Callers on
# PythonAnywhere must point this at an approved sandbox/report path via
# --sandbox-dir; the default below is intentionally relative and inert
# until explicitly confirmed by the operator.
DEFAULT_SANDBOX_DIR = "./uaart_gate_sandbox"

# Redaction pattern for anything that looks like a secret/token in logs.
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*\S+"
)


def _redact(text: str) -> str:
    return _SECRET_PATTERN.sub(lambda m: m.group(1) + "=<REDACTED>", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        return _redact(msg)


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("uaart_card_factory_gate")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RedactingFormatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


LOG = _build_logger()


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CardInspectionResult:
    card_id: str
    exists: bool
    read_only: bool = True
    checks: dict[str, bool] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def passed(self) -> bool:
        return self.exists and not self.errors and all(self.checks.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "exists": self.exists,
            "read_only": self.read_only,
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
            "passed": self.passed,
            "timestamp_utc": self.timestamp_utc,
            "gate_version": GATE_VERSION,
        }


# ---------------------------------------------------------------------------
# Read-only data source abstraction
# ---------------------------------------------------------------------------

class CardSource:
    """
    Abstract, strictly read-only accessor for card records.

    Concrete production wiring (DB/CRM connection) is intentionally NOT
    included in this cloud deliverable, because this repository must
    never embed production credentials or live connection logic. The
    default implementation below reads from a local JSON fixture only,
    which is sufficient to prove the gate's inspection logic and its
    read-only contract. Any real PythonAnywhere wiring must inject a
    read-only adapter that satisfies this same interface and must not
    expose write methods.
    """

    def get_card(self, card_id: str) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class JsonFixtureCardSource(CardSource):
    def __init__(self, fixture_path: Optional[Path]):
        self.fixture_path = fixture_path
        self._data: dict[str, Any] = {}
        if fixture_path and fixture_path.exists():
            try:
                with fixture_path.open("r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                LOG.warning("Could not read fixture %s: %s", fixture_path, exc)
                self._data = {}

    def get_card(self, card_id: str) -> Optional[dict[str, Any]]:
        return self._data.get(card_id)


# ---------------------------------------------------------------------------
# Core inspection logic
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = ("title", "sku", "status", "category")


def inspect_card(
    card_id: str,
    source: CardSource,
    allow_protected_readonly_inspect: bool = False,
) -> CardInspectionResult:
    result = CardInspectionResult(card_id=card_id, exists=False)

    if card_id in PROTECTED_CARD_IDS and not allow_protected_readonly_inspect:
        result.errors.append(
            f"{card_id} is protected. Pass --allow-protected-readonly-inspect "
            "to permit a READ-ONLY look (mutation remains impossible)."
        )
        return result

    card = source.get_card(card_id)
    if card is None:
        result.errors.append(f"Card {card_id} not found in the read-only source.")
        return result

    result.exists = True

    for field_name in REQUIRED_FIELDS:
        present = bool(card.get(field_name))
        result.checks[f"has_{field_name}"] = present
        if not present:
            result.warnings.append(f"Missing or empty field: {field_name}")

    status = str(card.get("status", "")).lower()
    result.checks["status_is_known"] = status in {
        "draft", "ready", "published", "archived", "pending_review",
    }
    if not result.checks["status_is_known"]:
        result.warnings.append(f"Unrecognized status value: {status!r}")

    sku = str(card.get("sku", ""))
    result.checks["sku_format_ok"] = bool(re.fullmatch(r"[A-Za-z0-9._-]{3,64}", sku))
    if not result.checks["sku_format_ok"]:
        result.warnings.append(f"SKU fails basic format check: {sku!r}")

    return result


# ---------------------------------------------------------------------------
# Sandbox-only report writer
# ---------------------------------------------------------------------------

def write_report(result: CardInspectionResult, sandbox_dir: Path) -> Path:
    sandbox_dir = sandbox_dir.resolve()
    sandbox_dir.mkdir(parents=True, exist_ok=True)

    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", result.card_id)
    report_path = sandbox_dir / f"gate_report_{safe_id}.json"

    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, indent=2, ensure_ascii=False)

    return report_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "UA ART card factory gate: read-only inspection of a card "
            "record. Never writes production or CRM data."
        )
    )
    parser.add_argument(
        "--card-id",
        default="UA-0009",
        help="Card identifier to inspect (default: UA-0009).",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help=(
            "Path to a local, read-only JSON fixture file used as the card "
            "source. Production wiring must be injected separately and must "
            "remain read-only."
        ),
    )
    parser.add_argument(
        "--sandbox-dir",
        type=Path,
        default=Path(DEFAULT_SANDBOX_DIR),
        help="Directory the gate is allowed to write reports into.",
    )
    parser.add_argument(
        "--allow-protected-readonly-inspect",
        action="store_true",
        help="Permit a READ-ONLY inspection of a protected card id (UA-0001..UA-0008).",
    )
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print only the JSON result to stdout (no human-readable summary).",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    source = JsonFixtureCardSource(args.fixture)
    result = inspect_card(
        card_id=args.card_id,
        source=source,
        allow_protected_readonly_inspect=args.allow_protected_readonly_inspect,
    )

    report_path: Optional[Path] = None
    try:
        report_path = write_report(result, args.sandbox_dir)
    except OSError as exc:
        LOG.error("Failed to write sandbox report: %s", exc)

    if args.json_only:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        LOG.info("Card: %s", result.card_id)
        LOG.info("Exists: %s", result.exists)
        LOG.info("Read-only mode: %s", result.read_only)
        LOG.info("Checks: %s", result.checks)
        for w in result.warnings:
            LOG.warning("WARNING: %s", w)
        for e in result.errors:
            LOG.error("ERROR: %s", e)
        LOG.info("PASSED: %s", result.passed)
        if report_path:
            LOG.info("Report written to: %s", report_path)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
