"""Offline verification of GET scope, safe helpers and full-file AST proof."""
import ast
import importlib.util
import io
import json
import pathlib
import tempfile
import types
import unittest
from unittest import mock
import urllib.request

import controller as c

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = '''from __future__ import annotations
DO_NOT_EXECUTE = open("downloaded-source-must-never-run", "w")
EDITABLE = [("price_uah", "Цена Украины"), ("price_georgia", "Цена Грузии")]
def remember_price(card_id, value):
    return value
def unrelated():
    return "entire original file must be retained"
def apply_value(card_id, field, raw, actor_id):
    """Existing validation."""
    return legacy_apply(card_id, field, raw, actor_id)
async def auto_catch(msg, card, actor_id, context):
    return await legacy_auto(msg, card, actor_id, context)
async def catch_message(update, context):
    msg = update.message
    user_id = update.effective_user.id
    input_text = msg.text
    thinking = None
    wait = context.user_data.get("car_wait")
    if not wait:
        return await auto_catch(msg, card, user_id, context)
    return legacy_route(wait, input_text)
'''
DB = b'''PRIVATE_CONFIG = "must not export arbitrary configuration"
class Soedinenie:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.commit()
def connect():
    return Soedinenie()
def log_action(card_id, field, old, new):
    return (card_id, field, old, new)
def update_card_field(card_id, field, value):
    return (card_id, field, value)
'''
PARSER = b'''MUST_NOT_EXECUTE = missing_runtime_global()
def parse_sale_price_message(text):
    return {"price_uah": float(text)}
'''


def remote_receipt():
    return json.dumps({"task_id": c.STAGE1_ID, "status": "PASS", "site_write": False,
        "publisher_write": False, "stage2_touched": False,
        "db": {"column": "price_georgia", "live_transaction_write_readback": "PASS",
               "rollback_to_original": "PASS", "test_car_id": 999},
        "private": "must never export"}).encode()


class FakeResponse(io.BytesIO):
    def __init__(self, body=b"", status=200, url=None, headers=None):
        super().__init__(body)
        self.status, self.url, self.headers = status, url, headers or {}
    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, response):
        self.response, self.requests = response, []
    def open(self, request, timeout):
        self.requests.append(request)
        self.response.url = self.response.url or request.full_url
        return self.response


class FakeAPI:
    def __init__(self, drift=False):
        self.get_count = self.response_body_bytes = 0
        self.paths, self.drift = [], drift
    def read(self, path):
        self.get_count += 1
        self.paths.append(path)
        data = {c.STAGE1_REMOTE_RECEIPT: remote_receipt(), c.SOURCE_PATHS[0]: FIXTURE.encode(),
                c.SOURCE_PATHS[1]: DB, c.SOURCE_PATHS[2]: PARSER}[path]
        if self.drift and path == c.SOURCE_PATHS[0] and self.paths.count(path) == 2:
            data += b"\n# changed"
        self.response_body_bytes += len(data)
        return data


