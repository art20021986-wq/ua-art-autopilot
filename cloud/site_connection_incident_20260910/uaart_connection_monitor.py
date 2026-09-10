#!/usr/bin/env python3
"""Read-only UA ART connection monitor. No reloads, writes to hosts, or alerts.

Only local JSON evidence is written. Run as a script for bounded subprocess probes;
the public functions accept stubs for deterministic, network-free tests.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener
import uuid


MAX_HTML_BYTES = 1_048_576
MIN_HTML_BYTES = 500
ALLOWED_HOSTS = frozenset({"uaart.com.ua", "www.uaart.com.ua"})


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str
    expected_final_url: str


ENDPOINTS = (
    Endpoint("apex_root", "https://uaart.com.ua/", "https://www.uaart.com.ua/video/index.html"),
    Endpoint("www_root", "https://www.uaart.com.ua/", "https://www.uaart.com.ua/video/index.html"),
    Endpoint("homepage", "https://www.uaart.com.ua/video/index.html", "https://www.uaart.com.ua/video/index.html"),
    Endpoint("catalog", "https://www.uaart.com.ua/video/katalog.html", "https://www.uaart.com.ua/video/katalog.html"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def url_identity(url: str) -> tuple:
    parsed = urlsplit(url)
    return parsed.scheme, parsed.hostname, parsed.port or 443, parsed.path or "/", parsed.username, parsed.password


class RedirectPolicyError(Exception):
    pass


class MonitorAlreadyRunning(Exception):
    pass


def has_site_title(body: bytes) -> bool:
    match = re.search(rb"<title\b[^>]*>(.*?)</title\s*>", body, re.I | re.S)
    if match is None:
        return False
    title = html.unescape(match.group(1).decode("utf-8", errors="replace"))
    return re.search(r"\bUA\s+ART\b", title, re.I) is not None


class SafeRedirectHandler(HTTPRedirectHandler):
    max_repeats = 2
    max_redirections = 6

    def __init__(self):
        super().__init__()
        self.history: list[dict] = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.history.append({"status": code, "from": req.full_url, "to": newurl})
        target = urlsplit(newurl)
        if (target.scheme != "https" or target.hostname not in ALLOWED_HOSTS
                or target.port not in (None, 443) or target.username or target.password):
            raise RedirectPolicyError("Redirect leaves the permitted HTTPS hostnames")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def result_base(endpoint: Endpoint) -> dict:
    return {"endpoint": endpoint.name, "requested_url": endpoint.url,
            "expected_final_url": endpoint.expected_final_url, "ok": False,
            "category": "not_started", "started_at": utc_now()}


def probe_once(endpoint: Endpoint, timeout: float = 20, *, opener=None) -> dict:
    """Validate transport, redirects and a bounded HTML response.

    The production caller uses a subprocess deadline; urllib's socket timeout by
    itself does not bound DNS resolution or the total duration of multiple reads.
    """
    if endpoint not in ENDPOINTS:
        raise ValueError("Only the four fixed public UA ART endpoints are permitted")
    started = time.monotonic()
    result = result_base(endpoint)
    redirect_handler = SafeRedirectHandler()
    if opener is None:
        opener = build_opener(redirect_handler, HTTPSHandler(context=ssl.create_default_context()))
    parts = urlsplit(endpoint.url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("uaart_probe", uuid.uuid4().hex))
    probe_url = urlunsplit(parts._replace(query=urlencode(query)))
    request = Request(probe_url, headers={
        "User-Agent": "UA-ART-Connection-Monitor/1.0",
        "Accept": "text/html", "Accept-Encoding": "identity",
        "Cache-Control": "no-cache, max-age=0", "Pragma": "no-cache",
    })
    result["probe_url"] = probe_url
    try:
        with opener.open(request, timeout=timeout) as response:
            status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            result.update(http_status=status, final_url=final_url, content_type=content_type)
            if status != 200:
                result.update(category="http_error", error=f"Expected HTTP 200, received {status}")
            elif url_identity(final_url) != url_identity(endpoint.expected_final_url):
                result.update(category="unexpected_destination", error="Final HTTPS hostname or path does not match the expected page")
            elif content_type.split(";", 1)[0].strip().lower() not in ("text/html", "application/xhtml+xml"):
                result.update(category="unexpected_content_type", error="Response is not HTML")
            else:
                body = response.read(MAX_HTML_BYTES + 1)
                result["bytes_read"] = len(body)
                if not MIN_HTML_BYTES <= len(body) <= MAX_HTML_BYTES:
                    result.update(category="invalid_body_size", error=f"HTML must be {MIN_HTML_BYTES}..{MAX_HTML_BYTES} bytes")
                elif not re.search(rb"<html(?:\s|>)", body, re.I):
                    result.update(category="invalid_html", error="Missing HTML document element")
                elif not has_site_title(body):
                    result.update(category="unexpected_page", error="HTML title does not contain UA ART branding")
                else:
                    result.update(ok=True, category="healthy", sha256=hashlib.sha256(body).hexdigest())
    except RedirectPolicyError as exc:
        result.update(category="unsafe_redirect", error=str(exc))
    except HTTPError as exc:
        result.update(category="http_error", http_status=exc.code, error=str(exc))
        exc.close()
    except (ssl.SSLError, URLError) as exc:
        reason = exc.reason if isinstance(exc, URLError) else exc
        if isinstance(reason, ssl.SSLError):
            category = "tls_error"
        elif isinstance(reason, (TimeoutError,)):
            category = "timeout"
        else:
            category = "connection_error"
        result.update(category=category, error=str(reason))
    except TimeoutError as exc:
        result.update(category="timeout", error=str(exc))
    except Exception as exc:
        result.update(category="probe_error", error=f"{type(exc).__name__}: {exc}")
    finally:
        result["redirects"] = redirect_handler.history
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["finished_at"] = utc_now()
    return result


def isolated_probe(endpoint: Endpoint, timeout: float) -> dict:
    """Hard wall-clock deadline, including DNS, TLS, redirects and body reads."""
    started = time.monotonic()
    result = result_base(endpoint)
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--_probe-json", json.dumps(asdict(endpoint)),
             "--timeout", str(timeout)], capture_output=True, text=True, timeout=timeout, check=False,
        )
        if completed.returncode != 0:
            result.update(category="probe_error", error=f"Probe subprocess exited {completed.returncode}")
        else:
            result = json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        result.update(category="timeout", error=f"Probe exceeded {timeout:g}s wall-clock deadline")
    except Exception as exc:
        result.update(category="probe_error", error=f"{type(exc).__name__}: {exc}")
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["finished_at"] = utc_now()
    return result


def write_evidence(path: Path, report: dict) -> None:
    """Replace the evidence atomically after startup, every round, and completion."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            temp_name = handle.name
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        Path(temp_name).replace(path)
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def run_monitor(evidence_path: Path, *, endpoints=ENDPOINTS, attempts=3,
                timeout=20.0, retry_delay=15.0, probe: Callable = isolated_probe,
                sleep: Callable = time.sleep) -> dict:
    if not endpoints or not 1 <= attempts <= 3 or not 0 < timeout <= 20 or retry_delay < 0:
        raise ValueError("Require endpoints, 1..3 attempts, 0 < timeout <= 20, and nonnegative retry delay")
    report = {"schema_version": 1, "check_id": uuid.uuid4().hex, "started_at": utc_now(),
              "status": "running", "exit_code": 3, "rounds": [],
              "settings": {"max_attempts": attempts, "probe_timeout_seconds": timeout,
                           "retry_delay_seconds": retry_delay, "method": "GET",
                           "tls_verification": True, "max_html_bytes": MAX_HTML_BYTES,
                           "network_scope": "four_public_https_pages", "read_only": True}}
    write_evidence(evidence_path, report)
    try:
        for attempt in range(1, attempts + 1):
            round_result = {"attempt": attempt, "started_at": utc_now(), "results": []}
            with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
                futures = [(endpoint, pool.submit(probe, endpoint, timeout)) for endpoint in endpoints]
                for endpoint, future in futures:
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = result_base(endpoint)
                        result.update(category="probe_error", error=f"{type(exc).__name__}: {exc}")
                    round_result["results"].append(result)
            round_result["finished_at"] = utc_now()
            round_result["ok"] = all(result["ok"] for result in round_result["results"])
            report["rounds"].append(round_result)
            write_evidence(evidence_path, report)
            if round_result["ok"]:
                report.update(status="healthy" if attempt == 1 else "recovered_transient", exit_code=0)
                break
            if attempt < attempts:
                sleep(retry_delay)
        else:
            report.update(status="persistent_failure", exit_code=2)
    except KeyboardInterrupt:
        report.update(status="interrupted", exit_code=130)
    except Exception as exc:
        report.update(status="monitor_error", exit_code=3, error=f"{type(exc).__name__}: {exc}")
    finally:
        report["finished_at"] = utc_now()
        write_evidence(evidence_path, report)
    return report


