#!/usr/bin/env python3
"""TASK105 Phase 0: deterministic, read-only repository architecture audit.

The script reads the checked-out repository and writes Markdown evidence only
under cloud/task_105_fast_pipeline_phase0 plus the two canonical status files.
It never contacts production services and never mutates runtime infrastructure.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "cloud" / "task_105_fast_pipeline_phase0"
WORKFLOWS = ROOT / ".github" / "workflows"
STATUS = ROOT / "cloud" / "latest_status.md"
OWNER_REPLY = ROOT / "cloud" / "owner_reply.md"

REQUIRED_OUTPUTS = [
    "WORKFLOW_INVENTORY.md",
    "DEPENDENCY_MAP.md",
    "ROOT_CAUSE_AUDIT_TASK096.md",
    "CURRENT_STATE_MACHINE.md",
    "TARGET_ARCHITECTURE.md",
    "MIGRATION_PLAN.md",
    "RISK_REGISTER.md",
    "ACCEPTANCE_TEST_PLAN.md",
    "PHASE0_REPORT.md",
]

TARGET_PIPELINES = {
    "uaart_fast.yml": "Низкорисковые контентные, SEO и локальные UI-изменения.",
    "uaart_standard.yml": "CRM, генераторы, счётчики и связанные функциональные изменения.",
    "uaart_critical.yml": "Миграции, безопасность, инфраструктура и массовые production-изменения.",
    "uaart_monitor.yml": "Read-only health, uptime, SEO и наблюдаемость без ремонтных записей.",
    "uaart_backup.yml": "Единый резервный снимок и проверка восстановимости.",
    "uaart_rollback.yml": "Параметризованный атомарный откат и post-rollback verify.",
    "uaart_maintenance.yml": "Плановые архивирование, cleanup и проверка дрейфа инфраструктуры.",
}


@dataclass
class WorkflowFact:
    path: str
    name: str
    size: int
    triggers: list[str]
    concurrency: str
    pythonanywhere: bool
    anthropic: bool
    production_write_capable: bool
    watchdog: bool
    queue_gate: bool
    retry_recovery: bool
    owner_gate: bool
    referenced_workflows: list[str]
    referenced_scripts: list[str]
    classification: str
    target_pipeline: str
    rationale: str


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rel(path: pathlib.Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def first_yaml_scalar(text: str, key: str, default: str) -> str:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text)
    if not match:
        return default
    value = match.group(1).strip().strip("'\"")
    return value or default


def detect_triggers(text: str) -> list[str]:
    trigger_names = [
        "workflow_dispatch", "workflow_call", "workflow_run", "repository_dispatch",
        "push", "pull_request", "pull_request_target", "schedule",
    ]
    found = [name for name in trigger_names if re.search(rf"(?m)^\s*{re.escape(name)}\s*:", text)]
    compact = re.search(r"(?m)^\s*on\s*:\s*\[([^\]]+)\]", text)
    if compact:
        for token in compact.group(1).split(","):
            token = token.strip().strip("'\"")
            if token and token not in found:
                found.append(token)
    return found or ["UNRESOLVED"]


def detect_concurrency(text: str) -> str:
    block = re.search(r"(?ms)^\s*concurrency\s*:\s*\n(?P<body>(?:^[ \t]+.*\n?)+)", text)
    if block:
        group = re.search(r"(?m)^\s*group\s*:\s*(.+?)\s*$", block.group("body"))
        if group:
            return group.group(1).strip().strip("'\"")
        return "DECLARED_NO_STATIC_GROUP"
    inline = re.search(r"(?m)^\s*concurrency\s*:\s*(.+?)\s*$", text)
    return inline.group(1).strip().strip("'\"") if inline else "NONE"


def find_references(text: str) -> tuple[list[str], list[str]]:
    workflow_refs = sorted(set(re.findall(r"(?<![\w.-])(\.github/workflows/[A-Za-z0-9._/-]+\.ya?ml)", text)))
    script_refs = sorted(set(
        value for value in re.findall(r"(?<![\w.-])((?:automation|cloud|src|scripts)/[A-Za-z0-9._/-]+\.(?:py|js|sh))", text)
        if ".." not in pathlib.PurePosixPath(value).parts
    ))
    return workflow_refs, script_refs


def classify(path: pathlib.Path, text: str, flags: dict[str, bool]) -> tuple[str, str, str]:
    name = path.name.casefold()
    folded = (path.as_posix() + "\n" + text[:12000]).casefold()
    numbered = bool(re.match(r"task\d+", path.stem, re.I))
    versioned = bool(re.search(r"(?:_v\d+|[-_]v\d+|retry|recovery|autostart|launch_after|slim|now)", name))
    obvious_stub = path.stat().st_size < 700 and numbered
    core_keep = {
        "claude_autopilot.yml",
        "safe_workflow_watchdog.yml",
        "pythonanywhere_sync.yml",
        "seo-watch-smoke.yml",
    }

    if "seo" in folded or "editorial" in folded:
        target = "uaart_monitor.yml" if not flags["production"] else "uaart_standard.yml"
    elif "backup" in folded:
        target = "uaart_backup.yml"
    elif "rollback" in folded:
        target = "uaart_rollback.yml"
    elif any(x in folded for x in ("crm", "voice", "photo", "container", "stage", "catalog", "card")):
        target = "uaart_standard.yml" if not flags["critical_hint"] else "uaart_critical.yml"
    elif flags["watchdog"]:
        target = "uaart_monitor.yml"
    elif flags["production"] or flags["pythonanywhere"]:
        target = "uaart_critical.yml"
    else:
        target = "uaart_fast.yml"

    if path.name in core_keep:
        return "KEEP", target, "Базовый действующий контур; сохранить до доказанного функционального эквивалента."
    if obvious_stub:
        return "ARCHIVE", target, "Короткий task-specific launcher/stub; после миграции сохранить только как историю."
    if numbered and versioned:
        return "ARCHIVE", target, "Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования."
    if numbered:
        return "MERGE", target, "Task-specific workflow должен стать параметром общего конвейера."
    if versioned:
        return "ARCHIVE", target, "Версионный инфраструктурный вариант; проверить преемника и затем архивировать."
    if "superseded" in folded or "deprecated" in folded or "obsolete" in folded:
        return "DELETE_CANDIDATE", target, "Явно помечен устаревшим; удалять только после dependency proof."
    return "MERGE", target, "Функцию следует объединить с постоянным параметризованным pipeline."


def audit_workflows() -> list[WorkflowFact]:
    paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    facts: list[WorkflowFact] = []
    for path in paths:
        text = read_text(path)
        folded = (path.as_posix() + "\n" + text).casefold()
        flags = {
            "pythonanywhere": "pythonanywhere" in folded or "api.pythonanywhere.com" in folded,
            "anthropic": "anthropic" in folded or "claude_worker" in folded,
            "production": any(marker in folded for marker in (
                "production", "gate_b", "gate b", "deploy", "publish_transaction",
                "atomic install", "remote write", "reload",
            )),
            "watchdog": "watchdog" in folded or "health probe" in folded,
            "queue": "production_queue" in folded or "queue gate" in folded,
            "retry": any(marker in folded for marker in (
                "retry", "rerun", "recovery", "recover", "attempt",
            )),
            "owner": any(marker in folded for marker in (
                "owner approval", "owner_approval", "approved_by_owner",
                "workflow_dispatch", "approval_phrase",
            )),
            "critical_hint": any(marker in folded for marker in (
                "database", "crm.db", "security", "credential", "dns", "cloudflare",
                "migration", "mass", "production",
            )),
        }
        workflow_refs, script_refs = find_references(text)
        classification, target, rationale = classify(path, text, flags)
        facts.append(WorkflowFact(
            path=rel(path),
            name=first_yaml_scalar(text, "name", path.stem),
            size=path.stat().st_size,
            triggers=detect_triggers(text),
            concurrency=detect_concurrency(text),
            pythonanywhere=flags["pythonanywhere"],
            anthropic=flags["anthropic"],
            production_write_capable=flags["production"],
            watchdog=flags["watchdog"],
            queue_gate=flags["queue"],
            retry_recovery=flags["retry"],
            owner_gate=flags["owner"],
            referenced_workflows=workflow_refs,
            referenced_scripts=script_refs,
            classification=classification,
            target_pipeline=target,
            rationale=rationale,
        ))
    return facts


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        return f"UNAVAILABLE: {exc}"


def task096_evidence() -> list[str]:
    log = git_output(
        "log", "--all", "--date=iso-strict",
        "--pretty=format:%h|%ad|%s", "--regexp-ignore-case", "--grep=task096",
    )
    return [line for line in log.splitlines() if line.strip() and not line.startswith("UNAVAILABLE:")]


def markdown_bool(value: bool) -> str:
    return "YES" if value else "NO"


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def render_inventory(facts: list[WorkflowFact]) -> str:
    counts = collections.Counter(f.classification for f in facts)
    target_counts = collections.Counter(f.target_pipeline for f in facts)
    rows = [
        "# WORKFLOW INVENTORY — TASK105", "", f"Generated: `{utc_now()}`",
        f"Total workflows: **{len(facts)}**", "", "## Classification totals", "",
        "| Class | Count |", "|---|---:|",
    ]
    for key in ("KEEP", "MERGE", "ARCHIVE", "DELETE_CANDIDATE"):
        rows.append(f"| {key} | {counts.get(key, 0)} |")
    rows += ["", "## Target consolidation", "", "| Target pipeline | Current workflows mapped |", "|---|---:|"]
    for target in TARGET_PIPELINES:
        rows.append(f"| `{target}` | {target_counts.get(target, 0)} |")
    rows += [
        "", "## Full inventory", "",
        "| # | Workflow | Trigger | Concurrency | PA | AI | Prod | Queue | Retry | Owner gate | Class | Target |",
        "|---:|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|",
    ]
    for index, f in enumerate(facts, 1):
        rows.append(
            f"| {index} | `{f.path}` | {', '.join(f.triggers)} | `{f.concurrency}` | "
            f"{markdown_bool(f.pythonanywhere)} | {markdown_bool(f.anthropic)} | "
            f"{markdown_bool(f.production_write_capable)} | {markdown_bool(f.queue_gate)} | "
            f"{markdown_bool(f.retry_recovery)} | {markdown_bool(f.owner_gate)} | "
            f"**{f.classification}** | `{f.target_pipeline}` |"
        )
    rows += ["", "## Per-workflow rationale", ""]
    for f in facts:
        rows += [
            f"### `{f.path}`",
            f"- Decision: **{f.classification}** → `{f.target_pipeline}`",
            f"- Rationale: {f.rationale}",
            f"- Referenced workflows: {', '.join(f'`{x}`' for x in f.referenced_workflows) or 'NONE'}",
            f"- Referenced scripts: {', '.join(f'`{x}`' for x in f.referenced_scripts) or 'NONE'}", "",
        ]
    return "\n".join(rows)


def render_dependency_map(facts: list[WorkflowFact]) -> str:
    script_users: dict[str, list[str]] = collections.defaultdict(list)
    workflow_edges: list[tuple[str, str]] = []
    groups: dict[str, list[str]] = collections.defaultdict(list)
    for f in facts:
        for script in f.referenced_scripts:
            script_users[script].append(f.path)
        for target in f.referenced_workflows:
            workflow_edges.append((f.path, target))
        if f.concurrency != "NONE":
            groups[f.concurrency].append(f.path)

    rows = [
        "# DEPENDENCY MAP — TASK105", "", "## Control-plane flow observed", "", "```text",
        "Owner/ChatGPT → tasks/task_NNN.md → GitHub workflow → deterministic scripts and/or Claude",
        "→ cloud outputs / evidence → PythonAnywhere transport (where explicitly enabled)",
        "→ production transaction → live verification / rollback", "```", "", "## High-risk capability groups", "",
    ]
    for label, predicate in [
        ("Production-write capable", lambda f: f.production_write_capable),
        ("PythonAnywhere transport", lambda f: f.pythonanywhere),
        ("Anthropic/Claude", lambda f: f.anthropic),
        ("Watchdog/health", lambda f: f.watchdog),
        ("Queue gate", lambda f: f.queue_gate),
        ("Retry/recovery", lambda f: f.retry_recovery),
    ]:
        selected = [f.path for f in facts if predicate(f)]
        rows += [f"### {label} ({len(selected)})"]
        rows += [f"- `{path}`" for path in selected] or ["- NONE"]
        rows.append("")

    rows += ["## Shared scripts by number of workflow callers", ""]
    repeated = False
    for script, users in sorted(script_users.items(), key=lambda item: (-len(item[1]), item[0])):
        if len(users) > 1:
            repeated = True
            rows.append(f"- `{script}` ← {len(users)} workflows")
            for user in sorted(users):
                rows.append(f"  - `{user}`")
    if not repeated:
        rows.append("- No repeated explicit script references detected.")
    rows += ["", "## Workflow-to-workflow edges", ""]
    rows += [f"- `{source}` → `{target}`" for source, target in sorted(workflow_edges)] or [
        "- No literal reusable-workflow paths detected; most coordination is event/script based."
    ]
    rows += ["", "## Concurrency groups", ""]
    for group, members in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        rows.append(f"### `{group}` ({len(members)})")
        rows += [f"- `{member}`" for member in sorted(members)]
        rows.append("")
    rows += [
        "## Finding", "",
        "Task-specific workflow names dominate the control plane. Shared behavior is implemented by",
        "copying orchestration patterns rather than calling a small set of parameterized reusable workflows.",
        "That increases transport drift, retry divergence and the probability that a repair fixes one path",
        "but not its siblings.",
    ]
    return "\n".join(rows)


def render_task096(lines: list[str]) -> str:
    rows = ["# ROOT CAUSE AUDIT — TASK096 v3–v8", "", f"Matching commits found: **{len(lines)}**", "", "## Commit evidence", ""]
    rows += [f"- `{line}`" for line in lines] or ["- No matching Git log evidence available in checkout."]
    subjects = "\n".join(lines).casefold()
    categories = {
        "Console/session readiness": ("console", "readiness", "session"),
        "Wrapper/launcher fragility": ("wrapper", "launcher", "trigger"),
        "Controller correctness": ("controller", "syntax", "attribute"),
        "Transport durability": ("transport", "pythonanywhere", "remote"),
        "API/model contract": ("sonnet", "api", "evidence handoff", "receipt"),
        "Repeated version launches": (" v3", " v4", " v5", " v6", " v7", " v8"),
    }
    rows += ["", "## Root-cause categories", ""]
    for category, terms in categories.items():
        hits = [term for term in terms if term in subjects]
        rows.append(f"- **{category}:** {'CONFIRMED (' + ', '.join(hits) + ')' if hits else 'NOT PROVEN BY COMMIT SUBJECTS'}")
    rows += [
        "", "## Systemic root cause", "",
        "TASK096 combined business delivery with unstable launcher, remote-console, transport, controller,",
        "model-output and evidence contracts. A failure in any layer generated a new versioned launch",
        "instead of first freezing the last-known-good transport and running deterministic preflight.",
        "", "## Failures that must move to deterministic preflight", "",
        "1. Compile every Python controller and wrapper before remote launch.",
        "2. Validate referenced paths/functions and import graph against the checked-out tree.",
        "3. Validate API model name, required request fields and structured-output schema using a bounded canary.",
        "4. Validate PythonAnywhere transport capability/readiness separately from the business payload.",
        "5. Validate receipt schema, evidence path allowlist and expected artifact count before dispatch.",
        "6. Freeze one immutable payload SHA and one transport SHA for the entire attempt.",
        "7. After a repeated non-transient error, stop blind versioning and enter ROOT_CAUSE_MODE.",
        "", "## Permanent rule", "",
        "`business payload` and `delivery transport` must have independent tests, versioning and rollback.",
        "A transport repair must not silently modify the requested site/CRM change.",
    ]
    return "\n".join(rows)


def render_current_state(facts: list[WorkflowFact]) -> str:
    return f"""# CURRENT STATE MACHINE — TASK105

