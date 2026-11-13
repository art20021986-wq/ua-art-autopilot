# Google Business Profile API — access application (owner «да» 2026-11-13)

Goal: read-only link from the autopilot to the UA ART COMPANY Business Profile (reviews and rating, views, calls,
directions; check website link, hours, category) for the SEO reports. Nothing is changed in the profile without the
owner's «да».

Facts: the profile exists (owner confirmed 13.11; the site's «Офіс на мапі» opens it). The autopilot's Google Cloud
project is `uaart-autopilot` (Search Console service account). Google accepts the application only from the business
owner (third parties must not apply on a client's behalf), so the owner submits the form; Claude prepares the answers.

## Owner steps (phone)
1. Open https://console.cloud.google.com/home/dashboard?project=uaart-autopilot → card «Project info» → copy
   **Project number** (digits; not the ID).
2. Open https://support.google.com/business/contact/api_default → choose **Application for Basic API Access**.
3. Fill in with the answers below; email = the Google account that owns the profile.
4. Send. Google answers by email (up to ~2 weeks). Then tell Claude «одобрили».

## Answers
- Company name: UA ART COMPANY LLC
- Website: https://www.uaart.com.ua
- Project ID: uaart-autopilot
- Project number: (from step 1)
- Business Profile: UA ART COMPANY, Kyiv (vul. Peremohy, 20)
- Use case: «We are the owner of this single business profile (UA ART COMPANY, car import, Kyiv). We need read-only
  access to our own profile: reviews and rating, performance metrics (views, calls, direction requests) and checks
  that the website link, hours and category are correct, for our internal SEO reports. No third-party profiles,
  no automated posting.»

## After approval (Claude)
- Enable My Business Account Management, Business Information and Business Profile Performance APIs in the project;
  OAuth client; the owner signs in once and presses «Allow» (scope business.manage); the refresh token is kept as a
  server secret (never in the repo). Then the GBP figures go into the 3-day SEO report.
