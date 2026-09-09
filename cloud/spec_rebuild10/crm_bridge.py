"""CRM events for the new specification store; no CRM/site/network writes.

Lifecycle execution is an injected, separately verified deployment route. There
is deliberately no default publisher, shell command, HALT change or worker.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal, InvalidOperation
import hashlib
import json
import logging
import re
from typing import Any, Callable, Mapping

from .store import StoreError

LOG = logging.getLogger(__name__)
EDITOR_KEYS = ("car_wait", "car_media_wait", "ua099_spec_edit", "spec_rebuild_edit")


class BridgeError(RuntimeError):
    pass


def canonical_uid(value: Any) -> str:
    text = str(value or "").strip().upper().translate(str.maketrans("‑–—", "---"))
    match = re.fullmatch(r"UA-?(\d{1,6})", text)
    if not match or int(match[1]) == 0:
        raise BridgeError("CRM_CARD_UID_REQUIRED")
    return "UA-%04d" % int(match[1])


def _pick(row: Mapping, *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip():
            return value
    return ""


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _engine(row: Mapping) -> str:
    raw = _pick(row, "engine_cc", "engine")
    if raw == "":
        return ""
    text = str(raw).strip().replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return _text(raw)
    try:
        value = Decimal(text)
        if 0 < value < 20:
            value *= 1000
        return format(value.normalize(), "f")
    except InvalidOperation:
        return _text(raw)


def identity_from_crm(row: Mapping) -> tuple[str, dict]:
    """Use stable allocation, never infer UA number from the database row ID."""
    uid = canonical_uid(_pick(row, "auto_number", "car_uid", "uid"))
    vin = re.sub(r"[\s-]", "", str(_pick(row, "vin", "vin_code"))).upper()
    if not vin:
        raise BridgeError("VIN_OR_FRAME_REQUIRED")
    # Japanese frame IDs remain identities; adapters choose supported coverage.
    if not re.fullmatch(r"[A-Z0-9]{5,25}", vin):
        raise BridgeError("INVALID_VIN_OR_FRAME")
    year = str(_pick(row, "year", "model_year")).strip()
    if year and not re.fullmatch(r"(?:19|20)\d{2}", year):
        raise BridgeError("INVALID_MODEL_YEAR")
    fuel = _text(_pick(row, "fuel", "fuel_type"))
    fuel = {"газ": "lpg", "lpi": "lpg", "бензин": "gasoline",
            "petrol": "gasoline", "дизель": "diesel"}.get(fuel, fuel)
    identity = {
        "vin": vin, "brand": _text(_pick(row, "brand", "make")),
        "model": _text(_pick(row, "model")), "year": year, "fuel": fuel,
        "engine_cc": _engine(row),
        "transmission": _text(_pick(row, "transmission", "gearbox")),
        "trim": _text(_pick(row, "trim")),
        "market": _text(_pick(row, "market", "origin_market")),
    }
    return uid, identity


def identity_hash(identity: Mapping) -> str:
    return hashlib.sha256(json.dumps(dict(identity), ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clear_editor_state(user_data: dict) -> int:
    removed = 0
    for key in EDITOR_KEYS:
        if key in user_data:
            del user_data[key]
            removed += 1
    return removed


@dataclass(frozen=True)
class PublicationTicket:
    uid: str
    action: str
    identity_hash: str
    revision: int
    facts_digest: str
    crm_row_sha256: str
    actor_id: int
    plan_id: str


class CrmBridge:
    def __init__(self, store):
        self.store = store

    def saved(self, row: Mapping) -> dict:
        uid, identity = identity_from_crm(row)
        before = self._vehicle_or_none(uid)
        # CRM.published is an intent/legacy flag, not a verified site receipt.
        published = bool(before and before.get("published"))
        self.store.upsert_vehicle(uid, identity, published=published)
        after = self.store.get_vehicle(uid)
        return {"uid": uid, "status": "TRACKED", "vehicle": after,
                "publication_performed": False}

    def _vehicle_or_none(self, uid):
        try:
            return self.store.get_vehicle(uid)
        except StoreError as exc:
            if str(exc) == "unknown or deleted vehicle":
                return None
            raise

    def reconcile_saved_rows(self, rows) -> dict:
        """Repair missed post-commit events; does not delete on incomplete scans."""
        result = {"tracked": [], "needs_input": [], "publication_performed": False}
        candidates = {}
        for row in rows:
            try:
                uid, identity = identity_from_crm(row)
                candidates.setdefault(uid, []).append(row)
            except BridgeError as exc:
                result["needs_input"].append({"card_id": row.get("id"), "reason": str(exc)})
        for uid, matches in candidates.items():
            if len(matches) > 1:
                result["needs_input"].extend({"card_id": row.get("id"), "reason": "DUPLICATE_CRM_UID"}
                                             for row in matches)
            else:
                result["tracked"].append(self.saved(matches[0])["uid"])
        return result

    def prepare(self, action: str, row: Mapping, actor_id: int,
                verify_readiness: Callable[[dict], Mapping]) -> PublicationTicket:
        if action not in {"publish", "hide", "delete", "sold"}:
            raise BridgeError("UNSUPPORTED_LIFECYCLE_ACTION")
        if not isinstance(actor_id, int) or isinstance(actor_id, bool) or actor_id <= 0:
            raise BridgeError("OWNER_ACTION_REQUIRED")
        self.saved(row)
        uid, identity = identity_from_crm(row)
        vehicle = self.store.get_vehicle(uid)
        revision = int(vehicle["revision"])
        facts = self.store.get_facts(uid)
        if action == "publish" and not facts:
            raise BridgeError("ACCEPTED_SPEC_REQUIRED")
        request = {"uid": uid, "action": action, "actor_id": actor_id,
                   "identity_hash": vehicle["identity_hash"], "revision": revision,
                   "facts_digest": self.store.facts_digest(uid),
                   "crm_row_sha256": identity_hash(dict(row))}
        proof = dict(verify_readiness(request))
        for field in ("gate_b", "route", "external_writers", "owner_action", "fresh"):
            if proof.get(field) != "PASS":
                raise BridgeError("READINESS_REQUIRED:" + field)
        if any(proof.get(key) != value for key, value in request.items()):
            raise BridgeError("READINESS_SCOPE_MISMATCH")
        if not proof.get("plan_id"):
            raise BridgeError("EXACT_PLAN_REQUIRED")
        return PublicationTicket(**request, plan_id=str(proof["plan_id"]))

    def observed(self, ticket: PublicationTicket, receipt: Mapping,
                 verify_readback: Callable[[PublicationTicket, Mapping], bool]) -> dict:
        if receipt.get("plan_id") != ticket.plan_id or receipt.get("action") != ticket.action:
            raise BridgeError("READBACK_PLAN_SCOPE_MISMATCH")
        vehicle = self.store.get_vehicle(ticket.uid)
        if not vehicle or int(vehicle["revision"]) != ticket.revision:
            raise BridgeError("SPEC_CHANGED_DURING_OPERATION")
        if (vehicle["identity_hash"] != ticket.identity_hash or
                self.store.facts_digest(ticket.uid) != ticket.facts_digest):
            raise BridgeError("SPEC_CHANGED_DURING_OPERATION")
        if verify_readback(ticket, receipt) is not True:
            raise BridgeError("ACTUAL_SITE_READBACK_REQUIRED")
        if ticket.action == "publish":
            self.store.mark_publication_verified(ticket.uid, ticket.revision, dict(receipt))
        else:
            self.store.mark_lifecycle_verified(ticket.uid, ticket.action, ticket.revision,
                ticket.identity_hash, ticket.facts_digest, dict(receipt))
        return {"uid": ticket.uid, "status": "VERIFIED", "action": ticket.action}

    def summary(self, row: Mapping) -> str:
        try:
            uid, _ = identity_from_crm(row)
            vehicle = self._vehicle_or_none(uid)
            if not vehicle:
                return "Специфікація: очікує автоматичного збору."
            count = len(self.store.get_facts(uid))
            snapshot = self.store.get_publication_snapshot(uid)
            site = "не опубліковано" if not vehicle["published"] else "очікує перевірки"
            if (vehicle["published"] and snapshot and
                    snapshot["facts_digest"] == self.store.facts_digest(uid)):
                site = "перевірено"
            return "Специфікація: %d підтверджених полів; стан сайту: %s." % (
                count, site)
        except BridgeError:
            return "Специфікація: заповніть VIN/номер кузова та рік."


@dataclass
class RuntimeBindings:
    bridge: CrmBridge
    verify_readiness: Callable
    execute_lifecycle: Callable
    verify_readback: Callable
    start_worker: Callable
    read_current_row: Callable
    verify_page_change: Callable | None = None


_runtime: RuntimeBindings | None = None
_runtime_factory: Callable | None = None
_bound_runtime = ContextVar("spec_rebuild10_runtime", default=None)
_active_ticket = ContextVar("spec_rebuild10_ticket", default=None)


@contextmanager
def _runtime_scope():
    existing = _bound_runtime.get()
    if existing is not None:
        yield existing
        return
    owned = _runtime_factory is not None
    runtime = _runtime_factory() if owned else _runtime
    token = _bound_runtime.set(runtime)
    try:
        yield runtime
    finally:
        _bound_runtime.reset(token)
        if owned and runtime is not None:
            runtime.bridge.store.close()


def configure_runtime(bindings: RuntimeBindings) -> None:
    """Called only by the separately reviewed CRM bootstrap after handoff."""
    global _runtime
    if not isinstance(bindings, RuntimeBindings) or any(not callable(getattr(bindings, key))
            for key in ("verify_readiness", "execute_lifecycle", "verify_readback", "start_worker", "read_current_row")):
        raise BridgeError("VERIFIED_RUNTIME_BINDINGS_REQUIRED")
    if _runtime_factory is not None or (_runtime is not None and _runtime is not bindings):
        raise BridgeError("RUNTIME_ALREADY_CONFIGURED")
    _runtime = bindings


def configure_runtime_factory(store_path: str, *, read_current_row: Callable,
                              verify_readiness: Callable, execute_lifecycle: Callable,
                              verify_readback: Callable, start_worker: Callable,
                              verify_page_change: Callable | None = None) -> None:
    """Thread-scoped bootstrap; dependencies must be the reviewed real route.

    Each outer event owns one SQLite connection; nested publisher callbacks use
    that event's binding. No connection is shared across Telegram worker threads.
    """
    global _runtime_factory
    if _runtime is not None or _runtime_factory is not None:
        raise BridgeError("RUNTIME_ALREADY_CONFIGURED")
    if not all(callable(value) for value in (read_current_row, verify_readiness,
            execute_lifecycle, verify_readback, start_worker)):
        raise BridgeError("VERIFIED_RUNTIME_BINDINGS_REQUIRED")
    from .store import SpecStore
    def factory():
        return RuntimeBindings(CrmBridge(SpecStore(store_path)), verify_readiness,
                               execute_lifecycle, verify_readback, start_worker,
                               read_current_row, verify_page_change)
    _runtime_factory = factory


def saved_after_commit(row: Mapping | None) -> dict:
    if row is None:
        return {"status": "CARD_MISSING", "publication_performed": False}
    try:
        with _runtime_scope() as runtime:
            if runtime is None:
                return {"status": "RUNTIME_UNCONFIGURED", "publication_performed": False}
            uid = canonical_uid(_pick(row, "auto_number", "car_uid", "uid"))
            current = runtime.read_current_row(uid)
            if not current:
                return {"status": "CARD_MISSING", "publication_performed": False}
            # Delayed events identify a card, never restore their stale payload.
            return runtime.bridge.saved(current)
    except Exception as exc:
        # CRM commit already succeeded. Preserve it; bootstrap reconciliation is
        # required for any event gap before publishing. Never report spec success.
        LOG.error("Specification post-commit event needs reconciliation: %s", type(exc).__name__)
        return {"status": "RECONCILIATION_REQUIRED", "publication_performed": False}


def runtime_summary(row: Mapping) -> str:
    with _runtime_scope() as runtime:
        return (runtime.bridge.summary(row) if runtime else
                "Специфікація: підключення нового модуля ще не завершено.")


def runtime_public_facts(uid: str) -> list[dict]:
    """One canonical read for every legacy composer and atomic page guard."""
    with _runtime_scope() as runtime:
        return _public_facts(runtime, uid)


def _public_facts(runtime, uid):
    if runtime is None:
        raise BridgeError("VERIFIED_RUNTIME_BINDINGS_REQUIRED")
    uid = canonical_uid(uid)
    row = runtime.read_current_row(uid)
    current_uid, identity = identity_from_crm(row)
    vehicle = runtime.bridge.store.get_vehicle(uid)
    # Store normalizes integer identity fields and removes blanks.
    from .store import _identity
    if current_uid != uid or _identity(identity)[1] != vehicle["identity_hash"] or vehicle["tombstoned"]:
        raise BridgeError("CRM_SPEC_IDENTITY_MISMATCH")
    facts = runtime.bridge.store.get_facts(uid)
    if not facts:
        raise BridgeError("ACCEPTED_SPEC_REQUIRED")
    output = []
    for fact in facts:
        item = dict(fact)
        item["is_visible"] = 0 if item.get("hidden") else 1
        if item.get("manual"):
            item["verification_status"] = "MANUAL_VERIFIED"
        elif item.get("verification") in (True, "verified", "confirmed", "official"):
            item["verification_status"] = "VERIFIED"
        output.append(item)
    return output


def start_configured_worker():
    with _runtime_scope() as runtime:
        if runtime is None:
            return {"status": "RUNTIME_UNCONFIGURED", "started": False}
        return runtime.start_worker()


def validate_runtime_page_change(before: str, after: str, uid: str, facts: list) -> dict:
    """Only an active exact manual-operation ticket may request a full-card delta."""
    from . import render, shell_guard
    with _runtime_scope() as runtime:
        ticket = _active_ticket.get()
        if (runtime is None or ticket is None or ticket.uid != uid or ticket.action != "publish"
                or not callable(runtime.verify_page_change)):
            raise BridgeError("AUTHORIZED_FULL_CARD_MANIFEST_REQUIRED")
        row = dict(runtime.read_current_row(uid))
        vehicle = runtime.bridge.store.get_vehicle(uid)
        if (vehicle["identity_hash"] != ticket.identity_hash or
                runtime.bridge.store.facts_digest(uid) != ticket.facts_digest):
            raise BridgeError("SPEC_CHANGED_DURING_OPERATION")
        shell = shell_guard.validate_shell_assets(before, after)
        request = {"uid": uid, "plan_id": ticket.plan_id, "action": ticket.action,
                   "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
                   "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
                   "crm_row_sha256": identity_hash(row),
                   "shell_assets_sha256": shell["ordered_static_assets_sha256"],
                   "revision": ticket.revision, "facts_digest": ticket.facts_digest,
                   "render_facts_sha256": render.facts_digest(facts)}
        manifest = dict(runtime.verify_page_change(request))
        if manifest.get("authorization") != "PASS" or any(manifest.get(k) != v for k, v in request.items()):
            raise BridgeError("AUTHORIZED_FULL_CARD_MANIFEST_REQUIRED")
        return render.validate_authorized_card_change(before, after, uid, facts, manifest, row)


def runtime_transition(action: str, row: Mapping, actor_id: int) -> tuple[bool, str]:
    with _runtime_scope() as runtime:
        return _transition(runtime, action, row, actor_id)


def _transition(runtime, action, row, actor_id):
    if runtime is None:
        return False, "Публікація ще не готова: модуль очікує перевіреного підключення."
    try:
        # The UI adds legacy fallback fields and can hold an old screen. Bind
        # authority to the current complete CRM row read by the route provider.
        uid = canonical_uid(_pick(row, "auto_number", "car_uid", "uid"))
        current = runtime.read_current_row(uid)
        if not current:
            raise BridgeError("CURRENT_CRM_CARD_MISSING")
        ticket = runtime.bridge.prepare(action, current, actor_id, runtime.verify_readiness)
    except BridgeError as exc:
        return False, "Дію не розпочато: " + str(exc)
    except Exception:
        return False, "Дію не розпочато: стан специфікації або дозволеного маршруту недоступний."
    # Executor must be idempotent by its operation receipt. Never retry here.
    token = _active_ticket.set(ticket)
    try:
        result = runtime.execute_lifecycle(ticket, dict(current))
    except Exception:
        return False, "Результат дії невідомий. Потрібна звірка стану; повторний запуск не виконано."
    finally:
        _active_ticket.reset(token)
    if result.get("ok") is not True:
        return False, str(result.get("detail", "Дію не завершено."))
    try:
        runtime.bridge.observed(ticket, result["receipt"], runtime.verify_readback)
    except Exception:
        return False, "Результат потребує перевірки. Не повторюйте дію до звірки стану сайту."
    return True, str(result.get("detail", "Зміни перевірено."))