## Observed problem

The repository has {len(facts)} workflow files with overlapping status vocabularies. Historical tasks use
`DONE`, `PASS`, `100%`, `WAITING_OWNER`, `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`,
workflow `success`, and production verification as different notions of completion.

## Current composite flow

```text
TASK CREATED
  → WORKFLOW TRIGGERED
  → AI/DESIGN/REPAIR OUTPUT CREATED
  → SANDBOX OR GATE A PASS
  → POSSIBLY WAITING OWNER
  → GATE B / PRODUCTION
  → POSSIBLY LIVE VERIFY
  → REPORT
```

The defect is that several intermediate states are presented as “finished”.

## Canonical replacement state machine

```text
QUEUED
  → CLASSIFYING
  → RUNNING
  → TESTING
  → READY_FOR_DEPLOY
  → DEPLOYING
  → VERIFYING
  → FINISHED
```

Exceptional terminal/holding states:

- `BLOCKED`: a resolvable external or owner dependency exists.
- `FAILED`: deterministic execution failed and no safe retry remains.
- `ROLLED_BACK`: attempted production change was reversed and rollback verified.

## Hard semantic rules

- `PASS` describes a test, never the whole task.
- `100%` is forbidden unless status is `FINISHED`.
- `WAITING_OWNER` is not finished.
- `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` maps to `READY_FOR_DEPLOY`.
- Workflow conclusion `success` means only that the workflow completed its own steps.
- `FINISHED` requires a final receipt proving the requested target environment and business result.
"""


def render_target_architecture() -> str:
    rows = ["# TARGET ARCHITECTURE — TASK105", "", "## Seven permanent workflows", ""]
    for name, purpose in TARGET_PIPELINES.items():
        rows += [f"### `{name}`", purpose, ""]
    rows += [
        "## Central orchestrator", "",
        "`automation/task_orchestrator.py` owns classification, task state, resource locks, retry policy,",
        "executor selection, evidence collection and final receipt validation.", "",
        "## Classification contract", "",
        "| Class | Default executor | Production path | AI default |", "|---|---|---|---|",
        "| FAST | deterministic scripts / GPT-authored patch | backup → deploy → smoke | NO_AI after patch |",
        "| STANDARD | deterministic runner + optional AI review | sandbox → backup → deploy → live verify | GPT_PRIMARY or CLAUDE_REVIEW |",
        "| CRITICAL | isolated implementation + dual gate | full regression → canary → approval → production | explicit budget |",
        "", "## Resource-aware locking", "",
        "Lock keys are scoped, for example: `CRM_DB`, `CATALOG_RENDERER`, `HOMEPAGE`, `CARD:UA-0016`,",
        "`CLOUDFLARE_CONFIG`. Read-only work and unrelated resources remain parallel.", "",
        "## AI routing", "",
        "Allowed routes: `NO_AI`, `GPT_PRIMARY`, `CLAUDE_REVIEW`, `CLAUDE_PRIMARY`, `DUAL_REVIEW`.",
        "AI is prohibited for HTTP checks, SHA verification, backups, copy/install, regex validation,",
        "queue polling and deterministic tests.", "", "## Final receipt", "",
        "`state/receipts/TASK_NNN.json` is the only authority allowed to set `FINISHED`.",
        "It must contain target environment, test result, deployment proof, live verification,",
        "unexpected-change count and rollback readiness.",
    ]
    return "\n".join(rows)


def render_migration_plan(facts: list[WorkflowFact]) -> str:
    counts = collections.Counter(f.classification for f in facts)
    return f"""# MIGRATION PLAN — TASK105

