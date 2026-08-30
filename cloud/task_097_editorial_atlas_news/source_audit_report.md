# Source audit report — 70-source candidate pool

Full machine-readable data is in `source_registry.csv`. This report explains the patterns and the MVP selection.

## 1. Aggregate result (VERIFIED from the attached probe)

- 70 candidate rows probed (one page GET + one `robots.txt` GET per domain), exactly 10 per geo: UA, GE, KR, JP, US, EU, CN.
- 46 rows returned an HTTP status below 400 at probe time; 24 rows returned an error/blocked response (403/401/404/202/ERROR), per the attached summary.
- Reachability at one point in time is **not** copyright permission and **not** an automation go-ahead; every row's `decision` column reflects that distinction.

## 2. Recurring failure patterns observed (VERIFIED)

| Pattern | Rows affected | Meaning for this project |
|---|---|---|
| Cloudflare/WAF interstitial ("Just a moment...", "Attention Required!") | UA-07, UA-08, UA-10, GE-04, GE-07, GE-08 | Not a login wall in the copyright sense, but automated GET cannot pass it; needs a rendering-capable, still-read-only fetch method later, or manual monitoring |
| Hard 403/401 without a challenge page | UA-01, UA-02, JP-01, US-01, US-03, US-04, US-05, EU-05, CN-02 | Either bot-blocking or an access wall; treated as **not currently automatable**, decision APPROVE_LATER or MANUAL_ONLY depending on category |
| HTTP 401 on a read-only GET (login/paywall signal) | US-06 (Reuters), CN-07 (Reuters) | Per the task's explicit rule against bypassing login/paywall, these exact endpoints are **REJECT**, not scheduled |
| DNS failure | GE-05 (Agenda.ge) | Domain unreachable at probe time; kept as PENDING, not deleted, per the task's rule |
| Network-level failure (timeout / connection reset / TLS failure) | CN-01, CN-03, CN-04, JP-07 | All CN rows with this pattern are official Chinese government/industry domains; **INFERRED**: consistent with common network-path filtering seen when reaching some mainland-China government domains from typical cloud/CI network ranges, but this is not independently confirmed as the cause — kept PENDING pending a re-probe |
| Unusual non-200/400 status (202 Accepted) | EU-02 (ACEA), JP-10 (Nissan Newsroom) | Not a normal static-page response; needs a re-probe before trust, kept PENDING |
| Domain redirect to a different-looking domain | KR-01 (motie.go.kr → motir.go.kr), KR-08 (joins.com → koreajoongangdaily.com), EU-05 (europe.autonews.com → autonews.com/europe/), KR-10 (404 on the listed path, correct path unconfirmed) | Any domain change must be manually confirmed as a genuine official redirect before ingestion is configured; treated as PENDING/REPLACE, never trusted automatically |
| Non-UTF-8 page encoding (mojibake) | KR-03 (KAMA), JP-03 (Japan Customs) | Automated text/title extraction is unreliable without a charset-aware parser; flagged, not silently guessed |

## 3. Sensitive-category cross-check (VERIFIED against the task's fixed sensitive list)

Sources whose `automotive_scope` includes customs, import/export policy, registration, or safety/recalls are marked `MANUAL_ONLY` in the registry **regardless of their reachability**, because the task fixes these categories as mandatory-manual with an official first-source requirement: UA-01, UA-02, UA-10, JP-01 (export policy), JP-03, KR-02, US-01, US-02, US-03, US-04, EU-09, and (for the paywalled/blocked-but-otherwise-official rows) noted accordingly.

## 4. MVP selection — 15 sources (Ukraine 5, Georgia 5, Korea 5)

The task requires the 15 MVP sources to be **chosen from the audit, not from popularity**. The selection rule applied uniformly: prefer sources that (a) returned HTTP < 400 at probe time, (b) were not blocked by a Cloudflare/WAF challenge, (c) exposed a working RSS feed or sitemap (structural discoverability), and (d) balance at least one official/class-A body per geo where one was actually reachable.

| Geo | Selected | Why |
|---|---|---|
| Ukraine | UA-03 (AUTO.RIA), UA-04 (Автоцентр), UA-05 (Укравтопром), UA-06 (eauto.org.ua), UA-09 (Інтерфакс-Україна) | These are the only 5 of the 10 UA candidates that returned HTTP 200 without a challenge page at probe time; UA-05 is the strongest official statistics body reachable; UA-09 has a Google News sitemap |
| Georgia | GE-01 (Revenue Service), GE-02 (Geostat), GE-03 (Ministry of Economy), GE-06 (Commersant), GE-09 (Netgazeti) | Three official bodies reachable without a challenge, plus the two GE media outlets with the best structural discoverability (Netgazeti has RSS+sitemap; Commersant has a sitemap) |
| Korea | KR-02 (Korea Customs Service), KR-04 (Yonhap), KR-05 (Korea Herald), KR-06 (Korea Times), KR-09 (KOTRA) | Two reachable official bodies (customs, trade) plus the three best-automatable English-language KR media outlets (RSS/sitemap present, no challenge, no encoding issue) |

Sources explicitly **excluded from the MVP but not rejected** (APPROVE_LATER/PENDING), with a one-line reason each, are documented in `source_registry.csv`'s `audit_note` column — for example, KR-01 (MOTIE) is withheld pending manual confirmation of its redirected domain, KR-03 (KAMA) is withheld pending a charset-aware parser, and GE-10 (APM Terminals Poti) is withheld only because it lacks RSS/sitemap structure, not because it is low-value.

## 5. What this audit does **not** grant

- No permission to copy a full article or an image from any of the 70 sources.
- No permission to bypass any Cloudflare challenge, CAPTCHA, login, or paywall (US-06 and CN-07 are explicitly rejected on this principle).
- No permission to treat a reachable government mirror domain (KR-01) as confirmed official without manual human confirmation.
- No automatic publication right for any sensitive-category topic, regardless of a source's class or reliability score.
