import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import controller


class FakeAPI:
    def __init__(self, receipt_text=None, exists_after=1):
        self.receipt_text = receipt_text
        self.exists_after = exists_after
        self.calls = 0
        self.cleaned = []
        self.commands = []

    def run_command(self, command):
        self.commands.append(command)
        return "trigger-1"

    def file_exists(self, path):
        self.calls += 1
        return self.calls >= self.exists_after and self.receipt_text is not None

    def read_file(self, path):
        return self.receipt_text

    def cleanup(self, trigger_id):
        self.cleaned.append(trigger_id)


class TestController(unittest.TestCase):
    def setUp(self):
        os.environ["PYTHONANYWHERE_API_TOKEN"] = "test-token-not-real"

    def tearDown(self):
        os.environ.pop("PYTHONANYWHERE_API_TOKEN", None)

    def test_rejects_wrong_account(self):
        api = FakeAPI()
        with self.assertRaises(controller.ControllerError):
            controller.PAController("someone_else", "www.pythonanywhere.com", api)

    def test_rejects_wrong_host(self):
        api = FakeAPI()
        with self.assertRaises(controller.ControllerError):
            controller.PAController("Carix", "evil.example.com", api)

    def test_pass_receipt(self):
        receipt = json.dumps({"production_touched": "NO", "crm_touched": "NO", "gate_b_executed": "NO", "files": []})
        api = FakeAPI(receipt_text=receipt, exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        data = ctl.run_discovery(
            "python3 discover.py",
            "/home/Carix/autopilot_runs/task_043_ferry_wording/receipt.json",
            timeout_seconds=5, poll_interval=0,
        )
        self.assertEqual(data["production_touched"], "NO")
        self.assertEqual(api.cleaned, ["trigger-1"])

    def test_blocked_flag_passthrough(self):
        receipt = json.dumps({
            "production_touched": "NO", "crm_touched": "NO", "gate_b_executed": "NO", "status": "BLOCKED",
        })
        api = FakeAPI(receipt_text=receipt, exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        data = ctl.run_discovery("python3 discover.py", "path", timeout_seconds=5, poll_interval=0)
        self.assertEqual(data["status"], "BLOCKED")

    def test_timeout(self):
        api = FakeAPI(receipt_text=None)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ControllerError):
            ctl.run_discovery("python3 discover.py", "path", timeout_seconds=1, poll_interval=0)
        self.assertEqual(api.cleaned, ["trigger-1"])

    def test_malformed_json(self):
        api = FakeAPI(receipt_text="{not json", exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ReceiptError):
            ctl.run_discovery("python3 discover.py", "path", timeout_seconds=5, poll_interval=0)

    def test_duplicate_keys_rejected(self):
        receipt = '{"a": 1, "a": 2, "production_touched": "NO", "crm_touched": "NO", "gate_b_executed": "NO"}'
        api = FakeAPI(receipt_text=receipt, exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ReceiptError):
            ctl.run_discovery("python3 discover.py", "path", timeout_seconds=5, poll_interval=0)

    def test_forbidden_command_rejected(self):
        api = FakeAPI(receipt_text="{}")
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ControllerError):
            ctl.run_gate_a("python3 gate_b_publish.py", "path")

    def test_secret_leakage_rejected(self):
        receipt = '{"production_touched": "NO", "crm_touched": "NO", "gate_b_executed": "NO", "note": "api_key leaked here"}'
        api = FakeAPI(receipt_text=receipt, exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ControllerError):
            ctl.run_discovery("python3 discover.py", "path", timeout_seconds=5, poll_interval=0)

    def test_wrong_sha_manifest_blocked(self):
        with self.assertRaises(controller.SafeInboxManifestError):
            controller.verify_manifest({"discover.py": "aaa"}, {"discover.py": "bbb"})

    def test_unsafe_flag_rejected(self):
        receipt = '{"production_touched": "YES", "crm_touched": "NO", "gate_b_executed": "NO"}'
        api = FakeAPI(receipt_text=receipt, exists_after=1)
        ctl = controller.PAController("Carix", "www.pythonanywhere.com", api)
        with self.assertRaises(controller.ControllerError):
            ctl.run_discovery("python3 discover.py", "path", timeout_seconds=5, poll_interval=0)


if __name__ == "__main__":
    unittest.main()
