"""Deterministic, dynamic transform for CRM card keyboards.

Removes exactly the two outer duplicate top-level buttons
(`loaded_to_container`, `in_transit`) and guarantees each remains exactly
once inside the single container section, preserving callback data,
handlers, and every other button untouched. Works generically for any
card_id (UA-0001..UA-0011 and any future card) -- no range()/hardcoded
UA-number lists are used.
"""

import copy

DUPLICATE_ACTIONS = {"loaded_to_container", "in_transit"}


def transform_keyboard(keyboard: dict) -> dict:
    new_kb = copy.deepcopy(keyboard)
    top = new_kb.get("top_menu", [])
    sections = new_kb.get("sections", {})
    container_section = sections.get("container_section")
    if container_section is None:
        raise ValueError("container_section missing - fail closed, refusing transform")
    container_buttons = container_section.setdefault("buttons", [])

    kept_top = []
    moved = {}
    for button in top:
        action = button.get("action")
        if action in DUPLICATE_ACTIONS:
            moved[action] = button
        else:
            kept_top.append(button)

    for action in DUPLICATE_ACTIONS:
        existing = [b for b in container_buttons if b.get("action") == action]
        if len(existing) > 1:
            raise ValueError(f"action {action} duplicated inside container_section - fail closed")
        if not existing:
            if action in moved:
                container_buttons.append(moved[action])
            else:
                raise ValueError(f"action {action} missing everywhere - fail closed")

    new_kb["top_menu"] = kept_top
    return new_kb


def audit_keyboard(keyboard: dict) -> dict:
    top = keyboard.get("top_menu", [])
    container_buttons = (
        keyboard.get("sections", {}).get("container_section", {}).get("buttons", [])
    )
    outer = sum(1 for b in top if b.get("action") in DUPLICATE_ACTIONS)
    inner_counts = {
        action: sum(1 for b in container_buttons if b.get("action") == action)
        for action in DUPLICATE_ACTIONS
    }
    return {"outer_duplicate_count": outer, "inner_counts": inner_counts}
