#!/usr/bin/env python3
"""Pure fail-closed guards for UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001.

This module deliberately contains no Production paths and no network calls.  It
is shared by the sandbox Gate B runner and by the future runtime integration.
The runtime integration is allowed to *call* these guards, but it must provide
its own audited storage adapters.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import html as html_module
import json
import math
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


CONTRACT_ID = "UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001"
CONTRACT_VERSION = "1.0"
MODE = "PREVIEW_ONLY"
BASE_SHA = "c0244c51c846a6370de943eb247496935125e677"
PUBLIC_MIN_VISIBLE_SPEC_ROWS = 10
MIN_AUTOMATIC_SPEC_CONFIDENCE = 0.90

UID_RE = re.compile(r"^UA-\d{4,5}$")
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCE_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
SPEC_ROW_RE = re.compile(
    r"class\s*=\s*(['\"])[^'\"]*\bua-addspec-row\b[^'\"]*\1",
    re.IGNORECASE,
)
SPEC_ROW_BLOCK_RE = re.compile(
    r"<(?:div|li)\b[^>]*class\s*=\s*(['\"])[^'\"]*\bua-addspec-row\b[^'\"]*\1[^>]*>"
    r"([\s\S]*?)</(?:div|li)>",
    re.IGNORECASE,
)

# These codes remain valid historical values.  They are hidden only from new
# keyboards and rejected only as new choices from stale Telegram messages.
HIDDEN_STATUS_CODES = frozenset(
    {"kr_bought", "sea_loaded", "sea_transit", "ua_handed"}
)

# Fields that a strict VIN decoder may propose.  The additional-spec service is
# never allowed to write them; a separate CAS writer applies this allowlist.
VIN_PRIMARY_FIELDS = frozenset(
    {
        "brand",
        "model",
        "year",
        "trim",
        "body",
        "fuel",
        "engine",
        "engine_cc",
        "gearbox",
        "drive",
    }
)

# Mileage and colour describe the individual vehicle and cannot be inferred
# from a VIN.  They may be copied only from an authenticated vehicle-specific
# record, or entered by the operator.
VEHICLE_PRIMARY_FIELDS = frozenset({"mileage", "mileage_km", "color"})
ALL_PRIMARY_FIELDS = VIN_PRIMARY_FIELDS | VEHICLE_PRIMARY_FIELDS
PRIMARY_ALIAS_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"engine", "engine_cc"}),
    frozenset({"mileage", "mileage_km"}),
)

# What the current public card displays under "Коротко".  Aliases allow the
# legacy and current CRM columns to coexist without a destructive migration.
PUBLIC_BASE_FIELD_GROUPS: tuple[tuple[str, ...], ...] = (
    ("brand",),
    ("model",),
    ("year",),
    ("vin",),
    ("fuel",),
    ("engine_cc", "engine"),
    ("gearbox",),
    ("drive",),
    ("mileage_km", "mileage"),
    ("color",),
)


class RecoveryGuardError(RuntimeError):
    """Machine-readable, owner-readable fail-closed error."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail)
        super().__init__(self.code + ((": " + self.detail) if self.detail else ""))


def canonical_uid(value: Any) -> str:
    uid = str(value or "").strip().upper()
    if not UID_RE.fullmatch(uid):
        raise RecoveryGuardError("INVALID_UID", uid)
    return uid


def normalize_vin(value: Any) -> str:
    vin = re.sub(r"[\s-]+", "", str(value or "")).upper()
    if not VIN_RE.fullmatch(vin):
        raise RecoveryGuardError("INVALID_VIN")
    return vin


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def vin_sha256(value: Any) -> str:
    return sha256_text(normalize_vin(value))


def stable_digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def is_blank(value: Any) -> bool:
    return value is None or _clean(value) == ""


def _as_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if type(value) is bool:
        return value
    if type(value) is int and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    raise RecoveryGuardError("BOOLEAN_VALUE_INVALID")


@dataclasses.dataclass(frozen=True)
class BaseCandidate:
    field: str
    value: str
    source_kind: str
    source: str
    confidence: float
    vin_sha256: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "BaseCandidate":
        return cls(
            field=str(value.get("field") or ""),
            value=_clean(value.get("value")),
            source_kind=str(value.get("source_kind") or ""),
            source=str(value.get("source") or ""),
            confidence=float(value.get("confidence") or 0.0),
            vin_sha256=str(value.get("vin_sha256") or ""),
        )


@dataclasses.dataclass(frozen=True)
class BaseFillPlan:
    writes: Mapping[str, str]
    provenance: Mapping[str, Mapping[str, Any]]
    preserved: tuple[str, ...]
    rejected: tuple[str, ...]
    before_digest: str

    @property
    def audit_digest(self) -> str:
        return stable_digest(
            {
                "writes": dict(self.writes),
                "provenance": dict(self.provenance),
                "preserved": self.preserved,
                "rejected": self.rejected,
                "before_digest": self.before_digest,
            }
        )


