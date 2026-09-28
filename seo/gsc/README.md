# UA ART — Google Search Console Gate A

Read-only, isolated Search Console integration.

## Safety
- Does not modify the website, CRM, sitemap, canonical tags, or Search Console property.
- Workflow is manual-only at Gate A.
- Uses the `webmasters.readonly` OAuth scope when the refresh token is created.
- Credentials live only in GitHub Actions Secrets.
- Uses Python standard library only.

## Required GitHub Actions Secrets
- `GSC_CLIENT_ID`
- `GSC_CLIENT_SECRET`
- `GSC_REFRESH_TOKEN`

Property: `sc-domain:uaart.com.ua`.

## Gate A PASS
The workflow must return URL Inspection data for the home page, catalog, and selection page without any write operation. Only after PASS should scheduled analytics be added.
