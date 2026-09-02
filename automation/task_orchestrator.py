#!/usr/bin/env python3
"""UA ART task orchestrator core — Phase 1 sandbox implementation.

This module is deliberately side-effect free: it classifies tasks, plans locks,
selects AI routes, evaluates retry policy, validates state transitions and
validates final receipts. It has no deploy, network, secret or production-write
capability. Production adapters are a later, separately gated phase.
"""
from __future__ import annotations

import argparse
import dataclasses
import enum
import json
import pathlib
import re
import sys
from typing import Any, Iterable, Mapping, Sequence


class OrchestratorError(ValueError):
    """Base validation error."""


class TaskClass(str, enum.Enum):
    FAST = "FAST"
    STANDARD = "STANDARD"
    CRITICAL = "CRITICAL"


class TaskStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    CLASSIFYING = "CLASSIFYING"
    RUNNING = "RUNNING"
    TESTING = "TESTING"
    READY_FOR_DEPLOY = "READY_FOR_DEPLOY"
    DEPLOYING = "DEPLOYING"
    VERIFYING = "VERIFYING"
    FINISHED = "FINISHED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class AIRoute(str, enum.Enum):
    NO_AI = "NO_AI"
    GPT_PRIMARY = "GPT_PRIMARY"
    CLAUDE_REVIEW = "CLAUDE_REVIEW"
    CLAUDE_PRIMARY = "CLAUDE_PRIMARY"
    DUAL_REVIEW = "DUAL_REVIEW"


class FailureClass(str, enum.Enum):
    TRANSIENT = "TRANSIENT"
    LOGICAL = "LOGICAL"
    SAFETY = "SAFETY"
    OWNER_DEPENDENCY = "OWNER_DEPENDENCY"
    UNKNOWN = "UNKNOWN"


