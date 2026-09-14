"""Authority tests: synthetic canonical chain, real isolated DB/files/locks.

These fixtures are expressly TEST evidence and cannot authorize /home/Carix.
"""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest

from test_runtime import load, HERE, outbox, runtime
binding = load("uaart_price_sync_binding", HERE / "uaart_price_sync_binding.py")


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.now = 1000000
        self.task = "TASK088-GE-PRICE-SITE-STAGE3-TEST-20260913"
        (self.root / "evidence").mkdir()
        (self.root / "private").mkdir(mode=0o700)
        (self.root / "journals").mkdir(mode=0o700)
        (self.root / "video").mkdir()
        self.lock = self.root / "publication.lock"
        self.lock.touch(mode=0o600)
        self.code = {}
        for path in binding.REQUIRED_CODE:
            content = ("# isolated TEST source " + path + "\n").encode()
            (self.root / path).write_bytes(content)
            self.code[path] = binding.sha(content)
        self.db = self.root / "crm.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER)")
            conn.executemany("INSERT INTO cars VALUES (?,?,1,10000,5000)", [(i, f"UA-{i:04d}") for i in range(1, 19)])
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            runtime.install(conn)
            conn.commit()
            self.schema = binding.schema_sha256(conn)
            conn.execute("BEGIN IMMEDIATE")
            outbox.enqueue(conn, event_key="a"*64, car_id=1, ukraine_usd="10000.00", georgia_usd="5000.00", now_ms=self.now)
            self.event = outbox.claim(conn, event_key="a"*64, nonce="b"*64, now_ms=self.now)
            conn.commit()
        self.put("private/mode.json", {"mode":"AUTOMATIC"})
        self.put("private/revocation.json", {"revoked":False})
        self.controls = {"provenance":"LOCAL_AUTHORITATIVE", "observations":{
            "mode":{"path":"private/mode.json", "format":"JSON_FIELD", "field":["mode"]},
            "halt":{"path":"private/halt.json", "format":"ABSENT_IS_CLEAR"},
            "revocation":{"path":"private/revocation.json", "format":"JSON_FIELD", "field":["revoked"]}}}
        self.policy = {"price_uah":{"currency":"USD"}, "price_georgia":{"currency":"USD"},
                       "notifications":"OWNER_PRIVATE_TELEGRAM_ONLY", "sla_ms":60000}
        self.raw_chat_fact = self.put("evidence/telegram_fact.json", {"source":"SYNTHETIC_TEST", "owner_user_id":42, "chat_id":42, "chat_type":"private", "bot_id":123,"observed_ms":self.now})
        self.chat = {"source":"AUTHENTICATED_CRM_BOT_PRIVATE_CHAT", "chat_type":"private", "owner_user_id":42,
            "chat_id":42, "bot_id":123, "verification":"VERIFIED", "evidence":self.raw_chat_fact}
        self.writers = {"publication_lock":str(self.lock), "uncovered_writers":[],
            "control_contract_sha256":binding.sha(binding.encoded(self.controls)),
            "writers":[{"path":path, "installed_sha256":self.code[path], "fence":"VERIFIED"}
                       for path in ("cars_ui.py", "ua_stage_catalog_sync.py", "publish_transaction_guard.py",
                                    "master_card.py", "publikaciya.py", "uaart_price_sync_runtime.py")]}
        self.artifacts = {}
        self.artifacts["owner_private_chat"] = self.put("evidence/chat.json", self.chat)
        self.artifacts["writer_fences"] = self.put("evidence/writers.json", self.writers)
        self.artifacts["owner_policy"] = self.put("evidence/policy.json", self.policy)
        self.delegation = {"contract":binding.CONTRACT, "environment":"TEST", "root":str(self.root), "task_id":self.task,
            "operation":"UPDATE_EXISTING_CARD_AND_CATALOG_PRICES", "activation":"BOUNDED_PRICE_EVENTS",
            "initial_publication":"OWNER_MANUAL", "fields":["price_uah","price_georgia"], "currency":"USD",
            "non_price_changes":"FORBIDDEN", "public_origin":"https://example.test", "database_path":"crm.db",
            "publication_lock":"publication.lock", "journal_root":"journals", "authorization_ttl_ms":10000,
            "car_identities":[[i,f"UA-{i:04d}"] for i in range(1,19)], "installed_code_sha256":self.code,
            "schema_sha256":self.schema, "control_contract":self.controls, "verified_recovery_successor_allowed":True,
            "owner_private_chat_fact_sha256":self.artifacts["owner_private_chat"]["sha256"],
            "writer_fence_report_sha256":self.artifacts["writer_fences"]["sha256"],
            "owner_policy":self.policy, "owner_chat_id":42, "bot_id":123, "detail_url":"https://example.test/report",
            "surfaces":{f"UA-{i:04d}":[{"kind":"CARD", "path":f"video/UA-{i:04d}.html", "url":f"https://example.test/video/UA-{i:04d}.html"},
                {"kind":"CATALOG", "path":"video/katalog.html", "url":"https://example.test/video/katalog.html"}] for i in range(1,19)}}
        self.rebuild_chain()

    def tearDown(self):
        self.temporary.cleanup()

    def put(self, path, value):
        raw = binding.encoded(value)
        destination = self.root / path
        destination.write_bytes(raw)
        destination.chmod(0o600)
        return {"path":path, "sha256":binding.sha(raw)}

    def rebuild_chain(self):
        manifest = {"price_event_delegation_sha256":binding.sha(binding.encoded(self.delegation)), "install_files_sha256":"1"*64}
        self.artifacts["manifest"] = self.put("evidence/manifest.json", manifest)
        gate = {"task_id":self.task, "status":"PASS", "manifest_sha256":self.artifacts["manifest"]["sha256"],
            "tests":"PASS", "unexpected_changes":0, "backup_plan_ready":True, "rollback_plan_ready":True,
            "writer_fence_report_sha256":self.artifacts["writer_fences"]["sha256"]}
        self.artifacts["gate_b"] = self.put("evidence/gate_b.json", gate)
        request = {"task_id":self.task, "requested_min_class":"CRITICAL", "production_required":True,
            "critical":{"manifest_sha256":self.artifacts["manifest"]["sha256"], "gate_a_sha256":self.artifacts["gate_b"]["sha256"], "owner_approval_sha256":"0"*64}}
        subject = (json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        owner = {"schema_version":"UA-ART-PRODUCTION-AUTHORIZATION-1", "task_id":self.task,
            "owner_authorized":True,"production_allowed":True,"authorized_environment":"production",
            "manifest_sha256":self.artifacts["manifest"]["sha256"],"gate_a_sha256":self.artifacts["gate_b"]["sha256"],
            "request_subject_sha256":binding.sha(subject)}
        self.artifacts["owner_approval"] = self.put("evidence/owner.json", owner)
        request["critical"]["owner_approval_sha256"] = self.artifacts["owner_approval"]["sha256"]
        self.artifacts["request"] = self.put("evidence/request.json", request)
        receipt = {"status":"INSTALLED_PENDING_LIVE_ACCEPTANCE", "task_id":self.task, "transaction_id":"tx-test-deployment-12345678",
            "request_sha256":self.artifacts["request"]["sha256"], "manifest_sha256":self.artifacts["manifest"]["sha256"],
            "gate_b_sha256":self.artifacts["gate_b"]["sha256"], "installed_files_sha256":self.code,
            "installed_schema_sha256":self.schema, "cars_audit_unchanged":True, "stage3_complete":False}
        self.artifacts["deployment_receipt"] = self.put("evidence/deployment.json", receipt)
        config_ref = self.put("private/config.json", {"delegation":self.delegation, "artifacts":self.artifacts})
        self.anchor_ref = self.put("private/anchor.json", {"contract":binding.ANCHOR_CONTRACT,
            "config_path":config_ref["path"], "config_sha256":config_ref["sha256"]})
        self.anchor = self.root / self.anchor_ref["path"]

    def provider(self):
        provider = binding.Provider(anchor_path=self.anchor, expected_anchor_sha256=self.anchor_ref["sha256"],
                                    test_root=self.root, clock=lambda:self.now)
        provider.verify_running_bot(SimpleNamespace(id=123))
        return provider

    def authorize(self, provider=None):
        provider = provider or self.provider()
        descriptor = os.open(self.lock, os.O_RDWR)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            return provider.authorize(self.event, provider.resolve_surfaces("UA-0001"))
        finally:
            os.close(descriptor)

    def test_real_artifact_hash_chain_creates_unique_durable_event_authority(self):
        provider = self.provider()
        proof = self.authorize(provider)
        self.assertNotEqual(proof["canonical_transaction_id"],proof["deployment_transaction_id"])
        self.assertEqual(proof["event_key"],self.event["event_key"])
        self.assertEqual(proof["claim_nonce"],self.event["claim_nonce"])
        self.assertEqual(proof["expires_ms"],self.now+10000)
        self.assertEqual(binding.sha(Path(proof["authorization_record_path"]).read_bytes()),proof["authorization_record_sha256"])
        self.assertEqual(self.authorize(provider),proof)
        self.assertEqual(len(list((self.root/"journals/authorizations").glob("*.json"))),1)

    def test_unverified_running_bot_cannot_authorize(self):
        provider = binding.Provider(anchor_path=self.anchor,test_root=self.root,clock=lambda:self.now)
        with self.assertRaisesRegex(binding.BindingError,"BOT_NOT_YET_VERIFIED"):
            self.authorize(provider)

    def test_anchor_external_pin_required_when_supplied(self):
        with self.assertRaisesRegex(binding.BindingError,"ANCHOR_HASH_MISMATCH"):
            binding.Provider(anchor_path=self.anchor,expected_anchor_sha256="f"*64,test_root=self.root)

    def test_test_fixture_cannot_bootstrap_production_root(self):
        with self.assertRaisesRegex(binding.BindingError,"ANCHOR_OUTSIDE_ROOT"):
            binding.Provider(anchor_path=self.anchor)

    def test_public_anchor_or_config_rejected(self):
        self.anchor.chmod(0o644)
        with self.assertRaisesRegex(binding.BindingError,"PRIVATE_INSTALLER_FILE"):
            self.provider()

    def test_changed_code_stops_existing_provider(self):
        provider=self.provider()
        (self.root/"cars_ui.py").write_bytes(b"foreign code")
        with self.assertRaisesRegex(binding.BindingError,"PINNED_FILE_HASH_MISMATCH"):
            self.authorize(provider)
        self.assertFalse((self.root/"journals/authorizations").exists())

    def test_changed_schema_stops_existing_provider(self):
        provider=self.provider()
        with sqlite3.connect(self.db) as conn:conn.execute("CREATE TABLE unexpected(x)")
        with self.assertRaisesRegex(binding.BindingError,"LIVE_SCHEMA_DRIFT"):
            self.authorize(provider)

    def test_changed_code_mapping_cannot_publish_another_car(self):
        provider=self.provider()
        with sqlite3.connect(self.db) as conn:conn.execute("UPDATE cars SET auto_number='UA-0002' WHERE id=1")
        with self.assertRaisesRegex(binding.BindingError,"LIVE_CAR_REGISTRY_DRIFT"):
            self.authorize(provider)

    def test_halt_revocation_or_manual_mode_immediately_blocks_existing_binding(self):
        for path,value in (("private/halt.json",{}),("private/mode.json",{"mode":"MANUAL"}),
                           ("private/revocation.json",{"revoked":True})):
            with self.subTest(path=path):
                provider=self.provider()
                prior=(self.root/path).read_bytes() if (self.root/path).exists() else None
                self.put(path,value)
                with self.assertRaises(binding.BindingError):self.authorize(provider)
                if prior is None:(self.root/path).unlink()
                else:(self.root/path).write_bytes(prior)

    def test_false_numeric_control_value_is_not_boolean_clear(self):
        self.put("private/revocation.json",{"revoked":0})
        with self.assertRaisesRegex(binding.BindingError,"CONTROL_BLOCKS"):
            self.authorize()

    def test_missing_observed_control_file_is_not_assumed_safe(self):
        (self.root/"private/mode.json").unlink()
        with self.assertRaises(FileNotFoundError):self.authorize()

    def test_ordinary_halt_keeps_crm_bootstrap_available_but_blocks_prices(self):
        self.put("private/halt.json",{"reason":"Owner stopped automation"})
        app=SimpleNamespace(bot=SimpleNamespace(id=123),bot_data={},post_init=None)
        actual=binding.bootstrap(app,anchor_path=self.anchor,test_root=self.root)
        asyncio.run(app.post_init(app))
        with self.assertRaisesRegex(binding.BindingError,"HALT_FILE"):
            self.authorize(actual.authorize.__self__)

    def test_in_memory_scope_mutation_cannot_bypass_pinned_configuration(self):
        provider=self.provider()
        provider.delegation["surfaces"]["UA-0001"][0]["path"]="another/UA-0001.html"
        with self.assertRaisesRegex(binding.BindingError,"IN_MEMORY_DELEGATION_CHANGED"):
            self.authorize(provider)

    def test_local_callback_claim_without_real_durable_row_is_rejected(self):
        provider=self.provider()
        self.event=dict(self.event,claim_nonce="c"*64)
        with self.assertRaisesRegex(binding.BindingError,"DURABLE_CURRENT_EVENT_CLAIM"):
            self.authorize(provider)

    def test_no_global_publication_lock_no_authorization(self):
        provider=self.provider()
        with self.assertRaisesRegex(binding.BindingError,"SHARED_PUBLICATION_LOCK_NOT_HELD"):
            provider.authorize(self.event,provider.resolve_surfaces("UA-0001"))

    def test_unapproved_surface_path_is_rejected(self):
        provider=self.provider()
        with self.assertRaisesRegex(binding.BindingError,"EVENT_SURFACE_SCOPE_MISMATCH"):
            provider.authorize(self.event,provider.resolve_surfaces("UA-0002"))

    def test_edited_receipt_bytes_are_detected_even_when_flags_remain_true(self):
        provider=self.provider()
        path=self.root/self.artifacts["deployment_receipt"]["path"]
        record=json.loads(path.read_bytes());record["request_sha256"]="c"*64
        path.write_bytes(binding.encoded(record))
        with self.assertRaisesRegex(binding.BindingError,"PINNED_FILE_HASH_MISMATCH"):
            self.authorize(provider)

    def test_forged_gate_pass_without_canonical_reference_fails(self):
        self.artifacts["gate_b"]=self.put("evidence/gate_b.json",{"status":"PASS"})
        config=self.put("private/config.json",{"delegation":self.delegation,"artifacts":self.artifacts})
        self.anchor_ref=self.put("private/anchor.json",{"contract":binding.ANCHOR_CONTRACT,"config_path":config["path"],"config_sha256":config["sha256"]})
        with self.assertRaisesRegex(binding.BindingError,"CANONICAL_REQUEST_CHAIN_MISMATCH"):
            self.provider()

    def test_symlink_to_pinned_code_is_rejected(self):
        provider=self.provider()
        path=self.root/"cars_ui.py";path.rename(self.root/"original.py");path.symlink_to(self.root/"original.py")
        with self.assertRaisesRegex(binding.BindingError,"SYMLINK_PATH_FORBIDDEN"):
            self.authorize(provider)

    def test_duplicate_json_key_cannot_override_pinned_semantics(self):
        with self.assertRaisesRegex(binding.BindingError,"DUPLICATE_JSON_KEY"):
            binding._json(b'{"status":"FAILED","status":"PASS"}')

    def test_bootstrap_preserves_post_init_and_does_not_read_uninitialized_bot(self):
        calls=[]
        class Bot:
            initialized=False
            @property
            def id(bot):
                if not bot.initialized:raise RuntimeError("Bot not initialized")
                return 123
        async def prior(app):calls.append("prior")
        app=SimpleNamespace(bot=Bot(),bot_data={},post_init=prior)
        actual=binding.bootstrap(app,anchor_path=self.anchor,test_root=self.root)
        self.assertIs(app.bot_data[runtime.BINDING_KEY],actual)
        self.assertEqual(calls,[])
        app.bot.initialized=True
        asyncio.run(app.post_init(app))
        self.assertEqual(calls,["prior"])
        provider=actual.authorize.__self__
        self.assertTrue(provider.running_bot_verified)

    def test_wrong_running_bot_refuses_after_initialize(self):
        app=SimpleNamespace(bot=SimpleNamespace(id=999),bot_data={},post_init=None)
        binding.bootstrap(app,anchor_path=self.anchor,test_root=self.root)
        with self.assertRaisesRegex(binding.BindingError,"RUNNING_CRM_BOT_IDENTITY_MISMATCH"):
            asyncio.run(app.post_init(app))

    def test_owner_fact_group_chat_even_fully_rehashed_is_rejected(self):
        self.chat["chat_type"]="group"
        self.artifacts["owner_private_chat"]=self.put("evidence/chat.json",self.chat)
        self.delegation["owner_private_chat_fact_sha256"]=self.artifacts["owner_private_chat"]["sha256"]
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError,"OWNER_PRIVATE_CHAT_FACT_REQUIRED"):
            self.provider()

    def external_cache(self):
        facts={"mode":{"path":str(self.root/"private/mode.json"),"sha256":binding.sha((self.root/"private/mode.json").read_bytes()),"value":"AUTOMATIC"},
               "halt":{"path":str(self.root/"private/halt.json"),"absent":True},
               "revocation":{"path":str(self.root/"private/revocation.json"),"sha256":binding.sha((self.root/"private/revocation.json").read_bytes()),"value":False}}
        self.controls["provenance"]="EXTERNAL_CACHE"
        self.controls["freshness"]={"source":"github:test-repo:main","producer_path":"start_safe.py",
                                      "path":"private/control_cache.json","max_age_ms":30000}
        self.cache={"source":"github:test-repo:main","observed_ms":self.now,"observations_sha256":binding.sha(binding.encoded(facts))}
        self.put("private/control_cache.json",self.cache)
        self.writers["control_contract_sha256"]=binding.sha(binding.encoded(self.controls))
        self.artifacts["writer_fences"]=self.put("evidence/writers.json",self.writers)
        self.delegation["writer_fence_report_sha256"]=self.artifacts["writer_fences"]["sha256"]
        self.rebuild_chain()

    def test_external_cache_binds_fresh_observations_and_caps_authorization_expiry(self):
        self.external_cache()
        provider=self.provider()
        self.now+=25000
        proof=self.authorize(provider)
        self.assertEqual(proof["expires_ms"],1000000+30000)
        self.now+=5001
        with self.assertRaisesRegex(binding.BindingError,"CONTROL_CACHE_STALE"):
            self.authorize(provider)

    def test_external_cache_future_timestamp_or_wrong_contents_never_authorizes(self):
        self.external_cache()
        provider=self.provider()
        self.cache["observed_ms"]=self.now+1
        self.put("private/control_cache.json",self.cache)
        with self.assertRaisesRegex(binding.BindingError,"CONTROL_CACHE_STALE"):
            self.authorize(provider)
        self.cache["observed_ms"]=self.now
        self.cache["observations_sha256"]="d"*64
        self.put("private/control_cache.json",self.cache)
        with self.assertRaisesRegex(binding.BindingError,"CONTROL_CACHE_CONTENT_BINDING_MISMATCH"):
            self.authorize(provider)

    def test_read_only_preflight_does_not_bootstrap_or_create_authorization_records(self):
        before={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result=binding.preflight(anchor_path=self.anchor,test_root=self.root)
        after={str(path.relative_to(self.root)):path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(result["status"],"INSTALLED_BINDING_VERIFIED_PENDING_BOT_INITIALIZATION")
        self.assertFalse(result["activated"])
        self.assertFalse(result["stage3_complete"])
        self.assertEqual(before,after)

    def test_read_only_preflight_without_actual_anchor_reports_blocked(self):
        result=binding.preflight(anchor_path=self.root/"private/not_installed.json",test_root=self.root)
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(result["activated"])

    def test_private_chat_summary_must_match_independently_read_raw_fact(self):
        fact=json.loads((self.root/self.raw_chat_fact["path"]).read_bytes())
        fact["chat_id"]=999
        self.raw_chat_fact=self.put(self.raw_chat_fact["path"],fact)
        self.chat["evidence"]=self.raw_chat_fact
        self.artifacts["owner_private_chat"]=self.put("evidence/chat.json",self.chat)
        self.delegation["owner_private_chat_fact_sha256"]=self.artifacts["owner_private_chat"]["sha256"]
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError,"PRIVATE_CHAT_SUMMARY_OBSERVATION_MISMATCH"):
            self.provider()


class BindingV5Tests(unittest.TestCase):
    """Real v5 admission/claims with an expressly synthetic installer chain."""
    put = BindingTests.put
    rebuild_chain = BindingTests.rebuild_chain
    provider = BindingTests.provider
    authorize = BindingTests.authorize
    tearDown = BindingTests.tearDown

    def setUp(self):
        BindingTests.setUp(self)
        for name in binding.V5_REQUIRED_CODE:
            content=("# isolated TEST source "+name+"\n").encode()
            (self.root/name).write_bytes(content)
            self.code[name]=binding.sha(content)
        with sqlite3.connect(self.db) as conn:
            conn.execute("ALTER TABLE cars ADD COLUMN vin TEXT")
            conn.execute("UPDATE cars SET vin='TESTVIN' || printf('%010d',id)")
            conn.execute("CREATE TABLE staff(user_id INTEGER PRIMARY KEY, active INTEGER, role TEXT)")
            conn.execute("INSERT INTO staff VALUES(700,1,'manager')")
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            outbox.install_v5(conn)
            conn.commit()
            self.schema = binding.schema_sha256(conn)
        self.delegation.update(contract=binding.CONTRACT_V5,
            operation="UPDATE_PUBLISHED_CAR_HOME_CATALOG_PRICES",
            identity_policy="AUTHENTICATED_CRM_PUBLISHED_CARS", schema_sha256=self.schema,
            operator_policy={"source":"AUTHENTICATED_TELEGRAM_UPDATE",
                             "permission":"EXISTING_CRM_EDIT_CAR_ACL", "chat_types":["private"],
                             "roles":["owner","admin","manager"]},
            surface_templates=[
                {"kind":"CARD", "path":"video/{auto_number}.html", "url":"https://example.test/video/{auto_number}.html", "price_applicable":True},
                {"kind":"CATALOG", "path":"video/katalog.html", "url":"https://example.test/video/katalog.html", "price_applicable":True},
                {"kind":"HOME", "path":"video/index.html", "url":"https://example.test/video/index.html", "price_applicable":False}])
        del self.delegation["surfaces"]
        self.rebuild_chain()
        self.event = self.new_operation()

    def provenance(self, car_id=1, **changes):
        return dict({"source":"SYNTHETIC_TEST", "actor_id":700, "chat_id":700,
                     "message_id":80, "update_id":900, "chat_type":"private", "bot_id":123,
                     "authorized_car_id":car_id, "permission":"EDIT_CAR"}, **changes)

    def test_missing_installed_reader_pin_refuses_v5_binding(self):
        self.code.pop("uaart_price_control_reader.py")
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError, "ALL_INSTALLED_WRITERS_AND_MODULES_REQUIRED"):
            self.provider()

    def new_operation(self, car_id=1, key="c"*64, provenance=None):
        with sqlite3.connect(self.db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            facts = self.provenance(car_id) if provenance is None else provenance
            outbox.submit(conn, event_key=key, car_id=car_id, field="price_georgia", value="6000",
                          actor_id=700, chat_id=facts["chat_id"], now_ms=self.now, provenance=facts)
            event = outbox.claim_operation(conn, event_key=key, nonce=binding.sha((key+"claim").encode()), now_ms=self.now)
            conn.commit()
        return event

    def test_verified_operator_claim_binds_actor_origin_and_actual_vin(self):
        proof = self.authorize()
        self.assertEqual(proof["operator_chat_id"],700)
        self.assertEqual(proof["operator_user_id"],700)
        self.assertNotEqual(proof["operator_chat_id"],self.delegation["owner_chat_id"])
        self.assertEqual(proof["revision"],self.event["sequence"])
        self.assertEqual(len(proof["allowed_paths"]),3)
        self.assertEqual(proof["operator_provenance_sha256"],binding.sha(binding.encoded(self.provenance())))

    def test_future_published_identity_needs_no_new_config_or_approval(self):
        provider = self.provider()
        before = self.anchor.read_bytes(), (self.root/"private/config.json").read_bytes()
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO cars VALUES (19,'UA-0019',1,12000,NULL,'TESTVIN0000000019')")
        self.event = self.new_operation(car_id=19,key="e"*64)
        descriptor = os.open(self.lock,os.O_RDWR)
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX)
            proof = provider.authorize(self.event,provider.resolve_surfaces("UA-0019"))
        finally:
            os.close(descriptor)
        self.assertEqual(proof["auto_number"],"UA-0019")
        self.assertIn(str(self.root/"video/UA-0019.html"),proof["allowed_paths"])
        self.assertEqual(before,(self.anchor.read_bytes(),(self.root/"private/config.json").read_bytes()))
        self.assertEqual(provider.binding().resolve_identity(19)["vin"],"TESTVIN0000000019")

    def test_unpublished_or_ambiguous_identity_cannot_get_surfaces(self):
        provider = self.provider()
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO cars VALUES (19,'UA-0019',0,12000,NULL,'TESTVIN0000000019')")
        with self.assertRaisesRegex(binding.BindingError,"PUBLISHED_CRM_IDENTITY_REQUIRED"):
            provider.resolve_surfaces("UA-0019")
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET published=1 WHERE id=19")
            conn.execute("INSERT INTO cars VALUES (20,'UA-0019',1,13000,NULL,'TESTVIN0000000020')")
        with self.assertRaisesRegex(binding.BindingError,"PUBLISHED_CRM_IDENTITY_REQUIRED"):
            provider.resolve_surfaces("UA-0019")

    def test_dynamic_policy_does_not_unpin_existing_identity(self):
        provider = self.provider()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET auto_number='UA-0040' WHERE id=1")
        with self.assertRaisesRegex(binding.BindingError,"LIVE_CAR_REGISTRY_DRIFT"):
            provider.resolve_identity(1)

    def test_claim_vin_must_match_independent_current_db_read(self):
        provider = self.provider()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET vin='TESTVIN0000009999' WHERE id=1")
        with self.assertRaisesRegex(binding.BindingError,"EVENT_CRM_VIN_MISMATCH"):
            self.authorize(provider)

    def test_mutated_event_is_not_a_durable_claim(self):
        self.event = dict(self.event, value="200")
        with self.assertRaisesRegex(binding.BindingError,"DURABLE_CURRENT_EVENT_CLAIM_REQUIRED"):
            self.authorize()

    def test_missing_actual_permission_or_wrong_bot_blocks_claim(self):
        for i, change in enumerate(({"permission":"VIEW_CAR"},{"bot_id":999},{"authorized_car_id":2})):
            with self.subTest(change=change):
                with sqlite3.connect(self.db) as conn:
                    conn.execute("INSERT INTO cars VALUES (? ,?,1,12000,NULL,?)",(21+i,f"UA-{21+i:04d}",f"TESTVIN{21+i:010d}"))
                self.event = self.new_operation(car_id=21+i, key=str(i+1)*64,
                                               provenance=self.provenance(21+i,**change))
                provider=self.provider()
                descriptor=os.open(self.lock,os.O_RDWR)
                try:
                    fcntl.flock(descriptor,fcntl.LOCK_EX)
                    with self.assertRaises(binding.BindingError):
                        provider.authorize(self.event,provider.resolve_surfaces(self.event["car_code"]))
                finally:os.close(descriptor)

    def test_synthetic_provenance_cannot_be_used_by_production_verifier(self):
        provider=self.provider()
        provider.testing=False
        with self.assertRaisesRegex(binding.BindingError,"AUTHENTICATED_OPERATOR_UPDATE_REQUIRED"):
            provider._operator_provenance(self.event)

    def test_revoked_existing_staff_permission_blocks_previously_claimed_work(self):
        provider=self.provider()
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE staff SET active=0 WHERE user_id=700")
        with self.assertRaisesRegex(binding.BindingError,"CURRENT_CRM_EDIT_PERMISSION_REQUIRED"):
            self.authorize(provider)

    def test_unrecognized_staff_role_cannot_be_delegated(self):
        self.delegation["operator_policy"]["roles"].append("observer")
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError,"EXPLICIT_OPERATOR_PERMISSION"):
            self.provider()

    def test_home_applicability_is_explicit_and_read_only_when_no_vehicle_tiles(self):
        surfaces=self.provider().resolve_surfaces("UA-0001")
        self.assertEqual([(s.kind,s.price_applicable) for s in surfaces],
                         [("CARD",True),("CATALOG",True),("HOME",False)])
        del self.delegation["surface_templates"][2]["price_applicable"]
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError,"EXACT_SURFACE_FIELDS_REQUIRED"):
            self.provider()

    def test_template_cannot_change_origin_escape_root_or_omit_home(self):
        originals=[dict(item) for item in self.delegation["surface_templates"]]
        for key,value in (("path","../{auto_number}.html"),("url","https://foreign.test/{auto_number}.html")):
            self.delegation["surface_templates"]=[dict(item) for item in originals]
            self.delegation["surface_templates"][0][key]=value
            self.rebuild_chain()
            with self.assertRaises(binding.BindingError):self.provider()
        self.delegation["surface_templates"]=originals[:2]
        self.rebuild_chain()
        with self.assertRaisesRegex(binding.BindingError,"EXACT_CARD_CATALOG_HOME_TEMPLATES_REQUIRED"):
            self.provider()


if __name__ == "__main__":
    unittest.main()
