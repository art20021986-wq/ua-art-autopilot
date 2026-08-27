#!/usr/bin/env python3
# UA ART autonomous Claude bridge: GitHub task -> Claude API -> cloud outputs
from __future__ import annotations

import datetime as dt
import hashlib
import http.client
import json
import os
import pathlib
import re
import socket
import tempfile
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
CLOUD = ROOT / "cloud"
CLOUD.mkdir(exist_ok=True)

DEFAULT_MODEL = "claude-sonnet-5"
DEFAULT_MAX_TOKENS = 64_000
MAX_ALLOWED_TOKENS = 128_000
DEFAULT_TIMEOUT_SECONDS = 1_200
DEFAULT_TOTAL_BUDGET_SECONDS = 1_500
DEFAULT_NETWORK_ATTEMPTS = 4
MAX_NETWORK_ATTEMPTS = 8
MAX_FILES = 20
MAX_TOTAL_FILE_CHARS = 4_000_000
STATUS_REL = "cloud/latest_status.md"
OWNER_REPLY_REL = "cloud/owner_reply.md"
MEMORY_ROOT = CLOUD / "shared_memory"
MAX_MEMORY_FILE_BYTES = 2_000_000
MEMORY_AUTHORITY_LEVELS = [
    "OWNER_DIRECTIVE",
    "OWNER_APPROVAL",
    "VERIFIED_PRODUCTION",
    "VERIFIED_CRM",
    "CANONICAL_GITHUB",
    "AUTOMATED_EVIDENCE",
    "AI_REPORT",
    "HYPOTHESIS",
]
MEMORY_EXCLUSIVE_CLASSES = {"DECISION", "OWNER_DIRECTIVE", "APPROVAL", "FACT"}

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "files": {
            "type": "array",
            "description": (
                "Complete UTF-8 deliverables. Every path must start with cloud/. "
                "Use one object per file and include the full file content."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative repository path starting with cloud/.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete UTF-8 file content, not a patch or excerpt.",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        "status": {
            "type": "string",
            "enum": ["DONE", "BLOCKED", "WAITING_OWNER"],
        },
        "summary": {"type": "string"},
        "owner_action_required": {
            "type": "string",
            "enum": ["YES", "NO"],
        },
        "owner_question": {"type": "string"},
    },
    "required": [
        "files",
        "status",
        "summary",
        "owner_action_required",
        "owner_question",
    ],
    "additionalProperties": False,
}


