# TASK 080 — Test Results (offline desk-check trace)

## Important disclaimer
No live pytest execution was performed inside this delivery channel — this
worker has no shell/execution tool available here. The table below is a
manual, line-by-line desk-check of `price_parser.parse_sale_price_message`
against every test in `tests/test_price_parser.py`, tracing the regex
matches and arithmetic by hand. It is offered as engineering evidence of
intended behavior, not as proof of live execution. The controller/ChatGPT
must actually run:

```
python -m pytest cloud/task_080_price_recognition/tests/test_price_parser.py -v
```

in a real Python 3.x environment and record the literal console output
before this candidate can be considered verified.

## Desk-check trace table

| Test | Input | Traced result | Expected |
|---|---|---|---|
| format_1 | `Стоимость автомобиля 11 400 долларов` | intent match `стоимость автомобиля`; grouped digits `11 400`→11400; no blockers | 11400 OK |
| format_2 | `цена машины 11400 $` | intent `цена машины`; plain digits 11400 | 11400 OK |
| format_3 | `цена авто: 11 400 USD` | intent `цена авто`; grouped digits | 11400 OK |
| format_4 | `ціна авто 11 400 доларів` | intent `ціна авто`; grouped digits | 11400 OK |
| format_5 | `... одиннадцать тысяч четыреста долларов` | intent `стоимость авто`; word run одиннадцать(11)+тысяч(*1000)=11000, +четыреста(400)=... traced group logic: одиннадцать→group=11, тысяч→total+=11*1000=11000,group=0; четыреста→group=400; end total=11000+400=11400 | 11400 OK |
| format_6 | `... одинадцять тисяч чотириста доларів` | same UA lexicon path | 11400 OK |
| format_7 | `цена 11,4 тыс. долларов` | thousand-suffix regex matches `11,4 тыс.`→11.4*1000=11400 | 11400 OK |
| format_8 | `цена 11.4k USD` | k-suffix regex matches `11.4k`→11.4*1000=11400 | 11400 OK |
| bare digits in wait mode | `11400`, wait=True | fast path bare digits accepted | 11400 OK |
| bare digits outside wait | `11400` | no intent phrase found | NO_SALE_PRICE_INTENT |
| NBSP grouping | `цена\u00a011\u00a0400` | normalized NBSP→space, then grouped digits `11 400` | 11400 OK |
| grouped comma | `цена 11,400` | grouped-digits regex matches | 11400 OK |
| grouped dot | `цена 11.400` | grouped-digits regex matches | 11400 OK |
| year only | `год выпуска 2014` | no sale-price intent phrase present | NO_SALE_PRICE_INTENT |
| mileage only | `пробег 120000 км` | no intent phrase | NO_SALE_PRICE_INTENT |
| engine only | `двигатель 2.0 л` | no intent phrase | NO_SALE_PRICE_INTENT |
| ETA only | `ETA 14 дней` | no intent phrase | NO_SALE_PRICE_INTENT |
| container only | `контейнер номер 4521` | no intent phrase | NO_SALE_PRICE_INTENT |
| purchase cost blocked | `цена закупки автомобиля 11400` | intent `цена` matches, but blocker `закуп\w*` also matches | AMBIGUOUS_CONTEXT_BLOCKED |
| logistics cost blocked | `стоимость логистики 11400` | intent `стоимость` matches, blocker `логистик\w*` matches | AMBIGUOUS_CONTEXT_BLOCKED |
| customs cost blocked | `стоимость таможни 500` | intent matches, blocker `таможен\w*` matches | AMBIGUOUS_CONTEXT_BLOCKED |
| two competing amounts | `цена 11400 или 12000 долларов` | two distinct numeric candidates {11400,12000} | MULTIPLE_COMPETING_AMOUNTS |
| zero rejected | `цена 0` | value=0 < MIN_SANE_PRICE | OUT_OF_RANGE |
| overflow rejected | `цена 99999999` | value > MAX_SANE_PRICE(500000) | OUT_OF_RANGE |
| explicit change intent | `измени цену на 12000` | change pattern `измен\w*` matches; value 12000 | ok=True, is_explicit_change_intent=True |
| no change intent | `цена 12000` | no change pattern | ok=True, is_explicit_change_intent=False |
| field always price_uah | 4 sale-price phrasings | field=='price_uah' on every success | confirmed by construction (result.field is hardcoded to "price_uah" in every ok branch) |
| performance | 1000 iterations of a typical phrase | pure regex + dict lookups, no I/O; each call touches <15 short regexes over a <60 char string | well under 50 ms/call by construction; needs real timer confirmation |

## Coverage note on existing/future cards (requirement 10)
The parser takes only a text string and a boolean wait-flag; it has no
dependency on any specific `auto_number` or card id, so — once wired through
a hash-verified integration into the live caller — it applies identically to
UA-0001 through the highest existing `auto_number` and to any future card
without per-card configuration. This claim is about the parser's code shape,
not about a live-executed sweep, because Gate A live access was not
available in this round (see `audit/GATE_A_STATUS.md`).

## Read-only audit of current cards (requirement 10, second half)
Not performed in this round: it requires a live read-only GET of the cards
table, which was not available in this delivery channel. This is recorded as
an open dependency for the controller, not fabricated as completed.
