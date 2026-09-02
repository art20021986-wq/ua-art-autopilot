#!/usr/bin/env python3
"""TASK105 Phase 2 shadow comparison and Phase 3 synthetic FAST canary.

No network, no production adapters, no secrets and no external side effects.
All mutations occur in TemporaryDirectory instances.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import tempfile
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from automation.task_orchestrator import (
    AIRoute,
    TaskClass,
    TaskRequest,
    TaskStatus,
    build_plan,
    locks_conflict,
    validate_receipt,
    validate_transition,
)

OUT = ROOT / "cloud" / "task_105_fast_pipeline_phase2"


@dataclasses.dataclass(frozen=True)
class ShadowCase:
    case_id: str
    title: str
    description: str
    changed_paths: tuple[str, ...]
    production_required: bool
    complexity: int
    expected_class: TaskClass
    expected_ai: AIRoute | None = None


SHADOW_CASES = (
    ShadowCase(
        "TASK102-SEO-TEXT",
        "SEO Korea Kyiv title and description",
        "replace exact SEO copy and validate HTTP 200",
        ("public/seo/korea-kyiv.html",),
        True,
        1,
        TaskClass.FAST,
        AIRoute.NO_AI,
    ),
    ShadowCase(
        "TASK103-COUNTRIES",
        "Add Georgian language and eight-country order selector",
        "update country configuration, form routes and catalog integration",
        ("src/country_config.py", "public/podbor.html"),
        True,
        3,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "TASK096-ALL-CARDS",
        "Enrich all cards with technical characteristics",
        "mass update all cards through generator",
        ("src/card_generator.py",),
        True,
        5,
        TaskClass.CRITICAL,
        AIRoute.DUAL_REVIEW,
    ),
    ShadowCase(
        "TASK104-RECOVERY",
        "Change workflow-level recovery supervisor",
        "deployment architecture and failure recovery",
        (".github/workflows/task104_canary_worker.yml",),
        False,
        5,
        TaskClass.CRITICAL,
        AIRoute.DUAL_REVIEW,
    ),
    ShadowCase(
        "TASK095-CATALOG",
        "Repair catalog renderer visibility",
        "catalog renderer and publication logic",
        ("src/catalog_renderer.py",),
        True,
        3,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "TASK094-DESIGN",
        "Restore catalog design from approved reference",
        "design and UX restoration on static page",
        ("public/catalog.html",),
        True,
        2,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "TASK093-COUNTERS",
        "Synchronize homepage stage counters",
        "counter and stage logic",
        ("src/counters.py", "public/index.html"),
        True,
        3,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "TASK089-READONLY",
        "Audit CRM voice and photo paths",
        "read only CRM voice photo audit",
        ("src/crm/voice.py", "src/crm/photo.py"),
        False,
        2,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "TASK084-CRM-HANG",
        "Fix CRM hang root cause",
        "CRM runtime and database ownership",
        ("src/crm/runtime.py",),
        True,
        4,
        TaskClass.STANDARD,
        AIRoute.CLAUDE_REVIEW,
    ),
    ShadowCase(
        "TASK082-CARD-TITLE",
        "Append VIN4 to CRM card title",
        "CRM card title logic",
        ("src/crm/cars_ui.py",),
        True,
        2,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "FAST-CONTACT",
        "Replace exact phone label",
        "replace exact text, checksum and HTTP 200",
        ("public/contact.html",),
        True,
        1,
        TaskClass.FAST,
        AIRoute.NO_AI,
    ),
    ShadowCase(
        "FAST-SOCIAL",
        "Add social links to footer",
        "static HTML link validation",
        ("public/index.html",),
        True,
        1,
        TaskClass.FAST,
        AIRoute.NO_AI,
    ),
    ShadowCase(
        "STD-CATALOG-TRANSLATION",
        "Translate one approved catalog label",
        "translate and update one static catalog string",
        ("public/uk/catalog.html",),
        True,
        1,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "CRIT-DB-MIGRATION",
        "Migrate CRM database schema",
        "database migration with rollback",
        ("runtime/crm.db",),
        True,
        5,
        TaskClass.CRITICAL,
        AIRoute.DUAL_REVIEW,
    ),
    ShadowCase(
        "CRIT-SECURITY",
        "Change authentication and security headers",
        "security and authorization changes",
        ("src/auth.py",),
        True,
        5,
        TaskClass.CRITICAL,
        AIRoute.DUAL_REVIEW,
    ),
    ShadowCase(
        "CRIT-CLOUDFLARE",
        "Change Cloudflare WAF configuration",
        "cloudflare security configuration",
        ("wrangler.jsonc",),
        True,
        5,
        TaskClass.CRITICAL,
        AIRoute.DUAL_REVIEW,
    ),
    ShadowCase(
        "STD-FORM",
        "Add order lead form to CRM",
        "form submission and CRM integration",
        ("src/crm/order_form.py", "public/order.html"),
        True,
        3,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "STD-PUBLISH",
        "Fix card publication transaction",
        "publication backend logic",
        ("src/publisher.py",),
        True,
        3,
        TaskClass.STANDARD,
        AIRoute.GPT_PRIMARY,
    ),
    ShadowCase(
        "FAST-ROBOTS",
        "Update one robots directive",
        "replace exact directive and static check",
        ("public/robots.txt",),
        True,
        1,
        TaskClass.FAST,
        AIRoute.NO_AI,
    ),
    ShadowCase(
        "FAST-ARIA",
        "Correct one aria label",
        "replace exact accessibility label and checksum",
        ("public/index.html",),
        True,
        1,
        TaskClass.FAST,
        AIRoute.NO_AI,
    ),
)


FAST_OPERATIONS = (
    ("title", "<title>Old</title>", "<title>New</title>"),
    ("meta", 'content="old description"', 'content="new description"'),
    ("phone", "Phone: old", "Phone: new"),
    ("address", "Address: old", "Address: new"),
    ("button", ">Old CTA<", ">New CTA<"),
    ("aria", 'aria-label="old"', 'aria-label="new"'),
    ("alt", 'alt="old"', 'alt="new"'),
    ("href", 'href="/old"', 'href="/new"'),
    ("image", 'src="/old.webp"', 'src="/new.webp"'),
    ("lang", '<html lang="ru">', '<html lang="uk">'),
    ("hreflang", 'hreflang="ru"', 'hreflang="uk"'),
    ("robots", "Disallow: /old", "Disallow: /private"),
    ("sitemap", "<loc>/old</loc>", "<loc>/new</loc>"),
    ("faq", "Old answer", "New answer"),
    ("footer", "Old footer", "New footer"),
    ("social", "data-social=old", "data-social=new"),
    ("css-gap", "gap: 15px", "gap: 16px"),
    ("css-size", "font-size: 15px", "font-size: 16px"),
    ("json-label", '"label":"old"', '"label":"new"'),
    ("locale", '"country":"old"', '"country":"new"'),
)


def utc_now() -> str:
    return (
        dt.datetime.now(dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def run_shadow() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in SHADOW_CASES:
        request = TaskRequest.from_mapping({
            "task_id": case.case_id,
            "title": case.title,
            "description": case.description,
            "changed_paths": list(case.changed_paths),
            "production_required": case.production_required,
            "complexity": case.complexity,
        })
        plan = build_plan(request)
        class_pass = plan.task_class == case.expected_class
        ai_pass = case.expected_ai is None or plan.ai_route == case.expected_ai
        results.append({
            "case_id": case.case_id,
            "expected_class": case.expected_class.value,
            "actual_class": plan.task_class.value,
            "expected_ai": case.expected_ai.value if case.expected_ai else None,
            "actual_ai": plan.ai_route.value,
            "resource_locks": list(plan.resource_locks),
            "pass": class_pass and ai_pass,
            "risk_reasons": list(plan.risk_reasons),
        })
    return results


def run_fast_canary() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, (name, old, new) in enumerate(FAST_OPERATIONS, 1):
        with tempfile.TemporaryDirectory(prefix=f"uaart-fast-{index:02d}-") as temp:
            root = pathlib.Path(temp)
            target = root / f"case_{index:02d}.txt"
            untouched = root / "protected.txt"
            target.write_text(f"prefix\n{old}\nsuffix\n", encoding="utf-8")
            untouched.write_text("protected baseline\n", encoding="utf-8")
            before_target = sha256(target)
            before_untouched = sha256(untouched)

            request = TaskRequest.from_mapping({
                "task_id": f"FAST-CANARY-{index:02d}",
                "title": f"Replace exact {name} value",
                "description": "replace exact text, checksum and static check",
                "changed_paths": [f"public/case_{index:02d}.html"],
                "production_required": True,
                "complexity": 1,
            })
            plan = build_plan(request)
            if plan.task_class != TaskClass.FAST or plan.ai_route != AIRoute.NO_AI:
                raise AssertionError(f"FAST_CLASSIFICATION_FAIL:{name}:{plan.to_dict()}")

            content = target.read_text(encoding="utf-8")
            if content.count(old) != 1 or content.count(new) != 0:
                raise AssertionError(f"PRECONDITION_FAIL:{name}")
            target.write_text(content.replace(old, new, 1), encoding="utf-8")
            after = target.read_text(encoding="utf-8")
            if after.count(old) != 0 or after.count(new) != 1:
                raise AssertionError(f"POSTCONDITION_FAIL:{name}")
            if sha256(target) == before_target:
                raise AssertionError(f"TARGET_UNCHANGED:{name}")
            if sha256(untouched) != before_untouched:
                raise AssertionError(f"PROTECTED_CHANGED:{name}")

            status_path = (
                TaskStatus.QUEUED,
                TaskStatus.CLASSIFYING,
                TaskStatus.RUNNING,
                TaskStatus.TESTING,
                TaskStatus.VERIFYING,
                TaskStatus.FINISHED,
            )
            for current, target_status in zip(status_path, status_path[1:]):
                validate_transition(current, target_status)

            receipt = {
                "task_id": request.task_id,
                "status": "FINISHED",
                "task_class": "FAST",
                "target_environment": "sandbox",
                "tests": "PASS",
                "unexpected_changes": 0,
                "rollback_ready": True,
                "production_required": False,
                "ai_calls": 0,
            }
            validate_receipt(receipt)
            results.append({
                "case": index,
                "name": name,
                "class": plan.task_class.value,
                "ai_route": plan.ai_route.value,
                "locks_planned": list(plan.resource_locks),
                "target_changed": True,
                "protected_unchanged": True,
                "receipt_valid": True,
                "pass": True,
            })
    return results


def validate_parallelism() -> dict[str, bool]:
    checks = {
        "different_cards_parallel": not locks_conflict(
            ("CARD:UA-0001",), ("CARD:UA-0002",)
        ),
        "homepage_and_crm_parallel": not locks_conflict(
            ("HOMEPAGE",), ("CRM_DB",)
        ),
        "same_crm_serialized": locks_conflict(
            ("CRM_DB",), ("CRM_DB",)
        ),
        "all_cards_blocks_single_card": locks_conflict(
            ("CATALOG_ALL_CARDS",), ("CARD:UA-0016",)
        ),
    }
    if not all(checks.values()):
        raise AssertionError(f"PARALLELISM_CHECK_FAIL:{checks}")
    return checks


def main() -> None:
    shadow = run_shadow()
    canary = run_fast_canary()
    parallel = validate_parallelism()

    shadow_pass = sum(bool(item["pass"]) for item in shadow)
    canary_pass = sum(bool(item["pass"]) for item in canary)
    if shadow_pass != len(SHADOW_CASES):
        failures = [item for item in shadow if not item["pass"]]
        raise SystemExit("SHADOW_MISMATCH:" + json.dumps(failures, ensure_ascii=False))
    if canary_pass != len(FAST_OPERATIONS):
        raise SystemExit("FAST_CANARY_FAILURE")

    now = utc_now()
    OUT.mkdir(parents=True, exist_ok=True)
    write(
        OUT / "shadow_results.json",
        json.dumps(shadow, ensure_ascii=False, indent=2, sort_keys=True),
    )
    write(
        OUT / "fast_canary_results.json",
        json.dumps(canary, ensure_ascii=False, indent=2, sort_keys=True),
    )
    write(
        OUT / "parallelism_results.json",
        json.dumps(parallel, ensure_ascii=False, indent=2, sort_keys=True),
    )

    shadow_rows = [
        "# TASK105 Phase 2 Shadow Report",
        "",
        "STATUS: PASS_PHASE2_SHADOW",
        f"GENERATED_AT_UTC: {now}",
        f"REPRESENTATIVE_CASES: {shadow_pass}/{len(SHADOW_CASES)} PASS",
        "PRODUCTION_TOUCHED: NO",
        "AI_CALLS: 0",
        "",
        "| Case | Expected | Actual | Expected AI | Actual AI | Result |",
        "|---|---|---|---|---|---|",
    ]
    for item in shadow:
        shadow_rows.append(
            f"| {item['case_id']} | {item['expected_class']} | {item['actual_class']} | "
            f"{item['expected_ai']} | {item['actual_ai']} | {'PASS' if item['pass'] else 'FAIL'} |"
        )
    write(OUT / "PHASE2_SHADOW_REPORT.md", "\n".join(shadow_rows))

    canary_rows = [
        "# TASK105 Phase 3 Synthetic FAST Canary",
        "",
        "STATUS: PASS_PHASE3_SYNTHETIC_FAST",
        f"GENERATED_AT_UTC: {now}",
        f"FAST_CASES: {canary_pass}/{len(FAST_OPERATIONS)} PASS",
        "PROTECTED_FILE_CHANGES: 0",
        "AI_CALLS: 0",
        "PRODUCTION_TOUCHED: NO",
        "",
        "Each case performed one exact isolated mutation, verified before/after hashes,",
        "proved an untouched protected file remained identical, traversed the canonical",
        "state machine and validated a sandbox FINISHED receipt.",
        "",
        "## Resource-lock acceptance",
        "",
    ]
    canary_rows += [f"- {name}: {'PASS' if value else 'FAIL'}" for name, value in parallel.items()]
    write(OUT / "PHASE3_FAST_CANARY_REPORT.md", "\n".join(canary_rows))

    overall_receipt = {
        "task_id": "TASK105-PHASE2-3",
        "status": "FINISHED",
        "task_class": "CRITICAL",
        "target_environment": "sandbox",
        "tests": "PASS",
        "shadow_cases": len(SHADOW_CASES),
        "fast_canary_cases": len(FAST_OPERATIONS),
        "unexpected_changes": 0,
        "rollback_ready": True,
        "production_required": False,
        "production_touched": False,
        "ai_calls": 0,
        "finished_at": now,
    }
    validate_receipt(overall_receipt)
    write(
        OUT / "phase2_3_receipt.json",
        json.dumps(overall_receipt, ensure_ascii=False, indent=2, sort_keys=True),
    )

    write(
        ROOT / "cloud" / "latest_status.md",
        f"""TASK_ID: task_105
