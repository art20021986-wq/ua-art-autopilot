#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import remote_lifecycle as lifecycle
import controller

class FakeAPI:
    calls=[]
    failure=None
    enabled=True
    def __init__(self):pass
    def supervisor(self):return {"id":266084,"command":lifecycle.COMMAND,"enabled":self.enabled,"state":"Running"}
    def set_enabled(self,value):
        self.calls.append(value)
        if self.failure is value:raise RuntimeError("NETWORK_UNKNOWN")
        return {"id":266084,"enabled":value,"state":"Running" if value else "Stopped"}

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.plan=self.root/"plan.json"
        self.plan.write_bytes(lifecycle.canonical({"alwayson_id":266084}))
        self.sha=hashlib.sha256(self.plan.read_bytes()).hexdigest()
        self.result=self.root/"install_verify-result.json"
        FakeAPI.calls=[];FakeAPI.failure=None;FakeAPI.enabled=True
        self.api=patch.object(lifecycle,"API",FakeAPI);self.api.start();self.addCleanup(self.api.stop)
    def call(self,op="install_verify"):
        return lifecycle.execute(op,self.plan,self.sha,self.result)
    def journal(self,stage,**extra):
        lifecycle.atomic(self.result.with_suffix(".journal.json"),
            {"plan_sha256":self.sha,"operation":"install_verify","stage":stage,**extra})
    def test_success_pauses_once_and_resumes(self):
        with patch.object(lifecycle,"child",return_value={"status":"PASS"}) as child:
            got=self.call();self.assertEqual(got["status"],"PASS")
            self.assertEqual(FakeAPI.calls,[False,True]);self.assertTrue(got["safe_to_stop"])
            self.call();self.assertEqual(child.call_count,1)
    def test_child_failure_rolls_back_before_resume(self):
        with patch.object(lifecycle,"child",side_effect=[RuntimeError("INSTALL_FAIL"),{"status":"PASS"}]) as child:
            got=self.call();self.assertEqual(got["status"],"FAIL")
            self.assertEqual([x.args[0] for x in child.call_args_list],["install_verify","rollback"])
            self.assertEqual(FakeAPI.calls,[False,True])
    def test_ambiguous_rollback_is_explicit_paused_terminal(self):
        with patch.object(lifecycle,"child",side_effect=[RuntimeError("INSTALL_FAIL"),RuntimeError("AMBIGUOUS")]):
            got=self.call();self.assertEqual(got["status"],"FAIL")
            self.assertEqual(FakeAPI.calls,[False]);self.assertFalse(got["crm_resume"]["enabled"])
            self.assertTrue(got["safe_to_stop"])
    def test_resume_retry_does_not_repeat_successful_child(self):
        FakeAPI.failure=True
        with patch.object(lifecycle,"child",return_value={"status":"PASS"}) as child:
            with self.assertRaisesRegex(RuntimeError,"NETWORK_UNKNOWN"):self.call()
            self.assertFalse(self.result.exists())
            saved=json.loads(self.result.with_suffix(".journal.json").read_text())
            self.assertEqual(saved["stage"],"RESUME_INTENT")
            self.assertEqual(saved["value"]["installer"],{"status":"PASS"})
            FakeAPI.failure=None;FakeAPI.enabled=False
            got=self.call();self.assertEqual(got["status"],"PASS")
            self.assertEqual(child.call_count,1);self.assertEqual(FakeAPI.calls,[False,True,True])
    def test_finished_journal_without_result_never_rolls_back(self):
        self.journal("FINISHED",value={"plan_sha256":self.sha,"operation":"install_verify", "status":"PASS","installer":{"status":"PASS"}})
        with patch.object(lifecycle,"child") as child:
            got=self.call();self.assertEqual(got["status"],"PASS");child.assert_not_called()
            self.assertEqual(FakeAPI.calls,[True])
    def test_interrupted_install_uses_rollback(self):
        self.journal("CHILD_STARTED");FakeAPI.enabled=False
        with patch.object(lifecycle,"child",return_value={"status":"PASS"}) as child:
            got=self.call();self.assertEqual(got["status"],"FAIL")
            self.assertEqual(child.call_args.args[0],"rollback")
            self.assertEqual(FakeAPI.calls,[False,True])
    def test_interrupted_install_unknown_pause_never_resumes(self):
        self.journal("CHILD_STARTED");FakeAPI.failure=False;FakeAPI.enabled=False
        with patch.object(lifecycle,"child") as child:
            with self.assertRaisesRegex(RuntimeError,"NETWORK_UNKNOWN"):self.call()
            child.assert_not_called();self.assertEqual(FakeAPI.calls,[False])
            self.assertFalse(self.result.exists())
            self.assertEqual(json.loads(self.result.with_suffix(".journal.json").read_text())["stage"],"CHILD_STARTED")
    def test_prechild_pause_failure_can_resume_without_rollback(self):
        FakeAPI.failure=False
        with patch.object(lifecycle,"child") as child:
            got=self.call();child.assert_not_called()
            self.assertEqual(FakeAPI.calls,[False,True]);self.assertEqual(got["status"],"FAIL")
    def test_failed_rollback_never_resumes(self):
        self.result=self.root/"rollback-result.json"
        with patch.object(lifecycle,"child",side_effect=RuntimeError("ROLLBACK_PARTIAL")):
            got=self.call("rollback")
            self.assertEqual(got["status"],"FAIL");self.assertEqual(FakeAPI.calls,[False])
            self.assertIn("rollback_error",got);self.assertFalse(got["crm_resume"]["enabled"])
    def test_plan_drift_never_calls_provider(self):
        self.plan.write_text("{}")
        with self.assertRaisesRegex(RuntimeError,"PLAN_SHA_MISMATCH"):self.call()
        self.assertEqual(FakeAPI.calls,[])

