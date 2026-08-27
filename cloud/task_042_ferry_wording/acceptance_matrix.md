# TASK 042 — Per-card acceptance matrix (SYNTHETIC evidence, pending real Gate A)

All rows below are produced by `gate_a_preview.py` against **synthetic proxy
fixtures**, because this execution context has no filesystem access to the
real UA ART source tree. Real per-card evidence must be captured once
`discover.py` runs on PythonAnywhere against the approved root.

| Card | Real source found | Internal stage before | Internal stage after | RU visible output | UA visible output | Forbidden wording present | Idempotent | data-stage / ?f=sea preserved |
|---|---|---|---|---|---|---|---|---|
| UA-0001 | NOT_PROVEN (no filesystem access) | sea | sea | На пароме | (mapping ready, not exercised on real UA text) | NO | YES | YES |
| UA-0002 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0003 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0004 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0005 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0006 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0007 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0008 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES |
| UA-0009 | NOT_PROVEN | sea | sea | На пароме | (mapping ready) | NO | YES | YES (not published) |
| future: internal `sea` (UA-0123 fixture) | SYNTHETIC by design | sea | sea | На пароме | На поромі (mapping applies identically) | NO | YES | YES |
| future: legacy alias `В море` (UA-0456 fixture) | SYNTHETIC by design | В море → normalizes to sea | sea | На пароме | На поромі | NO | YES | YES |

Container/tracking behavior, diagnostics companion pages, links/media, and
source/live hashes are unchanged in all rows because no production or CRM
write occurred at any point in this task; the fixtures never touch those
systems.
