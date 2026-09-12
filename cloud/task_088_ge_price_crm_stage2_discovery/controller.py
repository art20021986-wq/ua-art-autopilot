#!/usr/bin/env python3
"""TASK088 pricing discovery: fixed GETs, AST inspection, no live execution.

Never imports downloaded code, downloads a database, or changes remote state.
FINISHED means this discovery completed; no CRM price acceptance is claimed.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import tempfile
import tokenize
import urllib.error
import urllib.request
from typing import Mapping

TASK_ID = "TASK088-GE-PRICE-CRM-STAGE2-DISCOVERY"
STAGE1_ID = "TASK088-GE-PRICE-CRM-STAGE1"
ROOT = pathlib.Path(__file__).resolve().parents[2]
PACKAGE_REL = "cloud/task_088_ge_price_crm_stage2_discovery"
REQUEST_REL = "tasks/requests/" + TASK_ID + ".json"
RECEIPT_REL = "state/receipts/" + TASK_ID + ".json"
EVIDENCE_REL = PACKAGE_REL + "/evidence.json"
STAGE1_RECEIPT_REL = "state/receipts/" + STAGE1_ID + ".json"
API_BASE = "https://www.pythonanywhere.com/api/v0/user/Carix/files/path"
SOURCE_PATHS = tuple("/home/Carix/" + name for name in (
    "cars_ui.py", "db.py", "cars_schema.py", "start_safe.py"))
STAGE1_REMOTE_DIR = "/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage1"
STAGE1_REMOTE_RECEIPT = STAGE1_REMOTE_DIR + "/receipt.json"
BACKUP_PATHS = tuple(STAGE1_REMOTE_DIR + "/backup/" + name for name in (
    "cars_ui.py", "crm.db"))
BODY_PATHS = frozenset((*SOURCE_PATHS, STAGE1_REMOTE_RECEIPT))
ALL_REMOTE_PATHS = BODY_PATHS | frozenset(BACKUP_PATHS)
ALLOWED_URLS = frozenset(API_BASE + path for path in ALL_REMOTE_PATHS)
MAX_SOURCE_BYTES = 1024 * 1024
MAX_RECEIPT_BYTES = 64 * 1024
MAX_FUNCTION_BYTES = 96 * 1024
MAX_EXPORTED_SOURCE_BYTES = 384 * 1024
SELECTED_FUNCTIONS = frozenset((
    "edit_menu", "edit_ask", "apply_value", "catch_message", "auto_catch",
    "set_field", "card_of", "card_kb", "db", "connect", "register"))
FIELD_CONSTANTS = frozenset(("EDITABLE", "MONEY", "NUMERIC", "LABELS_ALL"))
PRICE_FIELDS = frozenset(("price_uah", "price_georgia"))
PRICE_LABELS = frozenset(("Цена Украины", "Цена Грузии", "Цена продажи",
                          "цена", "цена Украины", "цена Грузии"))
SECRET_NAME = re.compile(
    r"(?:^|_)(?:token|password|passwd|secret|credential|authorization|api_key|private_key)(?:$|_)",
    re.I)
TOKEN_PATTERN = re.compile(
    r"(?:\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|\b(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{12,}"
    r"|\bAKIA[0-9A-Z]{16}\b|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|[A-Za-z0-9_+/=-]{40,}"
    r"|(?:password|passwd|secret|api[_-]?key|authorization|token)\s*[:=]\s*[^\s,;{}]{5,}"
    r"|https?://[^/\s]+:[^/\s]+@)", re.I)


class DiscoveryError(RuntimeError):
    """Only fixed error codes may leave this controller."""


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_symbol(value):
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,100}", value) else "<omitted>"


def symbol(node):
    if isinstance(node, ast.Name):
        return safe_symbol(node.id)
    if isinstance(node, ast.Attribute):
        return symbol(node.value) + "." + safe_symbol(node.attr)
    return type(node).__name__


def expression_shape(node):
    """Routing structure without arbitrary literal/configuration exports."""
    if isinstance(node, ast.Call):
        return {"call": symbol(node.func),
                "args": [expression_shape(item) for item in node.args],
                "keywords": [{"name": safe_symbol(item.arg), "value": expression_shape(item.value)}
                             for item in node.keywords]}
    if isinstance(node, (ast.Name, ast.Attribute)):
        return {"symbol": symbol(node)}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return {type(node).__name__: [expression_shape(item) for item in node.elts]}
    if isinstance(node, ast.Constant):
        if type(node.value) is str and node.value in PRICE_FIELDS | PRICE_LABELS | {"car_wait", "car_setf:"}:
            return {"literal": node.value}
        return {"constant_type": type(node.value).__name__}
    return {"node": type(node).__name__}


class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Reject even same-origin redirects; credentials cannot reach another URL.
        raise DiscoveryError("REDIRECT_FORBIDDEN")


class ReadOnlyAPI:
    def __init__(self, token):
        if not token or len(token) > 256 or re.search(r"[\s\x00-\x1f\x7f]", token):
            raise DiscoveryError("TOKEN_INVALID")
        self._token = token
        # Respect runner network/proxy configuration; never follow redirects.
        self._opener = urllib.request.build_opener(RefuseRedirects())
        self.get_count = 0
        self.response_body_bytes = 0

    def _open(self, path, existence_only=False):
        if path not in ALL_REMOTE_PATHS or (existence_only != (path in BACKUP_PATHS)):
            raise DiscoveryError("REMOTE_SCOPE")
        url = API_BASE + path
        if url not in ALLOWED_URLS:
            raise DiscoveryError("URL_SCOPE")
        headers = {"Authorization": "Token " + self._token,
                   "User-Agent": "ua-art-task088-get-only-discovery/1",
                   "Accept-Encoding": "identity"}
        if existence_only:
            headers["Range"] = "bytes=0-0"
        req = urllib.request.Request(url, headers=headers, method="GET")
        self.get_count += 1
        try:
            response = self._opener.open(req, timeout=30)
        except urllib.error.HTTPError as exc:
            exc.close()
            code = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else 0
            raise DiscoveryError("REMOTE_HTTP_" + str(code)) from None
        except (urllib.error.URLError, OSError, ValueError):
            raise DiscoveryError("REMOTE_TRANSPORT_FAILURE") from None
        if response.geturl() != url or response.geturl() not in ALLOWED_URLS:
            response.close()
            raise DiscoveryError("RESPONSE_URL_MISMATCH")
        if response.status not in ((200, 206) if existence_only else (200,)):
            response.close()
            raise DiscoveryError("REMOTE_STATUS_INVALID")
        if response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
            response.close()
            raise DiscoveryError("CONTENT_ENCODING_FORBIDDEN")
        return response

    def read(self, path):
        if path not in BODY_PATHS:
            raise DiscoveryError("BODY_READ_SCOPE")
        limit = MAX_RECEIPT_BYTES if path == STAGE1_REMOTE_RECEIPT else MAX_SOURCE_BYTES
        with self._open(path) as response:
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit() or int(length) > limit):
                raise DiscoveryError("REMOTE_SIZE_LIMIT")
            data = response.read(limit + 1)
        if len(data) > limit:
            raise DiscoveryError("REMOTE_SIZE_LIMIT")
        self.response_body_bytes += len(data)
        return data

    def backup_exists(self, path):
        if path not in BACKUP_PATHS:
            raise DiscoveryError("BACKUP_SCOPE")
        with self._open(path, existence_only=True) as response:
            # Deliberately do not call read(): neither database nor backup source
            # bytes enter Python memory, output, logs, or repository artifacts.
            return {"path": path, "exists": True, "http_status": response.status,
                    "method": "GET", "body_bytes_read": 0,
                    "integrity": "NOT_VERIFIED", "restore_test": "NOT_PERFORMED"}


def contains_sensitive_source(source, node):
    """Reject a selected snippet as a whole if it could expose credentials."""
    for item in ast.walk(node):
        targets = []
        if isinstance(item, ast.keyword) and SECRET_NAME.search(item.arg or ""):
            return "SECRET_KEYWORD"
        if isinstance(item, ast.Dict) and any(
            isinstance(key, ast.Constant) and isinstance(key.value, str)
            and SECRET_NAME.search(key.value) for key in item.keys
        ):
            return "SECRET_DICT_KEY"
        if isinstance(item, ast.arguments):
            positional = [*item.posonlyargs, *item.args]
            defaulted = positional[len(positional) - len(item.defaults):] if item.defaults else []
            defaulted += [arg for arg, default in zip(item.kwonlyargs, item.kw_defaults) if default is not None]
            if any(SECRET_NAME.search(arg.arg) for arg in defaulted):
                return "SECRET_ARGUMENT_DEFAULT"
        if isinstance(item, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
        for target in targets:
            for part in ast.walk(target):
                name = part.id if isinstance(part, ast.Name) else part.attr if isinstance(part, ast.Attribute) else ""
                if SECRET_NAME.search(name):
                    return "SECRET_ASSIGNMENT"
                if isinstance(part, ast.Subscript) and isinstance(part.slice, ast.Constant) and isinstance(part.slice.value, str) and SECRET_NAME.search(part.slice.value):
                    return "SECRET_SUBSCRIPT_ASSIGNMENT"
        if isinstance(item, ast.Constant) and isinstance(item.value, (str, bytes)):
            text = item.value.decode("utf-8", errors="replace") if isinstance(item.value, bytes) else item.value
            if TOKEN_PATTERN.search(text):
                return "TOKEN_LIKE_LITERAL"
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and TOKEN_PATTERN.search(token.string):
                return "TOKEN_LIKE_COMMENT"
    except (tokenize.TokenError, IndentationError):
        return "TOKENIZATION_FAILURE"
    return None


def selected_constants(node):
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return None
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = [item.id for item in targets if isinstance(item, ast.Name) and item.id in FIELD_CONSTANTS]
    if not names:
        return None
    try:
        value = ast.literal_eval(node.value)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return {name: {"literal": False} for name in names}
    result = {}
    for name in names:
        if name == "EDITABLE" and isinstance(value, (list, tuple)):
            result[name] = [{"field": item[0], "label": item[1] if item[1] in PRICE_LABELS else "<omitted>"}
                            for item in value if isinstance(item, (list, tuple)) and len(item) == 2
                            and isinstance(item[0], str) and item[0] in PRICE_FIELDS
                            and isinstance(item[1], str)]
        elif name == "LABELS_ALL" and isinstance(value, dict):
            result[name] = {key: value[key] if isinstance(value[key], str) and value[key] in PRICE_LABELS else "<omitted>"
                            for key in sorted(PRICE_FIELDS) if key in value}
        elif name in {"MONEY", "NUMERIC"} and isinstance(value, (list, tuple, set)):
            result[name] = sorted({safe_symbol(item) for item in value})
        else:
            result[name] = {"literal": True, "shape": "UNSUPPORTED"}
    return result


def inspect_source(payload, path):
    if path not in SOURCE_PATHS or len(payload) > MAX_SOURCE_BYTES:
        raise DiscoveryError("SOURCE_SCOPE_OR_SIZE")
    try:
        source = payload.decode("utf-8-sig")
        tree = ast.parse(source, filename=path)
    except (UnicodeDecodeError, SyntaxError, ValueError, RecursionError):
        raise DiscoveryError("SOURCE_PARSE_FAILED") from None
    functions, selected, constants, aliases, imports, routing = [], {}, [], [], [], []
    exported = 0
    for index, node in enumerate(tree.body):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports.append({"order": index, "module": getattr(node, "module", None),
                            "names": [{"name": item.name, "alias": item.asname} for item in node.names]})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = ast.get_source_segment(source, node)
            if segment is None:
                raise DiscoveryError("SOURCE_SEGMENT_MISSING")
            digest = sha(segment.encode("utf-8"))
            summary = {"name": safe_symbol(node.name), "line": node.lineno,
                       "order": index, "sha256": digest,
                       "decorators": [expression_shape(item) for item in node.decorator_list]}
            functions.append(summary)
            if node.name in SELECTED_FUNCTIONS:
                details = dict(summary)
                reason = contains_sensitive_source(segment, node)
                count = len(segment.encode("utf-8"))
                if count > MAX_FUNCTION_BYTES or exported + count > MAX_EXPORTED_SOURCE_BYTES:
                    reason = "EXPORT_SIZE_LIMIT"
                if reason:
                    details.update({"source_exported": False, "omission_reason": reason})
                else:
                    details.update({"source_exported": True, "source": segment,
                                    "source_scope": "EXACT_FUNCTION_WITHOUT_DECORATORS"})
                    exported += count
                selected.setdefault(node.name, []).append(details)
        fields = selected_constants(node)
        if fields is not None:
            constants.append({"order": index, "line": node.lineno, "values": fields})
        if isinstance(node, ast.Assign) and isinstance(node.value, (ast.Name, ast.Attribute)):
            names = [item.id for item in node.targets if isinstance(item, ast.Name)]
            if names and not any(SECRET_NAME.search(name) for name in names):
                aliases.append({"order": index, "line": node.lineno,
                                "targets": [safe_symbol(name) for name in names],
                                "value": symbol(node.value)})
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            routing.append({"order": index, "line": node.lineno, "shape": expression_shape(node.value)})
    return {"path": path, "sha256": sha(payload), "bytes": len(payload),
            "syntax": "PASS", "imports": imports, "function_definitions": functions,
            "selected_functions": selected, "field_constants": constants,
            "top_level_symbol_aliases": aliases, "top_level_call_shapes": routing,
            "all_definitions_retained": True, "exported_function_bytes": exported,
            "full_source_exported": False, "live_module_imported": False,
            "runtime_handler_binding": "NOT_VERIFIED"}


def read_local_json(root, relative, limit=MAX_RECEIPT_BYTES):
    path = root / relative
    current = root
    for component in pathlib.PurePosixPath(relative).parts:
        current = current / component
        if current.is_symlink():
            raise DiscoveryError("LOCAL_SYMLINK_FORBIDDEN")
    if not path.is_file() or path.stat().st_size > limit:
        raise DiscoveryError("LOCAL_FILE_INVALID")
    data = path.read_bytes()
    if len(data) > limit:
        raise DiscoveryError("LOCAL_SIZE_LIMIT")
    try:
        value = json.loads(data)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise DiscoveryError("LOCAL_JSON_INVALID") from None
    if not isinstance(value, dict):
        raise DiscoveryError("LOCAL_JSON_OBJECT_REQUIRED")
    return value, data


def validate_identity(env, root):
    if env.get("UAART_TASK_ID") != TASK_ID or env.get("UAART_RECEIPT_PATH") != RECEIPT_REL or env.get("UAART_REQUEST_PATH") != REQUEST_REL:
        raise DiscoveryError("EXECUTION_IDENTITY")
    run_id = env.get("UAART_RUN_ID", "")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", run_id):
        raise DiscoveryError("RUN_ID_INVALID")
    request, raw = read_local_json(root, REQUEST_REL)
    request_sha = sha(raw)
    if request_sha != env.get("UAART_REQUEST_SHA256"):
        raise DiscoveryError("REQUEST_SHA_MISMATCH")
    if request.get("task_id") != TASK_ID or request.get("production_required") is not False or request.get("read_only") is not True or request.get("requested_min_class") != "STANDARD":
        raise DiscoveryError("REQUEST_DISCOVERY_SCOPE")
    execution = request.get("execution", {})
    if execution.get("receipt_path") != RECEIPT_REL or execution.get("controller_path") != PACKAGE_REL + "/controller.py":
        raise DiscoveryError("REQUEST_EXECUTION_SCOPE")
    if set(execution.get("evidence_paths", [])) != {RECEIPT_REL, EVIDENCE_REL}:
        raise DiscoveryError("REQUEST_EVIDENCE_SCOPE")
    for relative in (RECEIPT_REL, EVIDENCE_REL):
        current = root
        for part in pathlib.PurePosixPath(relative).parts:
            current = current / part
            if current.is_symlink():
                raise DiscoveryError("LOCAL_SYMLINK_FORBIDDEN")
        if current.exists():
            raise DiscoveryError("DISCOVERY_OUTPUT_EXISTS")
    prior, prior_raw = read_local_json(root, STAGE1_RECEIPT_REL)
    if prior.get("task_id") != STAGE1_ID or prior.get("status") != "FINISHED" or prior.get("tests") != "PASS":
        raise DiscoveryError("STAGE1_PREREQUISITE_FAILED")
    return request_sha, run_id, sha(prior_raw)


def remote_stage1_summary(raw):
    if len(raw) > MAX_RECEIPT_BYTES:
        raise DiscoveryError("STAGE1_REMOTE_SIZE")
    try:
        receipt = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise DiscoveryError("STAGE1_REMOTE_JSON") from None
    if not isinstance(receipt, dict) or receipt.get("task_id") != STAGE1_ID or receipt.get("status") != "PASS":
        raise DiscoveryError("STAGE1_REMOTE_PREREQUISITE")
    if any(receipt.get(key) is not False for key in ("site_write", "publisher_write", "stage2_touched")):
        raise DiscoveryError("STAGE1_REMOTE_SCOPE")
    db = receipt.get("db")
    if not isinstance(db, dict) or db.get("column") != "price_georgia" or db.get("live_transaction_write_readback") != "PASS" or db.get("rollback_to_original") != "PASS":
        raise DiscoveryError("STAGE1_REMOTE_TESTS")
    result = {"path": STAGE1_REMOTE_RECEIPT, "sha256": sha(raw), "task_id": STAGE1_ID,
              "status": "PASS", "historical_transaction_write_readback": "PASS",
              "historical_rollback": "PASS", "live_schema_verification": "NOT_PERFORMED"}
    for kind in ("before_sha256", "after_sha256"):
        hashes = receipt.get(kind, {})
        value = hashes.get("/home/Carix/cars_ui.py") if isinstance(hashes, dict) else None
        if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value):
            result[kind] = {"/home/Carix/cars_ui.py": value}
    return result


def write_new_json(root, relative, value):
    # Fixed output locations, no replacement of existing evidence or receipts.
    if relative not in (EVIDENCE_REL, RECEIPT_REL):
        raise DiscoveryError("OUTPUT_SCOPE")
    path = root / relative
    parent = root
    for part in pathlib.PurePosixPath(relative).parts[:-1]:
        parent = parent / part
        if parent.is_symlink():
            raise DiscoveryError("OUTPUT_SYMLINK")
        parent.mkdir(exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=parent, prefix=".discovery-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError:
        raise DiscoveryError("OUTPUT_ALREADY_EXISTS") from None
    finally:
        os.unlink(temporary)


def execute(env: Mapping[str, str], *, root=None, api=None):
    root = ROOT if root is None else pathlib.Path(root).resolve()
    request_sha, run_id, stage1_sha = validate_identity(env, root)
    api = ReadOnlyAPI(env.get("PYTHONANYWHERE_API_TOKEN", "")) if api is None else api
    stage1 = remote_stage1_summary(api.read(STAGE1_REMOTE_RECEIPT))
    backups = [api.backup_exists(path) for path in BACKUP_PATHS]
    sources = {path: inspect_source(api.read(path), path) for path in SOURCE_PATHS}
    # Double GET proves these four source snapshots remained stable during this
    # read window; it cannot prove the running bot has imported those bytes.
    for path in SOURCE_PATHS:
        if sha(api.read(path)) != sources[path]["sha256"]:
            raise DiscoveryError("SOURCE_CHANGED_DURING_DISCOVERY")
    if sha(api.read(STAGE1_REMOTE_RECEIPT)) != stage1["sha256"]:
        raise DiscoveryError("STAGE1_RECEIPT_CHANGED_DURING_DISCOVERY")
    finished = now()
    evidence = {"task_id": TASK_ID, "scope": "GET_ONLY_DISCOVERY", "status": "COMPLETED",
                "run_id": run_id, "request_sha256": request_sha, "finished_at": finished,
                "target_environment": "shadow", "live_source_environment": "production",
                "stage1_durable_prerequisite": {"path": STAGE1_RECEIPT_REL, "sha256": stage1_sha,
                                                "status": "FINISHED", "tests": "PASS"},
                "stage1_remote_receipt": stage1, "stage1_backup_existence": backups,
                "sources": sources, "source_snapshot_consistency": "PASS",
                "http_methods": ["GET"], "remote_get_count": api.get_count,
                "remote_response_body_bytes": api.response_body_bytes, "remote_write_count": 0,
                "database_bytes_exported": 0, "stage2_acceptance": "NOT_PERFORMED",
                "telegram_ui": "NOT_VERIFIED", "current_database_schema": "NOT_VERIFIED",
                "price_readback": "NOT_PERFORMED", "cross_write_tests": "NOT_PERFORMED",
                "controlled_price_rollback": "NOT_PERFORMED", "live_process_inspection": "NOT_PERFORMED"}
    receipt = {"task_id": TASK_ID, "status": "FINISHED", "task_class": "STANDARD",
               "target_environment": "shadow", "live_source_environment": "production",
               "tests": "PASS", "tests_scope": "DISCOVERY_IDENTITY_PREREQUISITE_GET_SCOPE_AND_SOURCE_CONSISTENCY",
               "unexpected_changes": 0, "rollback_ready": True,
               "rollback_ready_scope": "NO_REMOTE_WRITES_LOCAL_DISCOVERY_ARTIFACTS_ONLY",
               "production_required": False, "request_sha256": request_sha,
               "run_id": run_id, "scope": "GET_ONLY_DISCOVERY", "remote_write_count": 0,
               "stage2_status": "NOT_PERFORMED", "stage2_acceptance": "NOT_PERFORMED",
               "crm_price_acceptance": "NOT_PERFORMED", "finished_at": finished,
               "completion_meaning": "READ_ONLY_DISCOVERY_ONLY",
               "evidence_path": EVIDENCE_REL}
    write_new_json(root, EVIDENCE_REL, evidence)
    write_new_json(root, RECEIPT_REL, receipt)
    return receipt


if __name__ == "__main__":
    try:
        execute(os.environ)
    except Exception as exc:
        # No traceback, request URLs, response bodies, or credential values.
        code = str(exc) if isinstance(exc, DiscoveryError) and re.fullmatch(r"[A-Z0-9_]+", str(exc)) else "UNEXPECTED_ERROR"
        print("DISCOVERY_STOP:" + code)
        raise SystemExit(1) from None