def plan_base_fill(
    current: Mapping[str, Any],
    candidates: Iterable[BaseCandidate | Mapping[str, Any]],
    *,
    expected_vin: Any,
    minimum_confidence: float = 0.90,
) -> BaseFillPlan:
    """Plan empty-only writes; never mutate ``current``.

    ``vin_decoder`` may fill only deterministic fields. ``auction_record`` and
    ``same_vin_crm`` may additionally supply mileage/colour because they refer
    to this exact vehicle.  All sources must be bound to the current VIN hash.
    Existing non-empty operator values always win.
    """

    expected_hash = vin_sha256(expected_vin)
    writes: dict[str, str] = {}
    provenance: dict[str, Mapping[str, Any]] = {}
    preserved: set[str] = set()
    rejected: list[str] = []
    ranked: dict[str, BaseCandidate] = {}

    for raw in candidates:
        item = raw if isinstance(raw, BaseCandidate) else BaseCandidate.from_mapping(raw)
        field = item.field
        if field not in ALL_PRIMARY_FIELDS:
            rejected.append(f"{field}:NOT_ALLOWLISTED")
            continue
        if item.vin_sha256 != expected_hash:
            rejected.append(f"{field}:VIN_MISMATCH")
            continue
        if not item.value:
            rejected.append(f"{field}:EMPTY")
            continue
        if item.confidence < minimum_confidence:
            rejected.append(f"{field}:LOW_CONFIDENCE")
            continue
        if field in VEHICLE_PRIMARY_FIELDS and item.source_kind not in {
            "auction_record",
            "same_vin_crm",
            "operator",
        }:
            rejected.append(f"{field}:VEHICLE_FACT_NOT_VERIFIED")
            continue
        previous = ranked.get(field)
        if previous is None or item.confidence > previous.confidence:
            ranked[field] = item

    # Alias columns feed one public concept. Writing two independently ranked
    # values could make renderer precedence replace an operator-visible fact.
    # Fail the whole alias group closed unless an explicit normalizer supplies
    # one canonical candidate.
    for group in PRIMARY_ALIAS_GROUPS:
        proposed = sorted(group & ranked.keys())
        if len(proposed) > 1:
            for field in proposed:
                ranked.pop(field, None)
                rejected.append(f"{field}:ALIAS_GROUP_CONFLICT")

    for field, item in sorted(ranked.items()):
        aliases = next(
            (group for group in PRIMARY_ALIAS_GROUPS if field in group),
            frozenset({field}),
        )
        if any(not is_blank(current.get(alias)) for alias in aliases):
            preserved.add(field)
            continue
        writes[field] = item.value
        provenance[field] = {
            "source_kind": item.source_kind,
            "source": item.source,
            "confidence": item.confidence,
            "vin_sha256": item.vin_sha256,
        }

    return BaseFillPlan(
        writes=writes,
        provenance=provenance,
        preserved=tuple(sorted(preserved)),
        rejected=tuple(sorted(rejected)),
        before_digest=stable_digest(dict(current)),
    )


def missing_public_base_fields(card: Mapping[str, Any]) -> tuple[str, ...]:
    missing: list[str] = []
    for aliases in PUBLIC_BASE_FIELD_GROUPS:
        if not any(not is_blank(card.get(name)) for name in aliases):
            missing.append("/".join(aliases))
    return tuple(missing)


@dataclasses.dataclass(frozen=True)
class SpecFact:
    field_key: str
    label_ru: str
    display_value: str
    category: str = "additional"
    unit: str = ""
    confidence: float = 0.0
    evidence_count: int = 0
    visible: bool = True
    manual: bool = False
    source_domains: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SpecFact":
        domains = value.get("source_domains") or ()
        if isinstance(domains, str):
            domains = (domains,)
        return cls(
            field_key=str(value.get("field_key") or "").strip(),
            label_ru=_clean(value.get("label_ru")),
            display_value=_clean(
                value.get("display_value")
                if "display_value" in value
                else value.get("field_value")
            ),
            category=str(value.get("category") or "additional"),
            unit=str(value.get("unit") or ""),
            confidence=float(value.get("confidence") or 0.0),
            evidence_count=int(value.get("evidence_count") or 0),
            visible=_as_bool(value.get("visible"), default=True),
            manual=_as_bool(value.get("manual"), default=False),
            source_domains=tuple(str(x).strip().lower() for x in domains),
        )

    def public_dict(self) -> dict[str, Any]:
        return {
            "field_key": self.field_key,
            "label_ru": self.label_ru,
            "display_value": self.display_value,
            "category": self.category,
            "unit": self.unit,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "visible": self.visible,
            "manual": self.manual,
            "source_domains": self.source_domains,
        }


@dataclasses.dataclass(frozen=True)
class SpecRevision:
    uid: str
    vin_sha256: str
    policy_version: str
    revision_id: str
    status: str
    facts: tuple[SpecFact, ...]
    digest: str
    # The count persisted beside the digest.  Keeping the declared value in
    # the in-memory object lets every publication preflight detect a forged or
    # stale row count instead of trusting a freshly computed property alone.
    declared_visible_count: int | None = None

    @property
    def visible_facts(self) -> tuple[SpecFact, ...]:
        # Integrity validation rejects non-boolean flags.  ``is True`` also
        # prevents values such as the string ``"false"`` from becoming visible
        # merely because Python considers a non-empty string truthy.
        return tuple(x for x in self.facts if x.visible is True and x.display_value)

    @property
    def visible_count(self) -> int:
        return len(self.visible_facts)


