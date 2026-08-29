#!/usr/bin/env python3
"""Assemble the TASK 081 Gate A verdict from fresh GET-only evidence.

No network calls or production writes occur here.  Candidate transforms are
applied only to the source copies downloaded by ``live_audit_v2.py``.
"""

from __future__ import annotations

import json
import os
import pathlib

import patcher_v2 as patcher


HERE = pathlib.Path(__file__).resolve().parent
LIVE_ROOT = pathlib.Path(
    os.environ.get("TASK081_LIVE_AUDIT_ROOT", str(HERE / "evidence" / "live_audit_v2"))
)
AUDIT = LIVE_ROOT / "live_audit.json"
SOURCES = LIVE_ROOT / "sources"
OUTPUT = HERE / "evidence" / "gate_a_v2.json"


def main() -> int:
    value = {
        "task_id": "UA-0013-PUBLISH-REPAIR-001",
        "mode": "FRESH_GET_ONLY_PLUS_LOCAL_COPY_CANARY",
        "status": "BLOCKED",
        "production_touched": False,
        "crm_write": False,
        "site_write": False,
        "process_restart": False,
        "stage": {},
        "missing_published_numbers": [],
        "source_sha256": {},
        "candidate_sha256": {},
        "checks": {},
        "errors": [],
    }
    try:
        audit = json.loads(AUDIT.read_text(encoding="utf-8"))
        if audit.get("status") != "PASS_AUDIT_DEFECT_REPRODUCED":
            raise RuntimeError("LIVE_AUDIT_NOT_PASS:%s" % audit.get("errors"))
        if audit.get("http_methods") != ["GET"]:
            raise RuntimeError("LIVE_AUDIT_NOT_GET_ONLY")
        value["stage"] = audit.get("derived_stage") or {}
        value["missing_published_numbers"] = (
            audit.get("publication_gap", {}).get("missing_published_numbers") or []
        )

        sources = {
            name: (SOURCES / name).read_text(encoding="utf-8")
            for name in patcher.FULL_FILE_SHA256
        }
        for name, source in sources.items():
            patcher.require_full_sha(name, source)
            value["source_sha256"][name] = patcher.sha256_text(source)
        candidates = patcher.build_candidates(sources, check_full_sha=True)
        value["candidate_sha256"] = patcher.candidate_hashes(candidates)

        toggle = next(patcher._function_spans(candidates["cars_ui.py"], "toggle_publish"))
        publisher = next(patcher._function_spans(candidates["publikaciya.py"], "opublikovat"))
        rollback = next(patcher._function_spans(candidates["publikaciya.py"], "_otkat"))
        checks = {
            "toggle_signature_preserved": toggle.source.startswith(
                "async def toggle_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):"
            ),
            "toggle_checks_exact_true": "if _ok_rem2 is not True:" in toggle.source,
            "toggle_no_intermediate_publisher_message": (
                "await q.message.reply_text(_txt_rem2)" not in toggle.source
            ),
            "toggle_preimage_all_publish_fields": all(
                field in toggle.source for field in ('"published"', '"status"', '"publish_pending"')
            ),
            "publisher_real_master": "_master(kod)" in publisher.source,
            "publisher_real_catalog": "_ua9_sobrat_katalog()" in publisher.source,
            "publisher_stage_only_build": "_stage_only_begin()" in publisher.source,
            "publisher_two_catalogs": (
                'os.path.join(folder, "katalog.html")' in publisher.source
            ),
            "publisher_generic_future_ids": 'r"^UA-[0-9]{4,}$"' in publisher.source,
            "rollback_restores_existing": "shutil.copy2(copy, path)" in rollback.source,
            "rollback_deletes_new": "os.remove(path)" in rollback.source,
            "seo_precheck_removed_all_three": all(
                "SEO068_DIAGNOSTIC_TARGET_MISSING"
                not in next(patcher._function_spans(candidates[name], "_ua_seo068_normalize")).source
                for name in ("stranica.py", "master_card.py", "yadro.py")
            ),
            "seo_wrong_link_guard_preserved_all_three": all(
                "SEO068_WRONG_DIAGNOSTIC"
                in next(patcher._function_spans(candidates[name], "_ua_seo068_normalize")).source
                for name in ("stranica.py", "master_card.py", "yadro.py")
            ),
            "diag_stage_mode_all_three": all(
                "_UA081_STAGE_ONLY"
                in next(patcher._function_spans(candidates[name], "_ua068_ensure_diag_files")).source
                for name in ("stranica.py", "master_card.py", "yadro.py")
            ),
            "ua0013_correct_stage": value["stage"] == {
                "catalog_category": "more",
                "owner_label": "На пароме",
                "status": "sea_loaded",
            },
            "ua0013_gap_reproduced": "UA-0013" in value["missing_published_numbers"],
        }
        for name, source in candidates.items():
            try:
                compile(source, name, "exec")
                checks["compile:" + name] = True
            except Exception:
                checks["compile:" + name] = False
        value["checks"] = checks
        failed = sorted(name for name, passed in checks.items() if not passed)
        if failed:
            raise RuntimeError("CANDIDATE_CHECKS_FAILED:" + ",".join(failed))
        value["status"] = "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL"
    except Exception as exc:  # noqa: BLE001
        value["errors"].append(type(exc).__name__ + ":" + str(exc))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": value["status"], "errors": value["errors"]}, ensure_ascii=False))
    return 0 if value["status"] == "PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
