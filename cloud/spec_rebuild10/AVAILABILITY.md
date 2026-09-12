# Availability constraint for the rebuild

Owner continuation on 2026-09-09 requires that the existing website remain
available during the specification restoration. This supersedes using the old
maintenance plan's temporary webapp outage for this continuation.

## Observed, read only

On 2026-09-09 at 15:43–15:55 UTC, the public www homepage opened; the catalogue
rendered 16 cards and its UA-0001 link opened the existing vehicle page. The
authenticated PythonAnywhere Web page showed the webapp enabled, Python 3.10,
and `/video/` mapped to `/home/Carix/video/`. No Disable, Reload, Delete, DNS,
static mapping or certificate operation was submitted. This is a point-in-time
check, not proof of uninterrupted service in other browsers or during an
installation. It does not establish the cause of the owner's earlier outage.

The current public UA-0001 page still has duplicated VIN and no rebuilt
specification link. Its catalogue stage is Georgia while its card route says
ferry; this existing mismatch is not a new restoration result or an approved
automatic data correction. Keep it recorded for the separate CRM consistency
acceptance; preserving page bytes alone does not resolve it.

## Execution boundary

The previous `prepare_maintenance_v3.py` plan explicitly proposes disabling the
webapp. Do not execute that plan under this availability requirement. Static
file mapping does not prove that public pages will remain served after the
webapp is disabled.

The separate versioned code/data installer only manipulates its admitted
targets under a borrowed holder and caller-provided authenticated verifier. It
does not implement or authorize process stopping, a webapp reload, traffic
switching or re-enabling workers. Its isolated test callbacks cannot supply
production authority.

Before production installation, provide a supported procedure that excludes
all old writers, including the complete old WSGI descendant scope, while
continuing to serve the existing site. Bind actual completion evidence to the
account, webapp, old generation, maintenance operation and exact installation
plan. Enabled flags, a separate Bash process list, elapsed time, old successful
tests or an unscoped goodbye log cannot provide that evidence. The current
checked route supplies no proven availability-preserving equivalent.

The support information request was already submitted at 12:32:50 UTC. Inspect
its technical response when available; do not send a duplicate or treat a
general procedure description as completion evidence for an actual operation.
There is no permission in that information request to stop or modify the site.

Continue isolated implementation and target-version verification while this
execution dependency is unresolved. Keep production Gate B pending and retain
the existing HALT, queue, drafts and protection against concurrent writes.
