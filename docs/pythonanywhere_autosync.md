# UA ART — Claude -> GitHub -> PythonAnywhere automatic file handoff

## What is automated

1. Owner/ChatGPT creates the newest task under `tasks/`.
2. `Claude Autopilot` GitHub Action calls the Anthropic API.
3. Claude API worker writes complete deliverables under `cloud/` and commits them to `main`.
4. `PythonAnywhere Inbox Sync` starts automatically on every `cloud/**` change.
5. The sync uploads all supported `cloud/` files to the safe PythonAnywhere inbox:
   `/home/Carix/autopilot_inbox/cloud/...`
6. A manifest is uploaded to:
   `/home/Carix/autopilot_inbox/_sync_manifest.json`

The transfer is automatic after one repository secret is configured.

## One-time owner setup

### 1. Get the PythonAnywhere API token

PythonAnywhere -> Account -> API token -> create/copy token.

Do not send the token in chat and do not put it in repository files.

### 2. Put it into GitHub Actions Secrets

Repository `art20021986-wq/ua-art-autopilot` -> Settings -> Secrets and variables -> Actions -> Secrets -> New repository secret.

Name exactly:

`PYTHONANYWHERE_API_TOKEN`

Value: the PythonAnywhere API token.

Save with `Add secret`.

### 3. First run

GitHub repository -> Actions -> `PythonAnywhere Inbox Sync` -> `Run workflow` -> branch `main` -> `Run workflow`.

Expected result: green `Success`.

### 4. Confirm on PythonAnywhere

Open Files and go to:

`/home/Carix/autopilot_inbox/cloud/`

Claude-generated files should be present there. The transfer manifest is:

`/home/Carix/autopilot_inbox/_sync_manifest.json`

## Safety boundary

This automation uploads files only to `/home/Carix/autopilot_inbox/`.

It does NOT:

- execute Claude-generated Python;
- overwrite `/home/Carix/master_card.py`, `stranica.py`, CRM or existing production files;
- reload the web application;
- publish UA-0009 or any other card.

This is intentional: automatic transport is safe; production execution remains a separate gated step.

## Running the current UA-0009 gate after sync

After automatic sync, the current file is available at:

`/home/Carix/autopilot_inbox/cloud/uaart_card_factory_gate.py`

Manual safe run for UA-0009:

`python3.10 /home/Carix/autopilot_inbox/cloud/uaart_card_factory_gate.py UA-0009`

When a stable allowlisted remote runner is approved, this final execution step can be automated separately without giving arbitrary Claude output direct production execution rights.
