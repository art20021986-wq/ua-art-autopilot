# Data model and pipeline (specification only, not deployed)

## 1. Isolation principle

The NEWS module must have its **own** database file/schema, its **own** lock, and its **own** queue. It must never write to any CRM/catalog table, never use a car's ID as a NEWS ID, and a failure inside the NEWS pipeline must never be able to stop, lock, or slow the CRM.

## 2. Pipeline stages

```
NEWS SCHEDULER -> SOURCE CONNECTORS -> INGESTION -> NEWS DB -> DEDUP -> FACT CHECK
 -> EDITORIAL ENGINE -> APPROVAL QUEUE -> NEWS PUBLISHER
```

- **NEWS SCHEDULER** — triggers each connector at its class-appropriate interval (class A: 10–15 min: class B: 20–30 min; class C: 45–60 min), independent of any CRM cron/queue.
- **SOURCE CONNECTORS** — one per source, each respecting `source_registry.csv`'s `access_method` (API → RSS → sitemap → HTML → browser-last-resort), each rate-limited and robots.txt-aware.
- **INGESTION** — normalizes a fetched item into a `source_items` row; stores only what is technically necessary (headline, short excerpt/metadata, structured facts extracted, link), never a full copy of the source article body beyond the minimum needed for fact-checking, and only for as long as technically necessary.
- **NEWS DB** — the durable store for all of the above; isolated schema (see §3).
- **DEDUP** — computes the merge bands from `dedup_scoring_autopilot.md` §1 and assigns/merges a STORY ID.
- **FACT CHECK** — computes `FACT_CONFIDENCE`, `SOURCE_CONFIDENCE`, `LEGAL_RISK`; flags sensitive categories.
- **EDITORIAL ENGINE** — drafts the neutral fact card, then separately drafts the UA and RU articles from it; computes `TEXT_ORIGINALITY`, `UA_QUALITY`, `RU_QUALITY`.
- **APPROVAL QUEUE** — holds every candidate for the owner (manual mode) or for the eligibility gate (future autopilot, disabled).
- **NEWS PUBLISHER** — the only component allowed to flip a story from draft to public, and only via the atomic bilingual transaction in §4.

## 3. Core tables (minimum set)

