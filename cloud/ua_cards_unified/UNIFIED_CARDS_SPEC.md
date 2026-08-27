# UNIFIED_CARDS_SPEC.md — TASK_016 (resumes TASK_014)

## Scope

Unify diagnostics + tracking controls across UA-0001..UA-0009 without
redesigning the approved UA ART card layout, and without ever touching
production from this worker.

## Required structure per card (in preview copies only)

1. Existing verified card markup, unmodified except for:
   - removal of legacy/duplicate diagnostic and tracking controls
     (see `LEGACY_CONFLICT_AUDIT.md`);
   - insertion of exactly one `Комплексная диагностика` button and
     exactly one `Отследить контейнер онлайн` button at the single
     `<!-- UA_CARD_ACTIONS_ANCHOR -->` structural anchor.
2. Two companion pages per card: `<code>_diagnostics.html` and
   `<code>_tracking.html`, generated from CRM data mapped through the
   explicit alias allowlist only. Missing data renders as `Уточняется`,
   never invented.
3. Media (photos/videos) referenced only if they pass containment,
   file-type, non-symlink, non-zero and SHA-256 duplicate checks;
   otherwise a locally generated fallback SVG is used.
4. Mobile viewport metadata is present on every generated page.
5. WhatsApp/floating widgets must not overlap the two required buttons
   (verified by DOM position class checks in `TEST_MATRIX.md`).

## Anchor contract

If a real card lacks a unique `<!-- UA_CARD_ACTIONS_ANCHOR -->` marker,
Gate A inserts one immediately before `</body>` only as a deterministic,
logged fallback; if more than one candidate anchor exists, the card is
marked FAIL and is not guessed.

## Synthetic regression fixtures

`UA-9998` (deliberately empty state) and `UA-9999` (deliberately full
state) remain permanent regression fixtures. They never substitute for
real UA-0001..UA-0009 inspection.

## Non-goals for TASK_016

- No redesign of the approved card.
- No production writes, no CRM writes, no WSGI reload.
- No UA-0009 publication.
- No Gate B execution.
