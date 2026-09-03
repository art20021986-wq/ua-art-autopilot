# TASK108 — free-source additional specification recovery

Status: **isolated branch / sandbox only**. Production, live CRM, public paths and services are untouched.

This package replaces the false-positive behaviour discovered in TASK096/TASK099: a processed card with zero accepted facts can no longer receive `PASS`, and repeated labels such as two rows named «Высота» are collapsed by canonical semantic code before rendering.

## What is included

- immutable evidence snapshot for all 16 current cards;
- explicit source/access policy with no paid API and no Russian sites;
- deterministic consensus and conflict quarantine;
- denylist for every primary CRM, commercial, history, option, media and logistics field;
- server-rendered `<details>` block plus `Vehicle.additionalProperty` JSON-LD;
- canary fixtures and previews for UA-0005 and UA-0015;
- strict publication gate, including the special UA-0009 gate;
- ten-run determinism proof and standard-library tests.

## Run locally

```bash
cd cloud/task_108_free_source_spec_recovery
python -m unittest discover -s tests -v
python run_canary.py
```

`run_canary.py` only reads package fixtures and writes package evidence/previews. It contains no production path, DB credential, deploy command or service restart.

## Interpretation

- `CANARY_PASS` means that the isolated transformation and renderer passed their checks.
- `REVIEW_REQUIRED` means an operator must resolve identity/source conflicts.
- neither status authorizes publication;
- the only publishable state is a future, separately authorised transaction whose strict gate is `PASS` for every target card.

## Source model

Runtime automatic access is limited to explicitly allowed, free official endpoints. Pages whose rules are unclear, forbid automated processing or return a bot block are represented only by manually verified fact snapshots; the package never crawls them. Source URLs and evidence timestamps are stored internally but not rendered in the public component.