def latest_task() -> pathlib.Path:
    files = sorted(TASKS.glob("task_*.md"))
    if not files:
        raise SystemExit("NO_TASK")
    return files[-1]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _read_memory_file(memory_root: pathlib.Path, rel: str) -> bytes:
    pure = pathlib.PurePosixPath(rel)
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise SystemExit(f"SHARED_MEMORY_UNSAFE_PATH:{rel}")

    root = memory_root.resolve(strict=True)
    candidate = memory_root.joinpath(*pure.parts)
    if candidate.is_symlink() or not candidate.is_file():
        raise SystemExit(f"SHARED_MEMORY_NOT_REGULAR:{rel}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise SystemExit(f"SHARED_MEMORY_PATH_ESCAPE:{rel}")
    size = candidate.stat().st_size
    if size > MAX_MEMORY_FILE_BYTES:
        raise SystemExit(f"SHARED_MEMORY_FILE_TOO_LARGE:{rel}:{size}")
    return candidate.read_bytes()


def load_shared_memory_context(memory_root: pathlib.Path = MEMORY_ROOT) -> dict:
    """Verify canonical managed-file hashes, then build a deterministic context."""
    if memory_root.is_symlink() or not memory_root.is_dir():
        raise SystemExit("SHARED_MEMORY_ROOT_INVALID")

    try:
        manifest = json.loads(_read_memory_file(memory_root, "manifest.json"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit("SHARED_MEMORY_MANIFEST_INVALID") from exc
    if not isinstance(manifest, dict):
        raise SystemExit("SHARED_MEMORY_MANIFEST_NOT_OBJECT")

    memory_version = manifest.get("memory_version")
    managed = manifest.get("managed_files")
    hashes = manifest.get("file_hashes")
    if not isinstance(memory_version, int) or memory_version < 1:
        raise SystemExit("SHARED_MEMORY_VERSION_INVALID")
    if manifest.get("canonical_branch") != "main":
        raise SystemExit("SHARED_MEMORY_BRANCH_INVALID")
    if not isinstance(managed, list) or not managed or len(managed) != len(set(managed)):
        raise SystemExit("SHARED_MEMORY_MANAGED_FILES_INVALID")
    if not isinstance(hashes, dict):
        raise SystemExit("SHARED_MEMORY_HASHES_INVALID")

    required = {"records.jsonl", "state/current_status.json"}
    if not required.issubset(set(managed)):
        raise SystemExit("SHARED_MEMORY_REQUIRED_FILES_MISSING")

    verified: dict[str, bytes] = {}
    for rel in managed:
        if not isinstance(rel, str):
            raise SystemExit("SHARED_MEMORY_MANAGED_PATH_INVALID")
        expected = hashes.get(rel)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise SystemExit(f"SHARED_MEMORY_EXPECTED_HASH_INVALID:{rel}")
        payload = _read_memory_file(memory_root, rel)
        actual = hashlib.sha256(payload).hexdigest()
        if actual != expected:
            raise SystemExit(f"SHARED_MEMORY_HASH_MISMATCH:{rel}")
        verified[rel] = payload

    records = []
    try:
        records_text = verified["records.jsonl"].decode("utf-8")
        for line_number, line in enumerate(records_text.splitlines(), 1):
            if not line.strip():
                continue
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"record {line_number} is not an object")
            records.append(record)
        current_status = json.loads(
            verified["state/current_status.json"].decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit("SHARED_MEMORY_CONTENT_INVALID") from exc
    if not records or not isinstance(current_status, dict):
        raise SystemExit("SHARED_MEMORY_CONTENT_EMPTY")

    for record in records:
        for field in ("record_id", "record_class", "subject", "authority"):
            if not isinstance(record.get(field), str) or not record[field]:
                raise SystemExit(f"SHARED_MEMORY_RECORD_FIELD_INVALID:{field}")
        if record["authority"] not in MEMORY_AUTHORITY_LEVELS:
            raise SystemExit("SHARED_MEMORY_RECORD_AUTHORITY_INVALID")

    superseded_ids = {
        record["supersedes"] for record in records if record.get("supersedes")
    }
    active_groups: dict[tuple[str, str], list[str]] = {}
    for record in records:
        if record["record_id"] in superseded_ids:
            continue
        key = (record["subject"], record["record_class"])
        active_groups.setdefault(key, []).append(record["record_id"])

    view = {}
    for record in records:
        record_id = record["record_id"]
        if record_id in superseded_ids:
            view[record_id] = "SUPERSEDED"
            continue
        key = (record["subject"], record["record_class"])
        if (
            record["record_class"] in MEMORY_EXCLUSIVE_CLASSES
            and len(active_groups.get(key, [])) > 1
        ):
            view[record_id] = "CONFLICT"
        else:
            view[record_id] = "ACTIVE"

    selected = [
        record for record in records if view[record["record_id"]] in {"ACTIVE", "CONFLICT"}
    ]
    selected.sort(
        key=lambda record: (
            MEMORY_AUTHORITY_LEVELS.index(record["authority"]),
            record["record_id"],
        )
    )
    enriched = [
        dict(record, computed_status=view[record["record_id"]]) for record in selected
    ]
    bundle = {
        "memory_version_read": memory_version,
        "canonical_branch": "main",
        "subject_filter": None,
        "records": enriched,
    }
    digest = hashlib.sha256(
        json.dumps(bundle, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "MEMORY_VERSION_READ": memory_version,
        "CONTEXT_BUNDLE_SHA256": digest,
        "bundle": bundle,
        "CURRENT_STATUS": current_status,
    }


def _clean_log_value(value: object, limit: int = 500) -> str:
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or "")).strip()
    text = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED]", text)
    return text[:limit]


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"INVALID_{name}") from exc
    if not minimum <= value <= maximum:
        raise SystemExit(f"INVALID_{name}_RANGE:{minimum}-{maximum}")
    return value


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    request_id = _clean_log_value(exc.headers.get("request-id", "NONE"), 120)
    error_type = "unknown"
    message = exc.reason or "HTTP error"
    try:
        body = exc.read().decode("utf-8", "replace")
        parsed = json.loads(body)
        error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
        if isinstance(error, dict):
            error_type = error.get("type", error_type)
            message = error.get("message", message)
    except Exception:
        pass
    return (
        f"ANTHROPIC_HTTP_ERROR status={exc.code} "
        f"type={_clean_log_value(error_type, 120)} "
        f"message={_clean_log_value(message)} request_id={request_id}"
    )


