"""Build a content-addressed read-only package from a real reviewed observation.

No source hashes, counts, quota, or acceptance evidence are supplied by defaults.
The observation comes from observe_install_inputs.py on the authenticated server.
It contains hashes/counts only; no CRM database or live Python source is packed.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

CATALOG_RECONCILIATION = {
    "contract": "PR114-EXACT-CATALOG-RECONCILIATION-INPUT-1",
    "observer_file": "catalog_reconciliation_observer_20260922.json",
    "observer_sha256": "07e07f499c20d5db62e0ae58cb4922be2cfacd4e8956879dbcd374322bb71454",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def package_mapping(repository, *, catalog_reconciliation=False):
    cloud = Path(repository) / "cloud"
    sync, renderer, policy = (cloud / name for name in (
        "task088_price_sync", "task088_stage3_renderer", "task088_autopilot_owner_policy"))
    mapping = {"uaart_market_prices.py": renderer / "uaart_market_prices.py",
        "uaart_price_sync_outbox.py": sync / "outbox.py"}
    for name in ("uaart_price_sync_runtime.py", "uaart_price_sync_binding.py", "uaart_price_sync_confirmation.py",
                 "uaart_price_control_reader.py", "preflight.py", "install_package.py", "patch_cars_ui.py", "patch_guard.py", "patch_site_counters.py", "patch_publikaciya.py"):
        mapping[name] = sync / name
    for name in ("patch_yadro.py", "patch_stranica.py", "patch_catalog_design_guard.py",
                 "patch_stage_catalog_sync.py", "initial_html_prices.py"):
        mapping[name] = renderer / name
    for name in ("owner_policy.py", "price_publication.py"):
        mapping[name] = policy / name
    for name in ("integrate_private_sources.py", "publication_fence.py", "mutation_recovery.py", "visibility_lifecycle.py"):
        mapping[name] = cloud / "task088_v5_writer_fence" / name
    if catalog_reconciliation:
        mapping["bound_catalog_reconciliation.py"] = sync / "bound_catalog_reconciliation.py"
    return mapping


def build(repository, *, observation, stage2_receipt, output_directory, routing_evidence=None,
          catalog_reconciliation_observer=None):
    repository = Path(repository).resolve()
    observed_raw = Path(observation).read_bytes()
    observed = json.loads(observed_raw)
    if (observed.get("contract") != "TASK088-V5-INSTALL-OBSERVATION-1" or
            observed.get("status") != "PASS" or observed.get("read_only") is not True):
        raise ValueError("REAL_COMPLETE_READONLY_OBSERVATION_REQUIRED")
    instant = datetime.fromisoformat(observed["observed_at"].replace("Z", "+00:00"))
    if instant.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - instant).total_seconds() <= 1800:
        raise ValueError("OBSERVATION_STALE")
    files = {name: path.read_bytes() for name, path in package_mapping(repository,
        catalog_reconciliation=catalog_reconciliation_observer is not None).items()}
    for name, data in files.items():
        compile(data, name, "exec")
    from install_package import SOURCES, DEPENDENCIES
    for key, expected in (("source_sha256", SOURCES), ("dependency_sha256", DEPENDENCIES)):
        if set(observed.get(key, {})) != expected or any(
                not re.fullmatch(r"[0-9a-f]{64}", value) for value in observed[key].values()):
            raise ValueError("COMPLETE_OBSERVED_PINS_REQUIRED:" + key)
    stage2_bytes = Path(stage2_receipt).read_bytes()
    stage2 = json.loads(stage2_bytes)
    if (stage2.get("task_id") != "TASK088-GE-PRICE-CRM-STAGE2" or stage2.get("status") != "FINISHED"
            or stage2.get("stage1_prerequisite") != "PASS" or stage2.get("stage2_status") != "PASS"
            or stage2.get("stage3_allowed") is not True
            or stage2.get("installed_source_sha256") != observed["source_sha256"]["cars_ui.py"]):
        raise ValueError("EXACT_STAGE1_STAGE2_PREREQUISITES_REQUIRED")
    bundle = {"contract": "TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "observation_sha256": sha(observed_raw),
        "package_sha256": {name: sha(data) for name, data in files.items()},
        "source_sha256": observed["source_sha256"], "dependency_sha256": observed["dependency_sha256"],
        "system_inventory": observed["system_inventory"],
        "expected_published_codes": observed["database"]["published_codes"],
        "expected_stage_counts": observed["stage_counts"],
        "quota_evidence": observed["quota_evidence"], "stage2_receipt": stage2,
        "canonical_stage2_raw_file_sha256": sha(stage2_bytes),
        "authority_status": "READONLY_PREFLIGHT_NOT_A_PRODUCTION_GATE"}
    if catalog_reconciliation_observer is not None:
        observer_bytes = Path(catalog_reconciliation_observer).read_bytes()
        if sha(observer_bytes) != CATALOG_RECONCILIATION["observer_sha256"]:
            raise ValueError("EXACT_CATALOG_RECONCILIATION_OBSERVER_REQUIRED")
        observer = json.loads(observer_bytes)
        if observer["database"]["published_sha256"] != observed["database"]["published_sha256"]:
            raise ValueError("CURRENT_PUBLISHED_ROWS_RECONCILIATION_BINDING_MISMATCH")
        bundle["catalog_reconciliation"] = dict(CATALOG_RECONCILIATION)
        files[CATALOG_RECONCILIATION["observer_file"]] = observer_bytes
    if routing_evidence is not None:
        from install_package import validate_routing
        routing_raw = Path(routing_evidence).read_bytes()
        routing = json.loads(routing_raw)
        validate_routing(routing)
        bundle.update({"routing": routing, "routing_evidence_sha256": sha(routing_raw),
                       "homepage_policy": {"site/index.html": "PROTECTED_LEGACY_NOT_SERVED"}})
    raw = json.dumps(bundle, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    files["preflight_bundle.json"] = raw
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    archive = output / ("uaart_price_sync_preflight_" + sha(raw)[:16] + ".zip")
    fd = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as packed:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o600 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            packed.writestr(info, data)
    metadata = {"archive": str(archive), "archive_sha256": sha(archive.read_bytes()),
                "bundle_sha256": sha(raw), "files": sorted(files), "bytes": archive.stat().st_size,
                "production_changed": False, "gate_b_created": False}
    print(json.dumps(metadata))
    return metadata


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("repository")
    parser.add_argument("--observation", required=True)
    parser.add_argument("--stage2-receipt", required=True)
    parser.add_argument("--output-directory", required=True)
    parser.add_argument("--routing-evidence")
    parser.add_argument("--catalog-reconciliation-observer")
    args = parser.parse_args()
    build(args.repository, observation=args.observation,
          stage2_receipt=args.stage2_receipt, output_directory=args.output_directory, routing_evidence=args.routing_evidence,
          catalog_reconciliation_observer=args.catalog_reconciliation_observer)
