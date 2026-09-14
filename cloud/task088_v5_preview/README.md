# Preview access update authorized by the owner

The owner explicitly requested a password-free alternative from a phone.
A private mode-0600 configuration may now select exactly
`access_policy: PUBLIC_READ_ONLY_PREVIEW_OWNER_AUTHORIZED` instead of `basic_auth`.
Only manifest-listed candidate pages and public assets become publicly readable;
HTTPS, exact host, source pins, GET/HEAD-only behavior, no indexing, and denial of
DB/source/config/audit routes remain mandatory. Missing, misspelled or mixed
access settings fail closed. Existing Basic-auth configurations retain their
original behavior. This changes only Preview access; it grants no Production PASS.
See `../task088_v5_acceptance/OWNER_PUBLIC_PREVIEW_CHANGE.json` and the one-time
`../task088_v5_preview_access/provision_public_preview.py`. The reference Basic
provisioning instructions below remain available but are no longer required for
this owner's Preview.

# Protected Stage 3 Preview

This package prepares a private, price-only candidate and serves it from a
separate authenticated HTTPS app. It does not install, reload, import or alter
the Production application. It never opens the CRM database or issues a network
request. A successful build or unit-test run does **not** grant Preview PASS.

## Build inputs and output

The input is the read-only capture containing `capture_manifest.json`, current
published price rows, both card/catalog copies, renderer sources and observed
routing sources. The builder verifies the captured hashes and the separately
recorded routing evidence. Three patched generator sources must compile; their
raw content is never included in the output.

An example staging-only build, with explicit public media directories:

```bash
python3 build_preview.py \
  --snapshot /absolute/path/to/private-capture \
  --output /absolute/path/to/new-private-preview \
  --source-origin https://www.uaart.com.ua \
  --routing-evidence /absolute/path/to/route_observations.json \
  --asset-root /home/Carix/video \
  --site-asset-root /home/Carix/site
```

The public media root applies only to its exact `/video/` prefix. Each referenced
file receives its own path, length, MIME type and SHA256 in the manifest. There
is no directory-serving fallback. Source, database, configuration and arbitrary
HTML routes cannot be added through asset roots. The legacy optional site-root
argument does not make `/site/` an HTTP surface: current routing proves it is
unserved. A `/site/` dependency referenced by a served page remains an explicit
failure, even if that file exists on disk.
The captured cards' inline `kadry` gallery lists explicitly bind every full-size
photo as well as static thumbnails. Only the known literal JSON list of canonical
gallery paths is accepted; malformed or dynamic declarations block the build.
The observed diagnostic gallery's `diag/UA-NNNN/m/NN.jpg` literal paths follow
the same checks; no other diagnostic directory or filename pattern is inferred.
JavaScript is never evaluated and photo directories are never enumerated.
Observed links to `info.html`, `podbor.html` and a published car's exact
`UA-NNNN-diag.html` may be copied unchanged from the captured manifest or an
explicit root. Each gets a source binding and byte-equality evidence, and is
read again before output creation to detect source drift. Their referenced
assets are also individually pinned. Unknown linked HTML remains an explicit
Gate failure, even if a matching file exists in the root.
Files over 32 MiB, unavailable files and third-party resources remain explicit
unresolved dependencies. The builder does not fetch them or invent substitutes.

The output directory must be new and outside the input trees. It has mode 0700;
written files have mode 0600. It contains `public/` candidate HTML/assets,
`offline/site/` protected candidate copies, `manifest.json`, and `provenance.json`.
Offline copies have no HTTP route or public manifest entry. Public media can
remain in the explicit asset root; any subsequent byte change results in HTTP
503 on that resource. The deterministic viewport harness is a separate public
manifest entry and never changes any candidate page bytes.

Observed Production serves `video/index.html`, which contains four stage tiles
and no individual-car price previews. Its bytes remain identical. The unserved
legacy `site/index.html` is excluded with its hash and routing proof recorded;
it is not mislabeled as a converted homepage. Only `/site/index.html` redirects
to the Preview's `/video/index.html`, matching the observed unconditional
Production WSGI redirect when a path is outside the `/video/` static mapping.
This exception requires the exact reviewed WSGI, analytics and bridge source
hashes plus routing evidence; unknown routes still return 404. The legacy HTML
itself is never served or altered. A separate whole-prefix proof verifies the
same three source versions, the sole `/video/` static mapping, and the exact
wrapper routes. Changing any of these blocks `/site/` exclusion from HTTP.

Each published car is migrated in both source roots, with two catalogs and the
served homepage: 39 protected price-source checks for the current 18-car capture.
Their before/after hashes and outside-price byte checks remain mandatory. The
19 `/site/` candidates stay under `offline/site/`; only 20 genuinely served
price pages enter the HTTP browser matrix, giving 120 RU/UA/GE × desktop/mobile
checks. Up to 20 unchanged linked `/video/` pages are recorded separately. They
do not inflate the price-surface matrix. Media and auxiliary crawling starts
only from served pages; it does not discard unresolved dependencies referenced
by those pages. All counts derive from the captured published rows.

## Dedicated app configuration