def _validate_result(result: object) -> dict:
    if not isinstance(result, dict):
        raise SystemExit("CLAUDE_RESULT_NOT_OBJECT")

    files = result.get("files")
    if not isinstance(files, list):
        raise SystemExit("CLAUDE_FILES_NOT_ARRAY")
    if len(files) > MAX_FILES:
        raise SystemExit(f"CLAUDE_TOO_MANY_FILES:{len(files)}")

    normalized_files = []
    seen = set()
    total_chars = 0
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise SystemExit(f"CLAUDE_FILE_ITEM_NOT_OBJECT:{index}")
        path = item.get("path")
        content = item.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            raise SystemExit(f"CLAUDE_FILE_ITEM_INVALID:{index}")
        if path in seen:
            raise SystemExit(f"CLAUDE_DUPLICATE_PATH:{path}")
        seen.add(path)
        total_chars += len(content)
        normalized_files.append({"path": path, "content": content})

    if total_chars > MAX_TOTAL_FILE_CHARS:
        raise SystemExit(f"CLAUDE_OUTPUT_TOO_LARGE:{total_chars}")

    status = str(result.get("status", "BLOCKED")).upper()
    if status not in {"DONE", "BLOCKED", "WAITING_OWNER"}:
        raise SystemExit(f"CLAUDE_STATUS_INVALID:{_clean_log_value(status, 80)}")

    owner_action = str(result.get("owner_action_required", "NO")).upper()
    if owner_action not in {"YES", "NO"}:
        raise SystemExit(
            f"CLAUDE_OWNER_ACTION_INVALID:{_clean_log_value(owner_action, 80)}"
        )

    summary = result.get("summary")
    owner_question = result.get("owner_question")
    if not isinstance(summary, str) or not isinstance(owner_question, str):
        raise SystemExit("CLAUDE_TEXT_FIELDS_INVALID")
    if status == "DONE" and not normalized_files:
        raise SystemExit("CLAUDE_DONE_WITHOUT_FILES")

    return {
        "files": normalized_files,
        "status": status,
        "summary": summary,
        "owner_action_required": owner_action,
        "owner_question": owner_question,
    }


