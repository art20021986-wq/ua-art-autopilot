#!/usr/bin/env python3
"""TASK096 sandbox-only semantic duplicate cleanup.

This helper is intentionally bounded to the TASK096 sandbox. It never writes the
live CRM, site, bot or production paths. Manual rows are never deleted.
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3

import remote_apply as base

RECEIPT = base.DATA_DIR / "receipt_semantic_cleanup.json"


def semantic_key(field_key: str, label: str) -> str:
    key = base.norm_key(field_key)
    text = (key + " " + base.norm_key(label)).lower()
    rules = (
        ("front_track", ("front_track", "track_front", "передняя_колея", "колея_передняя")),
        ("rear_track", ("rear_track", "track_rear", "задняя_колея", "колея_задняя")),
        ("wheelbase", ("wheelbase", "wheel_base", "колесная_база", "колёсная_база")),
        ("length", ("overall_length", "vehicle_length", "body_length", "длина_автомобиля", "габаритная_длина", "длина")),
        ("width", ("overall_width", "vehicle_width", "body_width", "ширина_автомобиля", "габаритная_ширина", "ширина")),
        ("height", ("overall_height", "vehicle_height", "body_height", "высота_автомобиля", "габаритная_высота", "высота")),
        ("max_power", ("max_power", "maximum_power", "engine_power", "максимальная_мощность")),
        ("max_torque", ("max_torque", "maximum_torque", "engine_torque", "максимальный_крутящий_момент")),
        ("fuel_tank_capacity", ("fuel_tank_capacity", "fuel_tank", "tank_capacity", "объем_топливного_бака", "объём_топливного_бака")),
        ("kerb_weight", ("kerb_weight", "curb_weight", "снаряженная_масса", "снаряжённая_масса")),
        ("co2_emissions", ("co2_emissions", "co2_emission", "выброс_co2", "выбросы_co2")),
        ("combined_fuel_economy", ("combined_fuel_economy", "combined_consumption", "смешанный_расход", "расход_топлива_смешанный_цикл")),
        ("urban_fuel_economy", ("urban_fuel_economy", "city_consumption", "городской_расход")),
        ("highway_fuel_economy", ("highway_fuel_economy", "highway_consumption", "загородный_расход")),
        ("engine_configuration", ("engine_configuration", "engine_layout", "конфигурация_двигателя")),
        ("electric_power_steering", ("electric_power_steering", "power_steering", "усилитель_рулевого_управления")),
    )
    for canonical, aliases in rules:
        if key == canonical or any(alias in text for alias in aliases):
            return canonical
    return key


def cars_hash(conn: sqlite3.Connection) -> str:
    return base.cars_snapshot(conn)["sha256"]


def run() -> dict:
    sandbox = base.find_sandbox()
    live_before = base.live_snapshot()
    removed = []
    groups_seen = 0
    with base.connect_rw(sandbox) as conn:
        if not base.table_exists(conn, "additional_specification"):
            raise RuntimeError("ADDITIONAL_SPEC_TABLE_MISSING")
        base.ensure_enrichment_tables(conn)
        before = cars_hash(conn)
        rows = conn.execute(
            """
            SELECT a.id,a.car_uid,a.field_key,a.field_value,a.confidence,
                   COALESCE(m.label_ru,a.field_key) AS label_ru,
                   COALESCE(m.is_manual,0) AS is_manual
              FROM additional_specification a
              LEFT JOIN additional_specification_meta m
                ON m.car_uid=a.car_uid AND m.field_key=a.field_key
             WHERE a.is_price_field=0
             ORDER BY a.car_uid,a.id
            """
        ).fetchall()
        grouped = {}
        for row in rows:
            item = dict(row)
            skey = semantic_key(item["field_key"], item["label_ru"])
            grouped.setdefault((item["car_uid"], skey), []).append(item)
        for (uid, skey), items in grouped.items():
            if len(items) < 2:
                continue
            groups_seen += 1
            manual = [item for item in items if int(item.get("is_manual") or 0) == 1]
            if len(manual) > 1:
                raise RuntimeError("MANUAL_SEMANTIC_DUPLICATE:%s:%s" % (uid, skey))
            keep = manual[0] if manual else sorted(
                items, key=lambda item: (-float(item.get("confidence") or 0.0), int(item["id"]))
            )[0]
            for item in items:
                if int(item["id"]) == int(keep["id"]):
                    continue
                if int(item.get("is_manual") or 0) == 1:
                    raise RuntimeError("MANUAL_ROW_DELETE_FORBIDDEN")
                conn.execute("DELETE FROM additional_specification WHERE id=?", (int(item["id"]),))
                remains = conn.execute(
                    "SELECT 1 FROM additional_specification WHERE car_uid=? AND field_key=? LIMIT 1",
                    (uid, item["field_key"]),
                ).fetchone()
                if not remains:
                    conn.execute(
                        "DELETE FROM additional_specification_meta WHERE car_uid=? AND field_key=? AND COALESCE(is_manual,0)=0",
                        (uid, item["field_key"]),
                    )
                removed.append({"car_uid": uid, "semantic_key": skey, "field_key": item["field_key"]})
        after_rows = conn.execute(
            """
            SELECT a.car_uid,a.field_key,COALESCE(m.label_ru,a.field_key) AS label_ru
              FROM additional_specification a
              LEFT JOIN additional_specification_meta m
                ON m.car_uid=a.car_uid AND m.field_key=a.field_key
             WHERE a.is_price_field=0
            """
        ).fetchall()
        seen = set()
        duplicates = []
        for row in after_rows:
            token = (row["car_uid"], semantic_key(row["field_key"], row["label_ru"]))
            if token in seen:
                duplicates.append("%s:%s" % token)
            seen.add(token)
        if duplicates:
            conn.rollback()
            raise RuntimeError("SEMANTIC_DUPLICATES_REMAIN:" + ",".join(sorted(set(duplicates))[:20]))
        after = cars_hash(conn)
        if before != after:
            conn.rollback()
            raise RuntimeError("SANDBOX_MAIN_CARS_CHANGED")
        quick = conn.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            conn.rollback()
            raise RuntimeError("SANDBOX_QUICK_CHECK_FAIL")
        preview = base.render_preview(conn, "UA-0015")
        total_rows = int(conn.execute("SELECT COUNT(*) FROM additional_specification").fetchone()[0])
        conn.commit()
    base.atomic_text(base.DATA_DIR / "ua0015_preview.html", preview)
    live_after = base.live_snapshot()
    if live_before["cars_sha256"] != live_after["cars_sha256"]:
        raise RuntimeError("LIVE_CRM_CHANGED_DURING_SEMANTIC_CLEANUP")
    result = {
        "contract_id": base.CONTRACT_ID,
        "task_id": base.TASK_ID,
        "phase": "SEMANTIC_DEDUP_SANDBOX",
        "status": "PASS",
        "semantic_dedup_pass": True,
        "duplicate_groups_seen": groups_seen,
        "rows_removed": len(removed),
        "removed": removed,
        "additional_spec_total_rows": total_rows,
        "sandbox_db_name": sandbox.name,
        "sandbox_quick_check": "ok",
        "production_touched": False,
        "live_crm_write": False,
        "main_fields_changed": False,
        "public_path_write": False,
        "bot_code_changed": False,
        "services_restarted": False,
        "autopublication": False,
        "purchase_price_extracted": False,
        "purchase_price_logged": False,
        "purchase_price_uploaded": False,
        "production_authorized": False,
    }
    base.atomic_json(RECEIPT, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        value = {
            "contract_id": base.CONTRACT_ID,
            "task_id": base.TASK_ID,
            "phase": "SEMANTIC_DEDUP_SANDBOX",
            "status": "FAIL",
            "errors": [type(exc).__name__ + ":" + str(exc)[:700]],
            "production_touched": False,
            "live_crm_write": False,
            "main_fields_changed": False,
            "public_path_write": False,
            "bot_code_changed": False,
            "services_restarted": False,
            "autopublication": False,
            "purchase_price_extracted": False,
            "purchase_price_logged": False,
            "purchase_price_uploaded": False,
            "production_authorized": False,
        }
        base.atomic_json(RECEIPT, value)
        print(json.dumps(value, ensure_ascii=False, sort_keys=True))
        raise SystemExit(1)
