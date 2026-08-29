"""Atomic sale-price writer for the real UA ART CRM schema.

The caller supplies the live connection factory and clock. The function uses
only fixed SQL, one write transaction, one UPDATE, and one audit INSERT.
The cars.price_history field is the existing JSON object keyed by CRM stage.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class PriceWriteResult:
    ok: bool
    reason: str
    card_id: int
    auto_number: Optional[str] = None
    old_value: Any = None
    new_value: Any = None


def _empty(value: Any) -> bool:
    return value in (None, "", 0)


def _same(left: Any, right: Any) -> bool:
    return str(left or "") == str(right or "")


def _price_value(value: Any, allow_clear: bool) -> tuple[bool, Any]:
    if allow_clear and _empty(value):
        return True, None
    if isinstance(value, bool):
        return False, None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False, None
    if not 1 <= number <= 500_000:
        return False, None
    return True, number


def _history(raw: Any) -> Optional[dict]:
    if raw in (None, ""):
        return {}
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_price(
    *,
    connect: Callable[[], sqlite3.Connection],
    now: Callable[[], str],
    card_id: int,
    expected_auto_number: Optional[str],
    expected_status: Any,
    expected_old: Any,
    new_value: Any,
    actor_id: int,
    stage_key: Any,
    correction: bool,
    allow_clear: bool = False,
) -> PriceWriteResult:
    """CAS-update price, stage history and audit in one transaction.

    A non-correction can fill an empty field only. A correction must still see
    exactly the old value observed by the caller. Undo uses allow_clear=True.
    """
    try:
        cid = int(card_id)
        actor = int(actor_id)
    except (TypeError, ValueError):
        return PriceWriteResult(False, "invalid_identity", -1)
    stage = str(stage_key or "")
    if not re.fullmatch(r"[1-9]\d{0,2}", stage):
        return PriceWriteResult(False, "invalid_stage", cid)
    valid_price, normalized = _price_value(new_value, allow_clear)
    if not valid_price:
        return PriceWriteResult(False, "invalid_price", cid)

    con = None
    try:
        con = connect()
        con.row_factory = sqlite3.Row
        with con:
            row = con.execute(
                "SELECT id,auto_number,price_uah,price_history,status "
                "FROM cars WHERE id=?",
                (cid,),
            ).fetchone()
            if row is None:
                return PriceWriteResult(False, "missing_card", cid)
            auto_number = row["auto_number"]
            if expected_auto_number and auto_number != expected_auto_number:
                return PriceWriteResult(
                    False, "identity_conflict", cid, auto_number=auto_number
                )
            if row["status"] != expected_status:
                return PriceWriteResult(
                    False,
                    "stage_conflict",
                    cid,
                    auto_number=auto_number,
                    old_value=row["price_uah"],
                    new_value=normalized,
                )
            current = row["price_uah"]
            if _same(current, normalized):
                return PriceWriteResult(
                    False,
                    "same",
                    cid,
                    auto_number=auto_number,
                    old_value=current,
                    new_value=normalized,
                )
            if correction:
                if not _same(current, expected_old):
                    return PriceWriteResult(
                        False,
                        "conflict",
                        cid,
                        auto_number=auto_number,
                        old_value=current,
                        new_value=normalized,
                    )
            elif not _empty(current):
                return PriceWriteResult(
                    False,
                    "filled",
                    cid,
                    auto_number=auto_number,
                    old_value=current,
                    new_value=normalized,
                )

            old_history = row["price_history"]
            history = _history(old_history)
            if history is None:
                return PriceWriteResult(
                    False,
                    "invalid_history",
                    cid,
                    auto_number=auto_number,
                    old_value=current,
                    new_value=normalized,
                )
            if normalized is None:
                history.pop(stage, None)
            else:
                history[stage] = normalized
            new_history = json.dumps(history, ensure_ascii=False, sort_keys=True)
            timestamp = now()
            cursor = con.execute(
                "UPDATE cars SET price_uah=?,price_history=?,updated_at=? "
                "WHERE id=? AND auto_number IS ? AND price_uah IS ? "
                "AND price_history IS ? AND status IS ?",
                (
                    normalized,
                    new_history,
                    timestamp,
                    cid,
                    auto_number,
                    current,
                    old_history,
                    expected_status,
                ),
            )
            if cursor.rowcount != 1:
                raise sqlite3.OperationalError("price CAS conflict")
            con.execute(
                "INSERT INTO audit "
                "(actor_id,action,entity_type,entity_id,field,"
                "old_value,new_value,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    actor,
                    "card_edit",
                    "cars",
                    cid,
                    "price_uah",
                    str(current) if current is not None else None,
                    str(normalized) if normalized is not None else None,
                    timestamp,
                ),
            )
            # Read back inside the same transaction. Any identity/value/history
            # mismatch raises and therefore rolls the UPDATE and audit INSERT
            # back together; a commit error is also handled by the same block.
            verified = con.execute(
                "SELECT auto_number,price_uah,price_history "
                "FROM cars WHERE id=?",
                (cid,),
            ).fetchone()
            if verified is None or verified["auto_number"] != auto_number:
                raise sqlite3.OperationalError("price readback identity")
            if not _same(verified["price_uah"], normalized):
                raise sqlite3.OperationalError("price readback value")
            read_history = _history(verified["price_history"])
            if read_history is None:
                raise sqlite3.OperationalError("price readback history")
            if normalized is None:
                history_ok = stage not in read_history
            else:
                history_ok = read_history.get(stage) == normalized
            if not history_ok:
                raise sqlite3.OperationalError("price readback history")
    except Exception as exc:
        return PriceWriteResult(False, "database:" + str(exc), cid)
    finally:
        if con is not None:
            try:
                con.close()
            except Exception:
                pass

    return PriceWriteResult(
        True,
        "applied",
        cid,
        auto_number=auto_number,
        old_value=current,
        new_value=normalized,
    )
