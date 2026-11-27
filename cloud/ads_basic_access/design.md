# UA ART COMPANY LLC — Google Ads API tool design document

**Company:** UA ART COMPANY LLC, Kyiv, Ukraine (vul. Peremohy, 20) · **Website:** https://www.uaart.com.ua
**Google Ads account:** 468-074-7874 (managed under our own manager account) · **Users:** our company only (internal tool).

## Purpose
UA ART helps clients in Ukraine buy cars from auctions in Korea, Japan and the USA. We advertise only our own
business on Google Search. The tool is an internal script that manages **our own** Google Ads account; it is not
offered to other advertisers or third parties.

## What the tool does
1. **Reporting (read):** daily statistics per campaign — impressions, clicks, cost, conversions, search terms,
   invalid clicks, impression share; account, billing and serving status. Reports are sent to the owner.
2. **Keyword management (write):** adds buyer search phrases generated from the car models and years on our
   auction pages (e.g. «kia k5 2019 з кореї»), phrase match, in batches; adds negative keywords; removes duplicates.
3. **Campaign maintenance (write):** creates and updates our Search campaigns (Korea, USA, Japan), ad groups,
   responsive search ads with texts approved by the owner, sitelinks, ad schedule, budgets and Maximize-clicks
   bid ceilings — every change only after the owner's explicit approval.
4. **Conversion setup:** a website conversion action for the lead form on our site.

## Why Basic access
Our keyword plan is about 30,000 phrases (all models × years × Ukrainian and Russian spellings for three countries).
With Explorer access (2,880 operations a day) this takes weeks; Basic access lets us finish in a few days and
keep daily reporting without hitting the quota.

## Technical design
- Python scripts using the Google Ads REST API (googleAds:search, googleAds:mutate with partial failure).
- Runs on our server as short scheduled jobs; OAuth refresh token of our own Google account stored on the server
  only; no data is shared with third parties.
- Every write is logged with state before and after; changes are made only on the owner's approval.
- Rate limits respected: batches of ≤600 operations, one run per night for bulk keyword additions.

## Contact
Owner / API contact: the Google account that owns the developer token (UA ART COMPANY LLC).
