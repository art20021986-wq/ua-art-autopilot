# TASK088: authoritative control bridge — verified capability boundary

Assessment: 2026-09-13. Status: **continuous control producer not available;
Stage 4 unattended activation is not proved**. No workflow, server control
file, repository visibility, credential or production setting was changed.

## What is actually available

- The server inventory performed in this task found no authoritative local
  `EXECUTION_MODE.json` or `AUTOPILOT_HALT.json` to read. Absence on that server
  does not mean the GitHub emergency stop is clear.
- Canonical global mode and HALT live in the repository. Its present public
  visibility is unexpected; the intended safe state is private.
- Authenticated GitHub app reads and branch writes are available to the current
  task. These do not provide an unattended authenticated server-side reader.
- Existing GitHub Actions jobs use `github.token` and
  `secrets.PYTHONANYWHERE_API_TOKEN`; neither value was accessed or exported by
  this assessment. Those credentials can remain inside their existing runner
  trust boundary. Their existence does not supply a reviewed running control-plane
  producer; that integration is still missing.
- Existing PythonAnywhere access can install a reviewed package after its
  normal gates. It cannot make a copied GitHub snapshot continuously fresh.

The binding provider requires current mode, HALT and revocation observations.
For `EXTERNAL_CACHE`, it binds their exact contents to an observation timestamp,
caps cache age at 60 seconds and event authorization at 30 seconds. Rewriting
only a timestamp, declaring a new local flag authoritative, or treating a
missing cache as clear would defeat that protection.

## Bounded Gate B window using existing credentials

A **possible bounded execution path**, not an installed bridge, is a reviewed
GitHub Actions job running for at most ten minutes:

1. Its existing runner token reads the current `main` ref and the exact mode,
   HALT tree entry and approval/delegation state from that commit. HALT absence
   must be proved from a complete Git tree, not inferred from an ambiguous HTTP
   404. Unknown or changed approval state means revoked, not clear.
2. It rechecks the ref before issuing each observation. A changed ref causes a
   new read; a failed read immediately ends renewal. A previous snapshot's
   timestamp is never advanced without a new authoritative observation.
3. The existing PythonAnywhere API transport writes only the approved private
   control-cache paths and reads them back. Credentials remain in Actions;
   control-cache artifacts contain no token, private source or unrelated data.
4. The cache binds repository/ref/commit, task/delegation identity, actual
   observation time and exact mode/HALT/revocation contents. The installed
   producer source is pinned in the existing binding contract. Content hashes
   are integrity bindings, not substitutes for authenticated producer identity.
5. Renew at approximately ten-second intervals while the job remains healthy;
   each observation expires within at most thirty seconds. A missed renewal,
   HALT, MANUAL, revoked approval or failed readback stops publication. No new
   local clear flag is created. At the ten-minute bound the runner stops;
   outstanding leases expire normally and cannot support later publication.

This could support Stage 3 installation/acceptance in a finite authorized
session **after** a concrete producer, transport scope and artifact chain are
implemented and verified. It is not a route to call Stage 4 complete. A local
mock or a sample workflow would not supply the missing real control channel.

## Why scheduled replication does not finish the requested 24/7 process

| Option | Safety and operational result |
| --- | --- |
| GitHub state push workflow alone | May deliver state changes, but provides no continuous proof that no change was missed. A fresh timestamp cannot be invented between deliveries. |
| GitHub cron every few minutes | Cannot satisfy a cache lifetime of at most 60 seconds. The recorded prior audit observed only about eight watchdog runs per day; this is historical evidence, not a newly measured count. |
| Long-running hosted Actions loop | Can renew while alive, but hosted jobs have a six-hour maximum; queue/renewal gaps still require fail-closed pauses. Continuous private-repository use also consumes billable runner time. This was not activated. |
| Anonymous server poll of the public repository | Would stop working after the intended privacy change and relies on retaining unintended public visibility. Not an acceptable permanent solution. |
| Fresh authenticated server-side read or authenticated continuously available relay | Could support the required freshness, but no such capability is currently present within the approved credentials and transport boundary. |

GitHub documents that scheduled jobs can be delayed and even dropped under
load: [workflow scheduling limitations](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows).
It also documents the six-hour hosted-job limit:
[Actions limits](https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/limits).
Private-repository hosted-runner execution accrues billable minutes:
[job execution time](https://docs.github.com/en/actions/how-tos/monitor-workflows/view-job-execution-time).

## Concrete blocker and next executable work

The missing capability is **an authenticated, private-repository-compatible,
continuously available reader or relay for canonical GitHub control state**.
It must deliver genuinely fresh observations within the provider's existing
time bound, independently of the current interactive task. Existing app access,
server access and intermittent GitHub schedules do not establish it.

The current connection does not expose a scoped unattended GitHub credential
for installation on the server. A continuous runner is not already configured,
and a finite runner cannot be described as proof of uninterrupted operation. Keep the completed price-sync/renderer/guard work
and server preflight evidence. Finish a real bounded Stage 3 control window if
its existing-authority runner and producer can be verified; leave unattended
Stage 4 activation blocked until the missing continuous capability is supplied
through an approved integration. Do not report a package or passing local
tests as an operating 24/7 autopilot.