def call_claude(system_text: str, task_text: str) -> dict:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY_MISSING")

    model = (os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()
    effort = (os.environ.get("ANTHROPIC_EFFORT") or "medium").strip().lower()
    if effort not in {"low", "medium", "high", "xhigh", "max"}:
        raise SystemExit("INVALID_ANTHROPIC_EFFORT")

    max_tokens = _env_int(
        "ANTHROPIC_MAX_TOKENS",
        DEFAULT_MAX_TOKENS,
        minimum=4_096,
        maximum=MAX_ALLOWED_TOKENS,
    )
    timeout_seconds = _env_int(
        "ANTHROPIC_TIMEOUT_SECONDS",
        DEFAULT_TIMEOUT_SECONDS,
        minimum=60,
        maximum=3_600,
    )
    total_budget_seconds = _env_int(
        "ANTHROPIC_TOTAL_BUDGET_SECONDS",
        DEFAULT_TOTAL_BUDGET_SECONDS,
        minimum=300,
        maximum=1_800,
    )
    network_attempts = _env_int(
        "ANTHROPIC_NETWORK_ATTEMPTS",
        DEFAULT_NETWORK_ATTEMPTS,
        minimum=1,
        maximum=MAX_NETWORK_ATTEMPTS,
    )

    instruction = (
        task_text
        + "\n\nProduce the complete task deliverables as a structured response. "
        + "The files field is an array of objects with path and full content. "
        + "Every path must start with cloud/. Include every deliverable named in the task, "
        + "including cloud/latest_status.md. Do not return patches, excerpts, placeholders, "
        + "or markdown fences around the outer response. Never propose or perform production "
        + "writes. Never include secrets, tokens, private keys, unrelated customer PII, or "
        + "database blobs/base64 payloads."
    )
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_text,
        "messages": [{"role": "user", "content": instruction}],
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA},
        },
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            "user-agent": "ua-art-autopilot/2",
        },
        method="POST",
    )

    transient_error = None
    deadline = time.monotonic() + total_budget_seconds
    for attempt in range(1, network_attempts + 1):
        remaining_seconds = int(deadline - time.monotonic())
        if remaining_seconds <= 0:
            raise SystemExit("ANTHROPIC_TOTAL_BUDGET_EXHAUSTED")
        attempt_timeout = max(1, min(timeout_seconds, remaining_seconds))
        try:
            print(
                f"ANTHROPIC_ATTEMPT attempt={attempt}/{network_attempts} "
                f"timeout_seconds={attempt_timeout} "
                f"remaining_budget_seconds={remaining_seconds}"
            )
            with urllib.request.urlopen(request, timeout=attempt_timeout) as response:
                request_id = response.headers.get("request-id", "NONE")
                data = json.load(response)
            transient_error = None
            break
        except urllib.error.HTTPError as exc:
            error_message = _http_error_message(exc)
            is_transient = exc.code in {408, 409, 425, 429} or 500 <= exc.code <= 599
            remaining_after_error = int(deadline - time.monotonic())
            if remaining_after_error <= 1:
                raise SystemExit("ANTHROPIC_TOTAL_BUDGET_EXHAUSTED") from exc
            if (
                not is_transient
                or attempt >= network_attempts
            ):
                raise SystemExit(error_message) from exc
            delay = min(60, 5 * (2 ** (attempt - 1)), remaining_after_error - 1)
            print(
                f"ANTHROPIC_TRANSIENT_HTTP_RETRY "
                f"attempt={attempt}/{network_attempts} "
                f"delay_seconds={delay} "
                f"error={_clean_log_value(error_message)}"
            )
            time.sleep(delay)
        except json.JSONDecodeError as exc:
            raise SystemExit("ANTHROPIC_RESPONSE_NOT_JSON") from exc
        except (
            urllib.error.URLError,
            TimeoutError,
            socket.timeout,
            http.client.RemoteDisconnected,
            http.client.IncompleteRead,
            http.client.BadStatusLine,
            ConnectionResetError,
            BrokenPipeError,
        ) as exc:
            transient_error = exc
            remaining_after_error = int(deadline - time.monotonic())
            if remaining_after_error <= 1:
                raise SystemExit("ANTHROPIC_TOTAL_BUDGET_EXHAUSTED") from exc
            if attempt >= network_attempts:
                reason = getattr(exc, "reason", exc)
                raise SystemExit(
                    f"ANTHROPIC_NETWORK_ERROR_AFTER_RETRIES:"
                    f"{_clean_log_value(reason)}"
                ) from exc
            delay = min(60, 5 * (2 ** (attempt - 1)), remaining_after_error - 1)
            print(
                f"ANTHROPIC_TRANSIENT_RETRY "
                f"attempt={attempt}/{network_attempts} "
                f"delay_seconds={delay} "
                f"error={_clean_log_value(exc)}"
            )
            time.sleep(delay)
    if transient_error is not None:
        raise SystemExit("ANTHROPIC_NETWORK_ERROR_AFTER_RETRIES")

    content = data.get("content", []) if isinstance(data, dict) else []
    if not isinstance(content, list):
        content = []
    content_types = [
        block.get("type", "unknown")
        for block in content
        if isinstance(block, dict)
    ]
    text = "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()
    stop_reason = data.get("stop_reason", "unknown") if isinstance(data, dict) else "unknown"
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    if not isinstance(usage, dict):
        usage = {}
    diagnostics = (
        f"stop_reason={_clean_log_value(stop_reason, 80)} "
        f"content_types={','.join(map(str, content_types)) or 'NONE'} "
        f"text_chars={len(text)} "
        f"input_tokens={usage.get('input_tokens', 'UNKNOWN')} "
        f"output_tokens={usage.get('output_tokens', 'UNKNOWN')} "
        f"request_id={_clean_log_value(request_id, 120)}"
    )
    print("CLAUDE_RESPONSE " + diagnostics)

    if stop_reason == "max_tokens":
        raise SystemExit("CLAUDE_OUTPUT_TRUNCATED " + diagnostics)
    if stop_reason == "refusal":
        stop_details = data.get("stop_details", {}) if isinstance(data, dict) else {}
        category = stop_details.get("category", "unknown") if isinstance(stop_details, dict) else "unknown"
        raise SystemExit(
            "CLAUDE_REFUSAL category=" + _clean_log_value(category, 120) + " " + diagnostics
        )
    if not text:
        raise SystemExit("CLAUDE_TEXT_MISSING " + diagnostics)

    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"CLAUDE_JSON_INVALID line={exc.lineno} col={exc.colno} " + diagnostics
        ) from exc
    return _validate_result(result)


