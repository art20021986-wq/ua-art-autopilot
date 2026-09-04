#!/usr/bin/env python3
"""Offline contract tests for UA111; no production or public writes."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import pathlib
import sqlite3
import sys
import tempfile
import types
import urllib.error

import controller
import integration_patcher
import source_policy
import vin_spec_service as service


HERE = pathlib.Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
UA099_SPEC_CANDIDATES = (
    REPO_ROOT / "cloud/task_099_site_crm_repair/ua_additional_spec.py",
    pathlib.Path("/workspace/scratch/9e6d78993a0b/repo/cloud/task_099_site_crm_repair/ua_additional_spec.py"),
)


def require(condition: object, label: str) -> None:
    if not condition:
        raise AssertionError(label)


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_main(path: pathlib.Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE cars(
                id INTEGER PRIMARY KEY,
                auto_number TEXT UNIQUE,
                vin TEXT,
                marka TEXT,
                model TEXT,
                god INTEGER,
                dvigatel TEXT,
                toplivo TEXT,
                status TEXT,
                mileage_km INTEGER,
                published INTEGER DEFAULT 0,
                price INTEGER
            );
            INSERT INTO cars VALUES
              (1,'UA-0001','WDDMH0BBXDV171918','Mercedes-Benz','B-Class',2013,
               '1800 см3, Дизель','Дизель','sea_transit',139000,1,11500),
              (2,'UA-0002','KNAGN4AD5F5067209','Kia','K5',2015,
               '2000 см3, Газ','LPI','ge_waiting',98000,0,9000),
              (3,'UA-0003','WDDMI0BBXDV171918','Mercedes-Benz','B-Class',2013,
               '1800 см3, Дизель','Дизель','sea_transit',100000,1,10000);
            CREATE TABLE additional_specification(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                car_uid TEXT NOT NULL,
                field_key TEXT NOT NULL,
                field_value TEXT NOT NULL,
                normalized_value TEXT,
                source TEXT,
                source_url TEXT,
                confidence REAL,
                is_price_field INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(car_uid,field_key)
            );
            CREATE TABLE additional_specification_meta(
                car_uid TEXT NOT NULL,
                field_key TEXT NOT NULL,
                label_ru TEXT,
                category TEXT,
                unit TEXT,
                evidence_count INTEGER,
                source_domains_json TEXT,
                verification_status TEXT,
                model_match_score REAL,
                is_manual INTEGER,
                is_visible INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(car_uid,field_key)
            );
            INSERT INTO additional_specification
              (car_uid,field_key,field_value,normalized_value,source,source_url,confidence,is_price_field)
              VALUES('UA-0001','legacy_boot','488 л','488 л','LEGACY',NULL,.9,0);
            INSERT INTO additional_specification_meta
              (car_uid,field_key,label_ru,category,unit,evidence_count,source_domains_json,
               verification_status,model_match_score,is_manual,is_visible)
              VALUES('UA-0001','legacy_boot','Объём багажника','capacity','л',1,'[]',
                     'MANUAL_VERIFIED',1,1,1);
            """
        )


def fake_enrich(car: dict[str, object]) -> dict[str, object]:
    url = "https://www.auto-data.net/ru/verified-test"
    return {
        "status": "READY",
        "sources": {
            "vpic.nhtsa.dot.gov": {"status": "PASS"},
            "auto-data.net": {"status": "PASS"},
            "carwiki.co.kr": {"status": "NO_CONFIDENT_MATCH"},
        },
        "facts": [
            {
                "field_key": "length",
                "label_ru": "Длина",
                "category": "dimensions",
                "display_value": "4359 мм",
                "unit": "мм",
                "confidence": 0.94,
                "evidence_count": 1,
                "source_domains": ["auto-data.net"],
                "source_urls": [url],
            },
            {
                "field_key": "wheelbase",
                "label_ru": "Колёсная база",
                "category": "dimensions",
                "display_value": "2699 мм",
                "unit": "мм",
                "confidence": 0.94,
                "evidence_count": 1,
                "source_domains": ["auto-data.net"],
                "source_urls": [url],
            },
            {
                "field_key": "price",
                "label_ru": "Цена",
                "category": "additional",
                "display_value": "10000 $",
                "confidence": 1,
                "source_domains": ["auto-data.net"],
                "source_urls": [url],
            },
            {
                "field_key": "brand",
                "label_ru": "Марка",
                "category": "additional",
                "display_value": "Wrong",
                "confidence": 1,
                "source_domains": ["auto-data.net"],
                "source_urls": [url],
            },
        ],
    }


