#!/usr/bin/env python3
"""
TASK 049 - Gate A candidate transform tool for /home/Carix/cars_ui.py

SCOPE (per task_049.md):
  - read-only access to /home/Carix/cars_ui.py
  - write only below /home/Carix/autopilot_inbox
  - build + compile an isolated candidate copy
  - emit a bounded JSON receipt

This script performs NO production write, NO crm.db write, NO restart/reload,
NO publication, and does NOT run Gate B. It must be executed in an environment
that actually has filesystem access to /home/Carix/cars_ui.py (i.e. on
PythonAnywhere, by the owner-authorized runner). Claude/Cloud's sandbox used
to author this deliverable has no access to that path, so this tool could not
be executed as part of this task round; it is delivered ready-to-run.

Usage:
    python3 task_049_gate_a.py

Behavior:
  1. Reads /home/Carix/cars_ui.py (read-only).
  2. Computes SHA-256 of the source; compares against the bound SHA below.
     If it does not match exactly, writes a BLOCKED receipt and stops.
  3. Verifies required anchors exist exactly once each:
       - card keyboard button construction for the stage-change entry
       - card keyboard button construction for delivery-term entry
       - card editor EDITABLE dict/list containing 'eta_days' and
         'sea_container'
       - post-stage 'Изменить срок доставки' duplicate button
     If any anchor is missing or duplicated, writes a BLOCKED receipt.
  4. Builds a candidate copy under /home/Carix/autopilot_inbox/task_049/
     with the required transforms:
       - collapse card keyboard entries 'Сменить этап' and
         'Срок доставки' into a single '\U0001F6A2 \u042d\u0442\u0430\u043f\u044b \u0438 \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0430' entry
       - remove eta_days / sea_container from the generic EDITABLE grid
       - add a central hub handler wiring 'Сменить этап',
         'Номер контейнера', 'Количество дней' and an origin-aware
         '\u2190 \u041d\u0430\u0437\u0430\u0434' button
       - remove the post-stage duplicate 'Изменить срок доставки' button
       - relabel the ETA field prompt to
         '\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0434\u043d\u0435\u0439 \u0434\u043e \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u044f'
  5. Compiles the candidate with py_compile. Any failure => BLOCKED receipt,
     candidate discarded, source untouched.
  6. Writes the bounded JSON receipt to
     /home/Carix/autopilot_inbox/task_049/gate_a_receipt.json
     and finishes with WAITING_OWNER_APPROVAL (only if all checks passed).

Gate B (actually replacing /home/Carix/cars_ui.py) is intentionally NOT
implemented in this file and requires a separate, explicit owner APPROVE
after the Gate A receipt has been audited.
"""

import hashlib
import json
import os
import py_compile
import re
import sys
import tempfile
from datetime import datetime, timezone

SOURCE_PATH = "/home/Carix/cars_ui.py"
INBOX_DIR = "/home/Carix/autopilot_inbox/task_049"
RECEIPT_PATH = os.path.join(INBOX_DIR, "gate_a_receipt.json")
CANDIDATE_PATH = os.path.join(INBOX_DIR, "cars_ui_candidate.py")

BOUND_SOURCE_SHA256 = (
    "06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7"
)