`wsgi_entry.py` is the WSGI entry point. The dedicated app must supply
`UA_ART_PREVIEW_CONFIG`, an absolute path to an existing private JSON file with
exactly these fields:

| Field | Required value |
|---|---|
| `contract` | `UA-ART-V5-PROTECTED-PREVIEW-1` |
| `preview_origin` | Explicit separately provisioned HTTPS origin, different from Production |
| `bundle_root` | Absolute candidate directory |
| `manifest_sha256` | Exact SHA256 returned by the build |
| `basic_auth.username` | Explicit Preview principal |
| `basic_auth.salt_hex` | Provisioned PBKDF2-HMAC-SHA256 salt, 16–64 bytes in lowercase hex |
| `basic_auth.iterations` | Provisioned verifier iteration count, 300000–2000000 |
| `basic_auth.password_hash_hex` | Existing 32-byte verifier in lowercase hex |

This package does not create accounts, passwords, billing changes, web apps,
DNS entries or access grants. Credentials must be provisioned through the
authorized hosting/authentication process. Never deploy the fixed test verifier.
Keep the private configuration outside any public directory and mode 0600.

The dedicated app has no Production WSGI wrapper imports, analytics service,
upload endpoint, CRM/API connection or write methods. It authenticates all
resources, requires the exact HTTPS host, allows GET/HEAD only, and returns only
manifest-pinned bytes. Browser responses disable caching/indexing, external
framing, forms and connection requests. Existing inline analytics markup is preserved,
but its endpoint is unavailable in Preview. External scripts are blocked by
the Preview CSP and remain recorded dependencies; this limitation cannot be
counted as successful verification of their behavior.

## Fixed CSS viewport observation

The dedicated authenticated route `/__uaart_preview__/viewport.html` contains a
reviewed, deterministic harness bound to the manifest and validated again by the
WSGI application. Its page selector lists only the allowed `/video/` documents.
It loads one candidate at either 390 × 844 or 1280 × 900 CSS pixels, using exact
iframe dimensions without scaling, transforms, browser emulation or injected
candidate code. It has no arbitrary target URL, proxy, network API or secret.

Only the exact query `?__uaart_viewport=1` on a listed candidate enables
`frame-ancestors 'self'`, `frame-src 'none'` and the HTTP sandbox
`allow-scripts allow-same-origin`. That HTTP restriction cannot be removed by
changing an iframe attribute. Harness responses retain `frame-ancestors 'none'`
and permit frames only at the explicit same-origin document paths. All routes,
including errors, the harness and its embedded assets, still require auth.
Normal top-level candidate URLs retain their previous CSP and page behavior.

Use the page's existing RU/UA/GE controls. The observation button reads the actual
inner viewport, matching media query, language, current price text, bounding
rectangles, font sizes, document width and loaded image/font state. It displays
`OBSERVED_ONLY` and `NOT_EVALUATED`; it never issues PASS, changes an acceptance
file, writes CRM data, rewrites candidate DOM or calls a network endpoint.
The selected source SHA is manifest evidence, not a DOM hash. Real screenshot
review and the complete protected-data comparisons remain separate checks.

This can establish responsive CSS layout in the browser actually used. It does
not emulate iOS Safari, touch input, mobile browser chrome, screen safe areas,
device-pixel ratio or native share/clipboard behavior. Sandbox restrictions also
prevent popups, forms and top navigation. Relative navigation loses the opt-in
query and cannot remain framed, so links and native/external buttons require
their separate ordinary top-level checks. These limitations are never reported
as successful iframe checks. The harness is served only from the authorized
dedicated HTTPS Preview; no local file URL, tunnel, alternate port or CDP path is
used.

## Verification and remaining Gate

```bash
UA088_LIVE_SOURCE_DIR=/absolute/path/to/private-capture \
  python3 -m unittest discover -s cloud/task088_v5_preview -p 'test_*.py' -v
```

The tests cover authentication, exact host/HTTPS, read-only methods, disclosure
and traversal attempts, symlink rejection, changed files, manifest pins, private
configuration modes, separate asset roots, resource bounds, dependency scanning,
source-bound unchanged linked HTML, the one proven legacy redirect, the separate
whole-prefix routing proof, public/offline coverage, canonical harness bytes,
exact query-scoped framing and sandbox boundaries,
and the actual captured-page build. They use isolated temporary fixtures and do
not activate anything.

`provenance.json` intentionally records every RU/UA/GE × desktop/mobile browser
check as `NOT_RUN` and `preview_gate` as `NOT_PASSED`. These are immutable build
facts, not fields to flip manually. Real browser receipts, actual complete asset
availability, correct links/buttons, the remaining protected-data comparisons,
writer exclusion and a fresh CRM/DB snapshot must be established by the Stage 3
acceptance process before it can issue its separate PASS receipt. Installation,
Production verification and the real Stage 4 operational cycle remain separate
gates.

The current read-only capture does not contain the 20 linked information,
selection and diagnostic files. The build now lists these omissions rather than
silently providing broken links. A fresh capture or a server build with the
explicit public root is required. Building the harness does not run it: every
planned browser-matrix entry remains `NOT_RUN` until actual observation.