def load_patched_spec(main: pathlib.Path, sidecar: pathlib.Path, target: pathlib.Path):
    ua099_spec = next((path for path in UA099_SPEC_CANDIDATES if path.is_file()), None)
    if ua099_spec is None:
        raise AssertionError("UA099 source fixture missing")
    source = ua099_spec.read_text(encoding="utf-8")
    target.write_text(integration_patcher.patch_additional_spec(source), encoding="utf-8")
    os.environ["UA_ART_CRM_DB"] = str(main)
    os.environ["UA_ART_SPEC_DB"] = str(sidecar)
    module_spec = importlib.util.spec_from_file_location("ua110_test_additional_spec", target)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_synthetic_extractors() -> None:
    mercedes = {
        "vin": "WDDMH0BBXDV171918", "brand": "Mercedes-Benz", "model": "B-Class",
        "year": "2013", "fuel": "Дизель", "engine_cc": 1800,
    }
    auto_html = """<html><body><h1>Mercedes-Benz B-Class 2013 1.8 CDI diesel</h1>
      <table><tr><th>Длина</th><td>4359 мм</td></tr>
      <tr><th>Расход топлива, смешанный цикл</th><td>4.4 л/100 км</td></tr>
      <tr><th>Цена</th><td>20000 $</td></tr></table></body></html>""".encode()
    score, facts = source_policy.extract_page_facts(
        mercedes, "https://www.auto-data.net/ru/mercedes-test", auto_html
    )
    require(score >= 0.64, "auto-data match")
    require({item.field_key for item in facts} == {"length", "combined_fuel_consumption"}, "auto-data fields")
    kia = {"vin": "KNAGN4AD5F5067209", "brand": "Kia", "model": "K5", "year": "2015", "fuel": "LPI", "engine_cc": 2000}
    carwiki_html = """<html><body><h1>2015 기아 K5 LPI 2.0</h1><table>
      <tr><th>전장</th><td>4855 mm</td></tr><tr><th>최고출력</th><td>180 PS</td></tr>
      <tr><th>복합연비</th><td>10 km/ℓ</td></tr></table></body></html>""".encode()
    score, facts = source_policy.extract_page_facts(
        kia, "https://www.carwiki.co.kr/model/10000_2015/k5", carwiki_html
    )
    require(score >= 0.68, "carwiki match")
    require([item.field_key for item in facts] == ["length"], "mixed-trim guard")
    exact_html = """<html><body><h1>2015 기아 K5 LPI 2.0</h1><div>제원</div><table>
      <tr><th>전장</th><td>4855 mm</td></tr><tr><th>엔진형식</th><td>누우 2.0 LPi</td></tr>
      <tr><th>최고출력</th><td>157 PS</td></tr><tr><th>연료</th><td>LPG</td></tr>
      <tr><th>복합연비</th><td>9.6 km/ℓ</td></tr><tr><th>배기량</th><td>1,999 cc</td></tr>
      </table><div>기본사양</div></body></html>""".encode()
    _, facts = source_policy.extract_page_facts(
        kia, "https://www.carwiki.co.kr/model/10000_2015/k5", exact_html
    )
    require(
        {item.field_key for item in facts} == {"length", "engine_code", "maximum_power", "combined_fuel_economy"},
        "exact powertrain segment",
    )