ROUND: 3
CLAUDE_STATUS: DONE
CURRENT_ACTION: Phase 2 shadow {shadow_pass}/{len(SHADOW_CASES)} and Phase 3 synthetic FAST {canary_pass}/{len(FAST_OPERATIONS)} PASS
FILES_CREATED: cloud/task_105_fast_pipeline_phase2/PHASE2_SHADOW_REPORT.md,cloud/task_105_fast_pipeline_phase2/PHASE3_FAST_CANARY_REPORT.md,cloud/task_105_fast_pipeline_phase2/phase2_3_receipt.json
PRODUCTION_TOUCHED: NO
OWNER_ACTION_REQUIRED: YES
OWNER_QUESTION: Approve controlled real FAST production canary only after review
NEXT_FOR_CHATGPT: review shadow/canary evidence and prepare bounded production canary proposal
UPDATED_AT_UTC: {now}
""",
    )
    write(
        ROOT / "cloud" / "owner_reply.md",
        f"""# Ответ владельцу — TASK105

СТАТУС: PASS PHASE 2–3 SANDBOX
SHADOW: {shadow_pass}/{len(SHADOW_CASES)} PASS
СИНТЕТИЧЕСКИЙ FAST CANARY: {canary_pass}/{len(FAST_OPERATIONS)} PASS
AI-ВЫЗОВЫ: 0
PRODUCTION: НЕ ЗАТРОНУТ
СЛЕДУЮЩИЙ БАРЬЕР: отдельный контролируемый реальный FAST production canary
""",
    )
    print(json.dumps(overall_receipt, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