```sql
-- Registry of allowed sources; mirrors source_registry.csv, machine-managed.
CREATE TABLE news_sources (
 source_id TEXT PRIMARY KEY,
 geo TEXT NOT NULL,
 source_class TEXT NOT NULL CHECK (source_class IN ('A','B','C')),
 primary_language TEXT NOT NULL,
 access_method TEXT NOT NULL,
 poll_interval_minutes INTEGER NOT NULL,
 decision TEXT NOT NULL,
 is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL
);

-- Raw ingested items, one per fetched source item, immutable snapshot.
CREATE TABLE source_items (
 item_id TEXT PRIMARY KEY,
 source_id TEXT NOT NULL REFERENCES news_sources(source_id),
 external_id TEXT, -- RSS guid / API id, if any
 url_hash TEXT NOT NULL, -- idempotency key
 normalized_url TEXT NOT NULL,
 fetched_at TIMESTAMPTZ NOT NULL,
 event_date DATE,
 headline_raw TEXT,
 excerpt_raw TEXT, -- minimum excerpt only, never full body beyond fact-check need
 content_hash TEXT NOT NULL,
 story_id TEXT REFERENCES news_stories(story_id),
 UNIQUE (source_id, external_id),
 UNIQUE (source_id, url_hash)
);

-- One row per real-world event.
CREATE TABLE news_stories (
 story_id TEXT PRIMARY KEY,
 first_detected_at TIMESTAMPTZ NOT NULL,
 event_date DATE,
 category TEXT NOT NULL,
 is_sensitive_category BOOLEAN NOT NULL DEFAULT FALSE,
 news_score NUMERIC,
 fact_confidence NUMERIC,
 source_confidence NUMERIC,
 duplicate_probability NUMERIC,
 legal_risk TEXT NOT NULL DEFAULT 'NONE' CHECK (legal_risk IN ('NONE','LOW','MEDIUM','HIGH')),
 status TEXT NOT NULL DEFAULT 'CANDIDATE'
 CHECK (status IN ('CANDIDATE','ARCHIVED','OWNER_QUEUE','TOP_NEWS','PUBLISHED','DELETED')),
 created_at TIMESTAMPTZ NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL
);

-- Many-to-many: which source_items corroborate which story.
CREATE TABLE story_sources (
 story_id TEXT NOT NULL REFERENCES news_stories(story_id),
 item_id TEXT NOT NULL REFERENCES source_items(item_id),
 similarity_score NUMERIC,
 PRIMARY KEY (story_id, item_id)
);

-- One row per (story_id, language); language pair is unique per story.
CREATE TABLE news_translations (
 translation_id TEXT PRIMARY KEY,
 story_id TEXT NOT NULL REFERENCES news_stories(story_id),
 language TEXT NOT NULL CHECK (language IN ('uk','ru')),
 headline TEXT NOT NULL,
 short_description TEXT NOT NULL,
 why_it_matters TEXT NOT NULL,
 body TEXT NOT NULL,
 text_originality NUMERIC,
 quality_score NUMERIC,
 version INTEGER NOT NULL DEFAULT 1,
 is_draft BOOLEAN NOT NULL DEFAULT TRUE,
 created_at TIMESTAMPTZ NOT NULL,
 updated_at TIMESTAMPTZ NOT NULL,
 UNIQUE (story_id, language)
);

-- Publication record: URL, canonical, hreflang pairing, publish/unpublish state.
CREATE TABLE news_publications (
 publication_id TEXT PRIMARY KEY,
 story_id TEXT NOT NULL REFERENCES news_stories(story_id),
 language TEXT NOT NULL CHECK (language IN ('uk','ru')),
 public_url TEXT NOT NULL UNIQUE,
 canonical_url TEXT NOT NULL,
 hreflang_partner_url TEXT,
 is_public BOOLEAN NOT NULL DEFAULT FALSE,
 date_published TIMESTAMPTZ,
 date_modified TIMESTAMPTZ,
 is_indexable BOOLEAN NOT NULL DEFAULT FALSE,
 soft_deleted_at TIMESTAMPTZ,
 UNIQUE (story_id, language)
);

-- Owner-facing manual workflow state.
CREATE TABLE approval_queue (
 queue_id TEXT PRIMARY KEY,
 story_id TEXT NOT NULL REFERENCES news_stories(story_id),
 presented_at TIMESTAMPTZ NOT NULL,
 owner_action TEXT CHECK (owner_action IN ('PUBLISH','DELETE','DEFER','AUDIT', NULL)),
 owner_action_at TIMESTAMPTZ,
 owner_action_by TEXT
);

-- Single-row (or single-active-row) master switch; disabled by default.
CREATE TABLE autopilot_settings (
 setting_id TEXT PRIMARY KEY DEFAULT 'GLOBAL',
 is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
 enabled_by TEXT,
 enabled_at TIMESTAMPTZ,
 confirmed_at TIMESTAMPTZ,
 min_news_score NUMERIC NOT NULL DEFAULT 85,
 min_fact_confidence NUMERIC NOT NULL DEFAULT 92,
 min_source_confidence NUMERIC NOT NULL DEFAULT 85,
 max_duplicate_probability NUMERIC NOT NULL DEFAULT 15,
 min_text_originality NUMERIC NOT NULL DEFAULT 90
);

-- Immutable append-only audit trail: every state change, every correction.
CREATE TABLE news_audit_log (
 log_id TEXT PRIMARY KEY,
 story_id TEXT REFERENCES news_stories(story_id),
 actor TEXT NOT NULL, -- e.g. 'SYSTEM:DEDUP', 'OWNER', 'SYSTEM:FACT_CHECK'
 action TEXT NOT NULL,
 before_snapshot JSONB,
 after_snapshot JSONB,
 created_at TIMESTAMPTZ NOT NULL
);

-- Bounded-retry failures, never an infinite loop, never silently dropped.
CREATE TABLE failed_jobs (
 job_id TEXT PRIMARY KEY,
 job_type TEXT NOT NULL, -- 'FETCH','DEDUP','TRANSLATE','PUBLISH', etc.
 reference_id TEXT, -- item_id or story_id
 attempt_count INTEGER NOT NULL DEFAULT 1,
 last_error TEXT,
 next_retry_at TIMESTAMPTZ,
 moved_to_dead_letter_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL
);
```

## 4. Atomic bilingual publish

1. Both `news_translations` rows (uk, ru) and both `news_publications` rows are created/updated with `is_public = FALSE`, `is_indexable = FALSE`.
2. A validation pass checks: both languages exist, both pass quality/originality thresholds, canonical/hreflang pairing is correct, sources exist and are non-empty, image rights are confirmed if an image is attached.
3. If validation passes for **both** languages, a single transaction flips both `news_publications` rows to `is_public = TRUE`, `is_indexable = TRUE`, sets `date_published` (first publish only) and `date_modified`.
4. If validation fails for **either** language, neither row is made public — the whole publish action rolls back, and the failure is logged to `news_audit_log`.
5. Draft/candidate rows are never included in the news sitemap, RSS, search index, or public navigation — enforced by the `is_indexable`/`is_public` flags being the single source of truth read by any sitemap/feed generator.

## 5. Idempotency and retry

- Natural idempotency keys: `(source_id, external_id)` and `(source_id, url_hash)` on `source_items`; `(story_id, language)` on `news_translations`/`news_publications`.
- Retries use bounded exponential backoff (`failed_jobs.attempt_count`, `next_retry_at`); once a configured max attempt count is exceeded, the job is moved to dead-letter (`moved_to_dead_letter_at`) and requires manual review — never retried forever.
- No source text beyond the minimum needed for fact-checking is retained longer than technically necessary; `source_items.excerpt_raw` is bounded in size and is not the published text.

## 6. Explicit non-goal for this task

No DDL above was executed against any real database, sandbox or otherwise. This is a schema specification for a later, separately-approved SANDBOX step.