## Phase 0 — completed by this audit

- Inventory and classify all {len(facts)} workflows.
- Map production, PythonAnywhere, Anthropic, watchdog, queue and retry capabilities.
- Define canonical state machine and target seven-workflow architecture.
- No production write.

## Phase 1 — sandbox orchestrator

- Add state schema, classifier, resource-lock planner and receipt validator.
- No deployment capability.
- Run unit tests and failure injection locally/GitHub only.

## Phase 2 — shadow mode

- Feed real task metadata to old and new routers.
- New router makes decisions but does not execute production.
- Compare classification, required locks and expected stages.

## Phase 3 — FAST canary

- 20 synthetic tasks: 20/20 PASS.
- 3 owner-approved low-risk production changes with backup and live smoke.
- Automatic rollback on any protected diff.

## Phase 4 — STANDARD canary

- 10 sandbox tasks and 3 controlled production tasks.
- Verify CRM/card/counter regression profiles.

## Phase 5 — CRITICAL adapter

- Preserve existing strict gates behind one parameterized critical workflow.
- No reduction of security controls until equivalent evidence exists.

## Phase 6 — consolidation

Current classification baseline:
- KEEP: {counts.get('KEEP', 0)}
- MERGE: {counts.get('MERGE', 0)}
- ARCHIVE: {counts.get('ARCHIVE', 0)}
- DELETE_CANDIDATE: {counts.get('DELETE_CANDIDATE', 0)}

