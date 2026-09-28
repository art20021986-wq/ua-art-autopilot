"""Evidence-based readiness metrics that exclude scheduled no-op inflation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


WEIGHTS = {
    "owner_request_autonomy": 0.20,
    "guarded_orchestration": 0.20,
    "production_reliability": 0.25,
    "live_result_quality": 0.20,
    "observability": 0.15,
}


def useful_run_metrics(runs: Iterable[Mapping[str, object]]) -> dict[str, float | int]:
    """Measure unique task execution and ignore monitor/maintenance no-op runs."""

    useful = []
    for run in runs:
        kind = run.get("kind")
        task_id = run.get("task_id")
        if kind in {"monitor", "maintenance", "watchdog_noop"}:
            continue
        if not isinstance(task_id, str) or not task_id:
            continue
        useful.append(run)

    attempts = len(useful)
    successes = sum(run.get("conclusion") == "success" for run in useful)
    first_attempt_tasks: dict[str, Mapping[str, object]] = {}
    for run in sorted(useful, key=lambda item: int(item.get("attempt", 1))):
        first_attempt_tasks.setdefault(str(run["task_id"]), run)
    first_attempt_successes = sum(
        run.get("conclusion") == "success" and int(run.get("attempt", 1)) == 1
        for run in first_attempt_tasks.values()
    )
    unique_tasks = len(first_attempt_tasks)
    return {
        "attempts": attempts,
        "successes": successes,
        "attempt_success_percent": round(100 * successes / attempts, 2) if attempts else 0.0,
        "unique_tasks": unique_tasks,
        "first_attempt_successes": first_attempt_successes,
        "first_attempt_success_percent": (
            round(100 * first_attempt_successes / unique_tasks, 2) if unique_tasks else 0.0
        ),
    }


def calculate_readiness(
    scores: Mapping[str, float],
    critical_gates: Mapping[str, bool],
) -> dict[str, object]:
    """Return weighted readiness with fail-closed caps for missing critical proof."""

    missing = sorted(set(WEIGHTS) - set(scores))
    if missing:
        raise ValueError(f"missing component scores: {', '.join(missing)}")
    normalized: dict[str, float] = {}
    for key in WEIGHTS:
        value = float(scores[key])
        if value < 0 or value > 100:
            raise ValueError(f"{key}: score outside 0..100")
        normalized[key] = value

    raw = sum(normalized[key] * weight for key, weight in WEIGHTS.items())
    required = {
        "main_protected",
        "rollback_5_of_5",
        "first_attempt_95",
        "status_fresh_5m",
        "vin_no_ads",
        "specification_complete",
        "soak_72h",
        "unexpected_changes_zero",
    }
    missing_gates = sorted(key for key in required if critical_gates.get(key) is not True)

    cap = 100.0
    if "unexpected_changes_zero" in missing_gates or "vin_no_ads" in missing_gates:
        cap = min(cap, 59.0)
    if "main_protected" in missing_gates or "rollback_5_of_5" in missing_gates:
        cap = min(cap, 79.0)
    if "first_attempt_95" in missing_gates or "soak_72h" in missing_gates:
        cap = min(cap, 89.0)
    if "status_fresh_5m" in missing_gates or "specification_complete" in missing_gates:
        cap = min(cap, 92.0)

    effective = min(raw, cap)
    return {
        "raw_score": round(raw, 2),
        "effective_score": round(effective, 2),
        "cap": cap,
        "missing_critical_gates": missing_gates,
        "status": "PASS_90" if effective >= 90 and not missing_gates else "NOT_ACCEPTED",
    }
