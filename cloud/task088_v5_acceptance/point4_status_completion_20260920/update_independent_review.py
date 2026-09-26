from pathlib import Path
import json,hashlib,datetime
HERE=Path(__file__).parent; ROOT=HERE.parent/'pr114_review/cloud'
p=HERE/'STATUS_LIFECYCLE_INDEPENDENT_REVIEW.json';r=json.loads(p.read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r['status']='SCOPED_CODE_PASS_FINAL_CANDIDATE_BINDING_PENDING'
r['updated_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
r['scope']='Independent review of exact saved private native call graph, current composed source outputs, changed public price/native/publisher/counter code, and isolated targeted probes. Full final installer candidate binding and current Preview/live/runtime acceptance remain separate.'
r['open_scoped_code_blockers']=[]
for f in r['review_feedback_during_implementation']:f['status']='RESOLVED_REVIEWED_CODE_AND_TARGETED_EVIDENCE'
r['review_feedback_during_implementation'] += [
 {'id':'S7','topic':'actual_catalog_counter_identity','finding':'Real dual-price translation data-ua captions were rejected as vehicle identifiers by server/client counters.','status':'RESOLVED_EXACT_PINNED_SERVER_CLIENT_PATCH_AND_REAL_HTML_PROBE'},
 {'id':'S8','topic':'authority_scope','finding':'Prior published-price-only delegation must not silently authorize all-record edits or native visibility.','status':'RESOLVED_EXACT_ALL_RECORD_AND_VISIBILITY_DELEGATION_REQUIRED'},
 {'id':'S9','topic':'hidden_completion_expiry','finding':'Deadline must remain valid through hidden completion commit.','status':'RESOLVED_PRECOMMIT_CHECKS_AND_IMPLEMENTER_EXPIRY_REGRESSION'},
 {'id':'S10','topic':'canonical_publisher_expiry_and_recovery','finding':'Forward publisher primitive must recheck deadline after rendering; expired authority must not prevent same-epoch owned compensation.','status':'RESOLVED_EXACT_PINNED_PUBLISHER_GUARD_HOOKS_AND_INDEPENDENT_REAL_FENCE_PROBE'},
 {'id':'S11','topic':'price_forward_switch_expiry','finding':'Independent probe reproduced public card write after expiry during validation while checkpoint remained DB_COMMITTED.','status':'RESOLVED_BEFORE_REPLACE_AND_FINAL_COMMIT_CHECKS_INDEPENDENT_AFTER_PROBE_PASS'},
 {'id':'S12','topic':'existing_spec_handoff','finding':'Replacement native handler initially omitted existing best-effort async spec scheduling.','status':'RESOLVED_DURABLE_ONCE_HANDOFF_UNKNOWN_ENQUEUE_NOT_REPEATED_SPEC_COMPLETION_NOT_CLAIMED'}]
names=['REAL_PAGE_RETIREMENT_PROBE.json','RETIREMENT_PLAN_RECOVERY_PROBE.json','NATIVE_RECOVERY_OWNERSHIP_PROBE.json','PRICE_SWITCH_EXPIRY_PROBE_BEFORE.json','PRICE_SWITCH_EXPIRY_PROBE_AFTER.json']
r['new_tests_executed']=[{'path':str(HERE/n),'sha256':sha(HERE/n),'status':json.loads((HERE/n).read_text())['status'],'scope':json.loads((HERE/n).read_text())['scope']} for n in names]
r['historical_failure_evidence']={'real_html_counter_before':{'path':str(HERE/'REAL_PAGE_RETIREMENT_PROBE_BEFORE.json'),'sha256':sha(HERE/'REAL_PAGE_RETIREMENT_PROBE_BEFORE.json')},'price_expired_switch_before_preserved':True}
files=['task088_price_sync/outbox.py','task088_price_sync/uaart_price_sync_runtime.py','task088_price_sync/uaart_price_sync_binding.py','task088_price_sync/patch_cars_ui.py','task088_price_sync/patch_guard.py','task088_price_sync/patch_publikaciya.py','task088_price_sync/patch_site_counters.py','task088_v5_writer_fence/visibility_lifecycle.py','task088_v5_writer_fence/integrate_private_sources.py','task088_v5_writer_fence/publication_fence.py']
r['reviewed_implementation_sha256']={n:sha(ROOT/n) for n in files}
r['implementer_reports_reviewed']={n:{'sha256':sha(HERE/n),'independent_suites_repeated':False} for n in ['PRICE_LIFECYCLE_IMPLEMENTATION_RESULT.json','NATIVE_VISIBILITY_RESULT.json','PUBLISHER_AUTHORITY_VALIDATION.json','counter_fix/RESULT.json']}
native=json.loads((HERE/'NATIVE_VISIBILITY_RESULT.json').read_text())
base=HERE.parent/'private_source_candidate_status'
r['native_composed_candidate_binding']={'path':str(base),'files':{n:{'sha256':sha(base/n),'matches_frozen_report':sha(base/n)==pin} for n,pin in native['output_sha256'].items()},'full_installer_candidate':False}
assert all(e['matches_frozen_report'] for e in r['native_composed_candidate_binding']['files'].values())
r['current_four_source_input_observation']={'source':'Root-owned authenticated console observation, not independently fetched in this subtask','evidence_path':str(HERE/'CURRENT_FOUR_SOURCE_HASHES.json'),'sha256':sha(HERE/'CURRENT_FOUR_SOURCE_HASHES.json'),'scope':'Only four source files; does not establish full current source/DB/HTML/Preview binding'}
r['resolved_architecture']=[
 'All CRM price records use one FIFO with stable car_id and preserve absent draft values; visibility never fabricates missing identity.',
 'Withdrawal retires exact known HTML and exact listing spans before same-ID hidden price reconciliation; preserves source media, other tile bytes and unserved legacy HOME.',
 'Publication drains accepted earlier prices outside locks, then checks pending queue in reserved DB transaction and renders latest confirmed data under canonical fence/quiescence.',
 'Immutable content-addressed data receipts keep prior public receipt history and explicitly mark site/public projection NOT_APPLICABLE for hidden records.',
 'Unknown projection is inspected before retry; persisted withdrawal plans use exact pre/postimage CAS and refuse newer unrelated public bytes.',
 'Native authority expiry guards DB and forward switches; compensation requires real fence ownership, PID/thread, latest journal revision and same full projection row.',
 'Price forward replace callback runs after tempfile fsync; final SITE_PUBLISHED checkpoint refuses expired authority.',
 'Counter correction distinguishes explicit vehicle identifiers from language captions on server/client and pure migration preserves unrelated markup.'
]
r['credential_boundary']={'stage3_requires_new_reader_token':False,'stage3_installs_code_only_no_reader_provision_or_restart':True,'runtime_requires_verified_anchor_delegation_running_bot_fresh_reader':True,'absent_immutable_anchor_effect':'Existing bootstrap stops CRM startup; never pretend runtime active.','stale_control_effect':'Operational price/native mutations fail closed.','missing_handler_binding_error':'VERIFIED_VISIBILITY_BINDING_REQUIRED','live_activation_proven':False}
r['limitations']=[
 'Full final installer candidate file/manifest binding is pending; this report alone does not close point4.',
 'Current Preview24/24 applicability and complete current DB/source/HTML/routing evidence are owned by root and not fabricated from isolated tests.',
 'No production mutations, real public-URL retirement, running reader/queue, live SLA, Stage3/4 receipts or final20/20 are asserted.',
 'HTML compensation relies on point5 cooperative-writer exclusion; arbitrary uncooperative HTML writes are not covered by a new CAS guarantee.',
 'Code-less incomplete records support data-only price operations; native hide/sold/publication fail closed without canonical public identity.',
 'Spec handoff means existing event-loop task scheduled once; supplier work/queue completion is not asserted.',
 '18-car saved HTML parser evidence is historical grammar evidence; current live inventory may differ.'
]
r['final_candidate_binding']={'status':'PENDING_PARENT_FULL_COMPOSITE'}
p.write_text(json.dumps(r,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'status':r['status'],'sha256':sha(p),'path':str(p),'scoped_blockers':[]},sort_keys=True))
