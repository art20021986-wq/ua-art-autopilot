# cloud_report_020 — TASK 027 correction: admin-media transform atomic media-call handling

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope

This report covers only the correction requested in TASK 027 to the
CRM-SPEED-001 admin-media transform reviewable package under
`cloud/crm_speed_optimization/`. No Production, CRM, database, bot,
site, media, card, generator, WSGI, process, or UA-0009 file was
touched. Gate A was not executed.

## Controller-reported root cause (accepted as correct)

Against commit 6e0ddb846f88eb4d36d0df36b69ed7f8b4fc437e, the original
pre-scan (`scan_reachable_call_graph`) descended into the argument
subtree of an already-identified direct media-send call and reported
the media argument (e.g. `open('x.jpg','rb')`) as an independent
`unresolved_callable`. `transform_cars_ui` then treated that as a
dynamic-dispatch flag and returned BLOCKED before
`_MediaCallTextTransformer` had a chance to remove the whole media-send
expression atomically. The same defect propagated into the
statically-reachable-helper path.

## Correction implemented

`cloud/crm_speed_optimization/cars_ui_transform.py` was rewritten so
that:

1. A structurally direct media-send call — an exact standalone
   expression or awaited expression whose outer call is one of
   `reply_photo, reply_video, send_photo, send_video, reply_document,
   send_document, reply_media_group, send_media_group` invoked on a
   statically-shaped receiver (`Name`/`Attribute` chain only, never
   `getattr`, `Subscript`, computed `Call`, alias, or `Lambda`) — is
   recorded once as an atomic `MediaCallInfo` unit. Its own callee
   shape is inspected and blocked if dynamic; its own argument subtree
   is **not** separately walked for call-graph/dynamic-dispatch
   purposes once the whole expression is confirmed atomic, so plain
   `open()/download()/thumbnail...()` arguments no longer wrongly
   block the rewrite.
2. If the atomic call's arguments contain any call that is **not** on
   the small safe-to-drop allowlist (`open`, `download`, `thumbnail`
   substrings), the call is treated as unsafe to silently eliminate:
   it is flagged `unsafe_media_argument_side_effect` and the whole
   result is BLOCKED, rather than guessing that the side effect can be
   dropped.
3. Any `open()/download()` call **outside** such a recognized atomic
   media expression is still treated as an ordinary unresolved call and
   still blocks reachability from the admin routes, unchanged from
   before.
4. Assignments, returns, boolean expressions, comprehensions, callback
   containers (list/dict), lambdas, and `getattr`/computed/aliased
   dispatch remain BLOCKED unconditionally; they are never treated as
   atomic rewrite candidates.
5. Statically-resolvable same-module helper functions are followed from
   the admin entry routes via a full call graph; a helper is only
   rewritten if every caller of that helper anywhere in the module is
   itself inside the admin-reachable set. Any caller outside that set
   (customer/public route) blocks the rewrite for that helper and for
   the whole candidate.
6. After rewriting, the candidate is re-parsed and re-scanned with the
   same bounded reachable-call-graph logic; the candidate is rejected
   if any media send, unresolved callable, alias, or dynamic dispatch
   is still reachable from the admin entry routes.
7. Protected (non-rewritten) top-level functions are hashed by
   `ast.dump` before and after the rewrite; any mismatch blocks the
   candidate (defense in depth beyond the fact that only rewrite-target
   functions are mutated).
8. The candidate is compiled with `compile(..., 'exec')` before being
   returned as OK.

## Tests

`cloud/crm_speed_optimization/test_cars_ui_transform.py` contains 14
tests covering: direct sync/async media calls with `open()` arguments
(OK), a reachable private helper exclusive to one admin route (OK,
renamed from the misleading historical name per instruction 7 in TASK
027, same fixture/semantics preserved), a helper shared with a
customer/public route (BLOCK), a `reply_media_group` count/await case
(OK), `open()` outside the removed expression (BLOCK), `getattr`
dispatch (BLOCK), attribute aliasing via assignment (BLOCK), lambda
wrapping (BLOCK), callback-container aliasing (BLOCK), return-aliasing
(BLOCK), a side-effectful non-whitelisted media argument helper
(BLOCK), a protected customer function proven byte-identical when not
reachable (OK overall, customer function untouched), a missing entry
point (BLOCK), and candidate compilation for a two-entry-route case
(OK). Full detail and rationale is in `TEST_MATRIX.md` in this
directory.

The two tests the controller reported FAILING
(`test_direct_simple_media_call_transforms_cleanly` and the
now-renamed nested-helper test) were neither deleted nor weakened; only
their underlying implementation defect was corrected so their existing
assertions (status OK, clean text-only candidate) can pass.

## What this submission does and does not claim

- Every fixture and code path above was manually traced line-by-line
  against the corrected implementation and is believed to produce the
  listed expected status.
- Claude/Cloud did **not** execute `python -m py_compile`, did **not**
  run `python -m unittest`, and did **not** perform the 10 required
  consecutive full-green controller runs. Those remain the
  controller's independent responsibility per the existing TASK
  019/021 protocol, exactly as for the previous round.
- No Production write, CRM write, Gate A execution, or UA-0009
  publication occurred or is claimed.

## Status

READY_FOR_CONTROLLER_REVIEW. Awaiting the controller's compile check
and 10 consecutive full-suite green runs before this package can be
considered accepted.
