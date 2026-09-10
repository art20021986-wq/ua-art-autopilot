# Manual publication with automatic additional specifications

Owner workflow confirmed on 10 September 2026:

1. Enter a VIN and create a CRM automobile.
2. Fill in the normal required business fields.
3. Press the ordinary advertisement publication button once.
4. Receive the verified public automobile URL.
5. Additional confirmed information appears automatically as it becomes available.

The first publication no longer waits for a minimum number of additional facts.
An empty specification has a visible native link and section with the honest
Ukrainian/Russian message that additional characteristics are being clarified.
This does not authorize fabricated equipment, initial automatic publication,
advertising, or replacing previously accepted characteristics with an empty set.
The owner still publishes UA-0017 and then UA-0018 manually.

## Implemented in this branch

- Empty specifications are accepted by the CRM bridge, renderer and verified
  publication snapshot. The pending state is distinguished from confirmed data.
- The normal advertisement action invokes publication directly after checking
  the existing required fields. Old refresh callbacks show status and cannot
  launch the old collector. The normal keyboard filters the refresh action.
- Success returns the exact verified UA ART automobile URL; the homepage,
  another automobile or an external URL is not a publication confirmation.
- Individual source failures do not discard confirmed results from other
  configured sources. Partial results and bounded retry/exhaustion are committed
  atomically; retry counters are not reset. Source trust and identity checks
  remain enforced.
- Already accepted public updates can synchronize when a collection attempt
  fails. Unknown publication outcomes still stop writes for reconciliation.
- Collector acceptance and the entire owner publication interval use the same
  injected verified publication lock. Network collection runs outside that
  lock; a late fact commit waits until the initial page snapshot is recorded.
- Old published fields, manual/hidden precedence, one visible VIN, existing
  page content and media protections remain in force.

## Verification completed locally

- Python 3.12.14: 250 tests discovered, **219 passed, 31 skipped**, no failures.
  The 31 exact private runtime installer tests were not supplied their target
  package in this run. This is not a PythonAnywhere Python 3.10 installation gate.
- Four exact pinned private CRM source modules generated and parsed/compiled
  without importing or installing those private modules.
- All **16 current public HTML copies** captured on 10 September were composed
  with the preserved facts from the 9 September snapshot: **16/16 passed**;
  550 visible historical characteristics retained; native specification link
  present; one visible VIN; zero byte changes outside the specification and
  previously reviewed VIN normalization regions. The input database was unchanged.
- Tests cover pending publication followed by automatic fact synchronization,
  no automatic draft publication, source partial success, repeated source
  failure limits, unsafe source rejection, rollback, retained old facts, and
  concurrent fact acceptance waiting for the initial publication snapshot.

Private pages, databases and compiled CRM modules are intentionally outside this
public repository. Historical facts are not claimed as freshly reverified data.

## Current production status and remaining blockers

**NOT INSTALLED. No live UA ART page, CRM record, job, worker, or server setting
was modified by this change. UA-0017 is not yet declared ready to click.**

1. The existing ExactPlan is an immutable plan for one reviewed execution. A
   permanent CRM workflow needs the real controller to create and authenticate
   a fresh exact operation after the owner's click, under the shared publication
   lock. Old fixed plans become stale after normal CRM edits or fact acceptance.
   A test callback that simply returns PASS is not that controller.
2. The existing route still requires verified exclusion of old writers and
   actual runtime installation while the current site remains available.
   No supported completion evidence for that handoff was obtained. The old
   webapp-disable maintenance plan remains excluded by the availability requirement.
3. The ten approved source entries are retained. This change does not provision
   nine supplier/document adapters, buy subscriptions or claim ten live
   extraction successes. A configured, permitted source connection and correct
   model/market mapping are still needed for each source. Missing sources do not
   authorize invention or loss of historical specifications.
4. Existing global unknown-outcome/outbox guards and invalid-CRM reconciliation
   guards remain. This branch isolates ordinary supplier failures; it does not
   claim that unresolved write corruption can be ignored per automobile.
5. A new package and target-version gate must cover these changed bytes. The
   earlier R2/R3 target receipts apply to the base revision, not to this change.

After the real route is ready: install and read back all 16 pages; verify the
loaded CRM callback and worker; then tell the owner to click UA-0017, verify its
actual page and catalogue entry, and only then proceed to UA-0018.
