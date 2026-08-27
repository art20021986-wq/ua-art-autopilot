#!/usr/bin/env python3
"""Gate A preview builder for TASK 042 (isolated, offline).

Builds preview HTML fragments for UA-0001..UA-0009 and two synthetic
future-card regression fixtures, applies the canonical ferry-wording
transform, and writes outputs ONLY under this task's own
``preview_output`` directory. Never touches production paths, CRM, or
any real card file.

The generator is generic across UA-XXXX and has no hardcoded upper
limit of 0009; ``CARD_IDS`` below only lists the nine currently real
cards for this task's matrix, while ``build_future_fixtures`` proves
the generic behavior for arbitrary future ids.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from transform import apply_transform  # noqa: E402

PREVIEW_DIR = HERE / "preview_output"
CARD_IDS = [f"UA-{i:04d}" for i in range(1, 10)]


def synthetic_card_source(card_id: str, stage_display: str) -> str:
    """Build a structurally faithful SYNTHETIC card fragment.

    NOTE: This is a synthetic proxy fixture, not the real UA ART page
    content, because this execution context has no filesystem access to
    the real production/source files. It preserves the internal stage
    key/attributes so the transform and tests exercise realistic
    anchors (data-stage, filter query, status pill, heading, legend).
    """
    return (
        f'<div class="card" data-card-id="{card_id}" data-stage="sea">\n'
        f'  <span class="status-pill">{stage_display}</span>\n'
        f'  <h2 class="stage-heading">{stage_display}: Корея → Грузия</h2>\n'
        f'  <div class="timeline-legend">Море</div>\n'
        f'  <a class="filter-btn" href="/catalog?f=sea">{stage_display}</a>\n'
        f'</div>\n'
    )


def build_preview_for_card(card_id: str) -> dict:
    before = synthetic_card_source(card_id, "В море")
    after = apply_transform(before)
    return {
        "card_id": card_id,
        "internal_stage_before": "sea",
        "internal_stage_after": "sea",
        "source_note": (
            "SYNTHETIC_PROXY_FIXTURE (real file NOT_PROVEN: no filesystem "
            "access to /home/Carix in this context)"
        ),
        "before": before,
        "after": after,
        "idempotent": apply_transform(after) == after,
    }


def build_future_fixtures() -> list:
    fixtures = []
    # Fixture A: future card whose internal stage is already sea and
    # already-canonical display text supplied.
    a_before = synthetic_card_source("UA-0123", "На пароме")
    fixtures.append({
        "fixture": "future_internal_sea",
        "card_id": "UA-0123",
        "before": a_before,
        "after": apply_transform(a_before),
    })
    # Fixture B: future card supplied with a proven legacy alias 'В море'.
    b_before = synthetic_card_source("UA-0456", "В море")
    fixtures.append({
        "fixture": "future_legacy_alias",
        "card_id": "UA-0456",
        "before": b_before,
        "after": apply_transform(b_before),
    })
    return fixtures


def main():
    PREVIEW_DIR.mkdir(exist_ok=True)
    cards = [build_preview_for_card(c) for c in CARD_IDS]
    future = build_future_fixtures()
    manifest = {"cards": cards, "future_fixtures": future}
    out_path = PREVIEW_DIR / "gate_a_preview_manifest.json"
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    for c in cards:
        (PREVIEW_DIR / f"{c['card_id']}_after.html").write_text(c["after"], encoding="utf-8")
    for f in future:
        (PREVIEW_DIR / f"{f['fixture']}_after.html").write_text(f["after"], encoding="utf-8")
    print(f"Wrote preview manifest to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
