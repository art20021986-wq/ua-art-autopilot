# TASK 067 — SEO LEADS KYIV 7D / SANDBOX + GITHUB PREVIEW ONLY

STATUS: APPROVED_FOR_SANDBOX_IMPLEMENTATION
SPEC_ID: SEO-LEADS-KYIV-7D-001 v1.0
OWNER_APPROVAL: `УТВЕРЖДАЮ SEO-LEADS-KYIV-7D-001 v1.0. РАЗРЕШАЮ ТОЛЬКО SANDBOX И GITHUB PREVIEW. PRODUCTION — ТОЛЬКО ПО МОЕЙ ОТДЕЛЬНОЙ КОМАНДЕ.`
WORK_BRANCH: `seo/index-leads-7d-001`
PRODUCTION_WRITE: NO
CRM_WRITE: NO
FORM_SUBMIT: NO

## Objective

Produce an auditable, deterministic SEO release candidate for UA ART in an isolated GitHub
branch. The candidate must remove indexation blockers in preview, generate correct `robots.txt`
and `sitemap.xml`, preserve every protected vehicle fact and prove the result with ten identical
builds. Do not deploy, merge or change PythonAnywhere, Cloudflare production, CRM or D1 data.

## Verified starting scope

- 17 read-only URLs: `/`, `robots.txt`, `sitemap.xml`, four public service pages and
  `UA-0001` through `UA-0010`.
- Current catalog count: 10.
- Operational reference: `P0=13`, `P1=75`; `UA-0009 public ready=false` before the latest
  diagnostics restoration.
- Re-measure all facts. Never copy a stale count into a PASS decision.

## Allowed candidate changes

1. HTML `<head>` only: remove `noindex`, add one self-canonical, add a unique description and
   factual schema where safe.
2. Candidate-only `robots.txt`, `sitemap.xml` and one-hop redirect declaration.
3. Add the existing canonical `mcf-diag-cta` block only when it is absent and only when the
   matching public `UA-XXXX-diag.html` page was independently verified HTTP 200 in the baseline.
4. Exact visible CTA text correction only on `UA-0002`, `UA-0007`, `UA-0008`:
   `Купить авто` / `Купити авто` to `Забронировать авто за 500$`.
5. Reports, tests, manifests and preview files under `cloud/seo_leads_7d/`.

## Forbidden changes

- Production deploy, service reload, main-branch merge or direct `main` commit.
- CRM/admin login, form submission, database write or secrets use.
- Any price, currency, vehicle ID, VIN, container, delivery stage, specification, image, video,
  diagnostic material or payment-condition change.
- Synthetic ratings/reviews, city doorway pages, spam links, hidden text or Indexing API use.

## Mandatory gates

- G0: baseline JSON + HTML + SHA-256 manifest for all 17 URLs.
- G1: 14 index candidates are 200, have no `noindex` and have a correct self-canonical.
- G2: unique title/H1/description checks and no preview canonical.
- G3: diagnostics and $500 CTA on 10/10 cards; protected body diff is zero outside CTA allowlist.
- G4: separate `UA-0009` and `UA-0010` readiness result.
- G5: valid `robots.txt`; sitemap contains exactly the approved 14 canonical URLs.
- G6: ten builds from one immutable baseline produce the same tree SHA.
- G7: rollback package is generated and tested locally.
- G8: owner visual review.
- G9: separate owner production phrase. It is not present in this task.

Any failed gate means `BLOCKED_FOR_PRODUCTION`, while the GitHub preview may remain available
for inspection.

## Deliverables

- `cloud/seo_leads_7d/README.md`
- `cloud/seo_leads_7d/config.json`
- `cloud/seo_leads_7d/baseline.py`
- `cloud/seo_leads_7d/build_candidate.py`
- `cloud/seo_leads_7d/gate.py`
- `cloud/seo_leads_7d/test_pipeline.py`
- `cloud/seo_leads_7d/evidence/BASELINE-SEO-001.json`
- `cloud/seo_leads_7d/evidence/BASELINE-SEO-001.html`
- `cloud/seo_leads_7d/evidence/sha256-manifest.txt`
- `cloud/seo_leads_7d/evidence/GATE-REPORT.json`
- `cloud/seo_leads_7d/evidence/REPEATABILITY.json`
- `.github/workflows/seo-leads-7d-preview.yml`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`
