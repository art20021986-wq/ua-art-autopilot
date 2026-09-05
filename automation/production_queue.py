#!/usr/bin/env python3
"""Fair, observable queue gate for UA ART production workflows.

Retries keep the same numeric task ticket, so a newer retry cannot repeatedly
push an older production task to the back of the queue.  A one-time
``--drain-before`` cut-over lets a newly installed gate safely wait for writers
that were already active before every workflow used the shared coordinator.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import time
import urllib.request


ACTIVE_STATES = {"queued", "in_progress", "pending", "requested", "waiting"}
PRODUCTION_MARKERS = (
    "production",
    "gate_b",
    "gate b",
    "deploy",
    "catalog_dedup",
    "catalog-dedup",
    "uaart_critical",
    "critical pipeline",
)
TASK_PATTERN = re.compile(r"(?i)task[_ -]?0*(\d+)")


def parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def task_number(run: dict) -> int | None:
    for value in (run.get("name"), run.get("path"), run.get("display_title")):
        match = TASK_PATTERN.search(str(value or ""))
        if match:
            return int(match.group(1))
    return None


def is_production_run(run: dict) -> bool:
    folded = " ".join(
        str(run.get(field) or "").casefold()
        for field in ("path", "name", "display_title")
    )
    return any(marker in folded for marker in PRODUCTION_MARKERS)


def _run_order(run: dict) -> tuple[dt.datetime, int]:
    created = parse_timestamp(run.get("created_at")) or dt.datetime.max.replace(
        tzinfo=dt.timezone.utc
    )
    return created, int(run.get("id") or 0)


def find_blockers(
    runs: list[dict],
    *,
    current_run_id: int,
    current_task: int,
    drain_before: dt.datetime | None,
) -> list[dict]:
    current = next(
        (run for run in runs if int(run.get("id") or 0) == current_run_id),
        None,
    )
    if current is None:
        raise RuntimeError("PRODUCTION_QUEUE_CURRENT_RUN_NOT_FOUND")
    current_path = str(current.get("path") or "").casefold()
    current_order = _run_order(current)
    blockers = []

    for run in runs:
        run_id = int(run.get("id") or 0)
        if run_id == current_run_id or run.get("status") not in ACTIVE_STATES:
            continue
        if not is_production_run(run):
            continue
        path = str(run.get("path") or "").casefold()
        # GitHub's workflow concurrency already serializes repetitions of the
        # same workflow. Ignoring that path also prevents a cancel/restart
        # transition from making a workflow wait on its own replacement.
        if path and path == current_path:
            continue

        created = _run_order(run)[0]
        other_task = task_number(run)
        legacy_writer = drain_before is not None and created <= drain_before
        older_ticket = other_task is not None and other_task < current_task
        same_ticket_older_run = (
            other_task == current_task and _run_order(run) < current_order
        )
        unnumbered_older_run = other_task is None and _run_order(run) < current_order

        if legacy_writer or older_ticket or same_ticket_older_run or unnumbered_older_run:
            blockers.append(run)

    return sorted(
        blockers,
        key=lambda run: (
            task_number(run) if task_number(run) is not None else 10**9,
            _run_order(run),
        ),
    )


def fetch_runs(repository: str, token: str) -> list[dict]:
    """Fetch only active runs, without walking the repository's full history."""
    values: dict[int, dict] = {}
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "ua-art-fair-production-queue/2",
    }
    for status in sorted(ACTIVE_STATES):
        for page in range(1, 101):
            request = urllib.request.Request(
                f"https://api.github.com/repos/{repository}/actions/runs"
                f"?status={status}&per_page=100&page={page}",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                batch = list((json.load(response).get("workflow_runs") or []))
            for run in batch:
                run_id = int(run.get("id") or 0)
                if run_id:
                    values[run_id] = run
            if len(batch) < 100:
                break
        else:
            raise RuntimeError("PRODUCTION_QUEUE_ACTIVE_RUN_PAGINATION_LIMIT:" + status)
    return list(values.values())


def wait_for_turn(args: argparse.Namespace) -> None:
    token = (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip()
    repository = (
        os.environ.get("REPOSITORY") or os.environ.get("GITHUB_REPOSITORY") or ""
    ).strip()
    run_id_text = (
        os.environ.get("CURRENT_RUN_ID") or os.environ.get("GITHUB_RUN_ID") or ""
    ).strip()
    if not token or not repository or not run_id_text:
        raise SystemExit("PRODUCTION_QUEUE_ENV_MISSING")

    current_run_id = int(run_id_text)
    drain_before = parse_timestamp(args.drain_before)
    deadline = time.monotonic() + args.timeout_seconds
    stable = 0
    poll = 0

    while time.monotonic() < deadline:
        poll += 1
        runs = fetch_runs(repository, token)
        blockers = find_blockers(
            runs,
            current_run_id=current_run_id,
            current_task=args.task,
            drain_before=drain_before,
        )
        if blockers:
            stable = 0
            detail = [
                {
                    "id": int(run.get("id") or 0),
                    "task": task_number(run),
                    "name": run.get("name"),
                    "status": run.get("status"),
                    "created_at": run.get("created_at"),
                }
                for run in blockers
            ]
            print(
                "PRODUCTION_QUEUE_WAIT "
                + json.dumps(
                    {
                        "task": args.task,
                        "run_id": current_run_id,
                        "poll": poll,
                        "blockers": detail,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                flush=True,
            )
            time.sleep(args.poll_seconds)
            continue

        stable += 1
        print(
            "PRODUCTION_QUEUE_QUIET "
            + json.dumps(
                {
                    "task": args.task,
                    "run_id": current_run_id,
                    "poll": poll,
                    "stable": stable,
                    "required": args.stable_polls,
                },
                separators=(",", ":"),
            ),
            flush=True,
        )
        if stable >= args.stable_polls:
            print(
                f"PRODUCTION_QUEUE_PASS task={args.task} run_id={current_run_id}",
                flush=True,
            )
            return
        time.sleep(args.poll_seconds)

    raise SystemExit(
        f"PRODUCTION_QUEUE_TIMEOUT task={args.task} run_id={current_run_id}"
    )


def self_test() -> None:
    base = {
        "status": "in_progress",
        "created_at": "2026-08-29T09:00:00Z",
    }
    current = {
        **base,
        "id": 300,
        "name": "task083-publish-transaction-production",
        "path": ".github/workflows/task083_publish_transaction.yml",
        "created_at": "2026-08-29T09:10:00Z",
    }
    older_task = {
        **base,
        "id": 100,
        "name": "task082-production",
        "path": ".github/workflows/task082_production.yml",
    }
    newer_task = {
        **base,
        "id": 400,
        "name": "task084-production",
        "path": ".github/workflows/task084_production.yml",
        "created_at": "2026-08-29T09:11:00Z",
    }
    legacy_newer_task = {
        **newer_task,
        "id": 200,
        "created_at": "2026-08-29T08:59:00Z",
    }
    same_path = {**current, "id": 299, "created_at": "2026-08-29T09:09:00Z"}

    ids = {
        int(run["id"])
        for run in find_blockers(
            [current, older_task, newer_task, legacy_newer_task, same_path],
            current_run_id=300,
            current_task=83,
            drain_before=parse_timestamp("2026-08-29T09:00:00Z"),
        )
    }
    assert ids == {100, 200}, ids
    assert task_number(newer_task) == 84
    assert is_production_run(newer_task)
    assert not is_production_run({"name": "read-only audit", "path": "probe.yml"})
    print("PRODUCTION_QUEUE_SELF_TEST_PASS")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("self-test")
    wait = subparsers.add_parser("wait")
    wait.add_argument("--task", type=int, required=True)
    wait.add_argument("--drain-before")
    wait.add_argument("--timeout-seconds", type=int, default=4_500)
    wait.add_argument("--poll-seconds", type=int, default=15)
    wait.add_argument("--stable-polls", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "self-test":
        self_test()
    else:
        wait_for_turn(args)


if __name__ == "__main__":
    main()