def test_ten_source_profiles() -> None:
    expected_sources = {
        "vpic.nhtsa.dot.gov", "auto-data.net", "carwiki.co.kr", "auto.danawa.com",
        "carisyou.com", "ultimatespecs.com", "automobile-catalog.com", "cars-data.com",
        "carfolio.com", "encycarpedia.com",
    }
    require(set(source_policy.SOURCE_DOMAINS) == expected_sources, "ten-source allowlist")
    fleet = (
        ("UA-0001", "WDDZF0EB7HA053001", "Mercedes-Benz", "E 220", 2017, "Дизель", 1950),
        ("UA-0002", "WDD2452322J561014", "Mercedes-Benz", "B-Class", 2010, "Бензин", 1700),
        ("UA-0003", "KNAGS416BLA375484", "Kia", "K5", 2019, "LPI", 2000),
        ("UA-0004", "KNAGS416BLA363849", "Kia", "K5", 2019, "LPI", 2000),
        ("UA-0005", "WDDMH0BBXDV171918", "Mercedes-Benz", "B-Class", 2013, "Дизель", 1800),
        ("UA-0006", "KNAGS416BLA359954", "Kia", "K5", 2019, "LPI", 2000),
        ("UA-0007", "WDD2452322J724006", "Mercedes-Benz", "B-Class", 2011, "Бензин", 1700),
        ("UA-0008", "WDD2452322J540158", "Mercedes-Benz", "B-Class", 2009, "Бензин", 1700),
        ("UA-0009", "KNAGU416BJA242741", "Kia", "K5", 2018, "Газ/LPI", 2000),
        ("UA-0010", "KNAGU416BKA324445", "Kia", "K5", 2018, "Газ/LPI", 2000),
        ("UA-0011", "KMHE341DBKA544289", "Hyundai", "Sonata", 2018, "LPI", 2000),
        ("UA-0012", "KNAGU416BJA244187", "Kia", "K5", 2018, "LPI", 2000),
        ("UA-0013", "WDDMH0JB6GN142530", "Mercedes-Benz", "B-Class", 2015, "Дизель", 2143),
        ("UA-0014", "KNAGS415GGA068770", "Kia", "K5", 2016, "Дизель", 1645),
        ("UA-0015", "KMHE341DBJA475862", "Hyundai", "Sonata", 2018, "Газ/LPI", 1999),
        ("UA-0016", "KNAGS416BHA141028", "Kia", "K5", 1999, "Газ/LPI", 1999),
    )

    def offline(*_args, **_kwargs):
        raise OSError("offline fixture")

    for uid, vin, brand, model, year, fuel, engine_cc in fleet:
        result = source_policy.enrich({
            "car_uid": uid, "vin": vin, "brand": brand, "model": model,
            "year": year, "fuel": fuel, "engine_cc": engine_cc,
        }, opener=offline)
        require(result["status"] == "READY", "profile ready " + uid)
        require(bool(result["profile_id"]), "profile identity " + uid)
        require(len(result["facts"]) >= 10, "profile depth " + uid)
        require(len(result["sources"]) == 10, "source status coverage " + uid)
        for fact in result["facts"]:
            require(fact["field_key"] not in source_policy.BLOCKED_PRIMARY_KEYS, "primary leak " + uid)
            require(not source_policy.PRICE_RE.search(fact["display_value"]), "price leak " + uid)
            require(all(item in expected_sources for item in fact["source_domains"]), "provenance " + uid)
    require(source_policy.vin_model_year("KNAGS416BHA141028") == 2017, "VIN lookup year")
    require(source_policy.lookup_years({"vin": "KNAGS416BHA141028", "year": 1999})[0] == "2017", "year fallback")

    high = source_policy.Fact(
        "maximum_power", "Максимальная мощность", "engine", "151 л.с.", "", .88,
        "auto.danawa.com", "https://auto.danawa.com/auto/?Work=model",
    )
    low_a = source_policy.Fact(
        "maximum_power", "Максимальная мощность", "engine", "160 л.с.", "", .99,
        "carfolio.com", "https://www.carfolio.com/test",
    )
    low_b = source_policy.Fact(
        "maximum_power", "Максимальная мощность", "engine", "160 л.с.", "", .99,
        "encycarpedia.com", "https://www.encycarpedia.com/test",
    )
    require(source_policy.deduplicate([low_a, low_b, high])[0]["display_value"] == "151 л.с.", "priority conflict")


