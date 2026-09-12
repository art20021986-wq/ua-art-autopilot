"""Read-only, offline rehearsal of the one-VIN shell contract on 32 cached pages."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def check(snapshot_root):
    root = Path(snapshot_root).resolve()
    spec = importlib.util.spec_from_file_location("offline_card_shell", HERE / "runtime/card_shell.py")
    shell = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shell)
    manifest_bytes = (root / "snapshot_manifest.json").read_bytes()
    entries = {entry["path"]: entry for entry in json.loads(manifest_bytes)["entries"]}
    expected = {f"{folder}/UA-{number:04d}.html" for folder in ("site", "video") for number in range(1, 17)}
    observed = {str(path.relative_to(root)) for folder in ("site", "video") for path in (root / folder).glob("UA-????.html")}
    if observed != expected:
        raise RuntimeError("CACHED_PRIMARY_SCOPE_MISMATCH")
    checks, originals, removals = [], {}, Counter()
    for relative in sorted(expected):
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("INPUT_MISSING_OR_SYMLINK:" + relative)
        raw = path.read_bytes()
        digest = sha(raw)
        if relative not in entries or entries[relative]["sha256"] != digest:
            raise RuntimeError("SNAPSHOT_MANIFEST_MISMATCH:" + relative)
        originals[relative] = digest
        before = raw.decode("utf-8")
        after = shell.normalize_html(before, path.stem)
        if shell.normalize_html(after, path.stem) != after:
            raise RuntimeError("NON_IDEMPOTENT_NORMALIZATION:" + relative)
        delta = shell.permitted_delta(before, after, path.stem)
        validation = shell.validate_one_visible_vin(after, path.stem)
        assets = shell.validate_shell_assets(before, after)
        for removal in delta["permitted_removals"]:
            removals[removal["reason"]] += 1
        checks.append({"path": relative, "uid": path.stem, "status": "PASS",
                       "original_sha256": digest, "candidate_sha256": sha(after.encode("utf-8")),
                       "original_bytes": len(raw), "candidate_bytes": len(after.encode("utf-8")),
                       "idempotent": True, "validation": validation, "delta": delta, "assets": assets})
    for relative, digest in originals.items():
        if sha((root / relative).read_bytes()) != digest:
            raise RuntimeError("INPUT_MODIFIED_DURING_REHEARSAL:" + relative)
    asset_hashes = sorted({row["assets"]["ordered_static_assets_sha256"] for row in checks})
    if len(asset_hashes) != 1:
        raise RuntimeError("CACHED_CARDS_DO_NOT_SHARE_STATIC_SHELL_ASSETS")
    return {"task_id": "UA-ART-SPEC-AUTO-10-RESTORE-001", "status": "PASS_CACHED_SINGLE_VIN_SHELL_ONLY",
            "full_gate_b_pass": False, "production_touched": False, "network_requests": 0,
            "source_kind": "cached_task116_primary_HTML", "snapshot_name": root.name,
            "source_manifest_sha256": sha(manifest_bytes),
            "module_sha256": sha((HERE / "runtime/card_shell.py").read_bytes()),
            "unique_cards": 16, "html_pages": len(checks), "all_one_visible_vin": True,
            "all_main_technical_vins_retained": True, "all_idempotent": True,
            "all_outside_permitted_regions_bytes_unchanged": True,
            "all_static_shell_assets_identical": True, "ordered_static_assets_sha256": asset_hashes[0],
            "description_duplicate_cards": ["UA-0001", "UA-0006", "UA-0012"],
            "permitted_removal_counts": dict(removals), "input_html_byte_changes": 0,
            "candidate_pages_saved": False,
            "preserved": ["main technical VIN", "all other descriptive text", "scripts", "JSON-LD", "service attributes",
                          "styles", "stage and route", "diagnostics links", "photos and videos", "prices", "header and footer"],
            "limitations": ["Cached source compatibility only; this does not prove current production HTML or installed writer bindings.",
                            "Visible VIN count is a conservative HTML text check, excluding head/script/style/template, hidden attributes and explicit inline hidden styles; it is not browser-computed visibility.",
                            "Static asset guard alone does not validate inline executable script changes, header/footer structure or legal CRUD field changes. The exact-byte permitted-delta contract covers all of these during specification-only repair.",
                            "Future unknown duplicate markup fails closed and requires an explicit reviewed template update."],
            "pages": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = check(args.snapshot_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(json.dumps({key: report[key] for key in ("status", "html_pages", "all_one_visible_vin",
                                                  "all_idempotent", "all_static_shell_assets_identical",
                                                  "permitted_removal_counts")}))


if __name__ == "__main__":
    main()