Archive only after replacement parity, dependency scan, rollback drill and owner approval.
Do not delete history during the migration.
"""


def render_risk_register(facts: list[WorkflowFact]) -> str:
    prod = sum(f.production_write_capable for f in facts)
    pa = sum(f.pythonanywhere for f in facts)
    ai = sum(f.anthropic for f in facts)
    return f"""# RISK REGISTER — TASK105

| ID | Risk | Evidence | Severity | Control |
|---|---|---|---|---|
| R1 | False `FINISHED` | Multiple intermediate completion vocabularies | Critical | Receipt-gated final state |
| R2 | Hidden production writer | {prod} workflows heuristically production-capable | Critical | Explicit capability manifest + deny-by-default |
| R3 | PythonAnywhere transport drift | {pa} workflows reference PythonAnywhere | High | One transport adapter with immutable SHA |
| R4 | Excess AI cost/latency | {ai} workflows reference Anthropic/Claude | High | AI router and per-task budgets |
| R5 | Global serialization | Shared queue patterns can block unrelated resources | High | Resource-aware locks |
| R6 | Retry storm | Versioned retry/recovery workflows exist | High | Transient allowlist, bounded retries, ROOT_CAUSE_MODE |
| R7 | Workflow cleanup breaks recovery | Many task-specific workflows may still be rollback paths | High | Archive first; delete only after dependency proof |
| R8 | New orchestrator misclassifies risk | Rule-based classifier may under-rank a change | Critical | Conservative default + protected-path escalation |
| R9 | Token/secret exposure | Multiple automation layers consume credentials | Critical | Least privilege, no secret logging, no PR secrets |
| R10 | Migration changes production too early | Pressure to speed up may bypass canary | Critical | Shadow mode and owner-controlled production gate |

