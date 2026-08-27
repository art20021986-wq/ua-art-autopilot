# TEST MATRIX — TASK 013

Legend: PASS (verified in this sandbox via the pure render functions), NOT_PROVEN (requires real PythonAnywhere execution/browser check, not available to this GitHub worker).

## Per-card static structural checks (executed against START_UA_CARDS_UNIFIED.py self-test, 10 deterministic runs)

| Card | 1 diag button | diag page exists | correct diag state | 1 track button | track page exists | correct track state | no unsafe href | no dup buttons | mobile structure class reused |
|---|---|---|---|---|---|---|---|---|---|
| UA-0001 (fixture: empty facts) | PASS | PASS | PASS (EMPTY) | PASS | PASS | PASS (NOT_SHIPPED) | PASS | PASS | PASS (structural) |
| UA-0002..UA-0008 | NOT_PROVEN (no real CRM read performed; only UA-0001/UA-0009/synthetic fixtures rendered in this round) | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN | NOT_PROVEN |
| UA-0009 (confirmed facts only, no diagnostics/tracking facts invented) | PASS | PASS | PASS (EMPTY diag, NOT_SHIPPED track) | PASS | PASS | PASS | PASS | PASS | PASS (structural) |
| Future empty card (UA-9998 fixture) | PASS | PASS | PASS (EMPTY) | PASS | PASS | PASS (UNKNOWN track raw -> NOT_SHIPPED default only because empty dict; real generator must still supply explicit stage) | PASS | PASS | PASS |
| Future full card (UA-9999 fixture) | PASS | PASS | PASS (PARTIAL: summary+body+obd present, no photos/videos) | PASS | PASS | PASS (IN_TRANSIT with valid carrier URL) | PASS | PASS | PASS |

## Diagnostics state cases (unit-level, exercised through CardFactsReader in self-test)

| Case | Result |
|---|---|
| Empty | PASS -> EMPTY, required empty paragraph rendered |
| Text only | PASS -> PARTIAL |
| OBD only | PASS -> PARTIAL |
| Photo only | PASS -> PARTIAL |
| Video only | PASS -> PARTIAL (subject to video validation) |
| Partial mixed | PASS -> PARTIAL |
| Full | PASS -> FULL |
| CRM reference to missing file | PASS -> video marked invalid ("not_regular_file"/unreadable), excluded from valid_videos, page still renders empty-video sub-state |
| Duplicate video SHA (vs main video or within card) | PASS -> flagged invalid with reason `duplicate_of_main_video_sha256` / `duplicate_sha256_within_card`, excluded from render |

## Tracking cases

| Case | Result |
|---|---|
| Korea / pre-container | PASS -> NOT_SHIPPED text |
| Number but no external URL | PASS -> CONTAINER_ASSIGNED_NO_NUMBER text (no external link rendered) |
| At sea with valid URL | PASS -> IN_TRANSIT + external carrier link rendered |
| Georgia (treated as IN_TRANSIT with route text) | PASS -> route line rendered, no invented container data |
| Kyiv / completed | PASS -> DELIVERED_KYIV text |
| Invalid external URL (javascript:/data:/empty) | PASS -> `is_safe_url` rejects it, external link omitted, no crash |

## Explicit gaps (NOT_PROVEN, honestly disclosed)

- Real browser rendering at 390/430/768/1366 px — NOT_PROVEN (no browser executed in this environment).
- Actual current UA-0002..UA-0008 CRM field values — NOT_PROVEN (no live read performed).
- WhatsApp floating widget non-overlap in a live DOM — NOT_PROVEN.
- HTTP reachability of any URL — NOT_PROVEN (no network access used).
