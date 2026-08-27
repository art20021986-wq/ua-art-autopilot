# LEGACY CONFLICT AUDIT — TASK 013

## Method

This worker has no live read access to the PythonAnywhere filesystem or CRM database. All findings below are based on: (a) prior task specifications and reports referenced in this repository under `cloud/` and `tasks/`, and (b) the externally observed defect on UA-0004 described in the task. No direct file listing of the production generator was performed in this round. Every claim is labeled PROVEN or NOT_PROVEN accordingly.

## Observed evidence (PROVEN, external)

- PROVEN: the live UA-0004 page currently lacks both required transitions (diagnostics, tracking), per owner-supplied external verification referenced in this task.
- PROVEN: card behavior is inconsistent across the existing set ("some existing cards show diagnostics only when certain data exists"), i.e., current logic is conditional rather than unconditional.

## Suspected legacy sources of conflict (NOT_PROVEN, inferred)

1. NOT_PROVEN — a single monolithic card-generation script that renders a diagnostics block only inside an `if diag_data:` guard, producing zero output (not even a stable link) when the CRM record has no diagnostics fields populated. This is the most likely direct cause of the UA-0004 defect described.
2. NOT_PROVEN — a possible second, older per-car HTML template committed manually for early cards (UA-0001..UA-0003) that predates the shared generator and was never migrated, causing divergent structure between old and new cards.
3. NOT_PROVEN — a possible scheduled/manual "regenerate card" job that overwrites the entry HTML but does not regenerate the diag/track companion pages, leaving stale or missing companion files after some updates.
4. NOT_PROVEN — a possible client-side/JS conditional that hides the tracking button via `display:none` when a stage field is absent, rather than the button being server-side present with a truthful empty destination page.
5. NOT_PROVEN — direct video-tag reuse of the main vehicle video file as a "diagnostic video" on some cards, without SHA-256 comparison, which the task explicitly forbids.

## Required confirmation before any production patch (Gate A prerequisite)

- A file listing / grep of the actual generator source on PythonAnywhere (read-only) confirming which of the above hypotheses is correct.
- A read-only export (not a migration) of the current CRM fields used by the generator, to correctly implement `CardFactsReader` against the real schema instead of the assumed compatibility model in this candidate.

## Conclusion

The candidate in this task package is written defensively so that it does NOT depend on which of the above hypotheses is correct: it introduces a **new, additive, unconditional render contract** (`render_card_entry_buttons`, `render_diag_page`, `render_track_page`) that can be layered on top of any of the suspected legacy sources once Gate A read-only confirmation is obtained, and is designed to be inserted without deleting legacy code paths outright — see PRODUCTION_PATCH_PLAN.md for the bounded allowlist and rollback design.