def test_controller_transport() -> None:
    responses = [504, 504, 200]

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read(_limit: int) -> bytes:
            return b"ok"

    def fake_open(request, timeout=0):
        del timeout
        code = responses.pop(0)
        if code != 200:
            raise urllib.error.HTTPError(
                request.full_url, code, "transient", {}, io.BytesIO(b"transient")
            )
        return Response()

    original_open, original_sleep = controller.urllib.request.urlopen, controller.time.sleep
    try:
        controller.urllib.request.urlopen = fake_open
        controller.time.sleep = lambda _seconds: None
        require(
            controller.API("test-token").request("GET", "https://example.invalid") == (200, b"ok"),
            "transient API retry",
        )

        class FakeAPI(controller.API):
            def __init__(self):
                self.deleted = []
                self.reads = [
                    json.dumps({"invocation": "old"}).encode(),
                    json.dumps({"invocation": "run-12345678", "status": "PASS"}).encode(),
                ]

            def delete_file(self, path):
                self.deleted.append(path)

            def create_trigger(self, command, description):
                del command, description
                return "schedule", 7

            def read(self, path, missing=False):
                del path, missing
                return self.reads.pop(0)

            def delete_trigger(self, trigger):
                self.deleted.append(trigger)

        fake = FakeAPI()
        receipt = "/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin/test.json"
        result = fake.run_remote("cmd", "task111", receipt, "run-12345678", 30)
        require(result["invocation"] == "run-12345678", "invocation receipt identity")
        require(fake.deleted == [receipt, receipt, ("schedule", 7)], "stale receipt cleanup")
    finally:
        controller.urllib.request.urlopen = original_open
        controller.time.sleep = original_sleep