def local_patcher():
    spec = importlib.util.spec_from_file_location("offline_local_patcher", ROOT / c.PATCHER_REL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ContractTests(unittest.TestCase):
    def setup_tree(self, root):
        hashes = {}
        for relative in c.DEPENDENCY_PATHS | {c.STAGE1_RECEIPT_REL}:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (ROOT / relative).read_bytes()
            path.write_bytes(data)
            hashes[relative] = c.sha(data)
        request = {"task_id": c.TASK_ID, "production_required": False, "read_only": True,
                   "requested_min_class": "STANDARD", "execution": {
                       "controller_path": c.PACKAGE_REL + "/controller.py",
                       "receipt_path": c.RECEIPT_REL,
                       "evidence_paths": [c.EVIDENCE_REL, c.RECEIPT_REL],
                       "dependency_paths": sorted(c.DEPENDENCY_PATHS), "file_sha256": hashes}}
        path = root / c.REQUEST_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(request))
        return {"UAART_TASK_ID": c.TASK_ID, "UAART_REQUEST_PATH": c.REQUEST_REL,
                "UAART_RECEIPT_PATH": c.RECEIPT_REL, "UAART_REQUEST_SHA256": c.sha(path.read_bytes()),
                "UAART_RUN_ID": "offline-verify"}

    def test_transport_only_allows_explicit_gets_without_database_urls(self):
        api = c.ReadOnlyAPI("offline-token")
        api._opener = FakeOpener(FakeResponse(b"ok"))
        self.assertEqual(api.read(c.SOURCE_PATHS[2]), b"ok")
        req = api._opener.requests[0]
        self.assertEqual(req.get_method(), "GET")
        self.assertIsNone(req.data)
        self.assertFalse(c.BACKUP_PATHS)
        for path in ("/home/Carix/crm.db", "/home/Carix/config.py", "/home/Carix/../Carix/cars_ui.py",
                     c.SOURCE_PATHS[0] + "?download=1", "/home/Carix/autopilot_inbox/receipt.json"):
            with self.subTest(path=path), self.assertRaises(c.DiscoveryError):
                api.read(path)
        self.assertFalse(any(hasattr(api, name) for name in ("upload", "delete", "trigger", "run", "post")))

    def test_redirects_size_encoding_and_token_injection_fail(self):
        request = urllib.request.Request(c.API_BASE + c.SOURCE_PATHS[0])
        with self.assertRaises(c.DiscoveryError):
            c.RefuseRedirects().redirect_request(request, None, 302, "Found", {}, request.full_url)
        for response in (FakeResponse(b"", url="https://evil.invalid"),
                         FakeResponse(b"", headers={"Content-Length": str(c.MAX_SOURCE_BYTES + 1)}),
                         FakeResponse(b"", headers={"Content-Encoding": "gzip"})):
            api = c.ReadOnlyAPI("offline-token")
            api._opener = FakeOpener(response)
            with self.assertRaises(c.DiscoveryError):
                api.read(c.SOURCE_PATHS[0])
        for token in ("", "line\nfeed", "has space", "x" * 257):
            with self.assertRaises(c.DiscoveryError):
                c.ReadOnlyAPI(token)

    def test_selected_class_and_parser_helpers_are_exact_and_source_not_executed(self):
        db = c.inspect_source(DB, c.SOURCE_PATHS[1])
        parser = c.inspect_source(PARSER, c.SOURCE_PATHS[2])
        self.assertIn("Soedinenie", db["selected_functions"])
        self.assertIn("self.commit()", db["selected_functions"]["Soedinenie"][0]["source"])
        text = parser["selected_functions"]["parse_sale_price_message"][0]["source"]
        self.assertIn('float(text)', text)
        self.assertNotIn("missing_runtime_global", json.dumps(parser))
        self.assertNotIn("must not export arbitrary configuration", json.dumps(db))
        self.assertFalse(parser["full_source_exported"])
        self.assertFalse(parser["live_module_imported"])
        ast.parse(text)

    def test_secret_helpers_omit_entire_snippet(self):
        for body in ('return connect(password="short-secret")', 'api_token = read_env()',
                     'return {"api_key": "short-secret"}', 'return "' + 'abcde' * 10 + '"'):
            source = ('def parse_sale_price_message(text):\n    ' + body + '\n').encode()
            item = c.inspect_source(source, c.SOURCE_PATHS[2])["selected_functions"]["parse_sale_price_message"][0]
            self.assertFalse(item["source_exported"])
            self.assertNotIn("source", item)

    def test_parser_syntax_failure_is_safe(self):
        with self.assertRaisesRegex(c.DiscoveryError, "SOURCE_PARSE_FAILED"):
            c.inspect_source(b"def parse_sale_price_message(:\n", c.SOURCE_PATHS[2])

    def test_full_original_candidate_preserves_source_and_never_executes_it(self):
        module = local_patcher()
        proxy = types.SimpleNamespace(TARGETS=module.TARGETS, HELPERS=module.HELPERS,
            build_candidate=lambda value: module.build_candidate(value, expected_sha256=module.digest(FIXTURE)))
        with mock.patch("builtins.open", side_effect=AssertionError("downloaded source executed")):
            # pathlib runtime.py read uses io.open and belongs to local reviewed patcher.
            result = c.verify_full_candidate(FIXTURE.encode(), root=ROOT, patcher=proxy)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["before_sha256"], c.sha(FIXTURE.encode()))
        self.assertEqual(result["candidate_compile"], "PASS")
        self.assertEqual(result["ast_and_routing"]["unrelated_top_level_ast"], "PASS")
        self.assertFalse(result["downloaded_code_executed"])
        self.assertNotIn("entire original file", json.dumps(result))

    def test_source_hash_drift_refuses_candidate_without_losing_safe_receipt(self):
        result = c.verify_full_candidate(FIXTURE.encode(), root=ROOT, patcher=local_patcher())
        self.assertEqual(result["status"], "REFUSED")
        self.assertEqual(result["stop_reason"], "LIVE_SOURCE_SHA_MISMATCH")
        self.assertEqual(result["installation"], "NOT_PERFORMED")

    def test_independent_ast_proof_rejects_unrelated_changes(self):
        module = local_patcher()
        candidate, _ = module.build_candidate(FIXTURE, expected_sha256=module.digest(FIXTURE))
        with self.assertRaisesRegex(c.DiscoveryError, "UNRELATED_AST_CHANGED"):
            c.independent_ast_proof(FIXTURE, candidate + '\nx = 1\n', module.TARGETS, module.HELPERS)

    def test_identity_prerequisite_and_dependencies_stop_before_any_get(self):
        for failure in ("identity", "stage1_hash", "dependency_hash"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = pathlib.Path(directory)
                env, api = self.setup_tree(root), FakeAPI()
                if failure == "identity":
                    env["UAART_TASK_ID"] = c.STAGE1_ID
                else:
                    path = root / (c.STAGE1_RECEIPT_REL if failure == "stage1_hash" else c.PATCHER_REL)
                    path.write_bytes(path.read_bytes() + b"\n")
                with self.assertRaises(c.DiscoveryError):
                    c.execute(env, root=root, api=api)
                self.assertEqual(api.get_count, 0)

    def test_complete_get_evidence_never_claims_installation_or_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            env, api = self.setup_tree(root), FakeAPI()
            prior = (root / c.STAGE1_RECEIPT_REL).read_bytes()
            result = c.execute(env, root=root, api=api)
            evidence = json.loads((root / c.EVIDENCE_REL).read_text())
            self.assertEqual(api.get_count, 8)
            self.assertEqual(set(api.paths), c.ALL_REMOTE_PATHS)
            self.assertEqual(result["stage2_acceptance"], "NOT_PERFORMED")
            self.assertEqual(result["candidate_verification"], "REFUSED")
            self.assertEqual(evidence["database_bytes_exported"], 0)
            self.assertEqual(evidence["remote_write_count"], 0)
            self.assertEqual(evidence["parser_verification"], "STATIC_AST_ONLY_NOT_EXECUTED")
            self.assertEqual((root / c.STAGE1_RECEIPT_REL).read_bytes(), prior)
            self.assertNotIn("must never export", json.dumps(evidence))
            self.assertFalse((root / "cars_ui.py").exists())
            with self.assertRaises(c.DiscoveryError):
                c.execute(env, root=root, api=api)
            self.assertEqual(api.get_count, 8)

    def test_concurrent_source_drift_prevents_evidence_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            env, api = self.setup_tree(root), FakeAPI(drift=True)
            with self.assertRaisesRegex(c.DiscoveryError, "SOURCE_CHANGED_DURING_DISCOVERY"):
                c.execute(env, root=root, api=api)
            self.assertFalse((root / c.RECEIPT_REL).exists())
            self.assertFalse((root / c.EVIDENCE_REL).exists())


if __name__ == "__main__":
    unittest.main()
