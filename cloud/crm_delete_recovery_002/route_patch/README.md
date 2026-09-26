# Exact deleted-card route candidate

Uninstalled WSGI candidate for `UA-ART-CRM-DELETE-RECOVERY-002`.
The private production source is an external build/test input and is not included.

`build_route_patch.py` accepts only the reviewed WSGI SHA-256
`3067d39ec9c2eb976114afc6744e2c34b088a8414e98eb3e33e0a47c1849e308`.
It appends a narrow integration block; existing analytics, bridge, base redirect,
robots and SEO code remain byte-for-byte unchanged.

The default historical incident routes are `/video/UA-0002.html`,
`/video/UA-0002-diag.html` and `/video/UA-0002-a6f9d391.html`. Their exact
existing preimages are proven by emergency plan SHA-256
`891dbad7211277f1613655da9cbcb2ea19f80937c375bc2575767858c2aa6442` and the
observed static mapping `/video/` → `/home/Carix/video/`. The evidence subset is
in `legacy_route_evidence.json`. The corresponding `site/` files are unserved
local mirrors. Other incident aliases require explicit `--legacy-route` inputs
after their exact URLs have been verified.
The builder never derives root, mirror, diagnostic, hash, case or wildcard aliases.

Routine deletions are read from `/home/Carix/crm.db`, opened read-only, and
`/home/Carix/ua_crm_deletion_state`, a private mode-0700 directory. The guard checks
the intent plan digest, backup manifest digest, snapshot binding and full core
plan equality. Only exact URLs in `manifest.plan.routes` whose value is in
`manifest.plan.direct` become tombstones. `local_only` mirror files do not invent
HTTP routes. All durable states (`REQUESTED`, `ROW_DELETED`, `COMPLETE`) reserve
the route, allowing HTTP verification before the final CRM-row deletion.

Confirmed routes return 410 with no redirect or caching. HEAD sends no body.
The existing dynamic `/sitemap.xml` excludes exact tombstone URL lines while
preserving the remaining response bytes and headers. A missing intent table is
allowed during staged deployment. A missing database, corrupt intent or manifest
produces a bounded 503 for affected car URLs and the dynamic sitemap. Card
lookups read only intents for that exact car code, so corruption of another
deletion record does not change their response. A global database/schema failure
affects all candidate card lookups. Other paths, robots, analytics and bridge
ingress continue through the original stack.
The verified historical route continues to return 410 even when the journal is
temporarily unavailable.

## Deployment dependency

The static web-server mapping `/video/` precedes WSGI. Existing static HTML can
therefore bypass this wrapper. The deletion coordinator must remove the exact
files and the writer guards must prevent recreation. WSGI must be reloaded only
after `ua_crm_deleted_routes.py` is installed and the current source SHA is checked
again. This candidate does not install, reload, remove files or mutate the DB.

## Verification

Run from this directory with the captured private source path:

```sh
UA_DELETE_WSGI_SOURCE=/absolute/path/to/captured_wsgi.py python -m unittest -v test_deleted_routes.py
```

The tests execute the actual built candidate with temporary SQLite state,
hash-bound manifests and stubbed existing integrations. They compare unrelated
responses against the unchanged source, verify route precision, GET/HEAD behavior,
all three deletion states, mirror-only paths, dynamic sitemap byte preservation,
corruption behavior and absence of DB writes. They do not claim live HTTP PASS.
