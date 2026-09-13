"""Assemble reviewed code for a read-only server check; never deploy live files."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(workspace):
    workspace = Path(workspace).resolve()
    cloud = workspace / "cloud"
    sync = cloud / "task088_price_sync"
    renderer = cloud / "task088_stage3_renderer"
    policy = cloud / "task088_autopilot_owner_policy"
    source = workspace / "live_source_private"
    mapping = {
        "uaart_market_prices.py": renderer / "uaart_market_prices.py",
        "uaart_price_sync_outbox.py": sync / "outbox.py",
        "uaart_price_sync_runtime.py": sync / "uaart_price_sync_runtime.py",
        "uaart_price_sync_binding.py": sync / "uaart_price_sync_binding.py",
        "owner_policy.py": policy / "owner_policy.py",
        "price_publication.py": policy / "price_publication.py",
    }
    for name in ("preflight.py", "install_package.py", "patch_cars_ui.py", "patch_guard.py"):
        mapping[name] = sync / name
    for name in ("patch_yadro.py", "patch_stranica.py", "patch_catalog_design_guard.py", "initial_html_prices.py"):
        mapping[name] = renderer / name
    files = {name: path.read_bytes() for name, path in mapping.items()}
    for name, data in files.items():
        compile(data, name, "exec")
    sources = {name: sha((source / name).read_bytes()) for name in (
        "cars_ui.py", "yadro.py", "stranica.py", "catalog_design_guard.py", "publish_transaction_guard.py")}
    dependencies = {name: sha((source / name).read_bytes()) for name in (
        "master_card.py", "publikaciya.py", "ua_stage_catalog_sync.py", "catalog_design_golden.html")}
    dependencies.update({
        "db.py": "b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086",
        "cars_schema.py": "1dd5d950eb4514901ca51911b4c5f89481263956ceea28f30e1fa2888cdd8d73",
        "start_safe.py": "21aded2b576b36c6cea84b431c691b22eb09105ca5ec13bb6fd0910452c2cbeb",
    })
    quota = json.loads((source / "quota_observation.json").read_text())
    stage2_bytes = (workspace / "runtime-repair/state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json").read_bytes()
    bundle = {
        "contract": "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "package_sha256": {name: sha(data) for name, data in files.items()},
        "source_sha256": sources,
        "dependency_sha256": dependencies,
        "expected_stage_counts": {"kiev": 5, "georgia": 5, "sea": 4, "korea": 4},
        "quota_evidence": quota,
        "stage2_receipt": json.loads(stage2_bytes),
        "canonical_stage2_raw_file_sha256": sha(stage2_bytes),
        "authority_status": "NOT_ACTIVATED_NO_TRUSTED_CONTROL_BRIDGE",
    }
    raw = json.dumps(bundle, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    files["preflight_bundle.json"] = raw
    output = workspace / "delivery"
    output.mkdir(exist_ok=True)
    identifier = sha(raw)[:12]
    archive = output / ("uaart_price_sync_preflight_" + identifier + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as packed:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            packed.writestr(info, data)
    metadata = {"archive": str(archive), "archive_sha256": sha(archive.read_bytes()),
                "bundle_sha256": sha(raw), "files": sorted(files), "bytes": archive.stat().st_size}
    (output / "preflight_upload.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace")
    build(parser.parse_args().workspace)