## Safety conclusion

Speed must come from eliminating duplicated orchestration and unnecessary AI, not by removing
backup, protected-path validation, live verification or rollback.
"""


def render_acceptance_plan() -> str:
    return """# ACCEPTANCE TEST PLAN — TASK105

## Phase 0 evidence tests

1. Every `.github/workflows/*.yml|yaml` appears exactly once in the inventory.
2. Every inventory row has one of KEEP / MERGE / ARCHIVE / DELETE_CANDIDATE.
3. Every row maps to exactly one target permanent workflow.
4. Production/PythonAnywhere/Anthropic/watchdog/queue/retry flags are emitted.
5. TASK096 commit evidence and deterministic-preflight recommendations are present.
6. No production, CRM, PythonAnywhere, Cloudflare or DNS write occurs.

## Phase 1 unit tests

- Classification of representative FAST/STANDARD/CRITICAL tasks.
- Protected paths always escalate to CRITICAL.
- Resource locks allow unrelated tasks and serialize conflicting tasks.
- Retry accepts transient failures only.
- Second repeated logical failure enters ROOT_CAUSE_MODE.
- Receipt validator rejects missing live verification or rollback data.

## Failure injection

1. GitHub runner cancellation.
2. Network timeout.
3. HTTP 429.
4. PythonAnywhere 502/503.
5. Syntax error.
6. Unit-test regression.
7. Protected-file mutation.
8. Duplicate task dispatch.
9. Two unrelated production resources.
10. Rollback verification failure.