def run() -> None:
    test_synthetic_extractors()
    test_ten_source_profiles()
    test_controller_transport()
    with tempfile.TemporaryDirectory(prefix="ua111-contract-") as folder:
        root = pathlib.Path(folder)
        main = root / "crm.db"
        sidecar = root / "vin_specs.db"
        create_main(main)
        service.MAIN_DB = main
        service.SPEC_DB = sidecar
        migrated = service.migrate_legacy_once()
        require(migrated == {"facts": 1, "meta": 1}, "legacy migration")
        cars_before = sha(main)
        scan = service.scan_new_vins()
        require(scan["valid_vins"] == 2 and scan["queued"] == 2, "valid VIN scanner")
        require(sha(main) == cars_before, "scanner changed CRM")

        with service.connect_spec(False) as conn:
            conn.execute(
                """UPDATE vin_spec_jobs SET status='RUNNING',attempts=3,
                   started_at='2000-01-01T00:00:00Z'
                   WHERE car_uid='UA-0001'"""
            )
            conn.commit()
        require(service.recover_interrupted_jobs() == 1, "stale job recovery")
        with service.connect_spec(True) as conn:
            recovered = conn.execute(
                "SELECT status,attempts FROM vin_spec_jobs WHERE car_uid='UA-0001'"
            ).fetchone()
        require(tuple(recovered) == ("PENDING", 0), "stale retry budget recovery")
        with service.connect_spec(False) as conn:
            conn.execute(
                "UPDATE vin_spec_jobs SET status='PROCESSING',started_at=? WHERE car_uid='UA-0002'",
                (service.utc_now(),),
            )
            conn.commit()
        full_requeue = service.requeue_all_current_vins()
        require(
            full_requeue["valid_vins"] == 2 and full_requeue["queued"] == 2,
            "full current VIN requeue",
        )
        with service.connect_spec(True) as conn:
            statuses = {str(row[0]) for row in conn.execute(
                "SELECT status FROM vin_spec_jobs WHERE policy_version=?",
                (source_policy.POLICY_VERSION,),
            )}
        require(statuses == {"PENDING"}, "interrupted job remained outside queue")

        published: list[str] = []
        publisher = types.ModuleType("publikaciya")
        publisher.opublikovat = lambda uid: (published.append(uid) is None, "updated")
        sys.modules["publikaciya"] = publisher
        processed = service.process_backlog(enricher=fake_enrich)
        require(len(processed) == 2, "backlog count")
        require(published == ["UA-0001"], "published-only refresh")
        require(sha(main) == cars_before, "enrichment changed CRM")
        require(service.scan_new_vins()["queued"] == 0, "idempotent scan")

        with service.connect_spec(True) as conn:
            keys = {row[0] for row in conn.execute(
                "SELECT field_key FROM additional_specification WHERE car_uid='UA-0001'"
            )}
            rejected = conn.execute(
                "SELECT COUNT(*) FROM additional_specification_rejections"
            ).fetchone()[0]
        require(keys == {"legacy_boot", "length", "wheelbase"}, "sidecar-only facts")
        require(rejected >= 4, "price/primary rejection audit")

        module = load_patched_spec(main, sidecar, root / "ua_additional_spec.py")
        page = module.render_public_block("UA-0001")
        require("4359 мм" in page and "488 л" in page, "public block values")
        require("auto-data.net" not in page and "http" not in page and "$" not in page, "public provenance/price leak")
        length = next(row for row in module.fetch_specs("UA-0001", True) if row["field_key"] == "length")
        module.set_manual_value(length["id"], "UA-0001", "4360 мм", actor_id=7)
        service._store_facts("UA-0001", fake_enrich({})["facts"])
        require(module.get_spec(length["id"], "UA-0001")["field_value"] == "4360 мм", "manual lock")

        with sqlite3.connect(main) as conn:
            conn.execute(
                "INSERT INTO cars VALUES(4,'UA-0004','KMHE341DBJA500001','Hyundai','Sonata',2018,'2000 см3, Газ','LPI','sea_transit',70000,0,10000)"
            )
        future_baseline = sha(main)
        future = service.scan_new_vins()
        require(future["queued"] == 1 and "UA-0004" in future["card_uids"], "future VIN queue")
        require(sha(main) == future_baseline, "future scan changed CRM")

        with sqlite3.connect(main) as conn:
            conn.execute("UPDATE cars SET vin='WDDMH0BBXDV171919' WHERE auto_number='UA-0001'")
        corrected_baseline = sha(main)
        corrected = service.scan_new_vins()
        require(corrected["queued"] == 1, "corrected VIN queue")
        require(sha(main) == corrected_baseline, "corrected VIN scan changed CRM")
        with service.connect_spec(True) as conn:
            auto_count = conn.execute(
                "SELECT COUNT(*) FROM additional_specification WHERE car_uid='UA-0001' AND field_key='wheelbase'"
            ).fetchone()[0]
            manual_state = conn.execute(
                "SELECT is_visible,verification_status FROM additional_specification_meta WHERE car_uid='UA-0001' AND field_key='legacy_boot'"
            ).fetchone()
        require(auto_count == 0, "old VIN auto facts survived")
        require(tuple(manual_state) == (0, "VIN_CHANGED_REVIEW"), "old VIN manual facts not quarantined")

        with service.connect_spec(True) as conn:
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            prices = conn.execute(
                "SELECT COUNT(*) FROM additional_specification WHERE is_price_field<>0 OR lower(field_key) LIKE '%price%'"
            ).fetchone()[0]
        require(quick == "ok" and prices == 0, "sidecar integrity")

        evidence = {
            "status": "PASS",
            "main_crm_unchanged_by_service": True,
            "valid_initial_vins": scan["valid_vins"],
            "processed_initial_cards": len(processed),
            "future_vin_queued": True,
            "corrected_vin_quarantined": True,
            "published_refreshes": published,
            "source_domains": list(source_policy.SOURCE_DOMAINS),
            "price_rows": prices,
            "sidecar_quick_check": quick,
        }
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    run()
