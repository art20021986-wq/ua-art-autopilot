"""Pure owner-policy candidate. NOT INTEGRATED / NOT DEPLOYED.

No network, filesystem writes, credentials, scheduler or execution capability.
Evidence must be independently verified by a future trusted adapter. A returned
eligibility decision is not authorization, receipt verification or deployment.
"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta
import hashlib
import json
import re


REPORT_TIMEZONE = "Asia/Ho_Chi_Minh"
REPORT_LOCAL_TIME = time(10, 0)
REPORT_FORMAT = "SHORT_WITH_DETAIL_LINK"
TELEGRAM_DESTINATION = "VERIFIED_OWNER_PRIVATE_CRM_CHAT"
NOTIFICATION_CHANNELS = ("TELEGRAM",)
FALLBACK_NOTIFICATION_CHANNELS = ()
TELEGRAM_UNAVAILABLE_ACTION = "KEEP_PENDING_UNTIL_VERIFIED_TELEGRAM_DELIVERY"
UNRESOLVED_INCIDENT_FOLLOWUP = "DAILY_REPORT_ONLY"
OPERATING_WINDOW = "24X7"
MAX_EVIDENCE_AGE = timedelta(minutes=5)
ORDINARY_START_DELAY = timedelta(minutes=5)
MAX_QUEUE_SNAPSHOT_AGE = timedelta(seconds=30)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z")
_TERMINAL = frozenset({"FINISHED", "FAILED", "ROLLED_BACK"})
_NOTIFIABLE = frozenset({"FAILURE", "START_DELAY", "DAILY_REPORT"})
_EVENTS = _NOTIFIABLE | {"PROGRESS", "STARTED", "COMPLETED", "RESUMED", "INCIDENT_REMINDER"}
_RESOURCE_ROOTS = frozenset({
    "GLOBAL_PRODUCTION", "CONTROL_PLANE", "SECURITY_CONTROL_PLANE", "CRM_DB",
    "CATALOG_RENDERER", "CATALOG_ALL_CARDS", "HOMEPAGE", "DOCS", "MEDIA",
    "TEST_FIXTURES", "APPLICATION_RUNTIME", "CLOUDFLARE_CONFIG", "DNS",
})


class PolicyInputError(ValueError):
    """Malformed evidence must stop the caller, never enable an operation."""


def _identifier(value: object, name: str) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise PolicyInputError("INVALID_" + name)
    return value


def _boolean(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise PolicyInputError("EXACT_BOOL_REQUIRED_" + name)
    return value


def _sha(value: object, name: str) -> str:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise PolicyInputError("SHA256_REQUIRED_" + name)
    return value


def _ids(values: object, name: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if type(values) is not tuple or (nonempty and not values):
        raise PolicyInputError("TUPLE_REQUIRED_" + name)
    for value in values:
        _identifier(value, name)
    if len(set(values)) != len(values):
        raise PolicyInputError("DUPLICATE_" + name)
    return values


def _instant(value: object, name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise PolicyInputError("AWARE_DATETIME_REQUIRED_" + name)
    return value


def _resources(values: object, name: str) -> tuple[str, ...]:
    resources = _ids(values, name, nonempty=True)
    for resource in resources:
        parts = resource.split("/")
        if any(part in {"", ".", ".."} for part in parts):
            raise PolicyInputError("NONCANONICAL_RESOURCE")
        if parts[0] not in _RESOURCE_ROOTS and not re.fullmatch(r"CARD:UA-[0-9]{4}", parts[0]):
            raise PolicyInputError("UNKNOWN_RESOURCE_SCOPE")
    return resources


@dataclass(frozen=True)
class Identity:
    task_id: str
    request_sha256: str
    attempt_id: str

    def __post_init__(self) -> None:
        _identifier(self.task_id, "TASK_ID")
        _sha(self.request_sha256, "REQUEST")
        _identifier(self.attempt_id, "ATTEMPT_ID")


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str


@dataclass(frozen=True)
class RecoveryEvidence:
    identity: Identity
    failure_id: str
    checked_at: datetime
    evidence_sha256: str
    checkpoint_sha256: str
    root_cause_fixed: bool
    checks_passed: bool
    checkpoint_verified: bool
    backup_verified: bool
    rollback_verified: bool
    gate_b_verified: bool
    owner_authorization_verified: bool
    gate_b_receipt_sha256: str

    def __post_init__(self) -> None:
        if type(self.identity) is not Identity:
            raise PolicyInputError("IDENTITY_REQUIRED")
        _identifier(self.failure_id, "FAILURE_ID")
        _instant(self.checked_at, "CHECKED_AT")
        _sha(self.evidence_sha256, "EVIDENCE")
        _sha(self.checkpoint_sha256, "CHECKPOINT")
        for name in ("root_cause_fixed", "checks_passed", "checkpoint_verified",
                     "backup_verified", "rollback_verified", "gate_b_verified",
                     "owner_authorization_verified"):
            _boolean(getattr(self, name), name.upper())
        if type(self.gate_b_receipt_sha256) is not str:
            raise PolicyInputError("INVALID_GATE_B_RECEIPT")
        if self.gate_b_receipt_sha256:
            _sha(self.gate_b_receipt_sha256, "GATE_B_RECEIPT")


def failure_decision(identity: Identity, failure_id: str, failure_kind: str) -> Decision:
    """All failure classes stop immediately; no transient-retry exception."""
    if type(identity) is not Identity:
        raise PolicyInputError("IDENTITY_REQUIRED")
    _identifier(failure_id, "FAILURE_ID")
    _identifier(failure_kind, "FAILURE_KIND")
    return Decision("STOP", "FAILURE_REQUIRES_NOTIFICATION_AND_VERIFIED_RECOVERY")


def resume_decision(*, identity: Identity, failure_id: str, task_state: str,
                    production: bool, planned_actions: tuple[str, ...],
                    completed_actions: tuple[str, ...], proposed_action: str,
                    next_action_not_started: bool, evidence: RecoveryEvidence,
                    now: datetime) -> Decision:
    """Evaluate eligibility only; never retry, dispatch, clear HALT or write."""
    if type(identity) is not Identity or type(evidence) is not RecoveryEvidence:
        raise PolicyInputError("EXACT_IDENTITY_AND_EVIDENCE_REQUIRED")
    _identifier(failure_id, "FAILURE_ID")
    _identifier(task_state, "TASK_STATE")
    _boolean(production, "PRODUCTION")
    _boolean(next_action_not_started, "NEXT_ACTION_NOT_STARTED")
    _ids(planned_actions, "PLANNED_ACTIONS", nonempty=True)
    _ids(completed_actions, "COMPLETED_ACTIONS")
    _identifier(proposed_action, "PROPOSED_ACTION")
    _instant(now, "NOW")
    if task_state in _TERMINAL:
        return Decision("STOP", "TERMINAL_TASK_MUST_NOT_RESUME")
    if task_state != "STOPPED":
        return Decision("STOP", "EXPLICIT_STOPPED_CHECKPOINT_REQUIRED")
    if evidence.identity != identity or evidence.failure_id != failure_id:
        return Decision("STOP", "RECOVERY_IDENTITY_OR_FAILURE_MISMATCH")
    age = now - evidence.checked_at
    if not timedelta(0) <= age <= MAX_EVIDENCE_AGE:
        return Decision("STOP", "EVIDENCE_STALE_OR_FROM_FUTURE")
    if not evidence.root_cause_fixed or not evidence.checks_passed:
        return Decision("STOP", "ROOT_CAUSE_AND_SUCCESSFUL_CHECKS_REQUIRED")
    if not evidence.checkpoint_verified or not next_action_not_started:
        return Decision("STOP", "AMBIGUOUS_EFFECT_MUST_BE_RECONCILED")
    if completed_actions != planned_actions[:len(completed_actions)]:
        return Decision("STOP", "CHECKPOINT_IS_NOT_AN_ORDERED_COMPLETED_PREFIX")
    if len(completed_actions) == len(planned_actions):
        return Decision("STOP", "ALL_ACTIONS_ALREADY_COMPLETE")
    if proposed_action in completed_actions:
        return Decision("STOP", "COMPLETED_ACTION_REPLAY_FORBIDDEN")
    if proposed_action != planned_actions[len(completed_actions)]:
        return Decision("STOP", "NEXT_ACTION_MUST_MATCH_VERIFIED_CHECKPOINT")
    if production and not (
        evidence.backup_verified and evidence.rollback_verified
        and evidence.gate_b_verified and evidence.owner_authorization_verified
        and evidence.gate_b_receipt_sha256
    ):
        return Decision("STOP", "PRODUCTION_BACKUP_ROLLBACK_AND_EXISTING_GATE_REQUIRED")
    return Decision("RESUME_ELIGIBLE", "SAME_ATTEMPT_NEXT_UNEXECUTED_ACTION_ONLY")


@dataclass(frozen=True)
class DependencyReceipt:
    identity: Identity
    status: str
    receipt_sha256: str
    independently_verified: bool

    def __post_init__(self) -> None:
        if type(self.identity) is not Identity:
            raise PolicyInputError("IDENTITY_REQUIRED")
        _identifier(self.status, "DEPENDENCY_STATUS")
        _sha(self.receipt_sha256, "DEPENDENCY_RECEIPT")
        _boolean(self.independently_verified, "DEPENDENCY_VERIFIED")


def _resource_conflict(a: str, b: str) -> bool:
    root_a, root_b = a.split("/")[0], b.split("/")[0]
    global_scopes = {"GLOBAL_PRODUCTION", "CONTROL_PLANE", "SECURITY_CONTROL_PLANE", "APPLICATION_RUNTIME", "DNS", "CLOUDFLARE_CONFIG"}
    if root_a in global_scopes or root_b in global_scopes:
        return True
    if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
        return True
    broad_catalog = {"CRM_DB", "CATALOG_RENDERER", "CATALOG_ALL_CARDS"}
    catalog = lambda value: value in broad_catalog | {"HOMEPAGE"} or value.startswith("CARD:")
    return (root_a in broad_catalog and catalog(root_b)) or (root_b in broad_catalog and catalog(root_a))


def independent_task_decision(*, candidate: Identity, stopped: Identity,
                              candidate_resources: tuple[str, ...],
                              stopped_resources: tuple[str, ...],
                              safety_proven: bool, impact_isolated: bool,
                              checked_at: datetime, evidence_sha256: str,
                              required_dependencies: tuple[Identity, ...],
                              receipts: tuple[DependencyReceipt, ...],
                              now: datetime) -> Decision:
    if type(candidate) is not Identity or type(stopped) is not Identity:
        raise PolicyInputError("EXACT_IDENTITIES_REQUIRED")
    _resources(candidate_resources, "CANDIDATE_RESOURCES")
    _resources(stopped_resources, "STOPPED_RESOURCES")
    _boolean(safety_proven, "SAFETY_PROVEN")
    _boolean(impact_isolated, "IMPACT_ISOLATED")
    _instant(checked_at, "CHECKED_AT")
    _instant(now, "NOW")
    _sha(evidence_sha256, "SAFETY_EVIDENCE")
    if type(required_dependencies) is not tuple or any(type(x) is not Identity for x in required_dependencies):
        raise PolicyInputError("EXACT_DEPENDENCIES_REQUIRED")
    if len(set(required_dependencies)) != len(required_dependencies):
        raise PolicyInputError("DUPLICATE_DEPENDENCY")
    if type(receipts) is not tuple or any(type(x) is not DependencyReceipt for x in receipts):
        raise PolicyInputError("EXACT_RECEIPTS_REQUIRED")
    if len({x.identity for x in receipts}) != len(receipts):
        raise PolicyInputError("DUPLICATE_DEPENDENCY_RECEIPT")
    if candidate.task_id == stopped.task_id:
        return Decision("WAIT", "STOPPED_TASK_IS_NOT_INDEPENDENT")
    if not safety_proven or not impact_isolated or not timedelta(0) <= now - checked_at <= MAX_EVIDENCE_AGE:
        return Decision("WAIT", "FRESH_ISOLATION_AND_SAFETY_PROOF_REQUIRED")
    if any(_resource_conflict(a, b) for a in candidate_resources for b in stopped_resources):
        return Decision("WAIT", "RESOURCE_OVERLAP_OR_GLOBAL_IMPACT")
    verified = {r.identity for r in receipts if r.status == "FINISHED" and r.independently_verified}
    if stopped in required_dependencies or candidate in required_dependencies:
        return Decision("WAIT", "STOPPED_OR_SELF_DEPENDENCY")
    if not set(required_dependencies).issubset(verified):
        return Decision("WAIT", "DEPENDENCY_SUCCESS_NOT_PROVEN")
    return Decision("CONTINUE_ELIGIBLE", "INDEPENDENT_RESOURCES_AND_DEPENDENCIES_VERIFIED")


def telegram_event_selected(event_type: str) -> bool:
    """Selection only; no sender. Already-reported incidents get no reminders.

    A trusted adapter must preserve incident identity across polls. A first
    alert awaiting confirmed delivery remains pending, not INCIDENT_REMINDER.
    Distinct new failures remain immediately notifiable.
    """
    if type(event_type) is not str or event_type not in _EVENTS:
        raise PolicyInputError("UNKNOWN_NOTIFICATION_EVENT")
    return event_type in _NOTIFIABLE


@dataclass(frozen=True)
class StartDelayDecision:
    action: str
    reason: str
    event_key: str | None = None
    event_type: str | None = None


def start_delay_decision(*, identity: Identity, snapshot_identity: Identity,
                         readiness_episode: str, task_kind: str, task_state: str,
                         approval_verified: bool, readiness_verified: bool,
                         ready_since: datetime, checked_at: datetime, now: datetime,
                         delivered_event_keys: tuple[str, ...]) -> StartDelayDecision:
    """Select one 5-minute start-delay alert; does not send or persist anything.

    The trusted adapter must preserve ready_since and readiness_episode across
    polls, verify identity/state, serialize dispatch, and record successful
    delivery durably. START_DELAY is a failure subtype, not a progress update.
    """
    if type(identity) is not Identity or type(snapshot_identity) is not Identity:
        raise PolicyInputError("EXACT_IDENTITIES_REQUIRED")
    _identifier(readiness_episode, "READINESS_EPISODE")
    _identifier(task_state, "TASK_STATE")
    if type(task_kind) is not str or task_kind not in {"ORDINARY", "PRICE_SYNC"}:
        raise PolicyInputError("UNSUPPORTED_TASK_KIND")
    _boolean(approval_verified, "APPROVAL_VERIFIED")
    _boolean(readiness_verified, "READINESS_VERIFIED")
    for value, name in ((ready_since, "READY_SINCE"), (checked_at, "CHECKED_AT"), (now, "NOW")):
        _instant(value, name)
    if ready_since > checked_at or checked_at > now:
        raise PolicyInputError("INVALID_QUEUE_TIMESTAMP_ORDER")
    _ids(delivered_event_keys, "DELIVERED_EVENT_KEYS")
    for key in delivered_event_keys:
        _sha(key, "DELIVERED_EVENT_KEY")
    if identity != snapshot_identity:
        return StartDelayDecision("WAIT", "READINESS_IDENTITY_MISMATCH")
    if task_kind == "PRICE_SYNC":
        return StartDelayDecision("WAIT", "PRICE_SYNC_HAS_SEPARATE_60_SECOND_DEADLINE")
    if task_state != "READY" or not approval_verified or not readiness_verified:
        return StartDelayDecision("WAIT", "TASK_NOT_APPROVED_AND_READY_TO_START")
    if now - checked_at > MAX_QUEUE_SNAPSHOT_AGE:
        return StartDelayDecision("WAIT", "FRESH_QUEUE_STATE_REQUIRED")
    if now - ready_since < ORDINARY_START_DELAY:
        return StartDelayDecision("WAIT", "START_DELAY_THRESHOLD_NOT_REACHED")
    binding = ["START_DELAY", identity.task_id, identity.request_sha256,
               identity.attempt_id, readiness_episode]
    event_key = hashlib.sha256(json.dumps(binding, separators=(",", ":")).encode()).hexdigest()
    if event_key in delivered_event_keys:
        return StartDelayDecision("WAIT", "THIS_READINESS_EPISODE_ALREADY_REPORTED", event_key)
    return StartDelayDecision("NOTIFY_ELIGIBLE", "READY_TASK_NOT_STARTED_FOR_300_SECONDS",
                              event_key, "START_DELAY")
