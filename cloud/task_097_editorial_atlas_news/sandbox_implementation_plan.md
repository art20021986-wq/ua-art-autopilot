# Next-gate SANDBOX implementation plan (not started; requires a separate owner approval)

## 1. Staged rollout (as fixed by the task)

1. **Read-only audit and registry** — this task (STAGE 0–2). ✅ Complete.
2. **Design prototype** — static, non-executing visual prototype of the components in `design_system_grand_touring.md` (no live data, no public route).
3. **Isolated SANDBOX, not indexed** — a fully separate database/schema, a separate process, `robots: noindex` everywhere, no entry in any public sitemap, no public navigation link, reachable only via a private/staging URL or local rendering — never on `www.uaart.com.ua`'s indexable tree.
4. **Manual MVP on 15 sources** — Ukraine 5 + Georgia 5 + Korea 5, exactly the sources marked `APPROVE_MVP` in `source_registry.csv`, manual-mode only (owner approves every story).
5. **Shadow-autopilot, ≥7 calendar days, zero publication** — autopilot scoring runs and is logged, but the master switch stays OFF; nothing it decides is ever published; used only to tune thresholds against real owner decisions.
6. **Canary** — one safe, non-sensitive category, maximum 1 story/day, still owner-confirmed before the switch could ever auto-publish.
7. **Expansion** — Japan/US/Europe/China sources (currently `APPROVE_LATER`/`PENDING`/`MANUAL_ONLY` per the registry) are added only after their individual PENDING items are resolved.
8. **Production** — only by a separate, explicit owner command, never implied by completion of an earlier stage.

## 2. What Stage 3 ("isolated SANDBOX") concretely requires before it can start

- A dedicated database file/schema for the tables in `data_model_pipeline.md`, created only inside a sandbox environment, never against the production CRM database.
- A dedicated process/workflow (`task_09x_news_sandbox_*` naming, following the repository's existing Gate A/B convention) with its own concurrency group, never sharing `claude_autopilot.yml`'s group or any CRM-bot workflow's triggers.
- Confirmation of the PENDING items in `seo_routing_audit.md` (actual `robots.txt`/`sitemap.xml` content) **before** any sandbox output is ever exposed on a real domain, even under `noindex`.
- A working connector for at least the 15 MVP sources, respecting each one's `access_method` from the registry (mostly SITEMAP/HTML for this MVP slate).

## 3. Kill switch design

- A single boolean, `autopilot_settings.is_enabled`, defaulting to `FALSE`, requiring both a toggle and a separate confirmation action to become `TRUE` (see the wireframe in `information_architecture_and_wireframes.md` §6).
- A second, independent boolean at the publisher level, `NEWS_PUBLISHING_ENABLED` (an environment/config flag, not a database row), which must also be `TRUE` for the `NEWS PUBLISHER` stage to ever flip any `news_publications` row to public — so a single flag flip (no deploy required) can freeze all publication instantly, independent of the autopilot switch.
- Both switches are owner-controlled and are never set by any Cloud-authored code without an explicit, separately-approved instruction.

## 4. Rollback plan

- Every SANDBOX code change ships as a normal, revertible Git commit under `cloud/`, following the repository's existing pattern.
- If a sandbox run misbehaves, `NEWS_PUBLISHING_ENABLED = FALSE` freezes all publication instantly; the underlying sandbox database can be dropped/recreated without touching any CRM/catalog table, because it is fully separate.
- No rollback plan in this task touches `master_card.py`, `stranica.py`, any CRM table, or any file under `/home/Carix/video` or `/home/Carix/site`.

## 5. Idempotency, retry, dead-letter (cross-reference)

See `data_model_pipeline.md` §5 and `risk_register.md` #11 — bounded exponential backoff, hard attempt caps, and a durable `failed_jobs` dead-letter table are required before Stage 3 can be considered safe to run unattended even inside the sandbox.

## 6. What this task explicitly requests from the owner

Nothing right now. When Stage 3 is proposed as a concrete, buildable change, it will be presented separately, with its own scoped diff, for explicit owner approval — consistent with the "PRODUCTION — ТОЛЬКО ПО ОТДЕЛЬНОЙ КОМАНДЕ" instruction governing this entire initiative.