class ControllerTests(unittest.TestCase):
    def test_existing_exact_worker_is_reused(self):
        api=controller.API("test-not-secret")
        payload=json.dumps([{"id":123,"command":"cmd","description":"desc"}]).encode()
        with patch.object(api,"request",return_value=(200,payload)) as request:
            self.assertEqual(api.trigger("cmd","desc"),123)
            self.assertEqual(request.call_args.args[0],"GET");self.assertEqual(request.call_count,1)
    def test_existing_worker_command_drift_rejected(self):
        api=controller.API("test-not-secret")
        payload=json.dumps([{"id":123,"command":"different","description":"desc"}]).encode()
        with patch.object(api,"request",return_value=(200,payload)):
            with self.assertRaisesRegex(RuntimeError,"IDENTITY_CONFLICT"):api.trigger("cmd","desc")
    def test_live_verification_missing_hash_fails(self):
        with self.assertRaisesRegex(RuntimeError,"PUBLIC_DIGESTS_REQUIRED"):controller.verify_public({},"123")
    def test_live_verification_exact_response_and_bad_bytes(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def geturl(self):return "https://www.uaart.com.ua/video/UA-0022.html"
            def read(self,size):return b"exact expected content"
        url="https://www.uaart.com.ua/video/UA-0022.html"
        expected=controller.sha(b"exact expected content")
        hashes={"https://www.uaart.com.ua/video/"+name:expected for name in ("UA-0022.html","UA-0022-diag.html","katalog.html","index.html")}
        with patch.object(controller.urllib.request,"urlopen",return_value=Response()):
            self.assertEqual(controller.verify_public({"public_http_sha256":hashes},"123",require_target=True)[0]["status"],"PASS")
            with self.assertRaisesRegex(RuntimeError,"PUBLIC_BYTES_MISMATCH"):
                controller.verify_public({"public_http_sha256":{**hashes,url:"0"*64}},"123")

if __name__=="__main__":unittest.main()
