# Visual Test Matrix (Task 092)

## Viewports required (Playwright or equivalent)

320×568, 360×800, 375×812, 390×844, 393×852, 430×932, 768×1024, 1366×768, 1440×900

## Pages/cards required per viewport

- Homepage
- Full catalog
- Each stage filter view (Korea / Sea / Georgia / Kyiv)
- UA-0001
- UA-0002
- UA-0003
- UA-0009
- UA-0011
- UA-0012
- UA-0013

## Mandatory screenshots

1. Stage cards (all 4, in Kyiv → Georgia → Sea → Korea order)
2. "Открыть все автомобили" CTA area (checking WhatsApp does not overlap)
3. Catalog start (first screen)
4. A card with a long title (2-line clamp check)
5. UA-0009 ETA card (catalog view)
6. A card with no video (fallback state)
7. WhatsApp collision case (bottom of viewport, safe-area-inset-bottom check)
8. RU→UA toggle, same card before/after
9. UA-0009 full card
10. UA-0013 full card

## Execution status this round

No canary build exists yet, so this matrix has not been executed. It is delivered here as the exact spec to run against the first working sandbox/canary build once real site material is supplied.
