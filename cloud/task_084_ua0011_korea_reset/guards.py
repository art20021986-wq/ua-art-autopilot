"""Permanent structural guards requested by owner directive item 7 and Gate A.

These are pure functions intended to be wired into the real CRM stage-change /
card-writer / catalog-publish pipeline by the controller. They contain no
network or DB code; they operate on plain dict snapshots so they can be unit
tested offline and then imported unmodified into the production pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable

KOREA_BOUGHT_STATUS = "kr_bought"
SUPERSEDED_FERRY_STATUSES = {"on_ferry", "ferry", "na_paromye"}


class GuardViolation(RuntimeError):
    pass


def crm_is_single_source_of_stage(publicly_shown_stage: str, crm_stage: str) -> None:
    """The publicly displayed stage MUST equal the CRM stage. Any divergence is
    a guard violation -- there must be no secondary/derived stage source.
    """
    if publicly_shown_stage != crm_stage:
        raise GuardViolation(
            f"Public stage '{publicly_shown_stage}' diverges from CRM stage "
            f"'{crm_stage}'. CRM must be the single source of truth for stage."
        )


def reject_superseded_task_082_ferry_status(status_field_value: str, vin: str) -> None:
    """TASK 082 logic that could push UA-0011 to a ferry/on-the-way stage is
    superseded by TASK 084. Any attempt to set that status for UA-0011 (or any
    card lacking confirmed loading/shipping evidence) must fail closed.
    """
    if status_field_value in SUPERSEDED_FERRY_STATUSES:
        raise GuardViolation(
            f"Attempted superseded TASK 082 ferry status '{status_field_value}' "
            f"for VIN {vin}. TASK 084 supersedes this; fail-closed, no write."
        )


def forbid_container_or_eta_when_kr_bought(
    status_value: str, container_value: Any, arrival_date_value: Any
) -> None:
    """Container number and arrival/ETA date MUST NOT be persisted while status
    is kr_bought. Empty string / None are the only allowed values.
    """
    if status_value == KOREA_BOUGHT_STATUS:
        if container_value not in (None, ""):
            raise GuardViolation(
                "Container number must not be saved while status is kr_bought."
            )
        if arrival_date_value not in (None, ""):
            raise GuardViolation(
                "Arrival/ETA date must not be saved (or computed) while status is kr_bought."
            )


def require_media_mapping_before_catalog_write(
    media_manifest: Iterable[Dict[str, Any]], vin: str
) -> None:
    """A catalog write for a card is blocked until its media mapping/sync is
    complete: there must be at least one media item, the first item must be
    flagged as this VIN's own cover photo, and no item may belong to another VIN.
    """
    media_list = list(media_manifest)
    if not media_list:
        raise GuardViolation(
            f"No media mapping for VIN {vin}; catalog write blocked until media sync completes."
        )
    first = media_list[0]
    if first.get("belongs_to_vin") != vin or first.get("role") != "cover":
        raise GuardViolation(
            f"First media item for VIN {vin} is not confirmed as its own cover photo; "
            "catalog write blocked."
        )
    for item in media_list:
        if item.get("belongs_to_vin") not in (None, vin):
            raise GuardViolation(
                f"Media item {item.get('id')} belongs to a different VIN "
                f"({item.get('belongs_to_vin')}); catalog write blocked for VIN {vin}."
            )


def idempotent_apply(card: Dict[str, Any], transform) -> bool:
    """Generic idempotency check: applying `transform` twice must yield the
    same result as applying it once.
    """
    once = transform(card)
    twice = transform(once)
    return once == twice


def ua0009_publication_guard(safe_to_publish_flag: str) -> None:
    """Per Shared Memory REC-0006/REC-0007, UA-0009 stays blocked from
    publication until real Gate A evidence proves it safe. This guard fails
    closed if anything tries to mark it publishable prematurely.
    """
    if safe_to_publish_flag not in ("NO",):
        raise GuardViolation(
            "UA-0009 safe_to_publish must remain 'NO' until verified Gate A "
            "evidence is recorded in canonical Shared Memory."
        )
