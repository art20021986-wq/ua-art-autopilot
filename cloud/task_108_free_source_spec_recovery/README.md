# TASK108 — free-source additional specification recovery

Status: **isolated branch / remediation in progress**. Production, live CRM, public paths and services are untouched.

This package replaces the false-positive behaviour discovered in TASK096/TASK099: a processed card with zero accepted facts can no longer receive `PASS`, and repeated labels such as two rows named «Высота» are collapsed by canonical semantic code before rendering.

## What is included

- immutable evidence snapshot for all 16 current cards;
- explicit source/access policy with no paid API and no Russian sites;
- integrity-checked source claim snapshots: a URL alone can never confirm a fact;
- deterministic consensus and conflict quarantine;
- denylist for every primary CRM, commercial, history, option, media and logistics field;
- server-rendered `<details>` block plus `Vehicle.additionalProperty` JSON-LD;
- canary fixtures for UA-0005/UA-0015 plus shared, VIN-type-bound W245 data for UA-0002/UA-0007/UA-0008;
- strict publication gate, including the special UA-0009 gate;
- ten-run determinism proof and standard-library tests.

## Live baseline — 2026-09-03

- Homepage and catalog agree: 16 total / Kyiv 3 / Georgia 1 / ferry 8 / Korea 4.
- All five catalog filters and all 16 public card URLs work.
- Fifteen cards render an empty «0 parameters» shell; only UA-0015 has 12 current rows.
- UA-0005 exposes two CRM editor prompts inside the customer description.
- The legacy TASK099 renderer, visual gate, finalizer and pre-write shadow gate are hardened on this branch so none of those states can pass again.
- UA-0012, UA-0014 and UA-0016 contain operator-owned values that require operator review; TASK108 records but never changes them.

## Run locally

```bash
cd cloud/task_108_free_source_spec_recovery
python -m unittest discover -s tests -v
python run_canary.py
```

`run_canary.py` only reads package fixtures and writes package evidence/previews. It contains no production path, DB credential, deploy command or service restart. The current suite contains 32 tests.

## Interpretation

- `CANARY_PASS` means that the isolated transformation and renderer passed their checks.
- `REVIEW_REQUIRED` means an operator must resolve identity/source conflicts.
- neither status authorizes publication;
- the only publishable state is a future, separately authorised transaction whose strict gate is `PASS` for every target card.

## Source model

Runtime automatic access is limited to explicitly allowed, free official endpoints. Pages whose rules are unclear, forbid automated processing or return a bot block are represented only by manually verified fact snapshots; the package never crawls them. Source URLs and evidence timestamps are stored internally but not rendered in the public component.

Every enrichment source now points to a canonical evidence JSON file and its SHA-256. A candidate fact is accepted only when two distinct allowed domains each contain the exact semantic code, value, unit and note. The inaccessible Automobile Catalog page and the conflict-only Danawa page are explicitly disabled for enrichment.

The source evidence must also match the bundle identity: brand, model, year/range, engine size, fuel, gearbox and—where the manufacturer exposes it—the factory VIN type prefix. Shared fact sets are immutable and reject inline overrides.
