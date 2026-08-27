# Operator Instructions — UA Cards Unified Gate A (TASK 021)

## Scope

This package performs Gate A only: bounded read-only discovery of exact
hardcoded candidate paths, an isolated preview transform written only
under `/home/Carix/video/reports/ua_cards_unified/`, and a read-only
CRM evidence check for UA-0009. It never writes to a live card,
generator, or database, never reloads the web app, and never runs
Production Gate B.

## What this GitHub round did

This round only authored and statically reviewed code inside this
repository. No PythonAnywhere command was executed by this round. No
preview was generated on the live filesystem. No claim is made about
live HTTP reachability.

## Exact one-line PythonAnywhere Bash command (documented only, NOT executed here)

```
cd /home/Carix && python3 -m ua_cards_unified.launcher
```

This command must only be run manually by the owner/operator on
PythonAnywhere after this package has been reviewed and after the
owner explicitly authorizes a Gate A execution attempt. Running it:

- performs discovery only against the exact hardcoded candidate paths
  listed in `common.py`;
- writes only under the two allowlisted report/preview roots;
- never touches production cards, generators, the WSGI process, or
  scheduled tasks;
- produces a `gate_a_receipt.json` under the report root with hashes.

## Preconditions before any real execution

1. The full offline unittest suite must pass:
   `python3 -m unittest discover -s cloud/ua_cards_unified/tests -t cloud`
2. A manifest must be built via `manifest_builder.build_manifest(...)`
   with real discovered input hashes recorded before execution.
3. The owner must explicitly authorize the Gate A attempt.

## What this package will never do

- No `--apply`, arbitrary-root, arbitrary-output, production, reload,
  or database-write flag exists.
- No recursive filesystem scan of `/home/Carix`.
- No synthetic substitution for UA-0001..UA-0008.
- No publication of UA-0009 based on CRM presence alone.
