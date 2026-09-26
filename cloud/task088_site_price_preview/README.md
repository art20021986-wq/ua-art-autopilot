# TASK088 — Stage 3 price-block preview only

Owner's latest instruction authorizes a visual split of the existing top price
area: Ukraine above Georgia, both in USD. It supersedes the prior prohibition
on this specific price-area layout change. It does not authorize Production.

`preview.html` is a static design review, not a deployed template or live data
integration. No launch marker, execution receipt, API call or live write exists.
Stage 2 is still not PASS.

## Current page observation

Observed card: https://www.uaart.com.ua/video/UA-0009.html

The existing `.blok` contains `.nom`, the title, `.chip`, `.cena` and the Kyiv
price explanation. Its current price is 11 500 USD. The rendered page is `uk`
and loads `/video/ua-site-languages.js?v=site-ge-002-v1`. No `data-market` or
`data-country` attributes were found on this page. This is page evidence only;
it does not establish the complete generator or market-routing architecture.

The preview retains the Ukraine explanation under Ukraine only, adds a thin
gold divider, and places Georgia below. The wider site description, VIN,
gallery, additional specification, diagnostics, route, CTA and catalog are not
part of this component or this change.

## Price binding for subsequent implementation

- Upper value: `price_uah`, using the existing USD formatter and existing value.
- Lower value: `price_georgia`, using the same formatter independently.
- When a price is set in the CRM bot and committed to its matching DB field,
  the site must display that value on the corresponding market row.
- Always render the Georgia heading and description, including when its price
  is absent. The preview's neutral description is “Придбання автомобіля в Грузії.”
- Never derive Georgia from Ukraine or the current vehicle stage.
- Language selection translates labels; it must not change either value.
- Retain the existing site language mechanism instead of adding a market router.
- The actual Georgia value of UA-0009 has not been read. The preview deliberately
  demonstrates a missing-value state and makes no assertion about that DB row.

## Approved missing-Georgia-price behavior

The owner's latest instruction explicitly approves **Цена уточняется**.
Use **Ціна уточнюється** in Ukrainian and **Цена уточняется** in Russian,
through the existing language mechanism. NULL/empty Georgia price does not
hide its heading, its description, the Ukraine price, or the vehicle card.
Do not use 0 or a dash as missing-price placeholders. Never copy the Ukraine
amount or invent a Georgia amount. This fallback needs no further approval.
This rule is specific to the Georgia price; existing Ukraine behavior stays
unchanged. The approval does not establish live integration or authorize
Production deployment.

Before implementation: inspect current generator/data propagation and language
integration, finish Stage 2, verify this Preview, and prepare
the existing backup/hash/preview/regression gates. Production remains subject
to separate explicit owner permission after Preview verification.
