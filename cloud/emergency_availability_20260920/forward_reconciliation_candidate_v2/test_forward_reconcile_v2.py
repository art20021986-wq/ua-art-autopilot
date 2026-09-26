import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

import forward_reconcile_v2 as fr


def b(obj):
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()


class V2Tests(unittest.TestCase):
    def setup_case(self, folder):
        root = pathlib.Path(folder) / "repo"
        values = {
            fr.TX_REL: {"schema_version":"UA-ART-PRODUCTION-TRANSACTION-2","task_id":fr.TASK,"run_id":fr.RUN,"request_sha256":fr.REQ_SHA,"transaction_id":fr.TXID,"status":"ROLLING_BACK"},
            fr.CLAIM_REL: {"task_execution_status":"BLOCKED_ROOT_CAUSE","production_transaction_status":"ROLLING_BACK","production_transaction_id":fr.TXID,"request_sha256":fr.REQ_SHA,"heartbeat_sequence":7},
            fr.HALT_REL: {"status":"EMERGENCY_HALT","task_id":fr.TASK,"run_id":fr.RUN,"request_sha256":fr.REQ_SHA},
            fr.BACKUP_REL: {"status":"PASS","backup":"PASS","task_id":fr.TASK,"run_id":fr.RUN,"transaction_id":fr.TXID,"request_sha256":fr.REQ_SHA,"backup_manifest_sha256":"a"*64},
            fr.REQUEST_REL: {"task_id":fr.TASK,"production_required":True},
        }
        repo_manifest = {}
        for rel, value in values.items():
            raw = b(value)
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            repo_manifest[rel] = {"sha256":hashlib.sha256(raw).hexdigest(),"blob_sha":"b"*40}
        install_hashes = {url:"d"*64 for url in set(fr.EXPECTED_URLS.values())}
        install_hashes[fr.EXPECTED_URLS["ua0022_card"]]="e"*64
        install_hashes[fr.EXPECTED_URLS["ua0022_diagnostic"]]="e"*64
        install = {"source":"AUTHENTICATED_PYTHONANYWHERE_FILE_EDITOR","receipt":{"status":"PASS","safe_to_stop":True,"crm_resume":{"enabled":True,"state":"Running"},"installer":{"status":"PASS","task_id":fr.TASK,"target":"UA-0022","integrity_pass":True,"post_check_pass":True,"other_rows_unchanged":True,"protected_pages_unchanged":True,"target_media_unchanged":True,"target_original_media_unchanged":True,"ua_ge_prices_unchanged":True,"publication_pass":True,"source_after_sha256":{k:"c"*64 for k in fr.RUNTIME_KEYS},"public_http_sha256":install_hashes}}}
        health = {"schema_version":"UAART-UA0022-FRESH-HEALTH-1","main":fr.MAIN,"production_write_performed":False,"started_at":"2026-09-20T11:09:00Z","finished_at":"2026-09-20T11:10:00Z","status":"healthy","exit_code":0,"routes":{k:{"http_status":200,"final_url":fr.EXPECTED_URLS[k],"sha256":"d"*64} for k in fr.HTTP_KEYS},"public_bytes_changed_after_install_observation":["ua0022_card","ua0022_diagnostic"]}
        ip = pathlib.Path(folder)/"install.json"; ip.write_bytes(b(install))
        hp = pathlib.Path(folder)/"health.json"; hp.write_bytes(b(health))
        manifest = {
            "schema_version":"UAART-UA0022-FORWARD-INPUT-MANIFEST-2",
            "main":fr.MAIN,
            "repo_inputs":repo_manifest,
            "must_not_exist":sorted(fr.ADDITIONS),
            "external":{
                "install":{
                    "path":fr.INSTALL_EVIDENCE_PATH,
                    "blob_sha":fr.INSTALL_EVIDENCE_BLOB,
                    "source_commit":fr.INSTALL_EVIDENCE_COMMIT,
                    "sha256":hashlib.sha256(ip.read_bytes()).hexdigest(),
                },
                "health":{
                    "path":fr.HEALTH_EVIDENCE_PATH,
                    "blob_sha":fr.HEALTH_EVIDENCE_BLOB,
                    "source_commit":fr.HEALTH_EVIDENCE_COMMIT,
                    "sha256":hashlib.sha256(hp.read_bytes()).hexdigest(),
                },
            },
        }
        mp = pathlib.Path(folder)/"manifest.json"; mp.write_bytes(b(manifest))
        return root, mp, ip, hp, manifest, health

    def build(self, case):
        return fr.build(case[0],case[1],case[2],case[3],"2026-09-20T11:15:00Z")

    def test_exact_success_and_scoped_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder); plan,out=self.build(case)
            self.assertFalse(plan["ready"]); self.assertEqual(len(plan["changes"]),8)
            receipt=json.loads(out[fr.RECEIPT_REL])
            self.assertEqual(receipt["rollback"],"NOT_PERFORMED")
            self.assertFalse(receipt["canonical_rollback_execution_ready"])
            self.assertTrue(receipt["rollback_ready"])
            self.assertEqual(receipt["tests"],"PASS")
            self.assertEqual(receipt["unexpected_changes"],0)
            self.assertEqual(receipt["production"],"PASS")
            self.assertEqual(receipt["live_verify"],"PASS")
            self.assertEqual(out[fr.HISTORY_HALT_REL],(case[0]/fr.HALT_REL).read_bytes())

    def test_receipt_satisfies_active_canonical_contract(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder); _,out=self.build(case)
            receipt=json.loads(out[fr.RECEIPT_REL])
            required={"task_id","status","task_class","target_environment","tests",
                      "unexpected_changes","rollback_ready","production_required",
                      "request_sha256","run_id"}
            self.assertFalse(required-set(receipt))
            self.assertEqual(receipt["status"],"FINISHED")
            self.assertEqual(receipt["task_class"],"CRITICAL")
            self.assertEqual(receipt["tests"],"PASS")
            self.assertEqual(receipt["unexpected_changes"],0)
            self.assertIs(receipt["rollback_ready"],True)
            self.assertEqual(receipt["task_id"],fr.TASK)
            self.assertEqual(str(receipt["run_id"]),fr.RUN)
            self.assertEqual(receipt["request_sha256"],fr.REQ_SHA)
            self.assertIs(receipt["production_required"],True)
            self.assertEqual(receipt["target_environment"],"production")
            self.assertEqual(receipt["production"],"PASS")
            self.assertEqual(receipt["live_verify"],"PASS")
            self.assertTrue(receipt.get("backup"))

    def test_external_provenance_drift_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); m=case[4]
            m["external"]["install"]["source_commit"]="f"*40
            case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"INSTALL_PROVENANCE_COMMIT"):
                self.build(case)

    def test_input_drift_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder); (case[0]/fr.TX_REL).write_bytes(b({}))
            with self.assertRaisesRegex(fr.ReconcileError,"INPUT_SHA256"): self.build(case)

    def test_empty_route_map_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); h=copy.deepcopy(case[5]); h["routes"]={}
            case[3].write_bytes(b(h)); m=case[4]; m["external"]["health"]["sha256"]=hashlib.sha256(case[3].read_bytes()).hexdigest(); case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"HEALTH_ROUTE_KEYS"): self.build(case)

    def test_failed_monitor_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); h=copy.deepcopy(case[5]); h["status"]="failed"; h["exit_code"]=1
            case[3].write_bytes(b(h)); m=case[4]; m["external"]["health"]["sha256"]=hashlib.sha256(case[3].read_bytes()).hexdigest(); case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"HEALTH_MONITOR"): self.build(case)

    def test_wrong_route_url_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); h=copy.deepcopy(case[5]); h["routes"]["ua0022_card"]["final_url"]=fr.EXPECTED_URLS["www_home"]
            case[3].write_bytes(b(h)); m=case[4]; m["external"]["health"]["sha256"]=hashlib.sha256(case[3].read_bytes()).hexdigest(); case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"HEALTH_URL:ua0022_card"): self.build(case)

    def test_false_changed_byte_list_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); h=copy.deepcopy(case[5]); h["public_bytes_changed_after_install_observation"]=[]
            case[3].write_bytes(b(h)); m=case[4]; m["external"]["health"]["sha256"]=hashlib.sha256(case[3].read_bytes()).hexdigest(); case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"HEALTH_CHANGED_BYTES_BINDING"): self.build(case)

    def test_stale_health_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder)
            with self.assertRaisesRegex(fr.ReconcileError,"HEALTH_STALE"): fr.build(case[0],case[1],case[2],case[3],"2026-09-20T13:15:00Z")

    def test_runtime_keyset_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=list(self.setup_case(folder)); x=json.loads(case[2].read_bytes()); x["receipt"]["installer"]["source_after_sha256"].pop("cars_ui.py")
            case[2].write_bytes(b(x)); m=case[4]; m["external"]["install"]["sha256"]=hashlib.sha256(case[2].read_bytes()).hexdigest(); case[1].write_bytes(b(m))
            with self.assertRaisesRegex(fr.ReconcileError,"RUNTIME_KEYSET"): self.build(case)

    def test_preexisting_addition_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder); p=case[0]/fr.RECEIPT_REL; p.parent.mkdir(parents=True,exist_ok=True); p.write_text("x")
            with self.assertRaisesRegex(fr.ReconcileError,"ADDITION_EXISTS"): self.build(case)

    def test_output_scope_and_expected_parent(self):
        with tempfile.TemporaryDirectory() as folder:
            case=self.setup_case(folder); plan,_=self.build(case)
            self.assertEqual(plan["expected_parent"],fr.MAIN)
            self.assertTrue(all(c["path"].startswith("state/") for c in plan["changes"]))
            self.assertFalse(plan["force_allowed"])


if __name__ == "__main__": unittest.main()
