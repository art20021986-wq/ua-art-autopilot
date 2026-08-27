# TASK 042 — «В море» → «На пароме» / «У морі» → «На поромі»

Self-contained Gate A candidate package. NO production, CRM, or live-card
writes occur from this package. Everything here operates on synthetic
proxy fixtures and/or a caller-supplied read-only root path.

## IMPORTANT EXECUTION-CONTEXT DISCLOSURE

The Claude/Cloud sandbox that authored this package has **no filesystem
access to `/home/Carix` or any real PythonAnywhere path**. Therefore:

- `discover.py` is a complete, bounded, read-only discovery tool that is
  ready to run for real once pointed at an approved root path on
  PythonAnywhere (via the reviewed safe-inbox / read-only discovery
  channel). Run without arguments in this environment, it correctly
  reports `NOT_PROVEN` instead of fabricating findings.
- `gate_a_preview.py` builds the nine-card and future-card preview matrix
  using clearly labelled **SYNTHETIC_PROXY_FIXTURE** content that mirrors
  the real anchors described in the task (`data-stage="sea"`, `?f=sea`,
  status pill, heading, timeline legend, filter button) so the transform
  and tests are meaningful, deterministic, and offline-verifiable.
- All acceptance tests in `tests/test_ferry_wording.py` run fully offline
  against these fixtures and the canonical mapping/transform modules.

Because real discovery against the live UA ART source tree has not been
performed (no access), and PythonAnywhere Gate A has not been executed,
the honest terminal state for this task is **READY_FOR_CODEX_AUDIT**,
not DONE and not AWAITING_GATE_B.

## Files

- `ferry_wording.py` — canonical presentation mapping (single source of
  truth for RU/UA long/heading/short forms of the sea/ferry stage, and
  legacy-alias normalization back to the internal key `sea`).
- `transform.py` — deterministic, idempotent text transform used to build
  Gate A candidates from any given source text.
- `discover.py` — bounded, read-only occurrence-discovery tool (safe to
  run against a real root path on PythonAnywhere later).
- `gate_a_preview.py` — isolated preview builder for UA-0001..UA-0009 and
  two future-card regression fixtures. Writes only to
  `preview_output/` inside this package.
- `tests/test_ferry_wording.py` — offline acceptance tests (stdlib
  `unittest`).
- `inventory.json` — occurrence inventory (NOT_PROVEN for the real tree;
  documents required classification schema and synthetic example rows).
- `manifest_hashes.json` — before/after hash tracking scaffold for
  protected assets (CRM, generators, live pages, media, UA-0001..0009).
  All protected items are marked `NOT_ACCESSED` because this context has
  no filesystem access to them; hashes must be captured by whoever runs
  the bounded read-only discovery on PythonAnywhere.
- `acceptance_matrix.md` — per-card acceptance matrix (synthetic
  evidence, pending real Gate A).
- `milestone_20.json` .. `milestone_80.json` — progress checkpoints
  actually reached in this run.
- `TASK_042_REPORT.md` — full technical report and UA-0009 decision.
- `rollback_gate_b_plan.md` — rollback/Gate B plan, not executable
  without later exact owner approval.

## How to run offline

```
cd cloud/task_042_ferry_wording
python3 -m unittest tests/test_ferry_wording.py -v
python3 gate_a_preview.py
python3 discover.py            # -> NOT_PROVEN (no real root in this context)
python3 discover.py /real/root # -> real scan, when run on PythonAnywhere
```

## Safety guarantees preserved in this package

- No production write, no CRM write, no `/home/Carix/crm.db` write.
- No live UA-0001..UA-0009 page is edited.
- UA-0009 is not published.
- No WSGI reload, no service restart, no scheduled-task change, no Gate B.
- Internal identifiers (`sea`, `data-stage="sea"`, `?f=sea`) are preserved
  by construction; tests assert this explicitly.
