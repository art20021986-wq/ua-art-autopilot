"""
Gate A runner for UA Cards Unified (TASK 021).

Bounded, read-mostly discovery + isolated preview transform.
Python 3.10 standard library only. No production write capability
exists in this module.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

from . import common

CheckpointCallback = Optional[Callable[[int, str], None]]


@dataclass
class CardResult:
    code: str
    status: str  # PASS | FAIL | BLOCKED
    reason: str = ""
    source_path: Optional[str] = None
    source_sha256: Optional[str] = None
    output_path: Optional[str] = None
    output_sha256: Optional[str] = None
    diag_href: Optional[str] = None
    track_href: Optional[str] = None


@dataclass
class GateAResult:
    overall_status: str
    checkpoints: list = field(default_factory=list)
    cards: dict = field(default_factory=dict)
    discovered_inputs: dict = field(default_factory=dict)
    protected_before: dict = field(default_factory=dict)
    protected_after: dict = field(default_factory=dict)
    unexpected_protected_changes: int = 0
    production_write: str = "NO"
    errors: list = field(default_factory=list)


def _emit(cb: CheckpointCallback, pct: int, msg: str) -> None:
    if cb:
        cb(pct, msg)


def discover_card_source(base_root: Path, code: str) -> Optional[Path]:
    candidates = common.candidate_card_paths(base_root, code)
    return common.find_existing_regular(candidates)


def discover_generators(base_root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for name in common.GENERATOR_CANDIDATE_NAMES:
        for p in (base_root / name, base_root / "generators" / name):
            if p.exists() and not p.is_symlink() and p.is_file():
                found[name] = str(common.canonical_resolve(p))
                break
    return found


def discover_crm(base_root: Path) -> Optional[Path]:
    for p in common.candidate_crm_paths(base_root):
        if p.exists() and not p.is_symlink() and p.is_file():
            return p
    return None


def _load_ua0009_evidence(crm_path: Optional[Path]) -> dict:
    """Read-only, non-mutating, allowlisted-column read of UA-0009
    evidence. Never performs DDL/DML/PRAGMA-write/VACUUM/REINDEX."""
    if crm_path is None:
        return {}
    allowlist = {"id", "code", "vin", "status", "carrier_url", "container", "diag_notes"}
    try:
        conn = common.open_crm_readonly(crm_path)
    except common.GateAError:
        return {}
    try:
        cur = conn.execute("PRAGMA table_info(cards);")
        cols = [row[1] for row in cur.fetchall()]
        selected_cols = [c for c in cols if c in allowlist]
        if not selected_cols or "code" not in cols:
            return {}
        col_list = ", ".join(selected_cols)
        cur = conn.execute(
            f"SELECT {col_list} FROM cards WHERE code = ?;", (common.UA0009,)
        )
        row = cur.fetchone()
        if row is None:
            return {}
        return dict(zip(selected_cols, row))
    except sqlite3.Error:
        return {}
    finally:
        conn.close()


def process_card_html(code: str, raw_html: str) -> tuple[str, list[str]]:
    """Return (transformed_html, errors). Never falls back to </body> or
    a guessed insertion point."""
    errors: list[str] = []
    matches = common.find_purchase_anchor_matches(raw_html)
    if len(matches) != 1:
        errors.append(f"expected exactly one purchase anchor, found {len(matches)}")
        return raw_html, errors
    anchor_text = matches[0]
    stripped = common.strip_legacy_blocks(raw_html)
    if anchor_text not in stripped:
        errors.append("purchase anchor lost during legacy block removal")
        return raw_html, errors
    snippet = common.build_diag_tracking_snippet(code)
    transformed = common.insert_before_anchor(stripped, anchor_text, snippet)
    return transformed, errors


def compute_overall_status(cards: dict, unexpected: int, errors: list) -> str:
    """Any FAIL/BLOCKED card, any unexpected protected change, or any
    recorded error forces overall BLOCKED. AWAITING_GATE_B requires
    every card PASS and zero unexpected changes and zero errors."""
    if errors:
        return "BLOCKED"
    if unexpected != 0:
        return "BLOCKED"
    if not cards:
        return "BLOCKED"
    if all(getattr(c, "status", None) == "PASS" for c in cards.values()):
        return "AWAITING_GATE_B"
    return "BLOCKED"


def run_gate_a(
    base_root: Path,
    report_root: Path,
    package_dir: Path,
    checkpoint_cb: CheckpointCallback = None,
) -> GateAResult:
    result = GateAResult(overall_status="BLOCKED")
    write_roots = [report_root, report_root / "preview"]
    writer = common.AtomicWriter(write_roots)

    # Checkpoint 20: bounded discovery only. No recursive scanning.
    _emit(checkpoint_cb, 20, "discovery started")
    card_sources: dict[str, Optional[Path]] = {}
    for code in common.ALL_CODES:
        card_sources[code] = discover_card_source(base_root, code)
        if card_sources[code] is not None:
            result.discovered_inputs[code] = str(common.canonical_resolve(card_sources[code]))
    generators = discover_generators(base_root)
    result.discovered_inputs.update(generators)
    crm_path = discover_crm(base_root)
    if crm_path is not None:
        result.discovered_inputs["crm.db"] = str(common.canonical_resolve(crm_path))
    _emit(checkpoint_cb, 20, "discovery complete")

    for name, path_str in result.discovered_inputs.items():
        try:
            fp = common.fingerprint_file(Path(path_str))
            result.protected_before[name] = fp.sha256
        except common.GateAError as exc:
            result.errors.append(f"fingerprint before failed for {name}: {exc}")

    # Checkpoint 40: read-only CRM evidence for UA-0009 only.
    _emit(checkpoint_cb, 40, "crm evidence read")
    ua0009_evidence = _load_ua0009_evidence(crm_path)
    _emit(checkpoint_cb, 40, "crm evidence complete")

    # Checkpoint 60: per-card structural transform, staged writes only.
    _emit(checkpoint_cb, 60, "per-card transform started")
    staging_root = report_root / "preview" / f".staging-{int(time.time_ns())}"
    cards: dict[str, CardResult] = {}
    for code in common.REAL_CODES:
        src = card_sources.get(code)
        if src is None:
            cards[code] = CardResult(
                code=code, status="BLOCKED",
                reason="missing real card source; no synthetic fallback permitted",
            )
            continue
        try:
            common.require_regular_non_symlink(src)
            raw = src.read_bytes().decode("utf-8", errors="strict")
        except (common.GateAError, UnicodeDecodeError) as exc:
            cards[code] = CardResult(code=code, status="BLOCKED", reason=str(exc))
            continue
        transformed, errors = process_card_html(code, raw)
        if errors:
            cards[code] = CardResult(
                code=code, status="FAIL", reason="; ".join(errors),
                source_path=str(common.canonical_resolve(src)),
                source_sha256=common.sha256_file(src),
            )
            continue
        out_path = staging_root / f"{code}.html"
        try:
            writer.write_text(out_path, transformed)
        except common.GateAError as exc:
            cards[code] = CardResult(code=code, status="BLOCKED", reason=str(exc))
            continue
        cards[code] = CardResult(
            code=code, status="PASS",
            source_path=str(common.canonical_resolve(src)),
            source_sha256=common.sha256_file(src),
            output_path=str(common.canonical_resolve(out_path)),
            output_sha256=common.sha256_file(out_path),
            diag_href=f"{code}-diag.html",
            track_href=f"{code}-track.html",
        )

    # UA-0009 readiness: only from real CRM/generator evidence, never
    # synthetic; owner directive requires real Gate A evidence which is
    # not established by CRM row presence alone.
    if ua0009_evidence:
        cards[common.UA0009] = CardResult(
            code=common.UA0009, status="BLOCKED",
            reason="UA-0009 CRM evidence present but full live Gate A card "
                   "evidence is not yet verified; readiness remains BLOCKED",
        )
    else:
        cards[common.UA0009] = CardResult(
            code=common.UA0009, status="BLOCKED",
            reason="no CRM/generator evidence found for UA-0009; readiness BLOCKED",
        )
    _emit(checkpoint_cb, 60, "per-card transform complete")

    # Checkpoint 80: validation + protected re-fingerprint.
    _emit(checkpoint_cb, 80, "validation started")
    for name, path_str in result.discovered_inputs.items():
        try:
            fp = common.fingerprint_file(Path(path_str))
            result.protected_after[name] = fp.sha256
        except common.GateAError as exc:
            result.errors.append(f"fingerprint after failed for {name}: {exc}")

    unexpected = 0
    for name, before in result.protected_before.items():
        after = result.protected_after.get(name)
        if after != before:
            unexpected += 1
    result.unexpected_protected_changes = unexpected
    _emit(checkpoint_cb, 80, "validation complete")

    # Checkpoint 100: execution finished (not a pass/fail claim by itself).
    _emit(checkpoint_cb, 100, "execution finished")

    result.overall_status = compute_overall_status(cards, unexpected, result.errors)
    result.cards = {k: asdict(v) for k, v in cards.items()}
    result.production_write = "NO"
    return result
