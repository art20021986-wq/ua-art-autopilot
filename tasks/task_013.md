# TASK 013 — UNIFIED CARD DIAGNOSTICS + CONTAINER TRACKING RELEASE CANDIDATE

MODE: BUILD_EXACT_RELEASE_CANDIDATE / SANDBOX_FIRST / DEFAULT_DENY / NO_BLIND_PRODUCTION
MAX_ROUNDS: 5

## Owner directive — highest priority

The owner has explicitly written:

`УТВЕРЖДАЮ ПУБЛИКАЦИЮ`

Record this as OWNER_PUBLICATION_INTENT_RECEIVED for the unified-card task. However, TASK 010 security rules remain mandatory: this phrase was received before an exact manifest SHA, verified 100% report, and factual preview URL existed. It MUST NOT be treated as a cryptographically bound Gate B approval for unknown future bytes. Do not reuse it after candidate bytes change. Prepare the exact candidate and evidence automatically, then request only the exact manifest-bound approval required by the installed gate.

Permanent owner authorization also allows Claude-filtered files to be automatically transferred to the PythonAnywhere quarantine/inbox. Quarantine upload is not execution and not production write.

## Business objective

Fix the root cause so every existing and future UA ART vehicle card always has:

1. exactly one visible link/button `Комплексная диагностика`;
2. exactly one visible link/button `Отследить контейнер онлайн`;
3. an internal diagnostics page that exists even with no diagnostics data;
4. an internal tracking/container page that exists even before a container is assigned;
5. truthful empty states, with no fabricated data, no broken links, no black video placeholder, and no per-card manual patching.

Targets:
- existing cards UA-0001 through UA-0008;
- UA-0009 readiness;
- all future UA-0010+ cards through the canonical generator.

## Current externally verified defect

The live UA-0004 page has neither required transition. Some existing cards show diagnostics only when certain data exists. The container transition is not consistently present. This conditional behavior is the defect.

## Non-negotiable safety boundary

This task MUST NOT:
- modify production;
- write CRM or migrate its schema;
- reload/restart WSGI;
- execute anything on PythonAnywhere;
- publish UA-0009;
- manually patch each live HTML card;
- claim a preview was visually checked without a factual reachable URL;
- claim 20/40/60/80/100 without evidence;
- treat the owner's early phrase as Gate B for bytes not yet manifested.

All deliverables must be Claude-authored under `cloud/`. GitHub-to-PythonAnywhere safe-inbox synchronization is allowed after Claude filtering. Actual script execution requires exact Gate A. Production publication requires a later exact Gate B bound to TASK_ID + manifest SHA-256.

## Canonical architecture requirement

Find the likely production generation chain using repository evidence and prior specifications. Produce a single canonical implementation candidate with equivalent operations:

- render diagnostics entry on card;
- render diagnostics page;
- render tracking entry on card;
- render tracking page.

Stable target URLs per card:

- `/video/UA-XXXX.html`
- `/video/UA-XXXX-diag.html`
- `/video/UA-XXXX-track.html`

A future card must automatically produce all three pages. Competing legacy rules that hide, duplicate, or overwrite buttons must be identified in the report. Do not blindly delete or modify production code; prepare a bounded patch/installer with exact allowlists and rollback.

## Diagnostics behavior

On every card, show exactly one `Комплексная диагностика` button regardless of whether diag_text, OBD, photo, video, or on-disk diagnostic files exist.

The internal diagnostics page must always render a truthful state:

- `Проверено` only with verified completed evidence;
- `Материалы добавляются` for partial evidence;
- `Диагностика ожидается` when empty;
- `Уточняется` for an unknown field.

Required empty text:

`Материалы комплексной диагностики готовятся. Они будут добавлены после проверки автомобиля.`

Available blocks must render independently: summary/text, body and safety, OBD/computer diagnostics, photos, diagnostic videos. Missing one block must not hide the page or other blocks.

Never copy data between cards. Never use a main vehicle video as a diagnostic video unless explicitly classified as such and unique. Detect duplicate video bytes with SHA-256.

Every diagnostic video candidate must be validated for:
- real regular non-symlink file;
- non-zero size;
- HTTP/readability evidence when executed later;
- browser-compatible metadata where evidence exists;
- `controls`, `playsinline`, `preload="metadata"`;
- a real poster/fallback so iPhone/Safari does not show a black rectangle before manual play;
- manual play remains the approved behavior;
- separate open-video link;
- no SHA duplicate.

OBD/external links:
- only http/https;
- reject empty, #, javascript:, data:;
- escape HTML special characters correctly;
- if absent, show truthful text rather than hiding the page.

## Tracking/container behavior

On every existing and future card, show exactly one `Отследить контейнер онлайн` button. It must link to the stable internal `UA-XXXX-track.html`, never directly disappear based on stage.

The internal page must show card ID, current stage, route, container number/carrier when present, update time when present, and a return-to-card link.

Truthful states:

- Before container assignment:
  `Автомобиль ещё не передан в контейнер. Номер и онлайн-отслеживание будут добавлены после отправки.`
- Container assigned but number/external link missing:
  `Номер контейнера уточняется. Онлайн-отслеживание станет доступно после обновления данных.`
- Delivered to Kyiv:
  `Доставка завершена. Автомобиль находится в Киеве.`

Only if a real validated http/https carrier URL exists, show an additional external link `Открыть отслеживание перевозчика` with safe target/rel attributes. Never invent or reuse another car's container number or URL.

## Data compatibility

Do not force a risky CRM migration. Implement a compatibility reader/default layer for optional logical fields:

- diagnostics status, summary, body/safety, OBD URL, photos, videos, updated time;
- tracking stage, route, container number, carrier, external URL, updated time.