## Canary gates

- FAST synthetic: 20/20 PASS.
- STANDARD sandbox: 10/10 PASS.
- False FINISHED: 0.
- Unexpected protected changes: 0.
- Production regression: 0.
- Rollback drill: PASS.
"""


def render_phase0_report(facts: list[WorkflowFact], task096: list[str], contents: dict[str, str]) -> str:
    counts = collections.Counter(f.classification for f in facts)
    hashes = "\n".join(f"- `{name}`: `{sha256_text(text)}`" for name, text in sorted(contents.items()))
    blockers = []
    if not facts:
        blockers.append("Workflow inventory is empty.")
    if not task096:
        blockers.append("TASK096 Git log evidence unavailable in checkout.")
    blocker_text = "\n".join(f"- {item}" for item in blockers) or "- NONE"
    return f"""# PHASE 0 REPORT — UA-ART-FAST-PIPELINE-001

STATUS: {'BLOCKED' if blockers else 'PASS_PHASE0'}
GENERATED_AT_UTC: {utc_now()}
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
PYTHONANYWHERE_PRODUCTION_TOUCHED: NO
CLOUDFLARE_DNS_TOUCHED: NO

## Verified inventory

- Workflows discovered: **{len(facts)}**
- KEEP: **{counts.get('KEEP', 0)}**
- MERGE: **{counts.get('MERGE', 0)}**
- ARCHIVE: **{counts.get('ARCHIVE', 0)}**
- DELETE_CANDIDATE: **{counts.get('DELETE_CANDIDATE', 0)}**
- TASK096 matching commits: **{len(task096)}**

