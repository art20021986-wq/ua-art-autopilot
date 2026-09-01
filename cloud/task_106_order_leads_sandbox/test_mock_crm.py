from __future__ import annotations

import copy
import sqlite3
import unittest
from pathlib import Path

from mock_crm import COUNTRIES, ContractError, ingest, initialize_mock_schema


ROOT = Path(__file__).resolve().parent


def base_payload() -> dict:
    return {
        "contract_version": 1,
        "request_id": "request-0001",
        "source_event_id": "site:request-0001",
        "source_channel": "site",
        "source_url": "https://preview.invalid/podbor.html?strana=canada&lang=uk",
        "lang": "uk",
        "client_name": "Артем",
        "phone": "+380992222020",
        "order_country_code": "canada",
        "order_country_label": "Канада",
        "requested_model": "Lexus RX 350",
        "budget_bucket": "25000-30000",
        "currency": "USD",
        "delivery_country": "Україна",
        "delivery_city": "Київ",
        "consent_at": "2026-09-01T09:00:00Z",
    }


class MockCrmTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        schema = (ROOT / "schema_order_requests.sql").read_text(encoding="utf-8")
        initialize_mock_schema(self.db, schema)

    def tearDown(self) -> None:
        self.db.close()

    def count(self, table: str) -> int:
        return int(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def test_all_eight_countries(self) -> None:
        for index, country in enumerate(COUNTRIES, 1):
            payload = base_payload()
            payload["request_id"] = f"request-country-{index:02d}"
            payload["source_event_id"] = f"site:country:{index:02d}"
            payload["order_country_code"] = country
            ingest(self.db, payload)
        self.assertEqual(self.count("order_requests"), 8)

    def test_three_languages_and_default_uk(self) -> None:
        for index, lang in enumerate(("uk", "ru", "ka"), 1):
            payload = base_payload()
            payload["request_id"] = f"request-lang-{index:02d}"
            payload["source_event_id"] = f"site:lang:{index:02d}"
            payload["lang"] = lang
            ingest(self.db, payload)
        payload = base_payload()
        payload["request_id"] = "request-default-lang"
        payload["source_event_id"] = "site:default-lang"
        payload.pop("lang")
        ingest(self.db, payload)
        values = [row[0] for row in self.db.execute("SELECT lang FROM order_requests ORDER BY id")]
        self.assertEqual(values, ["uk", "ru", "ka", "uk"])

    def test_unknown_values_fail_closed(self) -> None:
        for field, value in (("lang", "ge"), ("order_country_code", "moon")):
            payload = base_payload()
            payload[field] = value
            with self.assertRaises(ContractError):
                ingest(self.db, payload)
        self.assertEqual(self.count("order_requests"), 0)

    def test_duplicate_request_id_creates_one_lead(self) -> None:
        first = ingest(self.db, base_payload())
        second = ingest(self.db, base_payload())
        self.assertEqual(first.status, "created")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(first.order_request_id, second.order_request_id)
        self.assertEqual(self.count("order_requests"), 1)
        self.assertEqual(self.count("clients"), 1)

    def test_duplicate_source_event_creates_one_lead(self) -> None:
        first = base_payload()
        second = copy.deepcopy(first)
        second["request_id"] = "request-0002"
        ingest(self.db, first)
        result = ingest(self.db, second)
        self.assertEqual(result.status, "duplicate")
        self.assertEqual(self.count("order_requests"), 1)

    def test_same_client_can_have_two_requests(self) -> None:
        first = base_payload()
        second = copy.deepcopy(first)
        second.update({
            "request_id": "request-0002",
            "source_event_id": "site:request-0002",
            "order_country_code": "georgia",
            "requested_model": "Toyota Camry",
        })
        a = ingest(self.db, first)
        b = ingest(self.db, second)
        self.assertEqual(a.client_id, b.client_id)
        self.assertEqual(self.count("clients"), 1)
        self.assertEqual(self.count("order_requests"), 2)

    def test_delivery_and_contact_are_required(self) -> None:
        for field in ("delivery_country", "delivery_city", "phone"):
            payload = base_payload()
            payload.pop(field)
            with self.assertRaises(ContractError):
                ingest(self.db, payload)

    def test_telegram_id_is_sufficient_contact_for_bot(self) -> None:
        payload = base_payload()
        payload.update({
            "request_id": "telegram-request-0001",
            "source_event_id": "12345:67890",
            "source_channel": "telegram_bot",
            "tg_user_id": "12345",
        })
        payload.pop("phone")
        result = ingest(self.db, payload)
        self.assertEqual(result.status, "created")

    def test_model_or_vehicle_type_required(self) -> None:
        payload = base_payload()
        payload.pop("requested_model")
        with self.assertRaises(ContractError):
            ingest(self.db, payload)
        payload["vehicle_type"] = "Кросовер"
        self.assertEqual(ingest(self.db, payload).status, "created")

    def test_georgia_is_not_a_catalog_stage(self) -> None:
        payload = base_payload()
        payload["order_country_code"] = "georgia"
        ingest(self.db, payload)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(order_requests)")}
        self.assertNotIn("catalog_stage", columns)
        self.assertEqual(self.db.execute("SELECT order_country_code FROM order_requests").fetchone()[0], "georgia")

    def test_no_cars_table_or_record_is_created(self) -> None:
        ingest(self.db, base_payload())
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("cars", tables)

    def test_payload_copy_does_not_store_direct_contacts(self) -> None:
        ingest(self.db, base_payload())
        payload_json = self.db.execute("SELECT payload_json FROM order_requests").fetchone()[0]
        self.assertNotIn("+380992222020", payload_json)
        self.assertNotIn('"phone"', payload_json)


if __name__ == "__main__":
    unittest.main()

