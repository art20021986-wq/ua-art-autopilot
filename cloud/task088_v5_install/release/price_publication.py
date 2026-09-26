"""Publication acknowledgement policy, NOT a publisher or verified live receipt.

A trusted adapter must read committed CRM state and parse PUBLIC card/catalog
content. HTTP success alone cannot construct verified semantic observations.
The adapter must hold the publication lock and recheck the current CRM revision
before using an acknowledgement. This module performs no writes or retries.
publication_failed is durable failure state for this attempt, not a poll-local
flag. A later successful readback must not reset it: reconciliation and the
existing verified recovery gates are required to leave the stopped state.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import re

from owner_policy import Identity, PolicyInputError, _boolean, _instant, _sha


PUBLICATION_DEADLINE = timedelta(seconds=60)
MAX_READBACK_AGE = timedelta(seconds=30)
CRM_ON_PUBLICATION_FAILURE = "KEEP_COMMITTED_PRICE"


@dataclass(frozen=True)
class PriceVersion:
    car_id: str
    revision: int
    ukraine_usd: str
    georgia_usd: str | None

    def __post_init__(self):
        if type(self.car_id) is not str or not re.fullmatch(r"UA-[0-9]{4}", self.car_id):
            raise PolicyInputError("CAR_ID_REQUIRED")
        if type(self.revision) is not int or self.revision < 1:
            raise PolicyInputError("POSITIVE_COMMITTED_REVISION_REQUIRED")
        for market, price in (("ukraine", self.ukraine_usd), ("georgia", self.georgia_usd)):
            if price is None and market == "georgia":
                continue
            if type(price) is not str or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.[0-9]{2}", price):
                raise PolicyInputError("CANONICAL_USD_AMOUNT_REQUIRED")


@dataclass(frozen=True)
class Readback:
    identity: Identity
    surface: str
    version: PriceVersion
    observed_at: datetime
    evidence_sha256: str
    semantics_verified: bool
    non_price_content_preserved: bool

    def __post_init__(self):
        if type(self.identity) is not Identity or type(self.version) is not PriceVersion:
            raise PolicyInputError("EXACT_IDENTITY_AND_VERSION_REQUIRED")
        if self.surface not in ("CRM", "CARD", "CATALOG"):
            raise PolicyInputError("UNKNOWN_PRICE_SURFACE")
        _instant(self.observed_at, "OBSERVED_AT")
        _sha(self.evidence_sha256, "READBACK_EVIDENCE")
        _boolean(self.semantics_verified, "SEMANTICS_VERIFIED")
        _boolean(self.non_price_content_preserved, "NON_PRICE_CONTENT_PRESERVED")


@dataclass(frozen=True)
class PublicationDecision:
    action: str
    reason: str
    crm_action: str = CRM_ON_PUBLICATION_FAILURE


def publication_decision(*, identity: Identity, expected: PriceVersion,
                         committed_at: datetime, now: datetime,
                         observations: tuple[Readback, ...],
                         publication_failed: bool) -> PublicationDecision:
    """Select eligibility only; no CRM rollback, publication or notifications."""
    if type(identity) is not Identity or type(expected) is not PriceVersion:
        raise PolicyInputError("EXACT_IDENTITY_AND_VERSION_REQUIRED")
    _instant(committed_at, "COMMITTED_AT")
    _instant(now, "NOW")
    _boolean(publication_failed, "PUBLICATION_FAILED")
    if now < committed_at:
        raise PolicyInputError("COMMIT_FROM_FUTURE")
    if type(observations) is not tuple or any(type(o) is not Readback for o in observations):
        raise PolicyInputError("READBACK_TUPLE_REQUIRED")
    surfaces = [o.surface for o in observations]
    if len(surfaces) != len(set(surfaces)):
        raise PolicyInputError("DUPLICATE_READBACK_SURFACE")
    if publication_failed:
        return PublicationDecision("STOP_AND_NOTIFY", "PUBLICATION_FAILURE_REQUIRES_RECONCILIATION")
    for observation in observations:
        if observation.identity != identity or observation.version.car_id != expected.car_id:
            return PublicationDecision("STOP_AND_NOTIFY", "READBACK_IDENTITY_MISMATCH")
        if not committed_at <= observation.observed_at <= now:
            return PublicationDecision("STOP_AND_NOTIFY", "READBACK_OUTSIDE_COMMIT_WINDOW")
        if not timedelta(0) <= now - observation.observed_at <= MAX_READBACK_AGE:
            return PublicationDecision("STOP_AND_NOTIFY", "READBACK_STALE")
        if not observation.semantics_verified or not observation.non_price_content_preserved:
            return PublicationDecision("STOP_AND_NOTIFY", "SEMANTIC_AND_PRESERVATION_EVIDENCE_REQUIRED")
        if observation.surface == "CRM" and observation.version != expected:
            return PublicationDecision("STOP_AND_RECONCILE", "CRM_CHANGED_NEVER_REPLAY_OLD_VERSION")
        if observation.surface != "CRM" and observation.version != expected:
            return PublicationDecision("STOP_AND_NOTIFY", "PUBLIC_PRICE_VERSION_MISMATCH")
    complete = (set(surfaces) == {"CRM", "CARD", "CATALOG"}
                and all(o.version == expected for o in observations))
    if complete:
        # SLA is measured to semantic readback, not to delayed report creation.
        within_deadline = max(o.observed_at for o in observations) - committed_at <= PUBLICATION_DEADLINE
        if within_deadline:
            return PublicationDecision("ACK_PUBLISHED_ELIGIBLE", "ALL_SURFACES_VERIFIED_WITHIN_60_SECONDS")
        return PublicationDecision("PUBLISHED_LATE_NOTIFY", "VERIFIED_BUT_60_SECOND_SLA_MISSED")
    if now - committed_at >= PUBLICATION_DEADLINE:
        return PublicationDecision("STOP_AND_NOTIFY", "PUBLICATION_DEADLINE_MISSED")
    return PublicationDecision("WAIT_FOR_VERIFIED_PUBLICATION", "CARD_AND_CATALOG_READBACK_REQUIRED")
