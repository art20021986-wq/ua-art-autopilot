# SEO-LEADS-KYIV-7D-001 — isolated preview pipeline

This package creates a static SEO release candidate from a read-only snapshot of the 17 approved
UA ART URLs. It never authenticates, submits a form, writes to production or deploys anything.

## Safety contract

- Branch: `seo/index-leads-7d-001`.
- Public source access: HTTP GET only.
- Output: local/GitHub Actions artifact only.
- Production, PythonAnywhere, CRM and database writes: forbidden.
- The body of every page must remain byte-equivalent after normalising the three explicitly
  approved CTA text replacements. All other changes are restricted to HTML `<head>`, candidate
  `robots.txt`, candidate `sitemap.xml` and candidate redirect declaration.
- Every generated HTML page carries a purple `GITHUB PREVIEW · PRODUCTION WRITE NO` guard. The
  guard loads public media with GET requests but blocks links, buttons and form submissions.

## Local run

```bash
python3 cloud/seo_leads_7d/baseline.py \
  --output /tmp/ua-art-baseline --save-raw

python3 cloud/seo_leads_7d/build_candidate.py \
  --baseline-dir /tmp/ua-art-baseline \
  --output /tmp/ua-art-candidate

python3 cloud/seo_leads_7d/gate.py \
  --baseline-dir /tmp/ua-art-baseline \
  --candidate-dir /tmp/ua-art-candidate \
  --report /tmp/ua-art-candidate/GATE-REPORT.json

python3 -m unittest cloud/seo_leads_7d/test_pipeline.py
```

The GitHub workflow repeats the candidate build ten times from the same captured baseline and
compares deterministic tree hashes. Its downloadable `seo-leads-7d-preview` artifact contains the
baseline evidence, candidate site, Gate report and repeatability report.

The branch-only Worker configuration serves the committed static candidate through Cloudflare's
generated branch preview URL. It has no cron or D1 binding, rejects every method except GET/HEAD,
adds `X-Robots-Tag: noindex, nofollow` and never owns the UA ART production domain.

## Gate interpretation

- `PASS_READY_FOR_OWNER_VISUAL_GATE`: technical sandbox checks passed. This is **not** production
  permission.
- `BLOCKED_FOR_PRODUCTION`: at least one P0 gate failed; inspect the exact result in
  `GATE-REPORT.json`.
- A merge or deploy always requires the separate exact owner production phrase from the approved
  specification.
