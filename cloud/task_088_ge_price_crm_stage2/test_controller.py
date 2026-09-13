"""Only authenticated, running, exactly identified CRM supervisors are accepted."""
import json
import unittest
from unittest import mock

import controller


class SupervisorObservationTests(unittest.TestCase):
    def setUp(self):
        self.api = controller.API({"UAART_RUN_ID": "12345", "UAART_REQUEST_SHA256": "a" * 64})
        self.observed = {"id": 266084, "command": "python3.10 /home/Carix/start_safe.py",
                         "enabled": True, "state": "running"}

    def observe(self, payload):
        with mock.patch.object(self.api, "request", return_value=(200, json.dumps(payload).encode())) as request:
            result = self.api.supervisor_observation()
        request.assert_called_once_with("GET", controller.BASE + "always_on/266084/")
        return result

    def test_only_exact_running_identity_is_normalized(self):
        result = self.observe(self.observed)
        self.assertEqual(result["source"], "PYTHONANYWHERE_AUTHENTICATED_API")
        self.assertEqual(result["status"], "Running")
        self.assertEqual(result["supervisor_id"], 266084)
        self.assertNotIn("pid", result)

    def test_wrong_service_or_command_or_disabled_is_rejected(self):
        for changes in ({"id": 270984}, {"command": "python3.10 other.py"}, {"enabled": False}):
            with self.subTest(changes=changes), self.assertRaisesRegex(controller.ControllerError, "SUPERVISOR_IDENTITY"):
                self.observe({**self.observed, **changes})

    def test_stopped_or_missing_state_is_rejected(self):
        for state in ("stopped", "starting", None, True):
            with self.subTest(state=state), self.assertRaisesRegex(controller.ControllerError, "SUPERVISOR_NOT_RUNNING"):
                self.observe({**self.observed, "state": state})

    def test_malformed_payload_is_rejected(self):
        with self.assertRaisesRegex(controller.ControllerError, "SUPERVISOR_IDENTITY"):
            self.observe([self.observed])


if __name__ == "__main__":
    unittest.main()
