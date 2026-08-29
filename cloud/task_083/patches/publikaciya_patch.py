"""
Patched publikaciya.py (relevant integration section only)

Change summary:
  - Publisher no longer writes primary/diag/catalogs as separate, independent
    steps.
  - Publisher builds all four artifacts (primary HTML, diag HTML, video
    katalog.html, site katalog.html) in memory, then hands them to
    TransactionalPublish.run() as a single atomic unit.
  - Publisher returns a structured result the caller (cars_ui.py) must check.
"""
from publish_transaction_guard import TransactionalPublish
from catalog_stage_guard_core_patch import ensure_diag_placeholder


def publish_car_transactional(car, primary_path, diag_path,
                               video_katalog_path, site_katalog_path,
                               primary_url, diag_url,
                               build_primary_html, build_diag_html,
                               upsert_catalog_entry):
    """
    car: dict with at least vin, stage, category, label fields already
         validated by the caller (no CRM field changes happen here).

    build_primary_html / build_diag_html: callables returning bytes for the
         respective HTML page given `car`.

    upsert_catalog_entry: callable(existing_catalog_bytes, car) -> new_catalog_bytes
         must guarantee the VIN appears exactly once in the returned catalog.
    """
    import os

    vin = car["vin"]

    ok, reason, placeholder_diag_bytes = ensure_diag_placeholder(
        vin, diag_path, car["stage"], car["category"]
    )
    if not ok:
        return {"ok": False, "reason": reason}

    primary_bytes = build_primary_html(car)
    diag_bytes = placeholder_diag_bytes if placeholder_diag_bytes is not None else build_diag_html(car)

    def _read_or_empty(path):
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        return b""

    video_catalog_before = _read_or_empty(video_katalog_path)
    site_catalog_before = _read_or_empty(site_katalog_path)

    video_catalog_after = upsert_catalog_entry(video_catalog_before, car)
    site_catalog_after = upsert_catalog_entry(site_catalog_before, car)

    artifacts = {
        primary_path: primary_bytes,
        diag_path: diag_bytes,
        video_katalog_path: video_catalog_after,
        site_katalog_path: site_catalog_after,
    }
    public_urls = {
        primary_path: primary_url,
        diag_path: diag_url,
    }

    txn = TransactionalPublish(artifacts, public_urls)
    result = txn.run()
    return result.to_dict()
