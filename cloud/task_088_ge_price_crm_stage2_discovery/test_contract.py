#!/usr/bin/env python3
"""Offline safety and evidence tests. No network and no live acceptance claims."""
import ast
import io
import json
import pathlib
import tempfile
import unittest
import urllib.request

import controller as c


SOURCE = b'''SECRET = "never export top-level config"
EDITABLE = [("vin", "Private label"), ("price_uah", "\xd0\xa6\xd0\xb5\xd0\xbd\xd0\xb0 \xd0\xa3\xd0\xba\xd1\x80\xd0\xb0\xd0\xb8\xd0\xbd\xd1\x8b"), ("price_georgia", "\xd0\xa6\xd0\xb5\xd0\xbd\xd0\xb0 \xd0\x93\xd1\x80\xd1\x83\xd0\xb7\xd0\xb8\xd0\xb8")]
MONEY = {"price_uah", "price_georgia"}
LABELS_ALL = {"vin": "Private label", "price_uah": "\xd1\x86\xd0\xb5\xd0\xbd\xd0\xb0 \xd0\xa3\xd0\xba\xd1\x80\xd0\xb0\xd0\xb8\xd0\xbd\xd1\x8b"}
def apply_value(field, value):
    return set_field(field, value)
def register(app):
    app.add_handler(apply_value)
_previous_register = register
def register(app):
    _previous_register(app)
def card_kb(car):
    return car["price_uah"]
def card_kb(car):
    return car["price_georgia"]
def unrelated():
    return "must not export arbitrary source"
'''


def remote_receipt():
    return json.dumps({"task_id": c.STAGE1_ID, "status": "PASS", "site_write": False,
                       "publisher_write": False, "stage2_touched": False,
                       "db": {"column": "price_georgia", "live_transaction_write_readback": "PASS",
                              "rollback_to_original": "PASS", "test_car_id": 999},
                       "unexpected_secret": "must not export receipt fields"}).encode()


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", status=200, url=None, headers=None):
        super().__init__(body)
        self.status = status
        self.url = url
        self.headers = headers or {}
        self.read_calls = 0

    def geturl(self):
        return self.url

    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        self.response.url = self.response.url or request.full_url
        return self.response


class FakeAPI:
    def __init__(self):
        self.get_count = 0
        self.response_body_bytes = 0
        self.paths = []
        self.drift = False

    def read(self, path):
        self.get_count += 1
        self.paths.append(path)
        result = remote_receipt() if path == c.STAGE1_REMOTE_RECEIPT else SOURCE
        if self.drift and path == c.SOURCE_PATHS[0] and self.paths.count(path) == 2:
            result += b"\n# drift"
        self.response_body_bytes += len(result)
        return result

    def backup_exists(self, path):
        self.get_count += 1
        self.paths.append(path)
        return {"path": path, "exists": True, "body_bytes_read": 0, "integrity": "NOT_VERIFIED"}


