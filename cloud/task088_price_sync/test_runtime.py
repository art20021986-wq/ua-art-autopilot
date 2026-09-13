"""Candidate runtime tests use isolated SQLite/files and synthetic public reads."""
import asyncio
from contextlib import contextmanager
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest


HERE = Path(__file__).resolve().parent
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


outbox = load("uaart_price_sync_outbox", HERE / "outbox.py")
prices = load("uaart_market_prices", HERE.parent / "task088_stage3_renderer" / "uaart_market_prices.py")
load("owner_policy", HERE.parent / "task088_autopilot_owner_policy" / "owner_policy.py")
load("price_publication", HERE.parent / "task088_autopilot_owner_policy" / "price_publication.py")
runtime = load("uaart_price_sync_runtime", HERE / "uaart_price_sync_runtime.py")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "crm.db"
        self.journals = self.root / "journals"
        self.journals.mkdir()
        self.clock_ms = 1_000_000
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE cars (id INTEGER PRIMARY KEY,auto_number TEXT,published INTEGER,price_uah INTEGER,price_georgia INTEGER,description TEXT)")
            conn.execute("INSERT INTO cars VALUES (1,'UA-0001',1,20000,5000,'preserved one')")
            conn.execute("INSERT INTO cars VALUES (2,'UA-0002',1,9000,NULL,'preserved two')")
            conn.commit()
            conn.execute("BEGIN IMMEDIATE")
            runtime.install(conn)
            conn.commit()
        self.paths = {"UA-0001": self.root / "UA-0001.html", "UA-0002": self.root / "UA-0002.html"}
        self.catalog = self.root / "katalog.html"
        self.old_fragments = {}
        for code, path in self.paths.items():
            old = dict(auto_number=code, price_uah=18000 if code == "UA-0001" else 9000, price_georgia=None)
            self.old_fragments[code] = prices.render_market_prices(old, require_car_id=True)
            path.write_text('<html><div data-spec="preserved">Спецификация 🚗</div>' + self.old_fragments[code] + '<img src="original.jpg"></html>')
        self.catalog.write_text('<html><nav>5/5/4/4</nav>' + ''.join(
            '<article class="catalog-card"><a href="%s.html?x=1"><img src="%s.jpg"></a>%s<a href="%s.html">Подробнее</a></article>'
            % (code, code, prices.render_market_prices(dict(auto_number=code, price_uah=18000 if code == "UA-0001" else 9000), compact=True, require_car_id=True), code)
            for code in self.paths) + '</html>')
        self.url_paths = {"https://example.test/" + path.name: path for path in (*self.paths.values(), self.catalog)}
        self.binding = runtime.Binding(db_path=self.db, publication_lock=self.root / ".publish.lock", journal_root=self.journals,
            resolve_surfaces=lambda code: (runtime.Surface("CARD", self.paths[code], "https://example.test/" + code + ".html"),
                                           runtime.Surface("CATALOG", self.catalog, "https://example.test/katalog.html")),
            authorize=self.authority, owner_chat_id=123, detail_url="https://example.test/report", owner_private_chat_verified=True,
            car_identities=((1,"UA-0001"),(2,"UA-0002")),
            read_public=lambda url: self.url_paths[url].read_bytes(), clock=lambda: self.clock_ms)
        self.worker = runtime.Worker(self.binding)
        self.initial = {path: path.read_bytes() for path in (*self.paths.values(), self.catalog)}
        self.key = self.enqueue(1, "20000.00", "5000.00")

    def tearDown(self):
        self.temp.cleanup()

    def authority(self, event, surfaces):
        # Explicit synthetic test authority; never exported as a live receipt.
        return dict(canonical_task_id="TEST", canonical_claim_id="TEST-CLAIM", canonical_transaction_id="TEST-TXN",
                    gate_b_receipt_sha256="a" * 64, event_key=event["event_key"], claim_nonce=event["claim_nonce"],
                    allowed_paths=[str(item.path) for item in surfaces], writer_fence_verified=True,
                    expires_ms=self.clock_ms + 1000)

    def enqueue(self, car_id, ua, ge):
        key = runtime.digest(f"{car_id}:{ua}:{ge}:{self.clock_ms}".encode())
        with sqlite3.connect(self.db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            outbox.enqueue(conn, event_key=key, car_id=car_id, ukraine_usd=ua, georgia_usd=ge, now_ms=self.clock_ms)
            conn.commit()
        return key

    def event(self, key=None):
        with sqlite3.connect(self.db) as conn:
            return outbox.get(conn, key or self.key)

    def notices(self):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(f"SELECT kind,state,text FROM {runtime.NOTICE_TABLE} ORDER BY kind").fetchall()

    def test_real_local_publish_updates_both_surfaces_preserves_other_car_and_crm(self):
        self.assertEqual(self.worker.tick(), "PUBLISHED")
        event = self.event()
        self.assertEqual(event["state"], "PUBLISHED")
        self.assertEqual(self.paths["UA-0002"].read_bytes(), self.initial[self.paths["UA-0002"]])
        old_catalog = self.initial[self.catalog].decode()
        new_catalog = self.catalog.read_text()
        start, end = runtime.fragment_span(old_catalog, kind="CATALOG", code="UA-0001")
        a, b = runtime.fragment_span(new_catalog, kind="CATALOG", code="UA-0001")
        self.assertEqual(old_catalog[:start] + old_catalog[end:], new_catalog[:a] + new_catalog[b:])
        receipt = (self.journals / self.key / "receipt.json").read_bytes()
        self.assertEqual(runtime.digest(receipt), event["receipt_sha256"])
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT price_uah,price_georgia,description FROM cars WHERE id=1").fetchone(), (20000,5000,"preserved one"))
        self.assertEqual(self.worker.tick(), "IDLE")
        self.assertEqual(self.notices(), [])

    def test_foreign_publication_lock_prevents_even_claim(self):
        with self.worker.lock():
            self.assertEqual(runtime.Worker(self.binding).tick(), "BUSY")
        self.assertEqual(self.event()["state"], "PENDING")

    def test_db_write_lock_spans_switch_and_public_readback(self):
        original = self.worker._switch
        def switch(prepared):
            with sqlite3.connect(self.db, timeout=0) as other:
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    other.execute("BEGIN IMMEDIATE")
            original(prepared)
        self.worker._switch = switch
        self.assertEqual(self.worker.tick(), "PUBLISHED")

    def test_partial_switch_rolls_back_only_known_files_and_keeps_crm(self):
        def partial(prepared):
            surface, before, after, mode = prepared[0]
            runtime._atomic_write(surface.path, after, mode)
            raise OSError("synthetic interruption")
        self.worker._switch = partial
        self.assertEqual(self.worker.tick(), "STOPPED")
        for path, before in self.initial.items():
            self.assertEqual(path.read_bytes(), before)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT price_georgia FROM cars WHERE id=1").fetchone()[0], 5000)
        self.assertEqual(self.worker.tick(), "IDLE")
        self.assertEqual([(kind,state) for kind,state,_ in self.notices()], [("FAILURE","PENDING")])

    def test_foreign_bytes_never_overwritten_during_rollback(self):
        def partial(prepared):
            surface, before, after, mode = prepared[0]
            runtime._atomic_write(surface.path, after, mode)
            self.catalog.write_bytes(b"foreign-writer-new-content")
            raise OSError("synthetic interruption")
        self.worker._switch = partial
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.catalog.read_bytes(), b"foreign-writer-new-content")
        self.assertEqual(self.paths["UA-0001"].read_bytes(), self.initial[self.paths["UA-0001"]])
        self.assertEqual(self.event()["reason"], "ROLLBACK_AMBIGUOUS_REQUIRES_RECONCILIATION")

    def test_interrupted_car_does_not_replay_and_independent_car_preserved(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("BEGIN IMMEDIATE")
            outbox.claim(conn,event_key=self.key,nonce="c"*64,now_ms=self.clock_ms)
            conn.execute("UPDATE cars SET price_uah=9500 WHERE id=2")
            conn.commit()
        key2 = self.enqueue(2,"9500.00",None)
        self.assertEqual(self.worker.tick(), "PUBLISHED")
        self.assertEqual(self.event()["state"], "STOPPED")
        self.assertEqual(self.event(key2)["state"], "PUBLISHED")
        self.assertEqual(self.paths["UA-0001"].read_bytes(), self.initial[self.paths["UA-0001"]])
        catalog = self.catalog.read_text()
        a,b = runtime.fragment_span(catalog,kind="CATALOG",code="UA-0001")
        self.assertIn('data-ua-value="18000"',catalog[a:b])
        self.assertNotIn('data-ua-value="20000"',catalog[a:b])

    def test_stale_crm_never_published(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET price_uah=21000 WHERE id=1")
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.event()["reason"], "CRM_CHANGED_NEVER_REPLAY_OLD_PRICE")
        self.assertEqual(self.catalog.read_bytes(), self.initial[self.catalog])

    def test_no_first_publication(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET published=0 WHERE id=1")
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.event()["reason"], "EXISTING_PUBLISHED_CAR_REQUIRED")

    def test_missing_or_wrong_identity_marker_stops(self):
        self.paths["UA-0001"].write_text(self.paths["UA-0001"].read_text().replace('data-ua-car="UA-0001"','data-ua-car="UA-0099"'))
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.event()["reason"], "EXISTING_PRICE_CAR_IDENTITY_MISMATCH")

    def test_reject_unfenced_authority_before_public_mutation(self):
        def bad(event,surfaces):
            proof=self.authority(event,surfaces)
            proof["writer_fence_verified"]=False
            return proof
        self.worker=runtime.Worker(replace(self.binding,authorize=bad))
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertIn(b"CLAIMED_NO_EFFECTS",(self.journals/self.key/"journal.json").read_bytes())
        self.assertEqual(self.catalog.read_bytes(),self.initial[self.catalog])

    def test_stale_public_readback_stops_and_rolls_back(self):
        calls={}
        def read(url):
            calls[url]=calls.get(url,0)+1
            path=self.url_paths[url]
            return path.read_bytes() if calls[url]==1 else self.initial[path]
        self.worker=runtime.Worker(replace(self.binding,read_public=read))
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.event()["reason"], "PUBLIC_READBACK_OR_LOCAL_POSTIMAGE_MISMATCH")
        self.assertEqual(self.catalog.read_bytes(),self.initial[self.catalog])

    def test_public_preimage_divergence_causes_zero_writes(self):
        self.worker=runtime.Worker(replace(self.binding,read_public=lambda url:b"different-serving-root"))
        self.assertEqual(self.worker.tick(), "STOPPED")
        self.assertEqual(self.event()["reason"], "PUBLIC_PREIMAGE_DIFFERS_FROM_BOUND_FILE")
        self.assertEqual(self.catalog.read_bytes(),self.initial[self.catalog])

    def test_commit_that_raises_after_actual_commit_never_rolls_back_publication(self):
        class AmbiguousConnection(sqlite3.Connection):
            commits=0
            def commit(conn):
                conn.commits+=1
                super().commit()
                if conn.commits==2:
                    raise OSError("commit completed but acknowledgement failed")
        @contextmanager
        def connection():
            conn=sqlite3.connect(self.db,factory=AmbiguousConnection)
            try: yield conn
            finally: conn.close()
        self.worker.connection=connection
        self.assertEqual(self.worker.tick(),"PUBLISHED_COMMIT_OBSERVED")
        self.assertEqual(self.event()["state"],"PUBLISHED")
        self.assertIn('data-ua-value="20000"',self.paths["UA-0001"].read_text())

    def test_ready_delay_over_five_minutes_notified_once_and_no_late_replay(self):
        self.clock_ms+=300001
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"PUBLICATION_DEADLINE_MISSED_BEFORE_SWITCH")
        self.assertEqual([row[0] for row in self.notices()],["DELAY","FAILURE"])
        self.assertEqual(self.worker.tick(),"IDLE")
        self.assertEqual(len(self.notices()),2)

    def test_successful_publication_with_late_readback_is_explicitly_late(self):
        calls=0
        def read(url):
            nonlocal calls
            calls+=1
            if calls==3:self.clock_ms+=61000
            return self.url_paths[url].read_bytes()
        self.worker=runtime.Worker(replace(self.binding,read_public=read))
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        self.assertEqual([row[0] for row in self.notices()],["LATE"])

    def test_telegram_failure_never_blindly_retries_and_daily_mentions_ambiguity(self):
        self.worker=runtime.Worker(replace(self.binding,read_public=lambda url:b"wrong"))
        self.worker.tick()
        class Bot:
            calls=0
            async def send_message(bot,**kwargs):
                bot.calls+=1
                self.assertEqual(kwargs["chat_id"],123)
                raise TimeoutError("delivery unknown")
        bot=Bot()
        asyncio.run(self.worker.deliver_notices(bot))
        asyncio.run(self.worker.deliver_notices(bot))
        self.assertEqual(bot.calls,1)
        self.assertEqual(self.notices()[0][1],"AMBIGUOUS")
        self.worker.queue_daily()
        self.worker.queue_daily()
        self.assertEqual(len(self.notices()),2)
        self.assertIn("без подтверждения доставки: 1",self.notices()[0][2])

    def test_telegram_confirmed_delivery_not_repeated(self):
        self.worker.queue_daily()
        class Bot:
            calls=0
            async def send_message(bot,**kwargs):
                bot.calls+=1
                return SimpleNamespace(message_id=99)
        bot=Bot()
        asyncio.run(self.worker.deliver_notices(bot))
        asyncio.run(self.worker.deliver_notices(bot))
        self.assertEqual(bot.calls,1)
        self.assertEqual(self.notices()[0][1],"SENT")

    def test_register_requires_verified_binding_and_uses_vietnam_10am(self):
        class Queue:
            jobs={}
            def get_jobs_by_name(queue,name):return queue.jobs.get(name,())
            def run_repeating(queue,callback,**kwargs):queue.jobs[kwargs["name"]]=kwargs
            def run_daily(queue,callback,**kwargs):queue.jobs[kwargs["name"]]=kwargs
        app=SimpleNamespace(bot_data={},job_queue=Queue())
        with self.assertRaisesRegex(runtime.SyncError,"VERIFIED_BINDING"):
            runtime.register(app)
        app.bot_data[runtime.BINDING_KEY]=self.binding
        runtime.register(app)
        runtime.register(app)
        self.assertEqual(len(app.job_queue.jobs),2)
        self.assertEqual(app.job_queue.jobs["uaart-price-sync-v1"]["interval"],5)
        daily=app.job_queue.jobs["uaart-price-sync-daily-v1"]["time"]
        self.assertEqual((daily.hour,daily.minute,str(daily.tzinfo)),(10,0,"Asia/Ho_Chi_Minh"))

    def test_legacy_single_anchor_catalog_is_supported(self):
        self.catalog.write_text('<html><a class="kat" href="UA-0001.html">'+self.old_fragments["UA-0001"]+'</a></html>')
        self.assertEqual(self.worker.tick(),"PUBLISHED")

    def test_duplicate_catalog_tiles_block_publication(self):
        self.catalog.write_text(self.catalog.read_text()+self.catalog.read_text())
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"EXACTLY_ONE_CATALOG_TILE_REQUIRED")

    def recovery_builder(self, outcome):
        def build(event, facts, observation_hash):
            return outbox.RecoveryEvidence(
                recovery_key="f"*64,event_key=event["event_key"],claim_nonce=event["claim_nonce"],
                current_revision=facts["current_revision"],outcome=outcome,reason="VERIFIED_SYNTHETIC_TEST_RECOVERY",
                cause_resolved=True,preflight_verified=True,public_state_verified=True,
                prices_match_current=facts["prices_match_current"],cause_fix_sha256="a"*64,
                preflight_sha256="b"*64,preflight_ms=facts["observed_ms"],observed_ms=facts["observed_ms"],
                card_sha256=facts["card_sha256"],catalog_sha256=facts["catalog_sha256"],evidence_sha256="e"*64,
                publication_receipt_sha256=observation_hash if outcome=="PUBLISHED" else None)
        return build

    def test_verified_restoration_closes_old_attempt_allows_only_new_revision(self):
        original=self.worker._switch
        def fail(prepared):
            original(prepared)
            raise OSError("test known switch failure")
        self.worker._switch=fail
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.clock_ms+=1
        with sqlite3.connect(self.db) as conn:conn.execute("UPDATE cars SET price_uah=22000 WHERE id=1")
        newer=self.enqueue(1,"22000.00","5000.00")
        self.assertEqual(self.worker.tick(),"IDLE")
        recovered=self.worker.reconcile_recovered(self.key,self.recovery_builder("RESTORED"))
        self.assertEqual(recovered["state"],"RECONCILED")
        self.assertEqual(self.paths["UA-0001"].read_bytes(),self.initial[self.paths["UA-0001"]])
        self.worker._switch=original
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        self.assertEqual(self.event(newer)["state"],"PUBLISHED")
        self.assertEqual(self.event()["state"],"RECONCILED")

    def test_forged_recovery_observation_binding_is_rejected(self):
        self.worker._switch=lambda prepared: (_ for _ in ()).throw(OSError("before switch"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.clock_ms+=1
        builder=self.recovery_builder("RESTORED")
        def wrong(event,facts,sha):return replace(builder(event,facts,sha),card_sha256="0"*64)
        with self.assertRaisesRegex(runtime.SyncError,"ACTUAL_OBSERVATION_MISMATCH"):
            self.worker.reconcile_recovered(self.key,wrong)
        self.assertEqual(self.event()["state"],"STOPPED")

    def test_ambiguous_commit_before_commit_can_be_reconciled_without_republishing(self):
        class FailBeforeCommit(sqlite3.Connection):
            commits=0
            def commit(conn):
                conn.commits+=1
                if conn.commits==2:raise OSError("commit not confirmed")
                super().commit()
        @contextmanager
        def connection():
            conn=sqlite3.connect(self.db,factory=FailBeforeCommit)
            try:yield conn
            finally:conn.close()
        self.worker.connection=connection
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"COMMIT_AMBIGUOUS_REQUIRES_RECONCILIATION")
        published=self.catalog.read_bytes()
        self.worker=runtime.Worker(self.binding)
        self.clock_ms+=1
        recovered=self.worker.reconcile_recovered(self.key,self.recovery_builder("PUBLISHED"))
        self.assertEqual(recovered["state"],"PUBLISHED")
        self.assertEqual(self.catalog.read_bytes(),published)
        self.assertEqual(self.worker.tick(),"IDLE")

    def test_recovered_publication_rejects_foreign_non_price_edits(self):
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        with sqlite3.connect(self.db) as conn:
            conn.execute(f"UPDATE {outbox.TABLE} SET state='STOPPED',reason='SYNTHETIC_TEST_INTERRUPTION' WHERE event_key=?",(self.key,))
        path=self.paths["UA-0001"]
        path.write_text(path.read_text().replace("Спецификация 🚗","FOREIGN SPEC CHANGE"))
        self.clock_ms+=1
        with self.assertRaisesRegex(runtime.SyncError,"NON_PRICE_CONTENT_CHANGED"):
            self.worker.reconcile_recovered(self.key,self.recovery_builder("PUBLISHED"))
        self.assertEqual(self.event()["state"],"STOPPED")
        self.assertIn("FOREIGN SPEC CHANGE",path.read_text())

    def test_verified_recovery_creates_one_fresh_successor_and_proof_replay_is_read_only(self):
        original=self.worker._switch
        self.worker._switch=lambda prepared: (_ for _ in ()).throw(OSError("test no effect"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.clock_ms+=1
        def allowed(event,surfaces):
            proof=self.authority(event,surfaces)
            proof["verified_recovery_successor_allowed"]=True
            return proof
        self.worker=runtime.Worker(replace(self.binding,authorize=allowed))
        builder=self.recovery_builder("NO_EFFECT")
        self.worker.reconcile_recovered(self.key,builder,resume_current=True,recovery_key="f"*64)
        with sqlite3.connect(self.db) as conn:
            rows=conn.execute(f"SELECT event_key,state,revision,claim_nonce FROM {outbox.TABLE} ORDER BY revision").fetchall()
            self.assertEqual(conn.execute("SELECT price_uah,price_georgia FROM cars WHERE id=1").fetchone(),(20000,5000))
        self.assertEqual([(row[1],row[2]) for row in rows],[("RECONCILED",1),("PENDING",2)])
        self.assertIsNone(rows[1][3])
        self.worker.reconcile_recovered(self.key,builder,resume_current=True,recovery_key="f"*64)
        with sqlite3.connect(self.db) as conn:self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {outbox.TABLE}").fetchone()[0],2)
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        self.assertNotEqual(self.event(rows[1][0])["claim_nonce"],rows[0][3])

    def test_recovery_successor_without_reviewed_delegation_rolls_back_closure(self):
        self.worker._switch=lambda prepared: (_ for _ in ()).throw(OSError("test no effect"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.clock_ms+=1
        with self.assertRaisesRegex(runtime.SyncError,"SUCCESSOR_DELEGATION_REQUIRED"):
            self.worker.reconcile_recovered(self.key,self.recovery_builder("NO_EFFECT"),resume_current=True)
        self.assertEqual(self.event()["state"],"STOPPED")

    def test_car_identity_reassignment_cannot_publish_another_vehicle(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET auto_number='UA-0002' WHERE id=1")
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"PINNED_CAR_IDENTITY_CHANGED")
        self.assertEqual(self.paths["UA-0002"].read_bytes(),self.initial[self.paths["UA-0002"]])

    def test_duplicate_car_code_blocks_even_pinned_target(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE cars SET auto_number='UA-0001' WHERE id=2")
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"DUPLICATE_CRM_CAR_CODE")

    def test_clock_before_persisted_event_creates_durable_runtime_stop_and_notice(self):
        self.clock_ms-=1000
        self.assertEqual(self.worker.tick(),"RUNTIME_STOPPED")
        failures=list((self.journals/"runtime_failures").glob("*.json"))
        self.assertEqual(len(failures),1)
        self.assertIn(b"CLAIM_BEFORE_EVENT",failures[0].read_bytes())
        self.clock_ms+=10000
        self.assertEqual(self.worker.tick(),"RUNTIME_STOPPED")
        self.assertEqual(self.event()["state"],"PENDING")

    def test_runtime_failure_notifies_without_working_crm_database(self):
        self.db.rename(self.root/"crm-offline.db")
        self.assertEqual(self.worker.tick(),"RUNTIME_STOPPED")
        class Bot:
            calls=0
            async def send_message(bot,**kwargs):
                bot.calls+=1
                return SimpleNamespace(message_id=321)
        bot=Bot()
        asyncio.run(self.worker.deliver_notices(bot))
        asyncio.run(self.worker.deliver_notices(bot))
        self.assertEqual(bot.calls,1)
        self.assertEqual(len(list((self.journals/"runtime_failures").glob("*.json"))),1)

    def test_restoration_can_follow_verified_other_car_catalog_publication(self):
        original=self.worker._switch
        self.worker._switch=lambda prepared: (_ for _ in ()).throw(OSError("test A fail"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.worker._switch=original
        with sqlite3.connect(self.db) as conn:conn.execute("UPDATE cars SET price_uah=9500 WHERE id=2")
        self.clock_ms+=1
        self.enqueue(2,"9500.00",None)
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        before_recovery=self.catalog.read_bytes()
        recovered=self.worker.reconcile_recovered(self.key,self.recovery_builder("RESTORED"))
        self.assertEqual(recovered["state"],"RECONCILED")
        self.assertEqual(self.catalog.read_bytes(),before_recovery)
        self.assertIn('data-ua-value="9500"',self.paths["UA-0002"].read_text())

    def test_other_car_unreceipted_catalog_changes_cannot_be_used_as_recovery_chain(self):
        self.worker._switch=lambda prepared: (_ for _ in ()).throw(OSError("test A fail"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.catalog.write_text(self.catalog.read_text().replace('data-ua-value="9000"','data-ua-value="9500"'))
        self.clock_ms+=1
        with self.assertRaisesRegex(runtime.SyncError,"PREIMAGES_NOT_RESTORED"):
            self.worker.reconcile_recovered(self.key,self.recovery_builder("RESTORED"))
        self.assertEqual(self.event()["state"],"STOPPED")

    def test_preflight_no_effect_failure_can_be_verified_and_closed(self):
        self.worker=runtime.Worker(replace(self.binding,read_public=lambda url:b"wrong serving origin"))
        self.assertEqual(self.worker.tick(),"STOPPED")
        self.assertEqual(self.event()["reason"],"PUBLIC_PREIMAGE_DIFFERS_FROM_BOUND_FILE")
        self.clock_ms+=1
        self.worker=runtime.Worker(self.binding)
        result=self.worker.reconcile_recovered(self.key,self.recovery_builder("NO_EFFECT"))
        self.assertEqual(result["state"],"RECONCILED")
        for path,value in self.initial.items():self.assertEqual(path.read_bytes(),value)

    def test_runtime_stop_resumes_only_after_verified_cause_fix_and_fresh_checks(self):
        self.clock_ms-=1000
        self.assertEqual(self.worker.tick(),"RUNTIME_STOPPED")
        path=next((self.journals/"runtime_failures").glob("*.json"))
        self.clock_ms+=2000
        with self.assertRaisesRegex(runtime.SyncError,"RECOVERY_PROOF_REQUIRED"):
            self.worker.resolve_runtime_failure(path,lambda facts:{})
        self.assertEqual(self.worker.tick(),"RUNTIME_STOPPED")
        def verify(facts):
            return dict(facts,cause_resolved=True,preflight_verified=True,gate_b_verified=True,
                        gate_b_receipt_sha256="a"*64,evidence_sha256="b"*64)
        self.assertEqual(self.worker.resolve_runtime_failure(path,verify),"RUNTIME_CAUSE_VERIFIED_RESOLVED")
        self.assertEqual(self.event()["state"],"PENDING")
        self.assertEqual(self.worker.tick(),"PUBLISHED")
        self.assertEqual(self.worker.resolve_runtime_failure(path,verify),"ALREADY_RESOLVED")

    def test_new_incident_after_verified_resolution_gets_new_notice(self):
        self.worker.record_runtime_failure(runtime.SyncError("SYNTHETIC_RUNTIME_FAILURE"))
        path=next((self.journals/"runtime_failures").glob("*.json"))
        self.worker.resolve_runtime_failure(path,lambda facts:dict(facts,cause_resolved=True,
            preflight_verified=True,gate_b_verified=True,gate_b_receipt_sha256="a"*64,evidence_sha256="b"*64))
        self.worker.record_runtime_failure(runtime.SyncError("SYNTHETIC_RUNTIME_FAILURE"))
        self.assertEqual(len(list((self.journals/"runtime_failures").glob("*.json"))),2)
        self.assertTrue(self.worker._runtime_blocked())

    def test_daily_fallback_survives_database_outage_without_repeating_same_day(self):
        self.db.rename(self.root/"crm-offline.db")
        self.worker.queue_daily_unavailable()
        self.worker.queue_daily_unavailable()
        notices=list((self.journals/"runtime_failures").glob("daily-*.json"))
        self.assertEqual(len(notices),1)
        self.assertIn("статистика CRM недоступна",json.loads(notices[0].read_bytes())["text"])


if __name__ == "__main__":
    unittest.main()
