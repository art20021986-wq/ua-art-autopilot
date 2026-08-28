# TASK 068 — SEO REHABILITATION / GITHUB PREVIEW ONLY

OWNER_APPROVAL: `SEO-LEADS-KYIV-7D-001 v1.0`
OWNER_SCOPE: SANDBOX AND GITHUB PREVIEW ONLY
PRODUCTION_WRITE: FORBIDDEN UNTIL A SEPARATE EXPLICIT OWNER COMMAND
CRM_WRITE: NO
PYTHONANYWHERE_WRITE: NO
SERVICE_RELOAD: NO

## Confirmed blockers

- UA-0009 and UA-0010 have no canonical.
- Home and catalog expose `noindex,nofollow` and canonical under `/video/preview/v4/`.
- `/robots.txt` and `/sitemap.xml` redirect to HTML home.
- UA-0002, UA-0007 and UA-0008 still show `Купить авто` instead of `Задаток 500 $`.

## Required rehabilitation

Build a bounded GitHub Preview candidate from public GET-only inputs. Enforce self-canonical, indexable HTML, real robots/sitemap resources, exact unified CTA, existing diagnostics, dynamically discovered current cards and a synthetic future `UA-9999` regression fixture. Preserve VIN, prices, stages, photos, IDs, destinations and all other business content.

## Acceptance

- every candidate page HTTP source is 200 and not redirected;
- exactly one production self-canonical per indexable candidate;
- zero HTML `noindex`/`nofollow` in the production candidate;
- exactly one CTA `Задаток 500 $` on every current/future card;
- exactly one diagnostics link of the same UA-ID;
- robots is 200 `text/plain`, sitemap is 200 XML, neither redirected;
- catalog cards, scanned cards and sitemap cards are the same dynamic set;
- protected diff has zero unexpected changes;
- ten identical builds produce one tree SHA-256;
- preview remains `noindex,nofollow,nosnippet`, GET/HEAD-only and form-disabled;
- no production, CRM, D1 or PythonAnywhere write.

Stop at a draft pull request and owner visual gate. Do not merge or publish to production.