class ContractTests(unittest.TestCase):
    def setup_tree(self, root):
        request = {"task_id": c.TASK_ID, "production_required": False, "read_only": True,
                   "requested_min_class": "STANDARD", "execution": {
                       "controller_path": c.PACKAGE_REL + "/controller.py",
                       "receipt_path": c.RECEIPT_REL,
                       "evidence_paths": [c.EVIDENCE_REL, c.RECEIPT_REL]}}
        for relative, value in ((c.REQUEST_REL, request), (c.STAGE1_RECEIPT_REL, {
            "task_id": c.STAGE1_ID, "status": "FINISHED", "tests": "PASS"})):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value))
        return {"UAART_TASK_ID": c.TASK_ID, "UAART_REQUEST_PATH": c.REQUEST_REL,
                "UAART_RECEIPT_PATH": c.RECEIPT_REL,
                "UAART_REQUEST_SHA256": c.sha((root / c.REQUEST_REL).read_bytes()),
                "UAART_RUN_ID": "offline-test-fixture"}

    def test_get_only_transport_and_exact_paths(self):
        api = c.ReadOnlyAPI("offline-test-token")
        response = FakeResponse(b"ok")
        opener = FakeOpener(response)
        api._opener = opener
        self.assertEqual(api.read(c.SOURCE_PATHS[0]), b"ok")
        self.assertEqual(opener.requests[0].get_method(), "GET")
        self.assertIsNone(opener.requests[0].data)
        for bad in ("/home/Carix/crm.db", "/home/Carix/config.py", "/home/Carix/../Carix/cars_ui.py",
                    c.SOURCE_PATHS[0] + "?download=1", "https://evil.invalid/file"):
            with self.subTest(bad=bad), self.assertRaises(c.DiscoveryError):
                api.read(bad)
        self.assertEqual(len(opener.requests), 1)
        self.assertFalse(any(hasattr(api, name) for name in ("upload", "delete", "trigger", "post", "run")))

    def test_backup_existence_never_reads_body_even_when_range_ignored(self):
        api = c.ReadOnlyAPI("offline-test-token")
        response = FakeResponse(b"private database contents", status=200)
        opener = FakeOpener(response)
        api._opener = opener
        result = api.backup_exists(c.BACKUP_PATHS[1])
        self.assertEqual(response.read_calls, 0)
        self.assertEqual(result["body_bytes_read"], 0)
        self.assertEqual(result["integrity"], "NOT_VERIFIED")
        self.assertEqual(opener.requests[0].get_header("Range"), "bytes=0-0")
        with self.assertRaises(c.DiscoveryError):
            api.read(c.BACKUP_PATHS[1])

    def test_redirects_and_response_url_change_are_rejected(self):
        request = urllib.request.Request(c.API_BASE + c.SOURCE_PATHS[0])
        for url in ("https://evil.invalid/", c.API_BASE + c.SOURCE_PATHS[0], c.API_BASE + c.SOURCE_PATHS[1]):
            with self.subTest(url=url), self.assertRaises(c.DiscoveryError):
                c.RefuseRedirects().redirect_request(request, None, 302, "Found", {}, url)
        api = c.ReadOnlyAPI("offline-test-token")
        response = FakeResponse(b"must not read", url="https://evil.invalid/")
        api._opener = FakeOpener(response)
        with self.assertRaises(c.DiscoveryError):
            api.read(c.SOURCE_PATHS[0])
        self.assertEqual(response.read_calls, 0)

    def test_limits_and_header_injection(self):
        for token in ("", "has\nnewline", "has space", "x" * 257):
            with self.subTest(token_length=len(token)), self.assertRaises(c.DiscoveryError):
                c.ReadOnlyAPI(token)
        for body, headers in ((b"x" * (c.MAX_SOURCE_BYTES + 1), {}),
                              (b"", {"Content-Length": str(c.MAX_SOURCE_BYTES + 1)}),
                              (b"", {"Content-Encoding": "gzip"})):
            api = c.ReadOnlyAPI("offline-test-token")
            api._opener = FakeOpener(FakeResponse(body, headers=headers))
            with self.assertRaises(c.DiscoveryError):
                api.read(c.SOURCE_PATHS[0])

    def test_selective_sources_keep_redefinitions_and_alias_order(self):
        result = c.inspect_source(SOURCE, c.SOURCE_PATHS[0])
        encoded = json.dumps(result)
        self.assertNotIn("never export top-level config", encoded)
        self.assertNotIn("Private label", encoded)
        self.assertNotIn("must not export arbitrary source", encoded)
        self.assertEqual(len(result["selected_functions"]["register"]), 2)
        self.assertEqual(len(result["selected_functions"]["card_kb"]), 2)
        versions = result["selected_functions"]["register"]
        alias = result["top_level_symbol_aliases"][0]
        self.assertLess(versions[0]["order"], alias["order"])
        self.assertLess(alias["order"], versions[1]["order"])
        self.assertIn("_previous_register(app)", versions[1]["source"])
        self.assertEqual(result["runtime_handler_binding"], "NOT_VERIFIED")

    def test_sensitive_function_sources_are_omitted(self):
        snippets = ["def edit_ask():\n    api_token = read_env()\n    return api_token\n",
                    "def edit_ask():\n    return '" + "abcdefghij" * 5 + "'\n",
                    "def edit_ask():\n    # token=" + "abcdefghij" * 5 + "\n    return None\n",
                    "def edit_ask():\n    return connect(password='smallsecret')\n",
                    "def edit_ask():\n    return {'api_key': 'smallsecret'}\n",
                    "def edit_ask(password='smallsecret'):\n    return None\n",
                    "def edit_ask(*, api_token='smallsecret'):\n    return None\n",
                    "def edit_ask():\n    settings['password'] = 'smallsecret'\n"]
        for source in snippets:
            with self.subTest(case=snippets.index(source)):
                result = c.inspect_source(source.encode(), c.SOURCE_PATHS[0])
                selected = result["selected_functions"]["edit_ask"][0]
                self.assertFalse(selected["source_exported"])
                self.assertNotIn("source", selected)

    def test_remote_stage1_receipt_exports_only_safe_prerequisite(self):
        result = c.remote_stage1_summary(remote_receipt())
        self.assertNotIn("test_car_id", json.dumps(result))
        self.assertNotIn("unexpected_secret", json.dumps(result))
        self.assertEqual(result["live_schema_verification"], "NOT_PERFORMED")
        bad = json.loads(remote_receipt())
        bad["db"]["rollback_to_original"] = "FAIL"
        with self.assertRaises(c.DiscoveryError):
            c.remote_stage1_summary(json.dumps(bad).encode())

    def test_complete_discovery_is_never_stage2_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            env = self.setup_tree(root)
            original = (root / c.STAGE1_RECEIPT_REL).read_bytes()
            api = FakeAPI()
            receipt = c.execute(env, root=root, api=api)
            evidence = json.loads((root / c.EVIDENCE_REL).read_text())
            self.assertEqual(receipt["status"], "FINISHED")
            self.assertEqual(receipt["stage2_acceptance"], "NOT_PERFORMED")
            self.assertEqual(receipt["crm_price_acceptance"], "NOT_PERFORMED")
            self.assertEqual(receipt["target_environment"], "shadow")
            self.assertEqual(receipt["live_source_environment"], "production")
            self.assertEqual(evidence["remote_write_count"], 0)
            self.assertEqual(evidence["current_database_schema"], "NOT_VERIFIED")
            self.assertEqual(api.get_count, 12)
            self.assertEqual(set(api.paths), c.ALL_REMOTE_PATHS)
            self.assertEqual((root / c.STAGE1_RECEIPT_REL).read_bytes(), original)
            with self.assertRaises(c.DiscoveryError):
                c.execute(env, root=root, api=api)
            self.assertEqual(api.get_count, 12)

    def test_identity_and_stage1_fail_before_any_remote_get(self):
        for failure in ("identity", "sha", "prerequisite", "symlink"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                env = self.setup_tree(root)
                if failure == "identity":
                    env["UAART_TASK_ID"] = c.STAGE1_ID
                elif failure == "sha":
                    env["UAART_REQUEST_SHA256"] = "0" * 64
                elif failure == "prerequisite":
                    (root / c.STAGE1_RECEIPT_REL).write_text('{"status":"FAIL"}')
                else:
                    (root / c.RECEIPT_REL).symlink_to(root / c.STAGE1_RECEIPT_REL)
                api = FakeAPI()
                with self.assertRaises(c.DiscoveryError):
                    c.execute(env, root=root, api=api)
                self.assertEqual(api.get_count, 0)
                self.assertFalse((root / c.EVIDENCE_REL).exists())

    def test_source_drift_does_not_create_success_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            env = self.setup_tree(root)
            api = FakeAPI()
            api.drift = True
            with self.assertRaisesRegex(c.DiscoveryError, "SOURCE_CHANGED_DURING_DISCOVERY"):
                c.execute(env, root=root, api=api)
            self.assertFalse((root / c.RECEIPT_REL).exists())
            self.assertFalse((root / c.EVIDENCE_REL).exists())

    def test_no_remote_code_execution_or_mutation_facilities(self):
        tree = ast.parse(pathlib.Path(c.__file__).read_text())
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        self.assertFalse(names & {"eval", "exec", "subprocess", "sqlite3", "shutil"})
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "Request":
                method = [item.value.value for item in node.keywords if item.arg == "method"]
                self.assertEqual(method, ["GET"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
