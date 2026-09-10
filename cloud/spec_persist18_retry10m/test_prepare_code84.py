from contextlib import contextmanager
import hashlib
import sys
import types
import unittest
from unittest.mock import patch

import prepare_code84 as patcher


class IntegrationPatcherTests(unittest.TestCase):
    def patch_stub(self, name, source):
        before = source.encode()
        with patch.dict(patcher.PINS, {name: hashlib.sha256(before).hexdigest()}):
            return patcher.patch_source(name, before)[0].decode()

    def helper(self, events):
        helper = types.ModuleType("ua_spec_permanent")
        from ua_spec_permanent import card_uid_from_path
        helper.card_uid_from_path = card_uid_from_path
        helper.ensure_html = lambda html, uid: events.append(("ensure", uid)) or html + "[spec]"
        @contextmanager
        def lock():
            events.append(("lock",))
            yield
            events.append(("unlock",))
        helper.write_lock = lock
        return helper

    def test_conditional_last_stranica_writer_is_wrapped_before_main(self):
        source = '''events = []
def nomer(m): return m["auto_number"]
def sobrat_kartochku(m, kadry, sredn=None): return "html"
def zapisat(put, text): raise AssertionError("not final writer")
if True:
    def zapisat(put, text, *args, **kwargs):
        events.append(("write", put, text, args, kwargs))
        return "written"
if __name__ == "__main__":
    zapisat("UA-0018", sobrat_kartochku({"auto_number":"UA-0018"}, []), 5, mode="x")
'''
        events = []
        namespace = {"__name__": "__main__"}
        with patch.dict(sys.modules, {"ua_spec_permanent": self.helper(events)}):
            exec(self.patch_stub("stranica.py", source), namespace)
        self.assertEqual(events, [("ensure", "UA-0018"), ("lock",), ("ensure", "UA-0018"), ("unlock",)])
        self.assertEqual(namespace["events"], [("write", "UA-0018", "html[spec][spec]", (5,), {"mode": "x"})])

    def test_diagnostic_and_catalog_writes_keep_original_route(self):
        source = '''events=[]
def _zapisat_atomarno(put,tekst):
    events.append((put,tekst))
    return "ok"
'''
        events, namespace = [], {"__name__": "publikaciya"}
        with patch.dict(sys.modules, {"ua_spec_permanent": self.helper(events)}):
            exec(self.patch_stub("publikaciya.py", source), namespace)
            for target in ("/home/Carix/video/index.html", "/home/Carix/video/UA-0017-diag.html"):
                self.assertEqual(namespace["_zapisat_atomarno"](target, "old"), "ok")
            namespace["_zapisat_atomarno"]("/home/Carix/video/UA-0017.html", "card")
        self.assertEqual(events, [("lock",), ("ensure", "UA-0017"), ("unlock",)])
        self.assertEqual(namespace["events"][-1][1], "card[spec]")

    def test_pin_mismatch_and_code_after_main_refuse(self):
        with self.assertRaisesRegex(ValueError, "ORIGINAL_PIN_MISMATCH"):
            patcher.patch_source("stranica.py", b"pass\n")
        source = '''def sobrat_kartochku(*args): pass
def zapisat(*args): pass
if __name__ == "__main__": pass
after_main = 1
'''
        with self.assertRaisesRegex(ValueError, "CODE_AFTER_MAIN_GUARD"):
            self.patch_stub("stranica.py", source)

    def test_worker_delegation_is_lazy_and_keeps_function_signatures(self):
        source = '''def start_worker(): raise AssertionError("old worker")
def stop_worker(timeout=5): pass
def retry_card(value): raise AssertionError("old retry")
def card_state(value): return {}
'''
        runtime = types.ModuleType("ua_spec84_runtime")
        runtime.start_worker = lambda: "new worker"
        runtime.stop_worker = lambda timeout: timeout
        runtime.retry_card = lambda value: ("cycle", value)
        runtime.card_state = lambda value: {"uid": value}
        namespace = {"__name__": "vin_spec_service"}
        exec(self.patch_stub("vin_spec_service.py", source), namespace)
        with patch.dict(sys.modules, {"ua_spec84_runtime": runtime}):
            self.assertEqual(namespace["start_worker"](), "new worker")
            self.assertEqual(namespace["retry_card"]("UA-0017"), ("cycle", "UA-0017"))
            self.assertEqual(namespace["card_state"]("UA-0017"), {"uid": "UA-0017"})


if __name__ == "__main__":
    unittest.main()
