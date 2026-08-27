# OPERATOR_INSTRUCTIONS.md — CRM-SPEED-001 (Task 024 correction)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What this package is

A corrected, offline-authored candidate implementation plus a fail-closed
Gate A runner for CRM-SPEED-001. Nothing in this package has been
installed into production. `PRODUCTION_TOUCHED: NO`, `CRM_TOUCHED: NO`,
`GATE_A_EXECUTED: NO`, `UA_0009_PUBLISHED: NO`.

## Step 1 — run the offline behavioral test suite (recommended first)

```
cd cloud/crm_speed_optimization
python3 -m py_compile *.py
python3 -m unittest -v test_crm_speed_gate_a.py
```

Repeat the unittest run at least 10 full times and confirm every run is
all-green before proceeding. This step touches only temporary directories
created by the OS `tempfile` module and independent `python3 -c` helper
subprocesses; it never touches `/home/Carix`.

## Step 2 — configure the UA-0009 fail-closed probe (required before Gate A)

Gate A will BLOCK, not silently pass, if no canonical UA-0009 URL is
configured. Set exactly one of:

* environment variable `UA0009_CANONICAL_URL=https://<real-canonical-url>`
* a JSON file at `cloud/crm_speed_optimization/config/ua0009_endpoint.json`
  with `{"ua0009_canonical_url": "https://<real-canonical-url>"}`

Do not guess this value. Obtain it from the owner-approved task contract.

## Step 3 — run Gate A on PythonAnywhere (owner-authorized, read-only against production)

```
cd /home/Carix
python3 cloud/crm_speed_optimization/RUN_GATE_A_CRM_SPEED.py
```

Gate A only reads the bounded input list from `/home/Carix` and writes
exclusively beneath `/home/Carix/qa/crm_speed_task020/<run_id>/`. It never
restarts any process, never writes to `/home/Carix` outside the QA root,
and never publishes UA-0009.

The process exits `0` only when `final_status` is
`GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`; any `BLOCKED` outcome exits
nonzero with exact reasons recorded in `receipt.json` under `blockers`.

## Step 4 — independently verify the receipt

```
python3 cloud/crm_speed_optimization/verify_gate_a.py /home/Carix/qa/crm_speed_task020/<run_id>
```

## What a PASS means and does not mean

A `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` result means the *candidate
copies* in the QA run directory satisfy every fail-closed proof. It does
**not** mean production has been changed, the CRM bot has been restarted,
or UA-0009 has been published. Installing the candidate into production is
a separate Gate B decision requiring independent review and explicit
owner approval.
