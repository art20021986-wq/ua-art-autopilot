# UNIFIED CARDS SPEC — TASK 013

STATUS OF THIS DOCUMENT: CANDIDATE DESIGN ONLY. NOT EXECUTED ON PRODUCTION. NO PYTHONANYWHERE ACCESS FROM THIS WORKER.

## 1. Goal

Every UA ART vehicle card (existing UA-0001..UA-0008, pending UA-0009, and all future UA-0010+) must deterministically expose:

1. Exactly one visible `Комплексная диагностика` control on `/video/UA-XXXX.html`.
2. Exactly one visible `Отследить контейнер онлайн` control on the same card.
3. A stable diagnostics page at `/video/UA-XXXX-diag.html` that renders even with zero diagnostic data.
4. A stable tracking page at `/video/UA-XXXX-track.html` that renders even before a container is assigned.
5. No fabricated data. No dead/empty hrefs. No black iOS video placeholder. No manual per-card HTML patch.

## 2. Why a compatibility layer instead of a CRM migration

The existing CRM schema for cards UA-0001..UA-0008 is unknown to this worker with certainty (no direct DB/file read was performed from this sandboxed environment against production). Forcing a migration is explicitly forbidden by policy and is unsafe without a verified schema snapshot. Instead we introduce a **read-only compatibility adapter**: `CardFactsReader`, which accepts partial/missing fields and always returns a fully-populated, truthfully-labeled `CardFacts` object with explicit `NOT_PROVEN` / `Уточняется` markers rather than assuming success.

## 3. Canonical data model (compatibility layer)

```
DiagnosticsFacts:
  status: one of {FULL, PARTIAL, EMPTY, UNKNOWN}
  summary_text: str|None
  body_safety_text: str|None
  obd_url: str|None (validated http/https only)
  photos: list[path] (validated real, non-symlink, non-zero)
  videos: list[VideoCandidate] (validated + de-duplicated by SHA-256)
  updated_at: str|None

TrackingFacts:
  stage: one of {NOT_SHIPPED, CONTAINER_ASSIGNED_NO_NUMBER, IN_TRANSIT, DELIVERED_KYIV, UNKNOWN}
  route: str|None
  container_number: str|None
  carrier_name: str|None
  carrier_url: str|None (validated http/https only)
  updated_at: str|None
```

All string fields are HTML-escaped at render time using `html.escape`, never trusted raw.

## 4. Render contract (idempotent, pure functions)

- `render_card_entry_buttons(card_id) -> str` — always returns exactly one diagnostics anchor and exactly one tracking anchor, pointing to the two stable URLs. Never conditioned on data presence.
- `render_diag_page(card_id, facts: DiagnosticsFacts) -> str` — always renders a full HTML document. Blocks (summary, body/safety, OBD, photos, videos) are rendered independently; a missing block prints its own truthful empty sub-state, never hides the whole page.
- `render_track_page(card_id, facts: TrackingFacts) -> str` — always renders a full HTML document with the truthful stage message from the fixed message table in the task spec, and only adds the external carrier link when `carrier_url` passed URL validation.

## 5. Video safety rules implemented

- reject symlinks (`os.path.islink`);
- reject non-regular files;
- reject zero-byte files;
- compute SHA-256 of every diagnostic video candidate and drop exact duplicates of the same card's main vehicle video unless explicitly tagged as a distinct diagnostic asset;
- always render `<video controls playsinline preload="metadata" poster="...">` with a real poster path when one exists, else a static neutral placeholder image (never a black frame, never `autoplay`);
- provide a separate `Открыть видео` direct link outside the `<video>` tag.

## 6. URL safety rules

- Accept only `http://` or `https://` schemes for `obd_url` and `carrier_url`.
- Reject empty string, `#`, `javascript:`, `data:`, and any scheme not in the allow-list.
- HTML-escape all attribute and text content.
- Add `rel="noopener noreferrer"` and `target="_blank"` only to real validated external links.

## 7. Card ID validation

Accept only `^UA-\d{4}$`. Reject anything else before any filesystem lookup, preventing path traversal. Resolve final paths with `os.path.realpath` and require them to remain inside an explicit allow-listed root; reject symlinked targets.

## 8. Stable URL routing

`/video/UA-XXXX.html`, `/video/UA-XXXX-diag.html`, `/video/UA-XXXX-track.html` — the entry card must link to the other two by fixed naming convention derived purely from `card_id`, not by lookup, so link-generation cannot silently fail even if the target page has not been generated yet (best effort: the generator always produces all three files together, atomically, or none).

## 9. Truthful state text table

Diagnostics:
- FULL -> "Проверено"
- PARTIAL -> "Материалы добавляются"
- EMPTY -> "Диагностика ожидается" + required paragraph: "Материалы комплексной диагностики готовятся. Они будут добавлены после проверки автомобиля."
- UNKNOWN -> "Уточняется"

Tracking:
- NOT_SHIPPED -> "Автомобиль ещё не передан в контейнер. Номер и онлайн-отслеживание будут добавлены после отправки."
- CONTAINER_ASSIGNED_NO_NUMBER -> "Номер контейнера уточняется. Онлайн-отслеживание станет доступно после обновления данных."
- DELIVERED_KYIV -> "Доставка завершена. Автомобиль находится в Киеве."
- IN_TRANSIT with valid carrier_url -> stage text + extra link "Открыть отслеживание перевозчика".

## 10. Visual/layout constraints preserved

Both buttons reuse the existing approved button CSS classes referenced in prior UA ART card templates (no new dark/gold variant introduced). Order fixed: diagnostics button first, tracking button second, both above the floating WhatsApp z-index layer, verified structurally (not screenshot-verified — no browser was executed in this environment) at 390/430/768/1366 px via static container width assertions in the fixture HTML (media-query classes reused, not redefined).

## 11. What remains NOT_PROVEN from this sandboxed worker

- The exact current production generator file/function name and its exact overwrite logic (see LEGACY_CONFLICT_AUDIT.md).
- Whether UA-0001..UA-0008 live HTML was produced by a single generator or by several ad-hoc scripts.
- Actual rendered pixel layout in a real browser (requires PythonAnywhere/browser execution, out of scope for this GitHub worker).
