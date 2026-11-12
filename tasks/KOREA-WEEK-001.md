# KOREA-WEEK-001 — Korea online auctions: weekly check

Owner 2026-11-12: «Проверять обязательно количество аукционов онлайн, которые проходят каждую неделю. Если будет
добавление каких-то аукционов, обязательно добавим информацию на сайт. Естественно, информацию о лотах.»

## Why
The site collector searches only the auction groups the Korea search form checks by default (4 and 5,
SOCIAL-PROBE-20261112-R11: groups 1, 2, 3, 4, 5, 6, 8). Auctions of other groups do not reach the site, and nobody
sees when the auction platform adds one.

## Package cloud/korea_week_001 (read-only)
- `week.py` — pure: form schedule (days, auctions under each, default), auctions of the coming 7 days (house + day,
  lots at the auction, lots on the site), comparison with the previous weekly report (`python3 cloud/korea_week_001/week.py OLD.json NEW.json`).
- `source_remote.py` — server run with the installed collector and the owner login: one search, the published lot list.
- `controller.py`, `transport.py`, `bootstrap.py`, `make_request.py` — the LOT-PROBE transport, own server prefix.

## Weekly
R1 (2026-11-12): the search ignores the day boxes — one search, checked against the published lot list (R2).

Every Monday: `make_request.py request <date>` → PR → merge → `make_request.py launch <date>` → PR → merge;
compare the report with the previous week; report to the owner. A new auction or one the site does not show →
proposal to the owner (what changes on the site) → owner «да» → install. No site/CRM write without «да».
