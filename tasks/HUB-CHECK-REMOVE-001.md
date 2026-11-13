# HUB-CHECK-REMOVE-001 — remove «Як ми перевіряємо авто до покупки» from the Korea hubs

Owner 2026-11-13 (screenshot of the uk hub): «Убери этот раздел. Никогда не пиши то, чего нету... Удали немедленно.»

## Change
`ua_seo_hub_texts.py`: the section's texts (uk `check_title`/`check`, ru likewise) and its place in `hub()` are
removed entirely; the install's landing refresh rewrites `/video/seo/ua/avto-z-korei-do-kyieva-pid-kluch.html` and
`/video/seo/ru/avto-iz-korei-v-kiev-pod-kluch.html`. Every other text stays (order steps unchanged).

## Next (owner)
A short description of what an auction inspection report gives (original mileage, accidents, technical condition),
without any link, for the owner's approval; the owner will choose the report service and its link later.