CLASS_RANK = {
    TaskClass.FAST: 1,
    TaskClass.STANDARD: 2,
    TaskClass.CRITICAL: 3,
}

ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.QUEUED: {TaskStatus.CLASSIFYING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.CLASSIFYING: {TaskStatus.RUNNING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.RUNNING: {TaskStatus.TESTING, TaskStatus.BLOCKED, TaskStatus.FAILED},
    TaskStatus.TESTING: {
        TaskStatus.READY_FOR_DEPLOY,
        TaskStatus.VERIFYING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.READY_FOR_DEPLOY: {
        TaskStatus.DEPLOYING,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.DEPLOYING: {
        TaskStatus.VERIFYING,
        TaskStatus.ROLLED_BACK,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.VERIFYING: {
        TaskStatus.FINISHED,
        TaskStatus.ROLLED_BACK,
        TaskStatus.BLOCKED,
        TaskStatus.FAILED,
    },
    TaskStatus.BLOCKED: {
        TaskStatus.QUEUED,
        TaskStatus.RUNNING,
        TaskStatus.FAILED,
    },
    TaskStatus.FAILED: set(),
    TaskStatus.ROLLED_BACK: set(),
    TaskStatus.FINISHED: set(),
}

CRITICAL_PATH_PATTERNS = (
    re.compile(r"^\.github/workflows/"),
    re.compile(r"^automation/(?:production_queue|pythonanywhere|.*deploy|.*release)"),
    re.compile(r"(?:^|/)(?:crm\.db|[^/]+\.sqlite3?|[^/]+\.db)$"),
    re.compile(r"(?:^|/)(?:\.env|secrets?|credentials?|private[_-]?keys?)(?:/|$)", re.I),
    re.compile(r"(?:^|/)(?:wrangler\.jsonc|cloudflare|dns)(?:/|$)", re.I),
)

STANDARD_PATH_PATTERNS = (
    re.compile(r"(?:^|/)(?:crm|catalog|cards?|generator|publisher|publication|stages?|counters?|forms?)(?:/|[._-])", re.I),
    re.compile(r"(?:^|/)src/"),
    re.compile(r"\.(?:py|js|ts|tsx)$", re.I),
)

CRITICAL_TEXT_MARKERS = (
    "database migration",
    "schema migration",
    "delete data",
    "mass update",
    "all cards",
    "authentication",
    "authorization",
    "credentials",
    "secret",
    "security",
    "dns",
    "cloudflare",
    "production architecture",
    "deployment architecture",
)

STANDARD_TEXT_MARKERS = (
    "crm",
    "counter",
    "stage",
    "generator",
    "publish",
    "publication",
    "backend",
    "form",
    "voice",
    "photo",
    "catalog",
    "card",
)

DETERMINISTIC_MARKERS = (
    "copy",
    "rename",
    "replace exact",
    "http 200",
    "sha-256",
    "checksum",
    "link validation",
    "backup",
    "rollback",
    "regex",
    "static check",
)

CONTENT_MARKERS = (
    "write text",
    "translate",
    "marketing",
    "seo copy",
    "description",
    "ux",
    "design",
)

TRANSIENT_PATTERNS = (
    re.compile(r"\b429\b"),
    re.compile(r"\b50[23]\b"),
    re.compile(r"timeout|timed out", re.I),
    re.compile(r"connection (?:reset|refused|aborted)", re.I),
    re.compile(r"remote disconnected", re.I),
    re.compile(r"temporar(?:y|ily)", re.I),
    re.compile(r"overloaded|rate[_ -]?limit", re.I),
    re.compile(r"runner (?:unavailable|lost|cancelled)", re.I),
)

LOGICAL_PATTERNS = (
    re.compile(r"syntax(?:error)?", re.I),
    re.compile(r"assert(?:ion)?(?:error| failed)", re.I),
    re.compile(r"schema (?:mismatch|invalid|error)", re.I),
    re.compile(r"regression", re.I),
    re.compile(r"(?:attribute|key|type|value|name)error", re.I),
    re.compile(r"invalid (?:data|state|payload|output)", re.I),
)

SAFETY_PATTERNS = (
    re.compile(r"protected[-_ ]file", re.I),
    re.compile(r"unexpected[-_ ](?:write|change|mutation)", re.I),
    re.compile(r"secret (?:leak|exposure)", re.I),
    re.compile(r"permission (?:escalation|violation)", re.I),
    re.compile(r"rollback (?:failed|failure)", re.I),
)

OWNER_PATTERNS = (
    re.compile(r"owner approval required", re.I),
    re.compile(r"waiting owner", re.I),
    re.compile(r"missing owner approval", re.I),
)


@dataclasses.dataclass(frozen=True)
class TaskRequest:
    task_id: str
    title: str
    description: str
    changed_paths: tuple[str, ...] = ()
    production_required: bool = False
    read_only: bool = False
    complexity: int = 1
    requested_min_class: TaskClass | None = None
    ai_requested: bool = False

    @staticmethod
    def _normalize_path(value: str) -> str:
        path = pathlib.PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise OrchestratorError(f"UNSAFE_PATH:{value}")
        return path.as_posix()

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "TaskRequest":
        try:
            task_id = str(raw["task_id"]).strip()
            title = str(raw["title"]).strip()
            description = str(raw.get("description", "")).strip()
        except KeyError as exc:
            raise OrchestratorError(f"MISSING_FIELD:{exc.args[0]}") from exc
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,79}", task_id):
            raise OrchestratorError("INVALID_TASK_ID")
        if not title:
            raise OrchestratorError("EMPTY_TITLE")
        changed_paths_raw = raw.get("changed_paths", ())
        if not isinstance(changed_paths_raw, (list, tuple)):
            raise OrchestratorError("CHANGED_PATHS_NOT_ARRAY")
        changed_paths = tuple(sorted(set(cls._normalize_path(str(p)) for p in changed_paths_raw)))
        complexity = int(raw.get("complexity", 1))
        if complexity < 1 or complexity > 5:
            raise OrchestratorError("COMPLEXITY_RANGE:1-5")
        min_class_raw = raw.get("requested_min_class")
        min_class = TaskClass(str(min_class_raw).upper()) if min_class_raw else None
        return cls(
            task_id=task_id,
            title=title,
            description=description,
            changed_paths=changed_paths,
            production_required=bool(raw.get("production_required", False)),
            read_only=bool(raw.get("read_only", False)),
            complexity=complexity,
            requested_min_class=min_class,
            ai_requested=bool(raw.get("ai_requested", False)),
        )


@dataclasses.dataclass(frozen=True)
class TaskPlan:
    task_id: str
    task_class: TaskClass
    risk_reasons: tuple[str, ...]
    resource_locks: tuple[str, ...]
    ai_route: AIRoute
    ai_call_budget: int
    retry_budget: int
    production_required: bool
    initial_status: TaskStatus = TaskStatus.QUEUED

    def to_dict(self) -> dict[str, Any]:
        raw = dataclasses.asdict(self)
        raw["task_class"] = self.task_class.value
        raw["ai_route"] = self.ai_route.value
        raw["initial_status"] = self.initial_status.value
        return raw


@dataclasses.dataclass(frozen=True)
class RetryDecision:
    failure_class: FailureClass
    action: str
    retry_allowed: bool
    retries_remaining: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        raw = dataclasses.asdict(self)
        raw["failure_class"] = self.failure_class.value
        return raw


def _matches_any(path: str, patterns: Sequence[re.Pattern[str]]) -> bool:
    return any(pattern.search(path) for pattern in patterns)


def _raise_to_minimum(actual: TaskClass, minimum: TaskClass | None) -> TaskClass:
    if minimum is None or CLASS_RANK[actual] >= CLASS_RANK[minimum]:
        return actual
    return minimum


def classify_task(request: TaskRequest) -> tuple[TaskClass, tuple[str, ...]]:
    text = f"{request.title}\n{request.description}".casefold()
    reasons: list[str] = []

    for path in request.changed_paths:
        if _matches_any(path, CRITICAL_PATH_PATTERNS):
            reasons.append(f"CRITICAL_PATH:{path}")
    for marker in CRITICAL_TEXT_MARKERS:
        if marker in text:
            reasons.append(f"CRITICAL_TEXT:{marker}")

    if reasons:
        detected = TaskClass.CRITICAL
    else:
        standard_reasons: list[str] = []
        for path in request.changed_paths:
            if _matches_any(path, STANDARD_PATH_PATTERNS):
                standard_reasons.append(f"STANDARD_PATH:{path}")
        for marker in STANDARD_TEXT_MARKERS:
            if marker in text:
                standard_reasons.append(f"STANDARD_TEXT:{marker}")
        if request.production_required and len(request.changed_paths) > 3:
            standard_reasons.append("MULTI_FILE_PRODUCTION")
        if request.complexity >= 4:
            standard_reasons.append("HIGH_COMPLEXITY")
        if standard_reasons:
            detected = TaskClass.STANDARD
            reasons.extend(standard_reasons)
        else:
            detected = TaskClass.FAST
            reasons.append("LOW_RISK_DEFAULT")

    final = _raise_to_minimum(detected, request.requested_min_class)
    if final != detected:
        reasons.append(f"OWNER_MINIMUM:{final.value}")
    if request.read_only and final == TaskClass.CRITICAL:
        reasons.append("READ_ONLY_DOES_NOT_DOWNGRADE_PROTECTED_SCOPE")
    return final, tuple(sorted(set(reasons)))


def resource_locks(request: TaskRequest, task_class: TaskClass) -> tuple[str, ...]:
    if request.read_only or not request.production_required:
        return ()

    locks: set[str] = set()
    text = f"{request.title}\n{request.description}".casefold()

    for path in request.changed_paths:
        folded = path.casefold()
        if path.startswith(".github/") or folded.startswith("automation/"):
            locks.add("CONTROL_PLANE")
        if re.search(r"(?:^|/)(?:crm\.db|[^/]+\.sqlite3?|[^/]+\.db)$", path, re.I) or "crm" in folded:
            locks.add("CRM_DB")
        if "catalog" in folded or "generator" in folded or "publisher" in folded:
            locks.add("CATALOG_RENDERER")
        if any(token in folded for token in ("index.html", "homepage", "home/")):
            locks.add("HOMEPAGE")
        match = re.search(r"ua[-_]?0*(\d{1,4})", path, re.I)
        if match:
            locks.add(f"CARD:UA-{int(match.group(1)):04d}")
        if "cloudflare" in folded or "wrangler" in folded:
            locks.add("CLOUDFLARE_CONFIG")
        if "dns" in folded:
            locks.add("DNS")
        if "security" in folded or "auth" in folded or "secret" in folded:
            locks.add("SECURITY_CONTROL_PLANE")

    if "all cards" in text or "mass update" in text:
        locks.add("CATALOG_ALL_CARDS")
    if task_class == TaskClass.CRITICAL and not locks:
        locks.add("GLOBAL_PRODUCTION")
    if task_class == TaskClass.STANDARD and not locks:
        locks.add("APPLICATION_RUNTIME")
    if task_class == TaskClass.FAST and not locks:
        locks.add("CONTENT_SURFACE")
    return tuple(sorted(locks))


def choose_ai_route(request: TaskRequest, task_class: TaskClass) -> tuple[AIRoute, int]:
    text = f"{request.title}\n{request.description}".casefold()
    deterministic = any(marker in text for marker in DETERMINISTIC_MARKERS)
    content_or_design = any(marker in text for marker in CONTENT_MARKERS)

    if task_class == TaskClass.FAST:
        if deterministic and not request.ai_requested:
            return AIRoute.NO_AI, 0
        if content_or_design or request.ai_requested:
            return AIRoute.GPT_PRIMARY, 1
        return AIRoute.NO_AI, 0

    if task_class == TaskClass.STANDARD:
        if deterministic and request.complexity <= 2 and not request.ai_requested:
            return AIRoute.NO_AI, 0
        if request.complexity >= 4:
            return AIRoute.CLAUDE_REVIEW, 2
        return AIRoute.GPT_PRIMARY, 1

    if request.complexity >= 4 or request.ai_requested:
        return AIRoute.DUAL_REVIEW, 3
    return AIRoute.CLAUDE_REVIEW, 2


def retry_budget(task_class: TaskClass) -> int:
    return {
        TaskClass.FAST: 2,
        TaskClass.STANDARD: 3,
        TaskClass.CRITICAL: 1,
    }[task_class]


def build_plan(request: TaskRequest) -> TaskPlan:
    task_class, reasons = classify_task(request)
    route, calls = choose_ai_route(request, task_class)
    return TaskPlan(
        task_id=request.task_id,
        task_class=task_class,
        risk_reasons=reasons,
        resource_locks=resource_locks(request, task_class),
        ai_route=route,
        ai_call_budget=calls,
        retry_budget=retry_budget(task_class),
        production_required=request.production_required,
    )


def classify_failure(message: str) -> FailureClass:
    for pattern in SAFETY_PATTERNS:
        if pattern.search(message):
            return FailureClass.SAFETY
    for pattern in OWNER_PATTERNS:
        if pattern.search(message):
            return FailureClass.OWNER_DEPENDENCY
    for pattern in LOGICAL_PATTERNS:
        if pattern.search(message):
            return FailureClass.LOGICAL
    for pattern in TRANSIENT_PATTERNS:
        if pattern.search(message):
            return FailureClass.TRANSIENT
    return FailureClass.UNKNOWN


def decide_retry(
    task_class: TaskClass,
    message: str,
    attempts_already_used: int,
    repeated_same_signature: int = 1,
) -> RetryDecision:
    if attempts_already_used < 0 or repeated_same_signature < 1:
        raise OrchestratorError("INVALID_RETRY_COUNTER")
    failure = classify_failure(message)
    budget = retry_budget(task_class)
    remaining = max(0, budget - attempts_already_used)

    if failure == FailureClass.TRANSIENT and remaining > 0:
        return RetryDecision(
            failure, "RETRY_SAME_TASK_ID", True, remaining - 1,
            "Transient allowlist matched; preserve task ticket and immutable payload.",
        )
    if failure == FailureClass.LOGICAL:
        action = "ROOT_CAUSE_MODE" if repeated_same_signature >= 2 else "BLOCKED_ROOT_CAUSE_REQUIRED"
        return RetryDecision(
            failure, action, False, remaining,
            "Logical failures are never retried blindly.",
        )
    if failure == FailureClass.SAFETY:
        return RetryDecision(
            failure, "STOP_AND_ROLLBACK", False, remaining,
            "Safety invariant failure requires immediate stop and verified rollback.",
        )
    if failure == FailureClass.OWNER_DEPENDENCY:
        return RetryDecision(
            failure, "BLOCKED_WAITING_OWNER", False, remaining,
            "Explicit owner dependency cannot be auto-retried.",
        )
    return RetryDecision(
        failure, "BLOCKED_CLASSIFY_ROOT_CAUSE", False, remaining,
        "Unknown failures require classification before any retry.",
    )


def validate_transition(current: TaskStatus | str, target: TaskStatus | str) -> None:
    current_status = current if isinstance(current, TaskStatus) else TaskStatus(str(current))
    target_status = target if isinstance(target, TaskStatus) else TaskStatus(str(target))
    if target_status not in ALLOWED_TRANSITIONS[current_status]:
        raise OrchestratorError(
            f"INVALID_TRANSITION:{current_status.value}->{target_status.value}"
        )


def locks_conflict(first: Iterable[str], second: Iterable[str]) -> bool:
    a = set(first)
    b = set(second)
    if not a or not b:
        return False
    if "GLOBAL_PRODUCTION" in a or "GLOBAL_PRODUCTION" in b:
        return True
    if "CATALOG_ALL_CARDS" in a and any(x.startswith("CARD:") or x == "CATALOG_RENDERER" for x in b):
        return True
    if "CATALOG_ALL_CARDS" in b and any(x.startswith("CARD:") or x == "CATALOG_RENDERER" for x in a):
        return True
    return bool(a & b)


def validate_receipt(raw: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "task_id", "status", "task_class", "target_environment", "tests",
        "unexpected_changes", "rollback_ready", "production_required",
    }
    missing = sorted(required - set(raw))
    if missing:
        raise OrchestratorError("RECEIPT_MISSING:" + ",".join(missing))
    if str(raw["status"]).upper() != TaskStatus.FINISHED.value:
        raise OrchestratorError("RECEIPT_STATUS_NOT_FINISHED")
    TaskClass(str(raw["task_class"]).upper())
    if str(raw["tests"]).upper() != "PASS":
        raise OrchestratorError("RECEIPT_TESTS_NOT_PASS")
    if int(raw["unexpected_changes"]) != 0:
        raise OrchestratorError("RECEIPT_UNEXPECTED_CHANGES")
    if not bool(raw["rollback_ready"]):
        raise OrchestratorError("RECEIPT_ROLLBACK_NOT_READY")

    production_required = bool(raw["production_required"])
    environment = str(raw["target_environment"]).casefold()
    if production_required:
        for field in ("backup", "production", "live_verify"):
            if field not in raw:
                raise OrchestratorError(f"RECEIPT_MISSING:{field}")
        if environment != "production":
            raise OrchestratorError("RECEIPT_WRONG_TARGET_ENVIRONMENT")
        if not str(raw["backup"]).strip():
            raise OrchestratorError("RECEIPT_BACKUP_MISSING")
        if str(raw["production"]).upper() != "PASS":
            raise OrchestratorError("RECEIPT_PRODUCTION_NOT_PASS")
        if str(raw["live_verify"]).upper() != "PASS":
            raise OrchestratorError("RECEIPT_LIVE_VERIFY_NOT_PASS")
    else:
        if environment not in {"sandbox", "shadow", "preview", "test"}:
            raise OrchestratorError("RECEIPT_NONPROD_ENVIRONMENT_INVALID")
    return dict(raw)


def _load_json(path: str | None) -> Any:
    if path in (None, "-"):
        return json.load(sys.stdin)
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def self_test() -> None:
    fast = TaskRequest.from_mapping({
        "task_id": "T-FAST",
        "title": "Replace exact phone label",
        "description": "replace exact text and check HTTP 200",
        "changed_paths": ["public/contact.html"],
        "production_required": True,
    })
    assert build_plan(fast).task_class == TaskClass.FAST
    assert build_plan(fast).ai_route == AIRoute.NO_AI

    standard = TaskRequest.from_mapping({
        "task_id": "T-STANDARD",
        "title": "Fix CRM stage counter",
        "description": "update stage counter logic",
        "changed_paths": ["src/crm/counters.py"],
        "production_required": True,
    })
    assert build_plan(standard).task_class == TaskClass.STANDARD

    critical = TaskRequest.from_mapping({
        "task_id": "T-CRITICAL",
        "title": "Change release workflow",
        "description": "deployment architecture",
        "changed_paths": [".github/workflows/release.yml"],
        "production_required": True,
    })
    plan = build_plan(critical)
    assert plan.task_class == TaskClass.CRITICAL
    assert "CONTROL_PLANE" in plan.resource_locks

    assert classify_failure("HTTP 503 temporary failure") == FailureClass.TRANSIENT
    assert classify_failure("SyntaxError line 2") == FailureClass.LOGICAL
    assert classify_failure("protected-file mutation") == FailureClass.SAFETY
    assert decide_retry(TaskClass.FAST, "HTTP 503", 0).retry_allowed
    assert decide_retry(TaskClass.FAST, "SyntaxError", 0, 2).action == "ROOT_CAUSE_MODE"

    validate_transition(TaskStatus.QUEUED, TaskStatus.CLASSIFYING)
    try:
        validate_transition(TaskStatus.QUEUED, TaskStatus.FINISHED)
    except OrchestratorError:
        pass
    else:
        raise AssertionError("invalid transition accepted")

    assert not locks_conflict(("CARD:UA-0001",), ("CARD:UA-0002",))
    assert locks_conflict(("CRM_DB",), ("CRM_DB",))
    assert locks_conflict(("CATALOG_ALL_CARDS",), ("CARD:UA-0002",))

    validate_receipt({
        "task_id": "T",
        "status": "FINISHED",
        "task_class": "FAST",
        "target_environment": "sandbox",
        "tests": "PASS",
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
    })
    print("UAART_ORCHESTRATOR_SELF_TEST_PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    classify = sub.add_parser("classify")
    classify.add_argument("input", nargs="?", default="-")

    retry = sub.add_parser("retry")
    retry.add_argument("--class", dest="task_class", required=True, choices=[x.value for x in TaskClass])
    retry.add_argument("--message", required=True)
    retry.add_argument("--attempts-used", type=int, default=0)
    retry.add_argument("--same-signature", type=int, default=1)

    transition = sub.add_parser("transition")
    transition.add_argument("current", choices=[x.value for x in TaskStatus])
    transition.add_argument("target", choices=[x.value for x in TaskStatus])

    receipt = sub.add_parser("validate-receipt")
    receipt.add_argument("input", nargs="?", default="-")

    sub.add_parser("self-test")

    args = parser.parse_args()
    if args.command == "classify":
        request = TaskRequest.from_mapping(_load_json(args.input))
        _dump(build_plan(request).to_dict())
    elif args.command == "retry":
        _dump(decide_retry(
            TaskClass(args.task_class),
            args.message,
            args.attempts_used,
            args.same_signature,
        ).to_dict())
    elif args.command == "transition":
        validate_transition(TaskStatus(args.current), TaskStatus(args.target))
        _dump({"status": "PASS", "transition": f"{args.current}->{args.target}"})
    elif args.command == "validate-receipt":
        _dump(validate_receipt(_load_json(args.input)))
    else:
        self_test()


if __name__ == "__main__":
    main()
