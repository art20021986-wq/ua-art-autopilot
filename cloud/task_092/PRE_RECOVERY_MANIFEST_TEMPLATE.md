# PRE_RECOVERY_MANIFEST — TEMPLATE (Task 092)

Status: TEMPLATE ONLY — no real production files were accessible in this bridge repository during this round. Fill each row from a verified source export before use.

## 1. Writers / Generators / Tasks inventory (named in task text; verify existence and add any undiscovered ones)

| Component | Claimed role | Verified path | SHA-256 | mtime | size | owner | Confirmed active writer? |
|---|---|---|---|---|---|---|---|
| master_card.py | card/master data generator | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| start_safe.py | startup/publish safety wrapper | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| fitfix.py | fit/layout fix script | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| yadro.py | unknown role — must audit | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| cron jobs | scheduled regeneration/publish | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| (unknown new generators) | to be discovered during inventory | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## 2. Backup/manifest targets

- Data (CRM export / canonical registry): PENDING
- Generators/templates: PENDING
- Production HTML/CSS/JS (as-served snapshot): PENDING
- Media manifests (photo/video/diagnostic asset lists + checksums): PENDING
- Diagnostics assets: PENDING
- Cache/Cloudflare configuration evidence (rules, TTL, purge history): PENDING

## 3. Three-way diff inputs required

1. Last confirmed working design version (design freeze snapshot) — PENDING SOURCE
2. Current production (as-served HTML/CSS/JS) — PENDING SOURCE
3. Current data for the 13 real cars (canonical CRM export) — PENDING SOURCE

## 4. Non-negotiable constraint reaffirmed

Any rollback that would lose UA-0011, UA-0012, UA-0013, any photo, any VIN, any description, or any new content is forbidden regardless of what the diff shows. This constraint is recorded here so it is enforced automatically once real diff data exists.

## Next action to unblock

Owner or ChatGPT/Codex must supply one of:
- a read-only export/zip of the live UA ART site repository + templates + generators,
- a read-only CRM data export (the 13-car canonical registry),
- a read-only PythonAnywhere filesystem listing with hashes,

into this bridge repository (or a retrievable path) so the manifest above can be completed with real values.