def _safe_destination(rel: str) -> pathlib.Path:
    pure = pathlib.PurePosixPath(rel)
    if pure.is_absolute() or not pure.parts or pure.parts[0] != "cloud":
        raise SystemExit(f"UNSAFE_PATH:{rel}")
    if ".." in pure.parts or pure.name in {"", ".", ".."}:
        raise SystemExit(f"UNSAFE_PATH:{rel}")

    cloud_root = CLOUD.resolve()
    destination = (ROOT / pathlib.Path(*pure.parts)).resolve(strict=False)
    if destination == cloud_root or not destination.is_relative_to(cloud_root):
        raise SystemExit(f"UNSAFE_PATH:{rel}")
    return destination


def _atomic_write(destination: pathlib.Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        delete=False,
    )
    temp_path = pathlib.Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def safe_write(files: list[dict]) -> list[str]:
    plan = []
    for item in files:
        rel = item["path"]
        plan.append((rel, _safe_destination(rel), item["content"]))

    written = []
    for rel, destination, content in plan:
        _atomic_write(destination, content)
        written.append(rel)
    return written


def required_output_paths(task_text: str) -> set[str]:
    match = re.search(
        r"(?ims)^##\s+Deliverables[^\n]*\n(.*?)(?=^##\s+|\Z)",
        task_text,
    )
    if not match:
        return {STATUS_REL, OWNER_REPLY_REL}
    discovered = set(re.findall(r"`(cloud/[A-Za-z0-9._/-]+)`", match.group(1)))
    # A task may name an output directory (for example `cloud/package/`).
    # Directories are scope declarations, not file deliverables; requiring Claude
    # to return a file whose path ends in `/` makes every otherwise-valid run fail.
    paths = {candidate for candidate in discovered if not candidate.endswith("/")}
    paths.update({STATUS_REL, OWNER_REPLY_REL})
    return paths


