"""TASK 060 minimal patch: AI must parse intake fields, never hand off to staff.

Drop-in replacement for the intake normalization/preview-building logic used by
the bot's photo/text/voice handlers. This module is self-contained so it can be
imported and unit-tested before being wired into the live handler file.

Installation note: this patch has NOT been applied to the live PythonAnywhere
bot process by Claude/Cloud. Per repository policy, Claude/Cloud never writes
to production directly. The owner or an authorized deploy step must copy this
logic into the running bot module, take the required backup, apply atomically,
and restart the bot process. See cloud/task_060/report.md for the exact
install/rollback steps to run on PythonAnywhere.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


def get_allowed_keys(ai_filter_module: Any) -> set:
    """Read ALLOWED at runtime from ai_filter module. Never hardcode keys."""
    allowed = getattr(ai_filter_module, "ALLOWED", None)
    if allowed is None:
        return set()
    return set(allowed)


def normalize_ai_result(raw: Any, allowed_keys: Iterable[str]) -> Dict[str, Any]:
    """Normalize AI vision/text/voice output into {key: value} for allowed keys only.

    Supports three shapes:
      1. Nested:  {"fields": {"price": {"value": 11400}, ...}}
      2. Scalar nested: {"fields": {"price": 11400, ...}}
      3. Flat allowed-key JSON: {"price": 11400, "vin": "..."}

    Missing / unreadable fields are simply absent from the result -- this is
    not an error condition. Unknown keys (not in allowed_keys) are ignored.
    """
    allowed = set(allowed_keys)
    result: Dict[str, Any] = {}

    if not isinstance(raw, dict):
        return result

    fields_block = raw.get("fields")
    if isinstance(fields_block, dict):
        for key, val in fields_block.items():
            if key not in allowed:
                continue
            if isinstance(val, dict) and "value" in val:
                candidate = val.get("value")
            else:
                candidate = val
            if candidate is None or candidate == "":
                continue
            result[key] = candidate

    # Flat top-level allowed keys (in addition to / instead of fields block)
    for key, val in raw.items():
        if key == "fields":
            continue
        if key not in allowed:
            continue
        if val is None or val == "":
            continue
        result.setdefault(key, val)

    return result


def has_any_readable_field(normalized: Dict[str, Any]) -> bool:
    return len(normalized) > 0


def build_crm_preview(normalized: Dict[str, Any], field_labels: Optional[Dict[str, str]] = None) -> str:
    """Build a preview message showing every readable allowed field.

    Does not save to CRM, does not touch the site, does not add the source
    image to any gallery, and does not publish a card. Caller is responsible
    for wiring the '\u2705 \u0420\u0430\u0437\u043c\u0435\u0441\u0442\u0438\u0442\u044c' button separately.
    """
    labels = field_labels or {}
    lines = ["\U0001F4CB \u041f\u0440\u0435\u0432\u044c\u044e CRM (\u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a):"]
    for key, value in normalized.items():
        label = labels.get(key, key)
        lines.append(f"\u2022 {label}: {value}")
    return "\n".join(lines)


def process_intake(raw_ai_result: Any, ai_filter_module: Any) -> Dict[str, Any]:
    """Top-level entry point for text/photo/voice intake handlers.

    Returns a dict:
      {
        "ok": bool,             # True if >=1 allowed field was found
        "fields": {...},        # normalized allowed fields
        "preview_text": str,    # ready-to-send CRM preview (only if ok)
        "route_to_staff": False # ALWAYS False -- staff handoff is forbidden
      }

    This function never routes to a manager and never claims "no managers in
    the system" -- that entire code path is removed. If no allowed field is
    readable, ok=False and the caller must ask the AI/user for a retry, not
    hand off to staff.
    """
    allowed = get_allowed_keys(ai_filter_module)
    normalized = normalize_ai_result(raw_ai_result, allowed)
    ok = has_any_readable_field(normalized)
    out: Dict[str, Any] = {
        "ok": ok,
        "fields": normalized,
        "route_to_staff": False,
    }
    if ok:
        out["preview_text"] = build_crm_preview(normalized)
    return out
