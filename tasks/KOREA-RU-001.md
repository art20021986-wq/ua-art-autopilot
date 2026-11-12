# KOREA-RU-001 — Korea auctions page: Russian version and sitemap

Owner «Да» 2026-11-12 to SEO items 1 and 3 (Korea page in the sitemap; its Russian version).
Item 5 (link from the «Авто з Кореї» hubs) is separate: text and place go to the owner first.

## Change
1. New `/video/ru/korea.html`: the Russian version of `/video/korea.html` (`ua_korea_ru.py`: the data-ru texts and
   attributes in place, `lang="ru"`, own canonical, hreflang pair, links absolute; script code untouched except the
   order link base). Kept in step by the existing card version job (`ua_card_lang_job.py`, once a minute).
2. `/video/korea.html`: only the hreflang pair (uk, ru, x-default) first in `<head>`.
3. `video/i18n-home-ge.js`: a page with language versions opens in its own language (as `ua-site-languages.js`
   since CARD-LANG-001). The home page has no such links and behaves as before.
4. `ua_seo_sitemap.py`: `korea.html` and `ru/korea.html` in CORE; web app reloaded (it serves /sitemap.xml);
   `ua_seo_index.refresh` notifies IndexNow and Google.

Side effect (same as the card versions): `/video/korea.html` opens in Ukrainian even for a visitor whose saved choice
is Russian; the RU button takes them to `/video/ru/korea.html`.

## Order
Coordinator: package and tests now; preview after the Korea sessions' installs (02, 06, 08) so the plan binds the
current korea.html; install only on the coordinator's «твоя очередь».

## Check (2026-11-12, iPhone 13, live page + candidate)
Russian page: lang ru, Russian title and texts (0 Ukrainian-letter texts), lots and photos load, UA → korea.html.
korea.html: Ukrainian. Home: Ukrainian by default, Georgian kept.