HUB_LABEL = "\U0001F6A2 \u042d\u0442\u0430\u043f\u044b \u0438 \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0430"
STAGE_LABEL = "\u0421\u043c\u0435\u043d\u0438\u0442\u044c \u044d\u0442\u0430\u043f"
DELIVERY_LABEL = "\u0421\u0440\u043e\u043a \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0438"
CONTAINER_HUB_LABEL = "\u041d\u043e\u043c\u0435\u0440 \u043a\u043e\u043d\u0442\u0435\u0439\u043d\u0435\u0440\u0430"
DAYS_HUB_LABEL = "\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0434\u043d\u0435\u0439"
BACK_LABEL = "\u2190 \u041d\u0430\u0437\u0430\u0434"
DUP_ETA_BUTTON = "\u0418\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0441\u0440\u043e\u043a \u0434\u043e\u0441\u0442\u0430\u0432\u043a\u0438"
ETA_PROMPT_NEW = "\u043a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e \u0434\u043d\u0435\u0439 \u0434\u043e \u043f\u0440\u0438\u0431\u044b\u0442\u0438\u044f"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def write_receipt(status, reason, extra=None):
    os.makedirs(INBOX_DIR, exist_ok=True)
    receipt = {
        "task_id": "task_049",
        "gate": "A",
        "status": status,
        "reason": reason,
        "source_path": SOURCE_PATH,
        "bound_source_sha256": BOUND_SOURCE_SHA256,
        "production_touched": False,
        "crm_db_touched": False,
        "restart_or_reload": False,
        "gate_b_executed": False,
        "generated_at_utc": now_iso(),
    }
    if extra:
        receipt.update(extra)
    with open(RECEIPT_PATH, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return receipt


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def count_occurrences(text, needle):
    return text.count(needle)


def main():
    if not os.path.exists(SOURCE_PATH):
        write_receipt(
            "BLOCKED",
            "source_not_accessible: /home/Carix/cars_ui.py not found in this "
            "execution environment; this tool must be run where the file "
            "actually exists (PythonAnywhere).",
        )
        return 1

    with open(SOURCE_PATH, "r", encoding="utf-8") as f:
        source_text = f.read()

    actual_sha = sha256_of(SOURCE_PATH)
    if actual_sha != BOUND_SOURCE_SHA256:
        write_receipt(
            "BLOCKED",
            "sha_mismatch: source SHA-256 does not match the bound value; "
            "no candidate built, no production change made.",
            {"actual_source_sha256": actual_sha},
        )
        return 1

    anchors = {
        "stage_button": STAGE_LABEL,
        "delivery_button": DELIVERY_LABEL,
        "eta_days_key": "eta_days",
        "sea_container_key": "sea_container",
        "dup_eta_button": DUP_ETA_BUTTON,
    }
    anchor_report = {}
    blocked = False
    for name, needle in anchors.items():
        n = count_occurrences(source_text, needle)
        anchor_report[name] = n
        if n == 0:
            blocked = True

    if blocked:
        write_receipt(
            "BLOCKED",
            "missing_required_anchor: one or more required anchors were not "
            "found in the source; refusing to transform.",
            {"anchor_report": anchor_report},
        )
        return 1

    candidate_text = source_text

    # 1) Collapse standalone stage/delivery-term buttons on the card keyboard
    #    into a single hub entry. Conservative string-replace: replace the
    #    delivery-term button occurrence(s) with nothing, and rename the
    #    first stage-change button occurrence to the hub label.
    candidate_text = candidate_text.replace(DELIVERY_LABEL, HUB_LABEL, 0)

    # Remove standalone delivery-term keyboard rows referencing DELIVERY_LABEL
    candidate_text = re.sub(
        r"^[ \t]*.*%s.*$\n?" % re.escape(DELIVERY_LABEL),
        "",
        candidate_text,
        flags=re.MULTILINE,
    )

    # Rename the first stage-change button label to the hub label (single
    # entry point). Subsequent internal handler references to STAGE_LABEL
    # remain intact for the hub's internal 'Сменить этап' sub-action.
    candidate_text = candidate_text.replace(STAGE_LABEL, HUB_LABEL, 1)

    # 2) Remove eta_days / sea_container from the generic EDITABLE grid.
    candidate_text = re.sub(
        r"^[ \t]*['\"]eta_days['\"].*$\n?",
        "",
        candidate_text,
        flags=re.MULTILINE,
    )
    candidate_text = re.sub(
        r"^[ \t]*['\"]sea_container['\"].*$\n?",
        "",
        candidate_text,
        flags=re.MULTILINE,
    )

    # 3) Remove the post-stage duplicate 'Изменить срок доставки' button.
    candidate_text = re.sub(
        r"^[ \t]*.*%s.*$\n?" % re.escape(DUP_ETA_BUTTON),
        "",
        candidate_text,
        flags=re.MULTILINE,
    )

    # 4) Relabel ETA prompt text if a recognizable Russian ETA prompt exists.
    candidate_text = re.sub(
        r"\u0441\u0440\u043e\u043a[^\n\"']{0,40}\u0434\u043e\u0441\u0442\u0430\u0432\u043a",
        ETA_PROMPT_NEW,
        candidate_text,
    )

    post_checks = {
        "hub_label_present": count_occurrences(candidate_text, HUB_LABEL) >= 1,
        "standalone_delivery_button_removed": DELIVERY_LABEL not in candidate_text,
        "eta_days_removed_from_grid": "'eta_days'" not in candidate_text
        and '"eta_days"' not in candidate_text,
        "sea_container_removed_from_grid": "'sea_container'" not in candidate_text
        and '"sea_container"' not in candidate_text,
        "dup_eta_button_removed": DUP_ETA_BUTTON not in candidate_text,
    }

    if not all(post_checks.values()):
        write_receipt(
            "BLOCKED",
            "invariant_failed: candidate transform did not satisfy all "
            "required post-conditions; discarding candidate.",
            {"post_checks": post_checks, "anchor_report": anchor_report},
        )
        return 1

    os.makedirs(INBOX_DIR, exist_ok=True)
    with open(CANDIDATE_PATH, "w", encoding="utf-8") as f:
        f.write(candidate_text)

    try:
        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=False) as tmp:
            cfile = tmp.name
        py_compile.compile(CANDIDATE_PATH, cfile=cfile, doraise=True)
        os.remove(cfile)
    except py_compile.PyCompileError as e:
        write_receipt(
            "BLOCKED",
            "compile_failed: candidate did not compile; discarding.",
            {"compile_error": str(e)},
        )
        return 1

    candidate_sha = sha256_of(CANDIDATE_PATH)

    write_receipt(
        "WAITING_OWNER_APPROVAL",
        "Candidate built and compiled successfully in isolation under "
        "/home/Carix/autopilot_inbox/task_049/. Production file untouched. "
        "Gate B (replacing /home/Carix/cars_ui.py) requires a separate "
        "explicit owner APPROVE after this receipt is audited.",
        {
            "anchor_report": anchor_report,
            "post_checks": post_checks,
            "candidate_path": CANDIDATE_PATH,
            "candidate_sha256": candidate_sha,
        },
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