@contextmanager
def monitor_lock(evidence_path: Path):
    """Keep a nonblocking POSIX process lock for the entire watch session."""
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with (evidence_path.parent / ".uaart-monitor.lock").open("a") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise MonitorAlreadyRunning("A monitor already holds this evidence-directory lock") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def run_watch(evidence_path: Path, *, interval=300.0, monitor: Callable = run_monitor,
              sleep: Callable = time.sleep, emit: Callable | None = None,
              max_cycles: int | None = None, **monitor_kwargs) -> int:
    """Run read-only cycles; retain latest state and one latest incident only.

    The interval starts after a completed cycle. max_cycles is a deterministic
    test seam, not a CLI argument. No reload, messaging or additional endpoints.
    """
    if interval <= 0 or (max_cycles is not None and max_cycles < 1):
        raise ValueError("Require a positive interval and positive max_cycles")
    if evidence_path.name in ("last_incident.json", ".uaart-monitor.lock"):
        raise ValueError("Evidence path conflicts with a reserved watch-mode file")
    if emit is None:
        emit = lambda line: print(line, flush=True)
    incident_path = evidence_path.parent / "last_incident.json"
    try:
        with monitor_lock(evidence_path):
            cycles = 0
            while True:
                report = monitor(evidence_path, **monitor_kwargs)
                if report["status"] != "healthy":
                    write_evidence(incident_path, report)
                emit(f"{utc_now()} {report['status'].upper()}")
                cycles += 1
                if report["exit_code"] == 130 or (max_cycles is not None and cycles >= max_cycles):
                    return report["exit_code"]
                sleep(interval)
    except KeyboardInterrupt:
        return 130


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, default=Path("artifacts/uaart-connection-monitor.json"))
    parser.add_argument("--attempts", type=int, choices=range(1, 4), default=3)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--retry-delay", type=float, default=15)
    parser.add_argument("--watch", action="store_true", help="Keep checking public pages; no server reloads or notifications")
    parser.add_argument("--interval", type=float, default=300, help="Seconds to wait after each watch cycle (default: 300)")
    parser.add_argument("--_probe-json", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args._probe_json is not None:
        print(json.dumps(probe_once(Endpoint(**json.loads(args._probe_json)), args.timeout)))
        return 0
    if args.watch:
        try:
            return run_watch(args.evidence, interval=args.interval, attempts=args.attempts,
                             timeout=args.timeout, retry_delay=args.retry_delay)
        except MonitorAlreadyRunning as exc:
            print(f"ALREADY_RUNNING: {exc}", flush=True)
            return 4
    report = run_monitor(args.evidence, attempts=args.attempts, timeout=args.timeout, retry_delay=args.retry_delay)
    print(f"{report['status'].upper()}: {len(report['rounds'])} round(s); evidence: {args.evidence}")
    for round_result in report["rounds"]:
        for result in round_result["results"]:
            if not result["ok"]:
                print(f"Attempt {round_result['attempt']}: {result['endpoint']}: {result['category']}")
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
