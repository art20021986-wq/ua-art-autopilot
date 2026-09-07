#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import unittest

import controller


class RecoveryContractTests(unittest.TestCase):
    def test_selects_only_exact_production_webapp(self):
        body = json.dumps([
            {"domain_name": "preview.uaart.com.ua", "enabled": True},
            {"domain_name": "www.uaart.com.ua", "enabled": True},
        ]).encode()
        selected = controller.API.select_exact(body)
        self.assertEqual(controller.API.domain_of(selected), controller.DOMAIN)

    def test_rejects_ambiguous_or_missing_webapp(self):
        with self.assertRaises(controller.RecoveryError):
            controller.API.select_exact(b"[]")
        duplicate = json.dumps([
            {"domain": controller.DOMAIN}, {"hostname": controller.DOMAIN}
        ]).encode()
        with self.assertRaises(controller.RecoveryError):
            controller.API.select_exact(duplicate)

    def test_accepts_pythonanywhere_domain_mapping(self):
        body = json.dumps({
            "www.uaart.com.ua": {"enabled": True, "python_version": "3.10"}
        }).encode()
        selected = controller.API.select_exact(body)
        self.assertEqual(selected["domain_name"], controller.DOMAIN)

    def test_checkpoint_drops_untrusted_fields(self):
        state = controller.API.safe_state({
            "domain_name": controller.DOMAIN,
            "enabled": True,
            "python_version": "3.10",
            "source_directory": "/home/Carix/video",
            "virtualenv_path": "/home/Carix/.virtualenvs/site",
            "password": "must-not-leak",
        })
        encoded = controller.canonical(state)
        self.assertEqual(controller.sha(encoded), controller.sha(encoded))
        self.assertNotIn(b"must-not-leak", encoded)

    def test_html_health_contract(self):
        body = b"<!doctype html><html><body>" + b"x" * 600 + b"</body></html>"
        value = controller.validate_page(
            controller.CORE_URLS[0], 200, controller.CORE_URLS[0], body
        )
        self.assertEqual(value["http"], 200)
        with self.assertRaises(controller.RecoveryError):
            controller.validate_page(
                controller.CORE_URLS[0], 503, controller.CORE_URLS[0], body
            )

    def test_apex_must_redirect_to_exact_www_index(self):
        body = b"<!doctype html><html><body>" + b"x" * 600 + b"</body></html>"
        allowed = controller.validate_page(
            controller.APEX_URL,
            200,
            "https://www.uaart.com.ua/video/index.html?_uaart_probe=test",
            body,
            expected_path=controller.APEX_FINAL_PATH,
        )
        self.assertEqual(allowed["expected_final_path"], "/video/index.html")
        for final_url in (
            "https://uaart.com.ua/",
            "http://www.uaart.com.ua/video/index.html",
            "https://www.uaart.com.ua/video/katalog.html",
            "https://preview.uaart.com.ua/video/index.html",
        ):
            with self.subTest(final_url=final_url):
                with self.assertRaises(controller.RecoveryError):
                    controller.validate_page(
                        controller.APEX_URL,
                        200,
                        final_url,
                        body,
                        expected_path=controller.APEX_FINAL_PATH,
                    )

    def test_cache_buster_and_spaced_round_contract(self):
        first = controller.cache_busted(controller.CORE_URLS[0], "round-1")
        second = controller.cache_busted(controller.CORE_URLS[0], "round-2")
        self.assertNotEqual(first, second)
        self.assertIn("_uaart_probe=round-1", first)
        self.assertGreaterEqual(controller.ROUND_INTERVAL_SECONDS, 15)
        self.assertEqual(len(controller.CORE_URLS), 5)
        self.assertEqual(len(controller.HEALTH_TARGETS), 6)

    def test_api_scope_is_exact(self):
        self.assertEqual(
            {controller.WEBAPPS_URL, controller.RELOAD_URL},
            {
                "https://www.pythonanywhere.com/api/v0/user/Carix/webapps/",
                "https://www.pythonanywhere.com/api/v0/user/Carix/webapps/www.uaart.com.ua/reload/",
            },
        )

    def test_all_package_modules_compile(self):
        for path in pathlib.Path(__file__).resolve().parent.glob("*.py"):
            compile(path.read_text(encoding="utf-8"), path.name, "exec")


if __name__ == "__main__":
    unittest.main(verbosity=2)
