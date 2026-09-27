# Desktop navigation on previously shared card URLs

Live read-only audit at 2026-09-27 22:16 UTC: `/video/UA-0023-956711ae.html` responds HTTP 200 without redirect and still contains the legacy touch-only viewer. Main media gallery migration selects only `UA-NNNN.html`, so existing public aliases keep the original desktop defect.

This companion release uses the exact same media renderer and migration as the owner-approved gallery. It changes only existing `UA-NNNN-xxxxxxxx.html` pages in video/site, preserving their vehicle data, photo order/URLs and all bytes outside media blocks. It does not rewrite canonical cards, application modules or CRM. Future aliases are already covered by the separately installed gallery generator. Canonical gallery installation and exact asset-byte verification are prerequisites, not bypassed.

No launch is created while that installation is pending. The separate immutable package retains the existing backup, rollback, bot identity, writer exclusion, public exact-byte verification, protected-data and fresh-plan checks. Every source dependency is protected in the plan. Original failed runs and all consumed packages stay unchanged.
