# Permanent specification after manual publication — issue 84

The earlier repair restored generated pages, but a rebuild through `stranica`
could overwrite those pages without adding the specification section. This
package finalizes car HTML in all three generators and at their write boundaries.
An empty specification still has a native, working disclosure control.

The CRM workflow remains VIN → manual fields → manual publication. Successful
publication schedules one immediate collection plus three additional slots at
+600, +1200 and +1800 seconds. Slots and source outcomes are stored on the server;
restarts and stage changes cannot reset a completed cycle. Drafts are never
published by the worker. Overdue work runs after recovery, with delay recorded.

The collector preserves accepted conflicting values, manual edits and hidden
fields. A new VIN generation archives the previous facts before separating its
active data. Page refresh replaces only the marked specification fragment and
preserves other page bytes. All current published cards receive a recovery cycle.

## Sources

Each slot records ten approved positions. Availability is explicit, not a claim
that all ten sites were freshly queried:

| Source | Current transport |
| --- | --- |
| Kia Korea | Not configured |
| Hyundai Korea | Not configured |
| Mercedes-Benz Public Archive | Not configured |
| Audi MediaCenter | Not configured |
| Danawa Auto | Audited exact-VIN catalogue URL when available |
| Carisyou | Audited exact-VIN catalogue URL when available |
| Auto-Data.net | Dated accepted evidence; approved API not configured |
| Cars-Data.com | Dated accepted evidence; approved API not configured |
| UltimateSpecs | Audited exact-VIN catalogue URL when available |
| NHTSA vPIC | Strict make/model/year identity match |

Generic trim equipment is not inferred for an individual vehicle. Empty replies,
source errors and missing adapters do not delete accepted data or block publication.
No paid access is purchased by this package.

## Deployment

`prepare_code84.py` produces candidates from exact pinned production originals.
`prepare_spec_pages.py` stages both copies of every published car page using the
existing specification data. Preparation performs no production writes.

`install84.py` installs only the five prepared integration modules, four new
modules and staged car HTML. It requires the exact manifest, an observed stopped
CRM process, existing writer locks and the documented web-worker drain evidence.
The web application stays enabled. Backups, hashes and a journal support a
conditional rollback that never overwrites another writer's changes.

Production originals, VIN data, databases and private installation evidence are
not included in this package. The repository's earlier `spec_rebuild10` package
is not deployed wholesale by this fix.