def static_check_python(written: list[str]) -> None:
    for rel in written:
        if not rel.endswith(".py"):
            continue
        path = _safe_destination(rel)
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, rel, "exec")
        except SyntaxError as exc:
            raise SystemExit(
                f"PYTHON_STATIC_CHECK_FAIL:{rel}:line={exc.lineno}:offset={exc.offset}"
            ) from exc
        print(f"PYTHON_STATIC_CHECK: PASS {rel}")


def write_fallback_status(task_id: str, result: dict, written: list[str]) -> str:
    rel = STATUS_REL
    files_for_status = written or ["NONE"]
    updated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    status = (
        f"TASK_ID: {task_id}\n"
        "ROUND: 1\n"
        f"CLAUDE_STATUS: {result['status']}\n"
        "CURRENT_ACTION: autonomous GitHub worker completed\n"
        f"FILES_CREATED: {','.join(files_for_status)}\n"
        "PRODUCTION_TOUCHED: NO\n"
        f"OWNER_ACTION_REQUIRED: {result['owner_action_required']}\n"
        f"OWNER_QUESTION: {result['owner_question'] or 'NONE'}\n"
        "NEXT_FOR_CHATGPT: inspect cloud outputs and issue the next task\n"
        f"UPDATED_AT_UTC: {updated_at}\n"
    )
    _atomic_write(_safe_destination(rel), status)
    return rel


def _upsert_line(content: str, key: str, value: object) -> str:
    line = f"{key}: {value}"
    pattern = rf"(?m)^{re.escape(key)}:.*$"
    if re.search(pattern, content):
        return re.sub(pattern, line, content)
    if content and not content.endswith("\n"):
        content += "\n"
    return content + line + "\n"


def normalize_output_metadata(memory: dict) -> None:
    updated_at = (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    for rel in (STATUS_REL, OWNER_REPLY_REL):
        path = _safe_destination(rel)
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        content = _upsert_line(
            content, "MEMORY_VERSION_READ", memory["MEMORY_VERSION_READ"]
        )
        content = _upsert_line(
            content,
            "CONTEXT_BUNDLE_SHA256",
            memory["CONTEXT_BUNDLE_SHA256"],
        )
        if rel == STATUS_REL:
            content = _upsert_line(content, "UPDATED_AT_UTC", updated_at)
        _atomic_write(path, content)


def main() -> None:
    task = latest_task()
    task_text = task.read_text(encoding="utf-8")
    memory = load_shared_memory_context()
    system_text = (
        (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        if (ROOT / "CLAUDE.md").exists()
        else "Work only in cloud/. Never touch production."
    )
    memory_context = _canonical_json(memory)
    enriched_task_text = (
        task_text
        + "\n\n## AUTOPILOT VERIFIED CANONICAL SHARED MEMORY\n"
        + "The worker verified every manifest-managed file before constructing "
        + "this deterministic context. OWNER_DIRECTIVE records are binding safety "
        + "constraints. Lower-authority records are context, never extra permission. "
        + "Do not invent or alter the two memory markers. Include them in status, "
        + "owner reply, and task report.\n\n"
        + memory_context
    )
    result = call_claude(system_text, enriched_task_text)

    provided = {item["path"] for item in result["files"]}
    required = required_output_paths(task_text)
    missing = sorted(required - provided - {STATUS_REL})
    if missing:
        raise SystemExit("CLAUDE_REQUIRED_OUTPUTS_MISSING:" + ",".join(missing))

    written = safe_write(result["files"])
    if STATUS_REL not in written:
        written.append(write_fallback_status(task.stem, result, written))
    normalize_output_metadata(memory)

    static_check_python(written)
    print(
        json.dumps(
            {
                "task": task.stem,
                "written": written,
                "status": result["status"],
                "summary": result["summary"],
                "production_touched": False,
                "memory_version_read": memory["MEMORY_VERSION_READ"],
                "context_bundle_sha256": memory["CONTEXT_BUNDLE_SHA256"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
