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

The optional media roots apply only to their exact `/video/` and `/site/`
prefixes. Each referenced file receives its own path, length, MIME type and SHA256
in the manifest. There is no directory-serving fallback. Source, database,
configuration and arbitrary HTML routes cannot be added through asset roots.
Files over 32 MiB, unavailable files and third-party resources remain explicit
unresolved dependencies. The builder does not fetch them or invent substitutes.

The output directory must be new and outside the input trees. It has mode 0700;
written files have mode 0600. It contains public candidate HTML/assets only,
`manifest.json`, and `provenance.json`. Public media can remain in the explicit
asset roots; any subsequent byte change results in HTTP 503 on that resource.

Observed Production serves `video/index.html`, which contains four stage tiles
and no individual-car price previews. Its bytes remain identical. The unserved
legacy `site/index.html` is excluded with its hash and routing proof recorded;
it is not mislabeled as a converted homepage. Each published car is migrated in
both roots, with two catalogs and the served homepage: 39 pages for the current
18-car capture. Publication counts are derived from the captured rows.

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
manifest-pinned bytes. Browser responses disable caching/indexing, framing,
forms and connection requests. Existing inline analytics markup is preserved,
but its endpoint is unavailable in Preview. External scripts are blocked by
the Preview CSP and remain recorded dependencies; this limitation cannot be
counted as successful verification of their behavior.

## Verification and remaining Gate

```bash
UA088_LIVE_SOURCE_DIR=/absolute/path/to/private-capture \
  python3 -m unittest discover -s cloud/task088_v5_preview -p 'test_*.py' -v
```

The tests cover authentication, exact host/HTTPS, read-only methods, disclosure
and traversal attempts, symlink rejection, changed files, manifest pins, private
configuration modes, separate asset roots, resource bounds, dependency scanning,
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