## Principal findings

1. The control plane is dominated by task-specific workflows and versioned recovery launchers.
2. Queue time is not the only latency source; orchestration and transport repair multiply task cycles.
3. Completion semantics are ambiguous and permit intermediate PASS/DONE states to look final.
4. Production serialization should be resource-aware.
5. AI must be routed and budgeted; deterministic operations must not call an LLM.
6. Seven permanent workflows plus one orchestrator can replace most task-specific control-plane code.
7. Existing workflows must be archived gradually, not deleted before parity and rollback proof.

## Unresolved blockers

{blocker_text}

## Deliverable SHA-256

{hashes}

## Decision

Phase 1 may begin only after human/ChatGPT review of this report. Phase 1 remains sandbox/shadow
mode; this report is not authorization to deploy the new pipeline to production.
"""


def validate(facts: list[WorkflowFact], generated: dict[str, str]) -> None:
    actual_paths = sorted([*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")])
    if len(facts) != len(actual_paths):
        raise SystemExit(f"INVENTORY_COUNT_MISMATCH:{len(facts)}!={len(actual_paths)}")
    seen = [f.path for f in facts]
    if len(seen) != len(set(seen)):
        raise SystemExit("DUPLICATE_WORKFLOW_INVENTORY")
    allowed_classes = {"KEEP", "MERGE", "ARCHIVE", "DELETE_CANDIDATE"}
    if any(f.classification not in allowed_classes for f in facts):
        raise SystemExit("INVALID_CLASSIFICATION")
    if any(f.target_pipeline not in TARGET_PIPELINES for f in facts):
        raise SystemExit("INVALID_TARGET_PIPELINE")
    missing = sorted(set(REQUIRED_OUTPUTS) - set(generated))
    if missing:
        raise SystemExit("MISSING_GENERATED_OUTPUTS:" + ",".join(missing))
    for name, text in generated.items():
        if len(text.strip()) < 200:
            raise SystemExit(f"OUTPUT_TOO_SMALL:{name}")


def self_test() -> None:
    sample = """
