#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from task108 import ROOT, report_markdown, run


def main() -> int:
    report = run()
    evidence = dict(report)
    previews = evidence.pop("previews")

    evidence_dir = ROOT / "evidence"
    preview_dir = ROOT / "previews"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    (evidence_dir / "report.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (evidence_dir / "REPORT.md").write_text(report_markdown(report), encoding="utf-8")
    for uid, document in previews.items():
        (preview_dir / f"{uid}.html").write_text(document, encoding="utf-8")

    print(report["status"])
    for item in report["canaries"]:
        print(item["auto_number"], item["status"], item["verified_fact_count"])
    print("EVIDENCE_BACKED_CARDS", len(report["enriched_cards"]))
    print("SAFE_TO_PUBLISH_ANYTHING", report["safe_to_publish_anything"])
    return 0 if report["status"].startswith("CANARY_PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