def _validated_facts(rows: Iterable[SpecFact | Mapping[str, Any]]) -> tuple[SpecFact, ...]:
    try:
        facts_list: list[SpecFact] = []
        for row in rows:
            if isinstance(row, SpecFact):
                if type(row.visible) is not bool or type(row.manual) is not bool:
                    raise RecoveryGuardError("SPEC_FACT_BOOLEAN_INVALID", row.field_key)
                if type(row.evidence_count) is not int:
                    raise RecoveryGuardError("SPEC_FACT_EVIDENCE_INVALID", row.field_key)
                facts_list.append(row)
            else:
                facts_list.append(SpecFact.from_mapping(row))
        facts = tuple(facts_list)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RecoveryGuardError("SPEC_FACT_INVALID", type(exc).__name__) from exc
    keys: set[str] = set()
    normalized: list[SpecFact] = []
    for fact in facts:
        field_key = str(fact.field_key or "").strip()
        if not field_key or not _clean(fact.label_ru) or not _clean(fact.display_value):
            raise RecoveryGuardError("SPEC_FACT_INVALID", field_key)
        if field_key in keys:
            raise RecoveryGuardError("SPEC_FACT_DUPLICATE", field_key)
        try:
            confidence = float(fact.confidence)
            evidence_count = int(fact.evidence_count)
        except (TypeError, ValueError, OverflowError) as exc:
            raise RecoveryGuardError(
                "SPEC_FACT_QUALITY_INVALID", field_key
            ) from exc
        if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
            raise RecoveryGuardError(
                "SPEC_FACT_CONFIDENCE_INVALID", field_key
            )
        if evidence_count < 0 or evidence_count != fact.evidence_count:
            raise RecoveryGuardError("SPEC_FACT_EVIDENCE_INVALID", field_key)
        manual = _as_bool(fact.manual, default=False)
        visible = _as_bool(fact.visible, default=True)
        raw_domains = fact.source_domains or ()
        if isinstance(raw_domains, str):
            raw_domains = (raw_domains,)
        domains = tuple(
            sorted(
                {
                    str(value).strip().lower().rstrip(".")
                    for value in raw_domains
                    if str(value).strip()
                }
            )
        )
        # Imported operator/manual rows predate automated provenance.  They
        # remain valid without synthetic confidence or domain-formatted source
        # attribution (some contain old free-text labels such as ``operator``).
        # Machine-produced facts, however, must be attributable and meet the
        # same high-confidence bar as the VIN primary-field writer.
        if not manual:
            if confidence < MIN_AUTOMATIC_SPEC_CONFIDENCE:
                raise RecoveryGuardError("SPEC_FACT_LOW_CONFIDENCE", field_key)
            if evidence_count < 1:
                raise RecoveryGuardError("SPEC_FACT_EVIDENCE_MISSING", field_key)
            if not domains:
                raise RecoveryGuardError("SPEC_FACT_SOURCE_MISSING", field_key)
            if any(not SOURCE_DOMAIN_RE.fullmatch(value) for value in domains):
                raise RecoveryGuardError("SPEC_FACT_SOURCE_INVALID", field_key)
        keys.add(field_key)
        normalized.append(
            dataclasses.replace(
                fact,
                field_key=field_key,
                label_ru=_clean(fact.label_ru),
                display_value=_clean(fact.display_value),
                category=_clean(fact.category) or "additional",
                unit=_clean(fact.unit),
                confidence=confidence,
                evidence_count=evidence_count,
                visible=visible,
                manual=manual,
                source_domains=domains,
            )
        )
    return tuple(sorted(normalized, key=lambda x: x.field_key))


def spec_revision_digest(
    *,
    uid: Any,
    vin_sha256_value: str,
    policy_version: str,
    revision_id: str,
    declared_visible_count: int,
    facts: Iterable[SpecFact | Mapping[str, Any]],
) -> str:
    """Recompute the canonical digest used by storage and preflight."""

    normalized_uid = canonical_uid(uid)
    normalized_vin_hash = str(vin_sha256_value or "").strip().lower()
    if not SHA256_RE.fullmatch(normalized_vin_hash):
        raise RecoveryGuardError("SPEC_VIN_DIGEST_INVALID", normalized_uid)
    validated = _validated_facts(facts)
    normalized_revision_id = str(revision_id or "").strip()
    if not normalized_revision_id:
        raise RecoveryGuardError("SPEC_REVISION_ID_MISSING", normalized_uid)
    if type(declared_visible_count) is not int or declared_visible_count < 0:
        raise RecoveryGuardError("SPEC_VISIBLE_COUNT_INVALID", normalized_revision_id)
    # The digest covers the full immutable revision, not only currently visible
    # rows.  Visibility changes or hidden-row corruption must therefore fail a
    # later load/preflight as well.
    all_facts = tuple(item.public_dict() for item in validated)
    return stable_digest(
        {
            "uid": normalized_uid,
            "vin_sha256": normalized_vin_hash,
            "policy_version": str(policy_version),
            "revision_id": normalized_revision_id,
            "declared_visible_count": declared_visible_count,
            "facts": all_facts,
        }
    )