name: Test
on:
  workflow_dispatch:
concurrency:
  group: test-${{ github.ref }}
jobs:
  x:
    steps:
      - run: python3 automation/production_queue.py wait --task 1
"""
    assert detect_triggers(sample) == ["workflow_dispatch"]
    assert "test-" in detect_concurrency(sample)
    refs = find_references("python3 automation/production_queue.py\nuses: ./.github/workflows/foo.yml")
    assert "automation/production_queue.py" in refs[1]
    assert ".github/workflows/foo.yml" in refs[0]
    assert sha256_text("x") == hashlib.sha256(b"x").hexdigest()
    print("TASK105_PHASE0_SELF_TEST_PASS")


def run() -> None:
    facts = audit_workflows()
    task096 = task096_evidence()
    generated: dict[str, str] = {
        "WORKFLOW_INVENTORY.md": render_inventory(facts),
        "DEPENDENCY_MAP.md": render_dependency_map(facts),
        "ROOT_CAUSE_AUDIT_TASK096.md": render_task096(task096),
        "CURRENT_STATE_MACHINE.md": render_current_state(facts),
        "TARGET_ARCHITECTURE.md": render_target_architecture(),
        "MIGRATION_PLAN.md": render_migration_plan(facts),
        "RISK_REGISTER.md": render_risk_register(facts),
        "ACCEPTANCE_TEST_PLAN.md": render_acceptance_plan(),
    }
    generated["PHASE0_REPORT.md"] = render_phase0_report(facts, task096, generated)
    validate(facts, generated)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in generated.items():
        write(OUT / name, content)

    metadata = {
        "generated_at_utc": utc_now(),
        "workflow_count": len(facts),
        "classification_counts": dict(collections.Counter(f.classification for f in facts)),
        "target_counts": dict(collections.Counter(f.target_pipeline for f in facts)),
        "task096_commit_count": len(task096),
        "production_touched": False,
        "outputs": {name: sha256_text(content) for name, content in generated.items()},
    }
    write(OUT / "phase0_manifest.json", json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))

    status = "BLOCKED" if not facts or not task096 else "DONE"
    write(STATUS, f"""TASK_ID: task_105
ROUND: 1
CLAUDE_STATUS: {status}
CURRENT_ACTION: Phase 0 deterministic read-only audit completed
FILES_CREATED: {','.join('cloud/task_105_fast_pipeline_phase0/' + name for name in REQUIRED_OUTPUTS)},cloud/task_105_fast_pipeline_phase0/phase0_manifest.json
PRODUCTION_TOUCHED: NO
OWNER_ACTION_REQUIRED: YES
OWNER_QUESTION: Review Phase 0 report before Phase 1 sandbox implementation
NEXT_FOR_CHATGPT: audit Phase 0 outputs and prepare Phase 1 only after review
UPDATED_AT_UTC: {utc_now()}
""")
    write(OWNER_REPLY, f"""# Ответ владельцу — TASK105

СТАТУС: {'PASS' if status == 'DONE' else 'FAIL'}
ЗАДАЧА: полный read-only аудит архитектуры выполнения задач UA ART
ЧТО СДЕЛАНО: проинвентаризировано {len(facts)} workflow; подготовлены dependency map, аудит TASK096, единая модель статусов, целевая архитектура, миграция, риски и тест-план
СОЗДАННЫЕ ФАЙЛЫ: cloud/task_105_fast_pipeline_phase0/
ЧТО НУЖНО ОТ ВЛАДЕЛЬЦА: после проверки отчёта отдельно разрешить Phase 1 sandbox
БЕЗОПАСНОСТЬ: production, CRM, PythonAnywhere production, Cloudflare и DNS не изменялись
""")
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    else:
        run()


if __name__ == "__main__":
    main()