Escape all values. Accept card IDs only with a strict UA numeric pattern. Prevent path traversal and symlinks. Unknown facts must be NOT_PROVEN or `Уточняется`, never assumed PASS.

## Visual rules

Preserve the approved UA ART card design. Do not redesign photos, pricing, descriptions, stages, navigation, analytics, CRM, or chat.

Both buttons must:
- be readable and visible;
- not be covered by floating WhatsApp;
- have consistent order on all cards;
- not cause horizontal scrolling or overlap;
- pass planned viewport checks at 390, 430, 768, and 1366 px.

Use the existing approved button style. Do not create duplicate dark/gold variants.

## Required Claude deliverables

Create under `cloud/ua_cards_unified/`:

1. `UNIFIED_CARDS_SPEC.md` — exact implementation and compatibility design.
2. `LEGACY_CONFLICT_AUDIT.md` — identify competing known/potential sources such as card generator functions and overwrite jobs; distinguish proven from NOT_PROVEN.
3. `START_UA_CARDS_UNIFIED.py` — one-file Python 3.10 stdlib-only safe launcher/candidate.
4. `PRODUCTION_PATCH_PLAN.md` — exact allowlist, atomic write, backup, rollback, and smoke-test plan; no execution in this task.
5. `TEST_MATRIX.md` — per-card and future-state matrix.
6. `PROGRESS_20.md`
7. `PROGRESS_40.md`
8. `PROGRESS_60.md`
9. `PROGRESS_80.md`
10. `PROGRESS_100.md` only if every GitHub-side/static prerequisite passes; otherwise `BLOCKED.md`.
11. `release_manifest_candidate.json` with exact candidate file SHA-256 values available at authoring time and explicit fields that still require post-commit binding. Never insert fake run IDs, commit SHAs, preview URLs, or PASS values.
12. `OWNER_NEXT_STEP.md` — one-screen Russian instructions for the exact next approval.
13. `cloud_report_013.md`.
14. update `cloud/latest_status.md`.
15. update `cloud/owner_reply.md`.

If practical, also create deterministic preview fixtures under `cloud/ua_cards_unified/preview_fixture/` for:
- UA-0001..UA-0008 representative entry checks;
- UA-0009 with only confirmed data;
- one fully empty future card;
- one fully populated future card.

Fixtures are not production proof and must be labeled as such.

## Launcher restrictions

The launcher must default to dry-run/sandbox. It must never mutate production merely by being executed without exact manifest-bound approvals.

Required controls:
- file lock;
- explicit allowed source and target roots;
- realpath containment;
- reject symlinks;
- CRM read-only if accessed;
- before/after SHA-256 snapshots;
- backup before any future mutable action;
- atomic temporary write + fsync + os.replace;
- zero-byte rejection;
- HTML/link validation;
- ten deterministic sandbox runs;
- rollback test;
- machine-readable receipt;
- no subprocess, shell, eval, exec, dynamic import, package install, arbitrary URL, arbitrary command, or arbitrary path supplied by free-form input.

Any production-capable path must hard-stop unless the trusted separate Gate B record for the exact manifest exists.

## Mandatory test matrix

For UA-0001..UA-0008, UA-0009, empty future card, and full future card, prove or mark NOT_PROVEN:

- one diagnostics button;
- diagnostics page exists;
- correct full/partial/empty state;
- one tracking button;
- tracking page exists;
- correct pre-container/in-transit/delivered state;
- no empty or unsafe href;
- no duplicate buttons;
- mobile structure.

Diagnostics state cases:
- empty;
- text only;
- OBD only;
- photo only;
- video only;
- partial mixed;
- full;
- CRM reference to missing file;
- duplicate video SHA.

Tracking cases:
- Korea/pre-container;
- number but no external URL;
- at sea with valid URL;
- Georgia;
- Kyiv/completed;
- invalid external URL.

## UA-0009 mandatory gate

Use only previously confirmed UA-0009 facts if needed:

- ID UA-0009
- VIN KNAGU416BJA242741
- Kia K5
- year 2018
- fuel gas
- engine 2000
- mileage 300000

Do not invent price, color, transmission, drivetrain, photos, diagnostics, container data, or status.

Final factual report later must contain:

`UA-0009 PUBLICATION READINESS: PASS|FAIL`
`SAFE TO PUBLISH UA-0009: YES|NO`

YES is forbidden without an executed sandbox, real reachable preview, all safety checks PASS, zero unexpected changes to UA-0001..UA-0008, and production untouched before exact Gate B.

## Progress reporting semantics

Do not time-round progress.

- 20%: architecture/conflict audit + baseline design completed.
- 40%: canonical candidate implementation + empty states completed.
- 60%: all current/future fixture cases generated and statically checked.
- 80%: ten deterministic local/sandbox-equivalent runs, rollback/static safety and manifest candidate completed.
- 100%: only after factual external execution evidence and reachable preview exist.

Because this GitHub Claude worker cannot execute PythonAnywhere, it normally MUST stop at 80% with `AWAITING_GATE_A`, not fabricate 100%. The later PythonAnywhere receipt must create the factual 100% report and preview links.

## Owner-facing truth

The current owner message authorizes the team to continue toward publication, but not to bypass the exact-manifest security model. The Russian reply must state:

- work has been launched through the connected GitHub → Claude → PythonAnywhere safe-inbox chain;
- no production write happened yet;
- why the exact manifest-bound Gate A/Gate B phrases are still required;
- the next owner action only after the exact candidate and hashes exist;
- no manual upload of individual files is required.

PRODUCTION_TOUCHED: NO
