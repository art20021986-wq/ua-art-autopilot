"""Pure reconciliation for canonical task registry snapshots."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping


def _ids(items: Iterable[Mapping[str, object]]) -> list[str]:
    values: list[str] = []
    for item in items:
        value = item.get("task_id")
        if isinstance(value, str) and value:
            values.append(value)
    return values


def reconcile_snapshot(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Find work that is duplicated, lost, orphaned or falsely closed."""

    required_collections = (
        "registry",
        "requests",
        "branches",
        "pull_requests",
        "claims",
        "runs",
        "transactions",
        "receipts",
    )
    collections: dict[str, list[Mapping[str, object]]] = {}
    for name in required_collections:
        value = snapshot.get(name)
        if not isinstance(value, list):
            raise ValueError(f"{name}: required list")
        if any(not isinstance(item, Mapping) for item in value):
            raise ValueError(f"{name}: every item must be an object")
        collections[name] = value

    registry_ids = set(_ids(collections["registry"]))
    request_ids = set(_ids(collections["requests"]))
    receipt_ids = set(_ids(collections["receipts"]))

    observed_ids: set[str] = set()
    for name in required_collections[1:]:
        observed_ids.update(_ids(collections[name]))

    lost_tasks = sorted(observed_ids - registry_ids)
    registry_without_request = sorted(registry_ids - request_ids)

    duplicates: dict[str, list[str]] = {}
    for name, items in collections.items():
        repeated = sorted(task_id for task_id, count in Counter(_ids(items)).items() if count > 1)
        if repeated:
            duplicates[name] = repeated

    active_states = {
        str(item.get("task_id")): str(item.get("state"))
        for item in collections["registry"]
        if isinstance(item.get("task_id"), str)
    }
    false_finished = sorted(
        task_id
        for task_id, state in active_states.items()
        if state == "FINISHED" and task_id not in receipt_ids
    )

    terminal = {"FINISHED", "ROLLED_BACK", "BLOCKED", "HALTED_P0"}
    active_ids = {task_id for task_id, state in active_states.items() if state not in terminal}
    active_claim_ids = set(_ids(collections["claims"]))
    missing_active_claims = sorted(active_ids - active_claim_ids)

    findings = {
        "lost_tasks": lost_tasks,
        "registry_without_request": registry_without_request,
        "duplicates": duplicates,
        "false_finished": false_finished,
        "missing_active_claims": missing_active_claims,
    }
    finding_count = (
        len(lost_tasks)
        + len(registry_without_request)
        + sum(len(value) for value in duplicates.values())
        + len(false_finished)
        + len(missing_active_claims)
    )
    return {
        "status": "PASS" if finding_count == 0 else "BLOCKED",
        "finding_count": finding_count,
        "findings": findings,
    }