def assert_spec_revision_integrity(
    revision: SpecRevision,
    *,
    expected_visible_count: int | None = None,
) -> None:
    """Fail closed if a revision's facts, declared count or digest diverge."""

    if not isinstance(revision, SpecRevision):
        raise RecoveryGuardError("SPEC_REVISION_INVALID")
    normalized_uid = canonical_uid(revision.uid)
    if normalized_uid != revision.uid:
        raise RecoveryGuardError("SPEC_UID_NONCANONICAL", normalized_uid)
    if not str(revision.revision_id or "").strip():
        raise RecoveryGuardError("SPEC_REVISION_ID_MISSING", normalized_uid)
    if not str(revision.policy_version or "").strip():
        raise RecoveryGuardError("SPEC_POLICY_VERSION_MISSING", normalized_uid)
    if revision.status not in {"CANDIDATE", "ACTIVE", "ARCHIVED", "REJECTED"}:
        raise RecoveryGuardError("SPEC_REVISION_STATUS_INVALID", revision.status)

    facts = _validated_facts(revision.facts)
    if facts != revision.facts:
        raise RecoveryGuardError("SPEC_FACTS_NONCANONICAL", revision.revision_id)
    actual_count = len(
        tuple(item for item in facts if item.visible and item.display_value)
    )
    declared = revision.declared_visible_count
    try:
        if declared is not None and type(declared) is not int:
            raise TypeError("declared_visible_count must be int")
        normalized_declared = declared
        normalized_expected = (
            int(expected_visible_count)
            if expected_visible_count is not None
            else None
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise RecoveryGuardError(
            "SPEC_VISIBLE_COUNT_INVALID", revision.revision_id
        ) from exc
    if normalized_expected is not None:
        if normalized_declared is not None and normalized_declared != normalized_expected:
            raise RecoveryGuardError(
                "SPEC_VISIBLE_COUNT_DECLARATION_MISMATCH",
                f"{revision.revision_id}:{normalized_declared}:{normalized_expected}",
            )
        normalized_declared = normalized_expected
    if normalized_declared is None:
        raise RecoveryGuardError(
            "SPEC_VISIBLE_COUNT_UNBOUND", revision.revision_id
        )
    if normalized_declared < 0 or normalized_declared != actual_count:
        raise RecoveryGuardError(
            "SPEC_VISIBLE_COUNT_MISMATCH",
            f"{revision.revision_id}:{normalized_declared}:{actual_count}",
        )
    computed = spec_revision_digest(
        uid=revision.uid,
        vin_sha256_value=revision.vin_sha256,
        policy_version=revision.policy_version,
        revision_id=revision.revision_id,
        declared_visible_count=normalized_declared,
        facts=facts,
    )
    if not SHA256_RE.fullmatch(str(revision.digest or "")) or computed != revision.digest:
        raise RecoveryGuardError("SPEC_DIGEST_MISMATCH", revision.revision_id)


def build_candidate_revision(
    uid: Any,
    vin: Any,
    policy_version: str,
    rows: Iterable[SpecFact | Mapping[str, Any]],
    *,
    revision_id: str,
    allow_manual_facts: bool = False,
) -> SpecRevision:
    normalized_uid = canonical_uid(uid)
    facts = _validated_facts(rows)
    if type(allow_manual_facts) is not bool:
        raise RecoveryGuardError("MANUAL_SPEC_IMPORT_FLAG_INVALID", normalized_uid)
    if any(fact.manual for fact in facts) and not allow_manual_facts:
        raise RecoveryGuardError("MANUAL_SPEC_IMPORT_NOT_AUTHORIZED", normalized_uid)
    visible = tuple(x.public_dict() for x in facts if x.visible and x.display_value)
    if len(visible) < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
        raise RecoveryGuardError(
            "SPEC_NOT_READY", f"{normalized_uid}:{len(visible)}/{PUBLIC_MIN_VISIBLE_SPEC_ROWS}"
        )
    vin_hash = vin_sha256(vin)
    digest = spec_revision_digest(
        uid=normalized_uid,
        vin_sha256_value=vin_hash,
        policy_version=str(policy_version),
        revision_id=str(revision_id),
        declared_visible_count=len(visible),
        facts=facts,
    )
    revision = SpecRevision(
        uid=normalized_uid,
        vin_sha256=vin_hash,
        policy_version=str(policy_version),
        revision_id=str(revision_id),
        status="CANDIDATE",
        facts=facts,
        digest=digest,
        declared_visible_count=len(visible),
    )
    assert_spec_revision_integrity(revision)
    return revision


def activate_candidate(
    active: SpecRevision | None, candidate: SpecRevision
) -> tuple[SpecRevision | None, SpecRevision]:
    """Return archived/active values without destroying an old revision.

    A same-VIN active snapshot is immutable under background/site/CRM changes.
    Only an explicit manual revision workflow may replace it; that workflow is
    outside this automatic recovery contract.
    """

    assert_spec_revision_integrity(candidate)
    if active is not None:
        assert_spec_revision_integrity(active)
    if candidate.visible_count < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
        raise RecoveryGuardError("SPEC_NOT_READY")
    if active and active.uid != candidate.uid:
        raise RecoveryGuardError("SPEC_UID_MISMATCH")
    if active and active.vin_sha256 == candidate.vin_sha256:
        # The old snapshot remains byte/logically identical.
        return None, active
    archived = dataclasses.replace(active, status="ARCHIVED") if active else None
    return archived, dataclasses.replace(candidate, status="ACTIVE")


def assert_spec_unchanged(before: SpecRevision, after: SpecRevision) -> None:
    assert_spec_revision_integrity(before)
    assert_spec_revision_integrity(after)
    if (before.revision_id, before.digest, before.facts, before.declared_visible_count) != (
        after.revision_id,
        after.digest,
        after.facts,
        after.declared_visible_count,
    ):
        raise RecoveryGuardError("SPEC_IMMUTABILITY_BREACH", before.uid)


@dataclasses.dataclass(frozen=True)
class WorkerHealth:
    worker_instance_id: str
    last_cycle_at: str
    last_success_at: str
    last_cycle_error: str = ""
    queue_depth: int = 0


def _parse_utc(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def worker_health_errors(
    health: WorkerHealth | Mapping[str, Any] | None,
    *,
    now: dt.datetime | None = None,
    max_age_seconds: int = 90,
) -> tuple[str, ...]:
    if health is None:
        return ("VIN_WORKER_HEARTBEAT_MISSING",)
    if not isinstance(health, WorkerHealth):
        health = WorkerHealth(
            worker_instance_id=str(health.get("worker_instance_id") or ""),
            last_cycle_at=str(health.get("last_cycle_at") or ""),
            last_success_at=str(health.get("last_success_at") or ""),
            last_cycle_error=str(health.get("last_cycle_error") or ""),
            queue_depth=int(health.get("queue_depth") or 0),
        )
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    errors: list[str] = []
    if not health.worker_instance_id:
        errors.append("VIN_WORKER_INSTANCE_MISSING")
    try:
        age = (now.astimezone(dt.timezone.utc) - _parse_utc(health.last_cycle_at)).total_seconds()
    except Exception:
        errors.append("VIN_WORKER_HEARTBEAT_INVALID")
    else:
        if age < -5 or age > max_age_seconds:
            errors.append("VIN_WORKER_STALE")
    try:
        success_age = (
            now.astimezone(dt.timezone.utc) - _parse_utc(health.last_success_at)
        ).total_seconds()
    except Exception:
        errors.append("VIN_WORKER_SUCCESS_MISSING")
    else:
        if success_age < -5 or success_age > max_age_seconds:
            errors.append("VIN_WORKER_SUCCESS_STALE")
    if health.last_cycle_error:
        errors.append("VIN_WORKER_LAST_CYCLE_ERROR")
    return tuple(errors)


@dataclasses.dataclass(frozen=True)
class PreflightResult:
    uid: str
    ok: bool
    codes: tuple[str, ...]
    visible_spec_rows: int
    spec_revision_id: str
    spec_digest: str


def publication_preflight(
    *,
    uid: Any,
    vin: Any,
    card: Mapping[str, Any],
    active_spec: SpecRevision | None,
    worker_health: WorkerHealth | Mapping[str, Any] | None,
    duplicate_active_uids: Iterable[str] = (),
    now: dt.datetime | None = None,
) -> PreflightResult:
    normalized_uid = canonical_uid(uid)
    normalized_vin = normalize_vin(vin)
    codes: list[str] = []
    identity_values = [
        card.get(name)
        for name in ("auto_number", "uid", "car_uid")
        if name in card and not is_blank(card.get(name))
    ]
    if not identity_values:
        codes.append("CARD_UID_MISSING")
    else:
        try:
            identities = {canonical_uid(value) for value in identity_values}
        except RecoveryGuardError:
            codes.append("CARD_UID_INVALID")
        else:
            if identities != {normalized_uid}:
                codes.append("STALE_CARD_UID")
    if normalize_vin(card.get("vin")) != normalized_vin:
        codes.append("STALE_CARD_VIN")
    duplicates = sorted(
        {
            canonical_uid(value)
            for value in duplicate_active_uids
            if canonical_uid(value) != normalized_uid
        }
    )
    if duplicates:
        codes.append("DUPLICATE_ACTIVE_VIN:" + ",".join(duplicates))
    missing = missing_public_base_fields(card)
    if missing:
        codes.append("BASE_SPEC_INCOMPLETE:" + ",".join(missing))
    if active_spec is None:
        codes.append("SPEC_NOT_READY:0/10")
        count, revision_id, digest = 0, "", ""
    else:
        count = active_spec.visible_count
        revision_id = active_spec.revision_id
        digest = active_spec.digest
        try:
            assert_spec_revision_integrity(active_spec)
        except RecoveryGuardError as exc:
            codes.append(exc.code + ((":" + exc.detail) if exc.detail else ""))
        if active_spec.uid != normalized_uid:
            codes.append("SPEC_UID_MISMATCH")
        if active_spec.vin_sha256 != vin_sha256(normalized_vin):
            codes.append("SPEC_VIN_MISMATCH")
        if active_spec.status != "ACTIVE":
            codes.append("SPEC_REVISION_NOT_ACTIVE")
        if count < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
            codes.append(f"SPEC_NOT_READY:{count}/{PUBLIC_MIN_VISIBLE_SPEC_ROWS}")
    codes.extend(worker_health_errors(worker_health, now=now))
    return PreflightResult(
        uid=normalized_uid,
        ok=not codes,
        codes=tuple(codes),
        visible_spec_rows=count,
        spec_revision_id=revision_id,
        spec_digest=digest,
    )


_INERT_HTML_TAGS = frozenset({"script", "style", "template", "noscript"})
_VOID_HTML_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
)


def _inline_hidden(attrs: Mapping[str, str | None]) -> bool:
    lowered = {str(key).casefold(): value for key, value in attrs.items()}
    classes = set(str(lowered.get("class") or "").casefold().split())
    if "hidden" in lowered or "inert" in lowered:
        return True
    if classes & {"hidden", "d-none", "display-none"}:
        return True
    if str(lowered.get("aria-hidden") or "").strip().casefold() in {"true", "1"}:
        return True
    style = str(lowered.get("style") or "")
    for declaration in style.split(";"):
        if ":" not in declaration:
            continue
        name, value = declaration.split(":", 1)
        name = re.sub(r"\s+", "", name).casefold()
        value = re.sub(r"\s+|!important", "", value, flags=re.IGNORECASE).casefold()
        if name == "display" and value == "none":
            return True
        if name == "visibility" and value in {"hidden", "collapse"}:
            return True
        if name == "content-visibility" and value == "hidden":
            return True
        if name == "opacity":
            try:
                if float(value) <= 0.0:
                    return True
            except ValueError:
                pass
    return False


@dataclasses.dataclass(frozen=True)
class VisibleHtmlEvidence:
    card_markers: tuple[str, ...]
    visible_text: str
    owned_text_chunks: tuple[tuple[str | None, str], ...]
    spec_section_count: int
    spec_section_owners: tuple[str | None, ...]
    spec_digest_markers: tuple[str, ...]
    spec_pairs: tuple[tuple[str, str], ...]
    spec_row_owners: tuple[str | None, ...]
    spec_rows_outside_section: int
    spec_row_shape_errors: tuple[str, ...]
    duplicate_security_attributes: tuple[str, ...]


class _VisibleHtmlParser(HTMLParser):
    """Extract only active DOM evidence, never comments or inert subtrees."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, Any]] = []
        self.card_markers: list[str] = []
        self.visible_chunks: list[str] = []
        self.owned_text_chunks: list[tuple[str | None, str]] = []
        self.section_count = 0
        self.section_owners: list[str | None] = []
        self.section_digests: list[str] = []
        self.rows: list[dict[str, Any]] = []
        self.rows_outside = 0
        self.duplicate_security_attributes: list[str] = []

    def _start(
        self, tag: str, attrs_list: list[tuple[str, str | None]], *, push: bool
    ) -> None:
        lowered_tag = str(tag).casefold()
        security_names = {
            "class",
            "style",
            "hidden",
            "inert",
            "aria-hidden",
            "data-ua-card",
            "data-ua-spec-card",
            "data-ua-spec-sha256",
            "data-ua-spec-revision",
            "href",
        }
        attribute_names = [str(key).casefold() for key, _value in attrs_list]
        for name in security_names:
            if attribute_names.count(name) > 1:
                self.duplicate_security_attributes.append(lowered_tag + ":" + name)
        attrs = {str(key).casefold(): value for key, value in attrs_list}
        parent = self.stack[-1] if self.stack else None
        hidden = bool(parent and parent["hidden"])
        hidden = hidden or lowered_tag in _INERT_HTML_TAGS or _inline_hidden(attrs)
        section = parent["section"] if parent else None
        card_owner = parent["card_owner"] if parent else None
        spec_owner = parent["spec_owner"] if parent else None
        row = parent["row"] if parent else None
        capture = parent["capture"] if parent else None

        if not hidden:
            classes = set(str(attrs.get("class") or "").casefold().split())
            marker = attrs.get("data-ua-card")
            if marker is not None:
                card_owner = str(marker).strip().upper()
                self.card_markers.append(card_owner)
            if "ua-additional-spec" in classes:
                self.section_count += 1
                section = self.section_count
                explicit_spec_owner = attrs.get("data-ua-spec-card")
                spec_owner = (
                    str(explicit_spec_owner).strip().upper()
                    if explicit_spec_owner is not None
                    else card_owner
                )
                self.section_owners.append(spec_owner)
            digest = attrs.get("data-ua-spec-sha256")
            if digest is not None and section is not None:
                self.section_digests.append(str(digest).strip().lower())
            if "ua-addspec-row" in classes:
                if section is None:
                    self.rows_outside += 1
                    row = None
                else:
                    nested = row is not None
                    self.rows.append(
                        {
                            "label": [],
                            "value": [],
                            "all": [],
                            "dt_count": 0,
                            "dd_count": 0,
                            "nested": nested,
                            "card_owner": spec_owner,
                        }
                    )
                    row = len(self.rows) - 1
                capture = None
            if row is not None and lowered_tag == "dt":
                self.rows[int(row)]["dt_count"] += 1
                capture = "label"
            elif row is not None and lowered_tag == "dd":
                self.rows[int(row)]["dd_count"] += 1
                capture = "value"

        frame = {
            "tag": lowered_tag,
            "hidden": hidden,
            "section": section,
            "card_owner": card_owner,
            "spec_owner": spec_owner,
            "row": row,
            "capture": capture,
        }
        if push and lowered_tag not in _VOID_HTML_TAGS:
            self.stack.append(frame)

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._start(tag, attrs, push=True)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._start(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        lowered = str(tag).casefold()
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == lowered:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        frame = self.stack[-1] if self.stack else None
        if frame and frame["hidden"]:
            return
        if _clean(data):
            self.visible_chunks.append(data)
            self.owned_text_chunks.append(
                ((frame["card_owner"] if frame else None), data)
            )
        if frame and frame["row"] is not None:
            row = self.rows[int(frame["row"])]
            row["all"].append(data)
            if frame["capture"] in {"label", "value"}:
                row[str(frame["capture"])].append(data)


def visible_html_evidence(source: str) -> VisibleHtmlEvidence:
    parser = _VisibleHtmlParser()
    try:
        parser.feed(str(source or ""))
        parser.close()
    except Exception as exc:
        raise RecoveryGuardError("HTML_PARSE_FAILED", type(exc).__name__) from exc
    pairs: list[tuple[str, str]] = []
    shape_errors: list[str] = []
    for index, row in enumerate(parser.rows):
        label = _clean(html_module.unescape(" ".join(row["label"])))
        value = _clean(html_module.unescape(" ".join(row["value"])))
        all_text = _clean(html_module.unescape(" ".join(row["all"])))
        pairs.append((label, value))
        if row["dt_count"] != 1 or row["dd_count"] != 1:
            shape_errors.append(
                f"SPEC_ROW_DT_DD_COUNT:{index}:{row['dt_count']}:{row['dd_count']}"
            )
        if row["nested"]:
            shape_errors.append(f"SPEC_ROW_NESTED:{index}")
        if all_text != _clean(label + " " + value):
            shape_errors.append(f"SPEC_ROW_EXTRA_TEXT:{index}")
    return VisibleHtmlEvidence(
        card_markers=tuple(parser.card_markers),
        visible_text=_clean(html_module.unescape(" ".join(parser.visible_chunks))),
        owned_text_chunks=tuple(parser.owned_text_chunks),
        spec_section_count=parser.section_count,
        spec_section_owners=tuple(parser.section_owners),
        spec_digest_markers=tuple(parser.section_digests),
        spec_pairs=tuple(pairs),
        spec_row_owners=tuple(row["card_owner"] for row in parser.rows),
        spec_rows_outside_section=parser.rows_outside,
        spec_row_shape_errors=tuple(shape_errors),
        duplicate_security_attributes=tuple(parser.duplicate_security_attributes),
    )


def card_identity_errors(
    html: str,
    *,
    uid: Any,
    vin: Any,
    expected_spec_rows: int,
    expected_spec_digest: str = "",
    expected_spec: SpecRevision | None = None,
) -> tuple[str, ...]:
    uid = canonical_uid(uid)
    vin = normalize_vin(vin)
    source = str(html or "")
    errors: list[str] = []
    try:
        evidence = visible_html_evidence(source)
    except RecoveryGuardError as exc:
        return (exc.code,)
    if evidence.duplicate_security_attributes:
        errors.append(
            "HTML_DUPLICATE_SECURITY_ATTRIBUTE:"
            + ",".join(evidence.duplicate_security_attributes)
        )
    matching_markers = [value for value in evidence.card_markers if value == uid]
    other_markers = [value for value in evidence.card_markers if value != uid]
    if len(matching_markers) != 1 or other_markers:
        errors.append(
            f"TARGET_IDENTITY_MARKER_COUNT:{len(matching_markers)}:OTHER:{len(other_markers)}"
        )
    visible_upper = evidence.visible_text.upper()
    target_visible_upper = _clean(
        " ".join(
            text for owner, text in evidence.owned_text_chunks if owner == uid
        )
    ).upper()
    if not re.search(
        r"(?<![A-Z0-9])" + re.escape(vin) + r"(?![A-Z0-9])",
        target_visible_upper,
    ):
        errors.append("TARGET_VIN_MISSING")
    if evidence.spec_section_count != 1:
        errors.append(f"SPEC_SECTION_COUNT_MISMATCH:{evidence.spec_section_count}:1")
    if evidence.spec_section_owners != (uid,):
        errors.append("SPEC_SECTION_OUTSIDE_TARGET_CARD")
    if evidence.spec_rows_outside_section:
        errors.append(f"SPEC_ROWS_OUTSIDE_SECTION:{evidence.spec_rows_outside_section}")
    errors.extend(evidence.spec_row_shape_errors)
    rendered = len(evidence.spec_pairs)
    if any(owner != uid for owner in evidence.spec_row_owners):
        errors.append("SPEC_ROW_OUTSIDE_TARGET_CARD")
    if rendered != int(expected_spec_rows):
        errors.append(f"SPEC_ROW_COUNT_MISMATCH:{rendered}:{expected_spec_rows}")
    if expected_spec_rows < PUBLIC_MIN_VISIBLE_SPEC_ROWS:
        errors.append(f"SPEC_NOT_READY:{expected_spec_rows}/10")
    if expected_spec_digest:
        matching_digests = [
            value for value in evidence.spec_digest_markers
            if value == expected_spec_digest.lower()
        ]
        other_digests = [
            value for value in evidence.spec_digest_markers
            if value != expected_spec_digest.lower()
        ]
        if len(matching_digests) != 1 or other_digests:
            errors.append(
                f"SPEC_DIGEST_MARKER_COUNT:{len(matching_digests)}:OTHER:{len(other_digests)}"
            )
    if expected_spec is not None:
        try:
            assert_spec_revision_integrity(expected_spec)
        except RecoveryGuardError as exc:
            errors.append("EXPECTED_" + exc.code)
        else:
            if expected_spec.uid != uid:
                errors.append("EXPECTED_SPEC_UID_MISMATCH")
            if expected_spec.vin_sha256 != vin_sha256(vin):
                errors.append("EXPECTED_SPEC_VIN_MISMATCH")
            if expected_spec.visible_count != int(expected_spec_rows):
                errors.append("EXPECTED_SPEC_ROW_COUNT_MISMATCH")
            if expected_spec_digest and expected_spec.digest != expected_spec_digest:
                errors.append("EXPECTED_SPEC_DIGEST_MISMATCH")
            errors.extend(spec_content_errors(source, expected_spec))
    # PythonAnywhere may return the generic landing page with HTTP 200 for a
    # missing card.  A status code is therefore never sufficient proof.
    if "ОТКРЫТЬ ВСЕ АВТОМОБИЛИ" in visible_upper and not matching_markers:
        errors.append("GENERIC_FALLBACK_PAGE")
    return tuple(errors)


def rendered_spec_pairs(source: str) -> tuple[tuple[str, str], ...]:
    """Extract exact active ``dt``/``dd`` text from one visible spec block."""

    return visible_html_evidence(source).spec_pairs


def spec_content_errors(source: str, spec: SpecRevision) -> tuple[str, ...]:
    """Bind rendered values to the immutable facts, not just a copied marker."""

    assert_spec_revision_integrity(spec)
    actual = list(rendered_spec_pairs(source))
    unmatched = list(actual)
    errors: list[str] = []
    for fact in spec.visible_facts:
        expected_label = _clean(fact.label_ru)
        expected_value = _clean(fact.display_value)
        allowed_values = {expected_value}
        unit = _clean(fact.unit)
        if unit:
            allowed_values.add(_clean(expected_value + " " + unit))
        found = next(
            (
                index
                for index, (label, value) in enumerate(unmatched)
                if label == expected_label
                and value in allowed_values
            ),
            None,
        )
        if found is None:
            errors.append("SPEC_FACT_CONTENT_MISSING:" + fact.field_key)
        else:
            unmatched.pop(found)
    if unmatched:
        errors.append("SPEC_FACT_CONTENT_UNEXPECTED:" + str(len(unmatched)))
    return tuple(errors)


def exact_catalog_link_count(html: str, uid: Any) -> int:
    uid = canonical_uid(uid)
    pattern = re.compile(
        r"href\s*=\s*(['\"])(?:[^'\"]*/)?"
        + re.escape(uid)
        + r"\.html(?:[?#][^'\"]*)?\1",
        re.IGNORECASE,
    )
    return len(pattern.findall(str(html or "")))


def is_exact_card_artifact(name: str, uid: Any) -> bool:
    uid = canonical_uid(uid)
    return bool(
        re.fullmatch(
            re.escape(uid) + r"(?:-diag|-[0-9a-f]{6,10})?\.html",
            os.path.basename(str(name)),
            re.IGNORECASE,
        )
    )


def filter_selectable_statuses(
    statuses: Mapping[str, tuple[int, str]],
) -> dict[str, tuple[int, str]]:
    return {code: value for code, value in statuses.items() if code not in HIDDEN_STATUS_CODES}


def classify_stage_callback(data: Any) -> tuple[str, int | None, str | None]:
    match = re.fullmatch(r"car_setstage:(\d+):([a-z0-9_]+)", str(data or ""))
    if not match:
        return "NOT_STAGE_CALLBACK", None, None
    card_id, code = int(match.group(1)), match.group(2)
    if code in HIDDEN_STATUS_CODES:
        return "BLOCKED_LEGACY_STATUS", card_id, code
    return "PASS_TO_CANONICAL_HANDLER", card_id, code


def resolved_under(root: Path | str, target: Path | str) -> Path:
    root_path = Path(root).resolve(strict=True)
    target_path = Path(target)
    if target_path.exists() and target_path.is_symlink():
        raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(target_path))
    resolved = target_path.resolve(strict=False)
    try:
        resolved.relative_to(root_path)
    except ValueError as exc:
        raise RecoveryGuardError("WRITE_OUTSIDE_PREVIEW", str(resolved)) from exc
    # Explicitly reject the known Production root even when a caller chooses it
    # as the nominal preview root.
    if resolved == Path("/home/Carix") or Path("/home/Carix") in resolved.parents:
        raise RecoveryGuardError("PRODUCTION_PATH_FORBIDDEN", str(resolved))
    return resolved


def tree_manifest(root: Path | str) -> dict[str, str]:
    root_path = Path(root).resolve(strict=True)
    result: dict[str, str] = {}
    for path in sorted(root_path.rglob("*")):
        if path.is_symlink():
            raise RecoveryGuardError("PREVIEW_SYMLINK_FORBIDDEN", str(path))
        if not path.is_file():
            continue
        relative = path.relative_to(root_path).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def assert_change_scope(
    before: Mapping[str, str],
    after: Mapping[str, str],
    *,
    allowed_exact_paths: Sequence[str],
) -> tuple[str, ...]:
    changed = tuple(
        sorted(
            key
            for key in set(before) | set(after)
            if before.get(key) != after.get(key)
        )
    )
    allowed = set(allowed_exact_paths)
    outside = [path for path in changed if path not in allowed]
    if outside:
        raise RecoveryGuardError("SITE_FOUNDATION_CHANGED", ",".join(outside))
    return changed


def evidence_envelope(**payload: Any) -> dict[str, Any]:
    if "observed_at_utc" in payload:
        raise RecoveryGuardError(
            "EVIDENCE_INVARIANT_OVERRIDE", "observed_at_utc"
        )
    protected = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "mode": MODE,
        "base_sha": BASE_SHA,
        "production_touched": False,
        "production_write_attempts": 0,
        "service_reloaded": False,
        "ua0017_published_production": False,
    }
    conflicts = sorted(
        key for key, value in protected.items()
        if key in payload and payload[key] != value
    )
    if conflicts:
        raise RecoveryGuardError(
            "EVIDENCE_INVARIANT_OVERRIDE", ",".join(conflicts)
        )
    result = {
        **protected,
        # Evidence generated on different local runs must identify when the
        # observation was made; a digest without an observation time can be
        # replayed and mistaken for current Gate B evidence.
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    result.update(payload)
    result["evidence_digest"] = stable_digest(result)
    return result


__all__ = [name for name in globals() if not name.startswith("_")]
