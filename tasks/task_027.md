# TASK 027 — CRM-SPEED-001 admin-media transform correction

## Owner authorization and safety

Continue the approved CRM-SPEED-001 repair. Correct only reviewable files under cloud/crm_speed_optimization and required status/report files. Do not execute Gate A or change Production, CRM, database, bot, site, media, cards, generators, WSGI, processes, or UA-0009.

## Controller execution result for commit 6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e

Python compile: PASS.
First unittest run: 51 tests; 49 PASS, 2 FAIL. Required 10 consecutive full green runs were not started.

Failures:
1. CarsUiTransformTests.test_direct_simple_media_call_transforms_cleanly
   - expected status OK after rewriting direct reply_photo/reply_video to reply_text
   - actual status BLOCKED.
2. CarsUiTransformTests.test_nested_helper_media_call_blocks
   - fixture name is historical; expected behavior is to rewrite the statically reachable helper's direct reply_photo call and return a clean candidate
   - actual status BLOCKED.

Root cause identified by controller:
scan_reachable_call_graph descends into the argument subtree of a direct media call. The direct media call is correctly marked rewritable, but its argument open('x.jpg','rb') is separately reported as unresolved_callable:open. transform_cars_ui then classifies that as a dynamic flag and blocks before _MediaCallTextTransformer can remove the whole media-send expression. The same occurs in a statically reachable helper.

## Required correction

1. In the original-graph pre-scan, recognize a structurally direct media-send call as one atomic rewritable expression:
   - record direct_media_call;
   - do not recursively treat calls contained only inside that media call's arguments as independent reachable runtime after the entire expression is replaced;
   - nevertheless inspect the target/callee shape itself and BLOCK any getattr/computed/aliased/dynamic dispatch.

2. Allow rewrite only for an exact standalone expression or awaited expression whose outer call is one of the enumerated Telegram media-send methods:
   reply_photo, reply_video, send_photo, send_video, reply_document, send_document, reply_media_group, send_media_group.
   Assignments, returns, boolean expressions, comprehensions, callback containers, aliases or unknown wrappers remain BLOCKED unless a dedicated semantics-preserving transform is implemented and tested.

3. Rewrite the entire direct expression, so original media arguments (open/download/thumbnail/binary operations) are not evaluated in the candidate. Emit concise text containing media type and count; preserve async await behavior.

4. Follow statically resolvable same-module helpers from the four entry routes. If a helper is reachable only from these admin routes and contains an exact direct media expression, rewrite it. If it has other module callers or caller scope cannot be proven, BLOCK rather than changing shared/customer behavior.

5. After transform:
   - rerun bounded reachable call graph;
   - require no media send, binary open/download/thumbnail fetch, aliases or ambiguous dispatch reachable from the four admin routes;
   - verify protected media persistence/customer/public functions by semantic hashes;
   - compile candidate.

6. Add/repair behavioral tests:
   - direct sync media call with open argument -> OK, text-only, no open remains reachable;
   - direct async awaited call -> OK;
   - reachable private helper exclusively used by admin route -> OK and clean;
   - shared helper also called by customer/public route -> BLOCK;
   - open/download outside the removed media-call expression -> BLOCK;
   - getattr literal/computed, alias, lambda, callback list/dict, return/await alias -> BLOCK;
   - side-effectful media argument helper -> BLOCK unless proven safe to eliminate;
   - candidate compile PASS.

7. Do not delete, skip or weaken the two failing tests. Rename the misleading nested-helper test if desired, but preserve its executed semantics.

8. Full suite must be capable of 10 consecutive green controller runs. Update cloud/latest_status.md, cloud/owner_reply.md, cloud_report_020.md and TEST_MATRIX truthfully. Status only READY_FOR_CONTROLLER_REVIEW or BLOCKED.

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO
