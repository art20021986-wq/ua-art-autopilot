"""Verified, bounded authority for recurring CRM price publication.

No import-time I/O, credentials, inferred server paths or manufactured receipts.
An explicit private installer anchor is the trust root. It pins a configuration
whose delegation and independently read canonical artifact chain bind the live
code, schema, identity registry, writer fences, owner and control observations.
The deployment transaction is provenance, never reused as an active event claim.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import time
from urllib.parse import urlsplit

import uaart_price_sync_outbox as outbox
import uaart_price_sync_runtime as runtime


LIVE_ROOT = Path("/home/Carix")
CONTRACT = "UA-ART-PRICE-EVENT-DELEGATION-1"
CONTRACT_V5 = "UA-ART-PRICE-EVENT-DELEGATION-2"
ANCHOR_CONTRACT = "UA-ART-PRICE-EVENT-ANCHOR-1"
MAX_FILE = 8 * 1024 * 1024
REQUIRED_CODE = frozenset({"cars_ui.py", "yadro.py", "stranica.py", "catalog_design_guard.py",
    "master_card.py", "publikaciya.py", "publish_transaction_guard.py", "ua_stage_catalog_sync.py",
    "uaart_market_prices.py", "uaart_price_sync_outbox.py", "uaart_price_sync_runtime.py",
    "uaart_price_sync_binding.py", "owner_policy.py", "price_publication.py", "start_safe.py",
    "db.py", "cars_schema.py"})
ARTIFACTS = frozenset({"manifest", "request", "owner_approval", "gate_b", "deployment_receipt",
                      "writer_fences", "owner_private_chat", "owner_policy"})
V5_REQUIRED_CODE = frozenset({"team_bot.py", "uaart_price_sync_confirmation.py", "uaart_price_control_reader.py",
    "publication_fence.py", "mutation_recovery.py", "ua_spec_permanent.py", "ua_additional_spec.py",
    "vin_spec_service.py", "lock4_zhurnal.py"})
# These exact sources can reach protected page/specification writes. Their
# presence is not a fencing fact; authenticated runtime evidence remains required.
V5_REQUIRED_WRITERS = frozenset({"stranica.py", "ua_spec_permanent.py", "ua_additional_spec.py", "vin_spec_service.py"})


class BindingError(runtime.SyncError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def _hash(value):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise BindingError("EXACT_SHA256_REQUIRED")
    return value


def _same(actual, expected, code):
    # JSON true must never satisfy an integer identity or timestamp comparison.
    if type(actual) is not type(expected) or actual != expected:
        raise BindingError(code)


def _integer(value, code):
    if type(value) is not int or not 0 <= value < 2**63:
        raise BindingError(code)
    return value


def _path(root, relative):
    if type(relative) is not str:
        raise BindingError("EXPLICIT_RELATIVE_PATH_REQUIRED")
    pure = PurePosixPath(relative)
    if (pure.is_absolute() or not pure.parts or pure.as_posix() != relative
            or any(part in (".", "..") for part in pure.parts)):
        raise BindingError("PATH_OUTSIDE_DELEGATED_ROOT")
    path = root.joinpath(*pure.parts)
    for item in (root, *(root.joinpath(*pure.parts[:i]) for i in range(1, len(pure.parts) + 1))):
        if item.is_symlink():
            raise BindingError("SYMLINK_PATH_FORBIDDEN")
    return path


def _read(path, *, private=False):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
        raise BindingError("REGULAR_BOUNDED_FILE_REQUIRED")
    if private and (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise BindingError("PRIVATE_INSTALLER_FILE_REQUIRED")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        current = os.fstat(descriptor)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise BindingError("FILE_CHANGED_DURING_OPEN")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(MAX_FILE + 1)
        if len(data) > MAX_FILE:
            raise BindingError("FILE_SIZE_LIMIT_EXCEEDED")
        return data
    finally:
        os.close(descriptor)


def schema_sha256(conn):
    """Exact schema, including triggers, independently observed on the live DB."""
    rows = conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name,tbl_name,sql").fetchall()
    return sha(encoded([list(row) for row in rows]))


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise BindingError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    value = json.loads(data, object_pairs_hook=pairs)
    if type(value) is not dict:
        raise BindingError("JSON_OBJECT_REQUIRED")
    return value


class Provider:
    def __init__(self, *, anchor_path, expected_anchor_sha256=None, test_root=None, clock=None):
        self.root = LIVE_ROOT if test_root is None else Path(test_root)
        if not self.root.is_absolute() or self.root.is_symlink():
            raise BindingError("EXACT_ROOT_REQUIRED")
        self.testing = test_root is not None
        self.clock = clock or (lambda: time.time_ns() // 1_000_000)
        anchor_path = Path(anchor_path)
        if not anchor_path.is_absolute():
            raise BindingError("EXPLICIT_ABSOLUTE_ANCHOR_REQUIRED")
        try:
            relative = str(anchor_path.relative_to(self.root))
        except ValueError as exc:
            raise BindingError("ANCHOR_OUTSIDE_ROOT") from exc
        self.anchor_path = _path(self.root, relative)
        anchor_bytes = _read(self.anchor_path, private=True)
        self.anchor_sha = sha(anchor_bytes)
        if expected_anchor_sha256 is not None:
            _same(self.anchor_sha, _hash(expected_anchor_sha256), "INSTALLER_ANCHOR_HASH_MISMATCH")
        anchor = _json(anchor_bytes)
        _same(anchor.get("contract"), ANCHOR_CONTRACT, "INSTALLER_ANCHOR_CONTRACT_REQUIRED")
        self.config_path = _path(self.root, anchor["config_path"])
        self.config_sha = _hash(anchor["config_sha256"])
        self.config = _json(self._pinned_read(self.config_path, self.config_sha, private=True))
        self.config_object_sha = sha(encoded(self.config))
        self.delegation = self.config["delegation"]
        if type(self.delegation) is not dict:
            raise BindingError("EXPLICIT_DELEGATION_REQUIRED")
        self.delegation_sha = sha(encoded(self.delegation))
        self.running_bot_verified = False
        self._validate_delegation()
        # A deliberate HALT/MANUAL or expired observation must stop price
        # publication, not take the owner's entire CRM bot offline on restart.
        self._verify_live(check_controls=False)

    def _pinned_read(self, path, expected, *, private=False):
        value = _read(path, private=private)
        _same(sha(value), _hash(expected), "PINNED_FILE_HASH_MISMATCH")
        return value

    def _reference(self, reference):
        if type(reference) is not dict or set(reference) != {"path", "sha256"}:
            raise BindingError("EXACT_ARTIFACT_REFERENCE_REQUIRED")
        raw = self._pinned_read(_path(self.root, reference["path"]), reference["sha256"])
        return raw, _json(raw)

    def _validate_delegation(self):
        d = self.delegation
        if d.get("contract") not in (CONTRACT, CONTRACT_V5):
            raise BindingError("EXACT_DELEGATION_CONTRACT_REQUIRED")
        self.dynamic_identities = d["contract"] == CONTRACT_V5
        _same(d.get("environment"), "TEST" if self.testing else "PRODUCTION", "ENVIRONMENT_BINDING_MISMATCH")
        _same(d.get("root"), str(self.root), "ROOT_BINDING_MISMATCH")
        if re.fullmatch(r"TASK088-GE-PRICE-SITE-STAGE3-[A-Za-z0-9-]+", d.get("task_id", "")) is None:
            raise BindingError("FRESH_STAGE3_IDENTITY_REQUIRED")
        operation = ("UPDATE_PUBLISHED_CAR_HOME_CATALOG_PRICES" if self.dynamic_identities
                     else "UPDATE_EXISTING_CARD_AND_CATALOG_PRICES")
        _same(d.get("operation"), operation, "PRICE_ONLY_DELEGATION_REQUIRED")
        _same(d.get("initial_publication"), "OWNER_MANUAL", "MANUAL_FIRST_PUBLICATION_REQUIRED")
        _same(d.get("fields"), ["price_uah", "price_georgia"], "EXACT_INDEPENDENT_FIELDS_REQUIRED")
        _same(d.get("currency"), "USD", "USD_ONLY_REQUIRED")
        _same(d.get("non_price_changes"), "FORBIDDEN", "PRICE_FRAGMENT_ONLY_REQUIRED")
        _same(d.get("public_origin"), "https://www.uaart.com.ua" if not self.testing else d.get("public_origin"), "PUBLIC_ORIGIN_MISMATCH")
        origin = urlsplit(d.get("public_origin", ""))
        if origin.scheme != "https" or not origin.hostname or origin.path or origin.query or origin.fragment or origin.username or origin.password:
            raise BindingError("EXACT_HTTPS_PUBLIC_ORIGIN_REQUIRED")
        self.db_path = _path(self.root, d["database_path"])
        self.lock_path = _path(self.root, d["publication_lock"])
        self.journal_root = _path(self.root, d["journal_root"])
        if not self.journal_root.is_dir() or stat.S_IMODE(self.journal_root.stat().st_mode) & 0o077:
            raise BindingError("PRIVATE_INSTALLED_JOURNAL_DIRECTORY_REQUIRED")
        identities = d.get("car_identities")
        if (type(identities) is not list
                or any(type(pair) is not list or len(pair) != 2 or type(pair[0]) is not int or pair[0] <= 0
                       or type(pair[1]) is not str or re.fullmatch(r"UA-[0-9]{4}", pair[1]) is None for pair in identities)
                or len({pair[0] for pair in identities}) != len(identities)
                or len({pair[1] for pair in identities}) != len(identities)):
            raise BindingError("UNIQUE_INITIAL_CAR_REGISTRY_REQUIRED")
        if not self.dynamic_identities and (len(identities) != 18
                or {pair[1] for pair in identities} != {f"UA-{i:04d}" for i in range(1, 19)}):
            raise BindingError("EXACT_18_CAR_REGISTRY_REQUIRED")
        if self.dynamic_identities:
            _same(d.get("identity_policy"), "AUTHENTICATED_CRM_PUBLISHED_CARS", "DYNAMIC_CRM_IDENTITY_DELEGATION_REQUIRED")
            policy = d.get("operator_policy")
            if (type(policy) is not dict or set(policy) != {"source", "permission", "chat_types", "roles"}
                    or policy.get("source") != "AUTHENTICATED_TELEGRAM_UPDATE"
                    or policy.get("permission") != "EXISTING_CRM_EDIT_CAR_ACL"
                    or type(policy.get("chat_types")) is not list or not policy["chat_types"]
                    or len(set(policy["chat_types"])) != len(policy["chat_types"])
                    or not set(policy["chat_types"]) <= {"private", "group", "supergroup"}
                    or policy.get("roles") != ["owner", "admin", "manager"]):
                raise BindingError("EXPLICIT_OPERATOR_PERMISSION_AND_CHAT_SCOPE_REQUIRED")
        self.identities = tuple(tuple(pair) for pair in identities)
        self.code_pins = d.get("installed_code_sha256", {})
        required = REQUIRED_CODE | (V5_REQUIRED_CODE if self.dynamic_identities else set())
        if type(self.code_pins) is not dict or not required <= set(self.code_pins):
            raise BindingError("ALL_INSTALLED_WRITERS_AND_MODULES_REQUIRED")
        for path, expected in self.code_pins.items():
            _path(self.root, path)
            _hash(expected)
        _hash(d["schema_sha256"])
        _hash(d["owner_private_chat_fact_sha256"])
        _hash(d["writer_fence_report_sha256"])
        self.control_contract = d.get("control_contract")
        if type(self.control_contract) is not dict:
            raise BindingError("OBSERVED_CONTROL_CONTRACT_REQUIRED")
        observations = self.control_contract.get("observations")
        if type(observations) is not dict or set(observations) != {"mode", "halt", "revocation"}:
            raise BindingError("MODE_HALT_REVOCATION_OBSERVATIONS_REQUIRED")
        if self.control_contract.get("provenance") not in ("LOCAL_AUTHORITATIVE", "EXTERNAL_CACHE"):
            raise BindingError("VERIFIED_CONTROL_PROVENANCE_REQUIRED")
        if (self.dynamic_identities and not self.testing
                and self.control_contract["provenance"] != "EXTERNAL_CACHE"):
            raise BindingError("INSTALLED_CANONICAL_READER_REQUIRED")
        for semantic, specification in observations.items():
            if type(specification) is not dict:
                raise BindingError("EXPLICIT_CONTROL_OBSERVATION_REQUIRED")
            _path(self.root, specification["path"])
            if specification.get("format") == "ABSENT_IS_CLEAR" and semantic == "halt":
                continue
            pointer = specification.get("field")
            if specification.get("format") != "JSON_FIELD" or type(pointer) is not list or not pointer:
                raise BindingError("EXPLICIT_OBSERVED_CONTROL_FIELD_REQUIRED")
        if self.control_contract["provenance"] == "EXTERNAL_CACHE":
            freshness = self.control_contract.get("freshness", {})
            if (type(freshness.get("source")) is not str or not freshness["source"]
                    or freshness.get("producer_path") not in self.code_pins):
                raise BindingError("PINNED_CONTROL_BRIDGE_REQUIRED")
            _path(self.root, freshness["path"])
            if self.dynamic_identities:
                _same(freshness.get("reader_contract"), "UA-ART-GITHUB-CONTROL-READER-1", "ACTUAL_CONTROL_READER_REQUIRED")
                _same(freshness.get("producer_path"), "uaart_price_control_reader.py", "PINNED_GITHUB_READER_REQUIRED")
                self._reader_config()
        if type(d.get("verified_recovery_successor_allowed")) is not bool:
            raise BindingError("EXPLICIT_RECOVERY_POLICY_REQUIRED")
        if not 1000 <= _integer(d.get("authorization_ttl_ms"), "AUTHORIZATION_TTL_REQUIRED") <= 30000:
            raise BindingError("BOUNDED_AUTHORIZATION_TTL_REQUIRED")
        if set(self.config.get("artifacts", {})) != ARTIFACTS:
            raise BindingError("COMPLETE_REAL_ARTIFACT_CHAIN_REQUIRED")
        surfaces = d.get("surfaces")
        if self.dynamic_identities:
            if surfaces is not None:
                raise BindingError("STATIC_AND_DYNAMIC_SURFACES_CANNOT_MIX")
            self._resolve_template_surfaces("UA-0001")
        else:
            if type(surfaces) is not dict or set(surfaces) != {code for _, code in self.identities}:
                raise BindingError("EXACT_SURFACE_REGISTRY_REQUIRED")
            for code in surfaces:
                self.resolve_surfaces(code)

    def resolve_identity(self, car_id):
        """Read a unique, currently published identity from the pinned CRM DB.

        The policy admitting future identities is explicitly manifest-bound.
        The supplied identifier never becomes a path without this DB check.
        """
        if not self.dynamic_identities:
            raise BindingError("DYNAMIC_CRM_IDENTITY_NOT_DELEGATED")
        if type(car_id) is not int or car_id <= 0:
            raise BindingError("EXACT_EVENT_CAR_ID_REQUIRED")
        with sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
            _same(schema_sha256(conn), self.delegation["schema_sha256"], "LIVE_SCHEMA_DRIFT")
            row = conn.execute("SELECT id,auto_number,vin,published FROM cars WHERE id=?", (car_id,)).fetchone()
            if (row is None or type(row[1]) is not str or re.fullmatch(r"UA-[0-9]{4}", row[1]) is None
                    or type(row[2]) is not str or not row[2].strip() or row[2] != row[2].strip()
                    or type(row[3]) is not int or row[3] != 1):
                raise BindingError("PUBLISHED_CRM_IDENTITY_REQUIRED")
            matching = conn.execute("SELECT id,auto_number FROM cars WHERE id=? OR auto_number=?", (car_id, row[1])).fetchall()
            if matching != [(car_id, row[1])]:
                raise BindingError("AMBIGUOUS_CRM_IDENTITY")
        initial_code = dict(self.identities).get(car_id)
        initial_id = {code: identifier for identifier, code in self.identities}.get(row[1])
        if (initial_code is not None and initial_code != row[1]) or (initial_id is not None and initial_id != car_id):
            raise BindingError("LIVE_CAR_REGISTRY_DRIFT")
        return {"id": row[0], "auto_number": row[1], "vin": row[2]}

    def _resolve_template_surfaces(self, code):
        raw = self.delegation.get("surface_templates")
        if (type(raw) is not list or not raw or any(type(item) is not dict for item in raw)
                or {item.get("kind") for item in raw} != {"CARD", "CATALOG", "HOME"}):
            raise BindingError("EXACT_CARD_CATALOG_HOME_TEMPLATES_REQUIRED")
        expanded = []
        for item in raw:
            fields = {"kind", "path", "url", "price_applicable"}
            if (set(item) != fields or any(type(item[key]) is not str for key in ("kind", "path", "url"))
                    or type(item["price_applicable"]) is not bool
                    or (item["kind"] != "HOME" and item["price_applicable"] is not True)):
                raise BindingError("EXACT_SURFACE_FIELDS_REQUIRED")
            expected_count = 1 if item["kind"] == "CARD" else 0
            for key in ("path", "url"):
                value = item[key]
                if value.count("{auto_number}") != expected_count or any(char in value.replace("{auto_number}", "") for char in "{}"):
                    raise BindingError("EXACT_CARD_ID_TEMPLATE_REQUIRED")
            expanded.append({key: value.replace("{auto_number}", code) if type(value) is str else value
                             for key, value in item.items()})
        return self._validated_surfaces(code, expanded, {"CARD", "CATALOG", "HOME"})

    def resolve_surfaces(self, code):
        if type(code) is not str or re.fullmatch(r"UA-[0-9]{4}", code) is None:
            raise BindingError("EXACT_SURFACE_CAR_CODE_REQUIRED")
        if self.dynamic_identities:
            with sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
                rows = conn.execute("SELECT id FROM cars WHERE auto_number=?", (code,)).fetchall()
            if len(rows) != 1 or self.resolve_identity(rows[0][0])["auto_number"] != code:
                raise BindingError("PUBLISHED_CRM_IDENTITY_REQUIRED")
            return self._resolve_template_surfaces(code)
        raw = self.delegation["surfaces"].get(code)
        return self._validated_surfaces(code, raw, {"CARD", "CATALOG"})

    def _validated_surfaces(self, code, raw, kinds):
        if type(raw) is not list or not raw or any(type(item) is not dict for item in raw) or {item.get("kind") for item in raw} != kinds:
            raise BindingError("EXACT_CARD_AND_CATALOG_SURFACES_REQUIRED")
        result = []
        for item in raw:
            fields = {"kind", "path", "url"} | ({"price_applicable"} if self.dynamic_identities else set())
            if set(item) != fields:
                raise BindingError("EXACT_SURFACE_FIELDS_REQUIRED")
            path = _path(self.root, item["path"])
            parsed = urlsplit(item["url"])
            if (parsed.scheme + "://" + parsed.netloc != self.delegation["public_origin"]
                    or parsed.query or parsed.fragment or parsed.username or parsed.password):
                raise BindingError("PUBLIC_SURFACE_ORIGIN_MISMATCH")
            wanted = {"CARD": code + ".html", "CATALOG": "katalog.html", "HOME": "index.html"}[item["kind"]]
            if path.name != wanted or parsed.path.rsplit("/", 1)[-1] != wanted:
                raise BindingError("PUBLIC_SURFACE_IDENTITY_MISMATCH")
            extras = {"price_applicable": item["price_applicable"]} if self.dynamic_identities else {}
            result.append(runtime.Surface(item["kind"], path, item["url"], **extras))
        if len({surface.path for surface in result}) != len(result):
            raise BindingError("DUPLICATE_SURFACE_PATH")
        return tuple(result)

    def _artifacts(self):
        raw, records = {}, {}
        for name, reference in self.config["artifacts"].items():
            raw[name], records[name] = self._reference(reference)
        hashes = {name: sha(value) for name, value in raw.items()}
        d = self.delegation
        task = d["task_id"]
        manifest, request, owner, gate, receipt, writers, chat, policy = (records[key] for key in
            ("manifest", "request", "owner_approval", "gate_b", "deployment_receipt", "writer_fences", "owner_private_chat", "owner_policy"))
        _same(manifest.get("price_event_delegation_sha256"), self.delegation_sha, "MANIFEST_DELEGATION_MISMATCH")
        _same(d["owner_private_chat_fact_sha256"], hashes["owner_private_chat"], "DELEGATED_PRIVATE_CHAT_FACT_MISMATCH")
        _same(d["writer_fence_report_sha256"], hashes["writer_fences"], "DELEGATED_WRITER_REPORT_MISMATCH")
        critical = request.get("critical", {})
        for name, expected in (("task_id", task), ("requested_min_class", "CRITICAL"), ("production_required", True)):
            _same(request.get(name), expected, "CANONICAL_REQUEST_REQUIRED")
        for name, expected in (("manifest_sha256", hashes["manifest"]), ("gate_a_sha256", hashes["gate_b"]),
                               ("owner_approval_sha256", hashes["owner_approval"])):
            _same(critical.get(name), expected, "CANONICAL_REQUEST_CHAIN_MISMATCH")
        subject = _json(raw["request"])
        subject["critical"]["owner_approval_sha256"] = "0" * 64
        subject_hash = sha((json.dumps(subject, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode())
        for name, expected in (("schema_version", "UA-ART-PRODUCTION-AUTHORIZATION-1"), ("task_id", task),
                               ("owner_authorized", True), ("production_allowed", True),
                               ("authorized_environment", "production"), ("manifest_sha256", hashes["manifest"]),
                               ("gate_a_sha256", hashes["gate_b"]), ("request_subject_sha256", subject_hash)):
            _same(owner.get(name), expected, "OWNER_AUTHORIZATION_CHAIN_MISMATCH")
        for name, expected in (("task_id", task), ("status", "PASS"), ("manifest_sha256", hashes["manifest"]),
                               ("tests", "PASS"), ("unexpected_changes", 0), ("backup_plan_ready", True),
                               ("rollback_plan_ready", True), ("writer_fence_report_sha256", hashes["writer_fences"])):
            _same(gate.get(name), expected, "VERIFIED_GATE_B_REQUIRED")
        # An install receipt permits only the explicitly delegated operations;
        # it is not reported here as completed Stage 3 or successful acceptance.
        if receipt.get("status") not in ("INSTALLED_PENDING_LIVE_ACCEPTANCE", "FINISHED"):
            raise BindingError("REAL_INSTALLED_DEPLOYMENT_RECEIPT_REQUIRED")
        for name, expected in (("task_id", task), ("request_sha256", hashes["request"]),
                               ("manifest_sha256", hashes["manifest"]), ("gate_b_sha256", hashes["gate_b"]),
                               ("installed_schema_sha256", d["schema_sha256"]), ("cars_audit_unchanged", True)):
            _same(receipt.get(name), expected, "DEPLOYMENT_RECEIPT_CHAIN_MISMATCH")
        installed = receipt.get("installed_files_sha256")
        if type(installed) is not dict or not {"cars_ui.py", "uaart_price_sync_binding.py", "uaart_price_sync_runtime.py",
                "uaart_price_sync_outbox.py", "uaart_market_prices.py"} <= set(installed):
            raise BindingError("REAL_INSTALLED_MODULE_HASHES_REQUIRED")
        for name in set(installed) & set(self.code_pins):
            _same(installed[name], self.code_pins[name], "INSTALLED_MODULE_DELEGATION_MISMATCH")
        if not re.fullmatch(r"tx-[A-Za-z0-9-]{8,100}", receipt.get("transaction_id", "")):
            raise BindingError("DEPLOYMENT_TRANSACTION_PROVENANCE_REQUIRED")
        if d.get("activation") != "BOUNDED_PRICE_EVENTS":
            raise BindingError("EXPLICIT_RECURRING_EVENT_ACTIVATION_REQUIRED")
        _same(writers.get("publication_lock"), str(self.lock_path), "WRITER_LOCK_MISMATCH")
        _same(writers.get("uncovered_writers"), [], "UNFENCED_WRITER_PRESENT")
        _same(writers.get("control_contract_sha256"), sha(encoded(self.control_contract)), "CONTROL_PROVENANCE_MISMATCH")
        listed = writers.get("writers")
        if (type(listed) is not list or not listed or any(type(item) is not dict or item.get("fence") != "VERIFIED"
                or item.get("path") not in self.code_pins
                or item.get("installed_sha256") != self.code_pins[item["path"]] for item in listed)):
            raise BindingError("VERIFIED_INSTALLED_WRITER_CONTRACTS_REQUIRED")
        required_writers = {"cars_ui.py", "ua_stage_catalog_sync.py", "publish_transaction_guard.py",
                            "master_card.py", "publikaciya.py", "uaart_price_sync_runtime.py"}
        if self.dynamic_identities:
            required_writers |= V5_REQUIRED_WRITERS
        if not required_writers <= {item["path"] for item in listed}:
            raise BindingError("ALL_PRICE_AND_CATALOG_WRITERS_REQUIRED")
        _same(policy, d["owner_policy"], "EXACT_OWNER_POLICY_ARTIFACT_REQUIRED")
        if (chat.get("source") != "AUTHENTICATED_CRM_BOT_PRIVATE_CHAT" or chat.get("chat_type") != "private"
                or chat.get("owner_user_id") != chat.get("chat_id") or type(chat.get("chat_id")) is not int
                or chat["chat_id"] <= 0 or type(chat.get("bot_id")) is not int or chat["bot_id"] <= 0
                or chat.get("verification") != "VERIFIED" or not chat.get("evidence")):
            raise BindingError("INDEPENDENT_OWNER_PRIVATE_CHAT_FACT_REQUIRED")
        _, observed_chat = self._reference(chat["evidence"])
        if observed_chat.get("source") not in (("AUTHENTICATED_CRM_BOT_PRIVATE_CHAT", "SYNTHETIC_TEST")
                if self.testing else ("AUTHENTICATED_CRM_BOT_PRIVATE_CHAT",)):
            raise BindingError("AUTHENTICATED_PRIVATE_CHAT_OBSERVATION_REQUIRED")
        for name, expected in (("owner_user_id", chat["owner_user_id"]), ("chat_id", chat["chat_id"]),
                               ("chat_type", "private"), ("bot_id", chat["bot_id"])):
            _same(observed_chat.get(name), expected, "PRIVATE_CHAT_SUMMARY_OBSERVATION_MISMATCH")
        if _integer(observed_chat.get("observed_ms"), "PRIVATE_CHAT_OBSERVATION_TIME_REQUIRED") > self.clock():
            raise BindingError("PRIVATE_CHAT_OBSERVATION_FROM_FUTURE")
        _same(d["owner_chat_id"], chat["chat_id"], "OWNER_CHAT_BINDING_MISMATCH")
        _same(d["bot_id"], chat["bot_id"], "CRM_BOT_IDENTITY_MISMATCH")
        return hashes, receipt

    def _reader_config(self):
        """Pin the reader config outside the delegation to avoid hash cycles.

        The installer anchor pins this reference together with the delegation
        and its real canonical artifacts; the reader in turn binds that already
        finalized delegation. A reader file does not authorize itself.
        """
        reference = self.config.get("control_reader")
        if type(reference) is not dict or set(reference) != {"path", "sha256"}:
            raise BindingError("INSTALLER_PINNED_READER_CONFIG_REQUIRED")
        reader = _json(self._pinned_read(_path(self.root,reference["path"]),reference["sha256"],private=True))
        freshness = self.control_contract["freshness"]
        expected = {"contract":"UA-ART-GITHUB-CONTROL-READER-1", "root":str(self.root),
                    "environment":"TEST" if self.testing else "PRODUCTION",
                    "repository":"art20021986-wq/ua-art-autopilot", "ref":"refs/heads/main",
                    "task_id":self.delegation["task_id"], "delegation_sha256":self.delegation_sha,
                    "source":freshness["source"], "freshness_path":freshness["path"],
                    "max_age_ms":freshness["max_age_ms"]}
        for key,value in expected.items():
            _same(reader.get(key),value,"CONTROL_READER_DELEGATION_MISMATCH")
        _same(reader.get("source"),"github:art20021986-wq/ua-art-autopilot:main",
              "EXACT_CANONICAL_READER_SOURCE_REQUIRED")
        if type(reader["max_age_ms"]) is not int or not 1000 <= reader["max_age_ms"] <= 30000:
            raise BindingError("CONTROL_READER_30_SECOND_BOUND_REQUIRED")
        if (type(reader.get("poll_interval_ms")) is not int
                or not 1000 <= reader["poll_interval_ms"] <= reader["max_age_ms"] // 2):
            raise BindingError("CONTROL_READER_RENEWAL_INTERVAL_REQUIRED")
        pins = reader.get("canonical_file_pins")
        if (type(pins) is not dict
                or not {"state/EXECUTION_MODE.json", "state/MANUAL_MODE.md", "automation/control_plane.py"} <= set(pins)
                or "state/AUTOPILOT_HALT.json" in pins):
            raise BindingError("FULL_CANONICAL_READER_CHAIN_REQUIRED")
        for path,digest in pins.items():
            _path(self.root,path); _hash(digest)
        artifacts = reader.get("price_artifacts")
        if type(artifacts) is not dict or set(artifacts) != {"manifest","request","owner_approval","gate_b"}:
            raise BindingError("EXACT_READER_PRICE_ARTIFACTS_REQUIRED")
        for semantic,field in (("mode","mode"),("halt","halt"),("revocation","revoked")):
            _same(self.control_contract["observations"][semantic],
                  {"path":reader["state_path"],"format":"JSON_FIELD","field":[field]},
                  "CONTROL_READER_OBSERVATION_PATH_MISMATCH")
        for name in ("manifest","request","owner_approval","gate_b"):
            path=artifacts[name]
            _path(self.root,path)
            _same(pins.get(path),self.config["artifacts"][name]["sha256"],
                  "CONTROL_READER_CANONICAL_ARTIFACT_MISMATCH")
        return reader

    def _control(self, now):
        contract = self.control_contract
        observations = contract.get("observations")
        if type(observations) is not dict or set(observations) != {"mode", "halt", "revocation"}:
            raise BindingError("MODE_HALT_REVOCATION_OBSERVATIONS_REQUIRED")
        facts = {}
        for semantic, specification in observations.items():
            path = _path(self.root, specification["path"])
            if specification.get("format") == "ABSENT_IS_CLEAR" and semantic == "halt":
                if path.exists():
                    raise BindingError("ACTIVE_OR_UNRECONCILED_HALT_FILE")
                facts[semantic] = {"path": str(path), "absent": True}
                continue
            if specification.get("format") != "JSON_FIELD":
                raise BindingError("OBSERVED_CONTROL_FORMAT_REQUIRED")
            raw = _read(path)
            value = _json(raw)
            pointer = specification.get("field")
            if type(pointer) is not list or not pointer or any(type(key) is not str for key in pointer):
                raise BindingError("EXPLICIT_OBSERVED_CONTROL_FIELD_REQUIRED")
            for key in pointer:
                if type(value) is not dict or key not in value:
                    raise BindingError("CONTROL_FIELD_MISSING")
                value = value[key]
            expected = "AUTOMATIC" if semantic == "mode" else False
            _same(value, expected, "CONTROL_BLOCKS_PRICE_PUBLICATION")
            facts[semantic] = {"path": str(path), "sha256": sha(raw), "value": value}
        provenance = contract.get("provenance")
        expiry = now + self.delegation["authorization_ttl_ms"]
        if provenance == "EXTERNAL_CACHE":
            freshness = contract.get("freshness")
            if type(freshness) is not dict:
                raise BindingError("EXTERNAL_CONTROL_CACHE_FRESHNESS_REQUIRED")
            max_age = _integer(freshness.get("max_age_ms"), "CONTROL_CACHE_MAX_AGE_REQUIRED")
            if not 1000 <= max_age <= 60000:
                raise BindingError("CONTROL_CACHE_MAX_AGE_TOO_LARGE")
            raw = _read(_path(self.root, freshness["path"]))
            stamp = _json(raw)
            if self.dynamic_identities:
                self._reader_config()
                for key,expected in (("reader_config_sha256",self.config["control_reader"]["sha256"]),
                                     ("task_id",self.delegation["task_id"]),
                                     ("delegation_sha256",self.delegation_sha)):
                    _same(stamp.get(key),expected,"CONTROL_CACHE_READER_IDENTITY_MISMATCH")
                if re.fullmatch(r"[0-9a-f]{40}",stamp.get("commit_sha", "")) is None:
                    raise BindingError("CONTROL_CACHE_CANONICAL_COMMIT_REQUIRED")
            observed = _integer(stamp.get("observed_ms"), "CONTROL_CACHE_TIMESTAMP_REQUIRED")
            if not 0 <= now - observed <= max_age or stamp.get("source") != freshness.get("source"):
                raise BindingError("CONTROL_CACHE_STALE_OR_WRONG_SOURCE")
            _same(stamp.get("observations_sha256"), sha(encoded(facts)), "CONTROL_CACHE_CONTENT_BINDING_MISMATCH")
            facts["cache"] = {"sha256": sha(raw), "observed_ms": observed}
            expiry = min(expiry, observed + max_age)
        elif provenance != "LOCAL_AUTHORITATIVE":
            raise BindingError("VERIFIED_CONTROL_PROVENANCE_REQUIRED")
        return facts, expiry

    def _verify_live(self, *, check_controls=True):
        _same(sha(encoded(self.delegation)), self.delegation_sha, "IN_MEMORY_DELEGATION_CHANGED")
        _same(sha(encoded(self.config)), self.config_object_sha, "IN_MEMORY_CONFIG_CHANGED")
        _same(sha(_read(self.anchor_path, private=True)), self.anchor_sha, "INSTALLER_ANCHOR_CHANGED")
        self._pinned_read(self.config_path, self.config_sha, private=True)
        hashes, receipt = self._artifacts()
        for relative, expected in self.code_pins.items():
            self._pinned_read(_path(self.root, relative), expected)
        if self.db_path.is_symlink() or not self.db_path.is_file():
            raise BindingError("EXISTING_DATABASE_REQUIRED")
        with sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
            _same(schema_sha256(conn), self.delegation["schema_sha256"], "LIVE_SCHEMA_DRIFT")
            for car_id, code in self.identities:
                rows = conn.execute("SELECT id,auto_number FROM cars WHERE id=? OR auto_number=?", (car_id, code)).fetchall()
                if rows != [(car_id, code)]:
                    raise BindingError("LIVE_CAR_REGISTRY_DRIFT")
        now = _integer(self.clock(), "VALID_CLOCK_REQUIRED")
        controls, expires = self._control(now) if check_controls else ({}, now)
        return hashes, receipt, controls, now, expires

    def _write_authorization(self, record):
        directory = _path(self.root, self.delegation["journal_root"] + "/authorizations")
        directory.mkdir(mode=0o700, exist_ok=True)
        if not directory.is_dir() or stat.S_IMODE(directory.stat().st_mode) & 0o077:
            raise BindingError("PRIVATE_AUTHORIZATION_DIRECTORY_REQUIRED")
        parent_fd = os.open(directory.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
        raw = encoded(record)
        name = sha(raw) + ".json"
        path = directory / name
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            _same(_read(path, private=True), raw, "AUTHORIZATION_RECORD_CONFLICT")
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        return str(path), sha(raw)

    def _operator_provenance(self, event):
        """Verify the immutable admission facts from the pinned CRM writer.

        These facts are not a substitute for Telegram authentication or the
        existing edit ACL. The installed CRM adapter must obtain them from the
        authenticated Update *after* its normal permission check; its code hash
        and the independently read durable operation are checked on every use.
        """
        raw = event.get("provenance_json")
        if type(raw) is not str:
            raise BindingError("DURABLE_OPERATOR_PROVENANCE_REQUIRED")
        facts = _json(raw)
        sources = {"TELEGRAM_UPDATE", "SYNTHETIC_TEST"} if self.testing else {"TELEGRAM_UPDATE"}
        if facts.get("source") not in sources:
            raise BindingError("AUTHENTICATED_OPERATOR_UPDATE_REQUIRED")
        for key in ("actor_id", "chat_id"):
            _same(facts.get(key), event.get(key), "OPERATOR_EVENT_IDENTITY_MISMATCH")
        _same(facts.get("bot_id"), self.delegation["bot_id"], "OPERATOR_CRM_BOT_MISMATCH")
        _same(facts.get("authorized_car_id"), event.get("car_id"), "OPERATOR_CAR_PERMISSION_MISMATCH")
        _same(facts.get("permission"), "EDIT_CAR", "OPERATOR_CAR_PERMISSION_REQUIRED")
        for key in ("actor_id", "message_id", "bot_id", "authorized_car_id"):
            if _integer(facts.get(key), "OPERATOR_UPDATE_INTEGER_REQUIRED") <= 0:
                raise BindingError("OPERATOR_UPDATE_POSITIVE_ID_REQUIRED")
        _integer(facts.get("update_id"), "OPERATOR_UPDATE_ID_REQUIRED")
        chat_id, chat_type = facts.get("chat_id"), facts.get("chat_type")
        if (type(chat_id) is not int or not -(2**63) < chat_id < 2**63 or chat_id == 0
                or chat_type not in self.delegation["operator_policy"]["chat_types"]):
            raise BindingError("OPERATOR_CHAT_OUTSIDE_DELEGATED_SCOPE")
        if (chat_type == "private" and chat_id != facts["actor_id"]) or (chat_type in ("group", "supergroup") and chat_id >= 0):
            raise BindingError("OPERATOR_CHAT_IDENTITY_MISMATCH")
        # Match the observed team_bot.who/db.get_staff authority. No separate
        # allow-list, owner-only rule, inferred manager privileges or module
        # import is introduced by this read.
        with sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
            rows = conn.execute("SELECT user_id,active,role FROM staff WHERE user_id=?", (facts["actor_id"],)).fetchall()
        if (len(rows) != 1 or type(rows[0][1]) is not int or rows[0][1] != 1
                or rows[0][2] not in self.delegation["operator_policy"]["roles"]):
            raise BindingError("CURRENT_CRM_EDIT_PERMISSION_REQUIRED")
        return facts

    def authorize(self, event, surfaces):
        if not self.running_bot_verified:
            raise BindingError("RUNNING_CRM_BOT_NOT_YET_VERIFIED")
        hashes, receipt, controls, now, expiry = self._verify_live()
        key, nonce = _hash(event.get("event_key")), _hash(event.get("claim_nonce"))
        if self.dynamic_identities:
            identity = self.resolve_identity(event.get("car_id"))
            code = identity["auto_number"]
            _same(event.get("car_code"), code, "EVENT_CRM_CAR_CODE_MISMATCH")
            _same(event.get("vin"), identity["vin"], "EVENT_CRM_VIN_MISMATCH")
        else:
            code = dict(self.identities).get(event.get("car_id"))
        if code is None or tuple(surfaces) != self.resolve_surfaces(code):
            raise BindingError("EVENT_SURFACE_SCOPE_MISMATCH")
        # The runtime owns BEGIN IMMEDIATE and the shared publication lock.
        # This independent read observes its already committed durable claim.
        with sqlite3.connect(self.db_path.as_uri() + "?mode=ro", uri=True, timeout=1) as conn:
            actual = (outbox.get_operation(conn, key) if self.dynamic_identities else outbox.get(conn, key))
            allowed_states = {"CLAIMED", "DB_COMMITTED", "SITE_PUBLISHED", "VERIFIED"} if self.dynamic_identities else {"CLAIMED", "STOPPED"}
            if actual is None or actual != event or actual["state"] not in allowed_states:
                raise BindingError("DURABLE_CURRENT_EVENT_CLAIM_REQUIRED")
        operator_facts = self._operator_provenance(actual) if self.dynamic_identities else None
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                raise BindingError("SHARED_PUBLICATION_LOCK_NOT_HELD")
        finally:
            os.close(descriptor)
        local_claim = "price-event-claim-" + sha(encoded((self.delegation_sha, key, nonce)))
        local_transaction = "price-event-tx-" + sha(encoded((self.delegation_sha, key, nonce, "PRICE_FRAGMENTS")))
        record = {"authority_kind": "CANONICAL_DEPLOYMENT_DELEGATED_LOCAL_PRICE_EVENT",
            "delegation_sha256": self.delegation_sha, "artifact_sha256": hashes,
            "canonical_task_id": self.delegation["task_id"],
            "deployment_transaction_id": receipt["transaction_id"],
            "canonical_claim_id": local_claim, "canonical_transaction_id": local_transaction,
            "event_key": key, "claim_nonce": nonce, "car_id": event["car_id"], "auto_number": code,
            "event_sha256": sha(encoded(event)), "revision": event["sequence"] if self.dynamic_identities else event["revision"],
            "gate_b_receipt_sha256": hashes["gate_b"], "writer_fence_verified": True,
            "verified_recovery_successor_allowed": self.delegation["verified_recovery_successor_allowed"],
            "allowed_paths": [str(surface.path) for surface in surfaces], "controls": controls,
            "observed_ms": now, "expires_ms": expiry}
        if operator_facts is not None:
            record["operator_provenance_sha256"] = sha(encoded(operator_facts))
            record["operator_chat_id"] = operator_facts["chat_id"]
            record["operator_user_id"] = operator_facts["actor_id"]
        path, record_hash = self._write_authorization(record)
        return dict(record, authorization_record_path=path, authorization_record_sha256=record_hash)

    def binding(self):
        detail = self.delegation["detail_url"]
        extras = {"resolve_identity": self.resolve_identity} if self.dynamic_identities else {}
        return runtime.Binding(db_path=self.db_path, publication_lock=self.lock_path,
            journal_root=self.journal_root, resolve_surfaces=self.resolve_surfaces, authorize=self.authorize,
            owner_chat_id=self.delegation["owner_chat_id"], detail_url=detail,
            owner_private_chat_verified=True, car_identities=self.identities, clock=self.clock, **extras)

    def verify_running_bot(self, bot):
        _same(getattr(bot, "id", None), self.delegation["bot_id"], "RUNNING_CRM_BOT_IDENTITY_MISMATCH")
        self.running_bot_verified = True


def bootstrap(app, *, anchor_path, expected_anchor_sha256=None, test_root=None):
    """Populate the existing app before runtime.register; never create another bot.

    The explicit anchor must be written by the verified installer only after a
    real deployment receipt. Missing recipient proof or immutable artifacts stop
    startup; operational controls stop only price publication. This function
    does not register jobs or report deployment success.
    """
    provider = Provider(anchor_path=anchor_path, expected_anchor_sha256=expected_anchor_sha256,
                        test_root=test_root)
    binding = provider.binding()
    current = app.bot_data.get(runtime.BINDING_KEY)
    if current is not None and current is not binding:
        raise BindingError("EXISTING_RUNTIME_BINDING_CANNOT_BE_OVERWRITTEN")
    prior_post_init = getattr(app, "post_init", None)

    async def verified_post_init(application):
        if prior_post_init is not None:
            await prior_post_init(application)
        provider.verify_running_bot(application.bot)

    # PTB calls post_init after Bot.initialize, before polling starts. Directly
    # constructed test/custom lifecycle applications must run this hook too;
    # authorize otherwise fails closed. No token access or API call is added.
    app.post_init = verified_post_init
    app.bot_data[runtime.BINDING_KEY] = binding
    return binding


def preflight(*, anchor_path, expected_anchor_sha256=None, test_root=None):
    """Read-only binding inspection; never bootstrap, send, write or authorize."""
    try:
        provider = Provider(anchor_path=anchor_path, expected_anchor_sha256=expected_anchor_sha256,
                            test_root=test_root)
        hashes, receipt, controls, observed, expiry = provider._verify_live()
        return {"status":"INSTALLED_BINDING_VERIFIED_PENDING_BOT_INITIALIZATION",
            "task_id":provider.delegation["task_id"], "delegation_sha256":provider.delegation_sha,
            "artifact_sha256":hashes, "deployment_status":receipt["status"],
            "bound_cars":len(provider.identities), "controls":controls,
            "observed_ms":observed, "control_valid_until_ms":expiry,
            "stage3_complete":False, "production_changed":False, "activated":False}
    except (BindingError, OSError, ValueError, TypeError, KeyError, sqlite3.Error) as error:
        return {"status":"BLOCKED", "reason":str(error) if isinstance(error,BindingError) else type(error).__name__,
                "stage3_complete":False,"production_changed":False,"activated":False}
