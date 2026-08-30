# Deduplication, NEWS SCORE, and autopilot eligibility (specification only — autopilot remains OFF)

## 1. Cross-language deduplication signals

Each incoming `source_item` is compared against existing `news_stories` using, in order of confidence:

1. Normalized URL and any declared `canonical` URL.
2. RSS/Atom item GUID/ID.
3. A content hash of the extracted text.
4. A normalized headline (lower-cased, punctuation-stripped, stop-words removed).
5. Extracted entities: organizations, countries, cities, ports, brands, models.
6. Extracted structured facts: dates, amounts, percentages, document numbers.
7. Semantic similarity (embedding-based).
8. Cross-language semantic similarity (for matching a Korean-language item to an English-language item about the same event).
9. A temporal window around the event date (events reported days apart are less likely to be the same story unless entities/facts strongly match).

### Merge bands

| Combined similarity | Action |
|---|---|
| 95–100% | Automatically merge into the same STORY ID |
| 85–94% | Treat as a probable update to the same STORY ID; a human/editorial-engine check confirms before merging |
| 70–84% | Related event; needs explicit classification (same story vs. a genuinely new, related story) |
| below 70% | Treated as a separate candidate |

Updating an existing story never creates a second URL: facts, sources, and `dateModified` are updated; `datePublished` and both URLs stay fixed; every change is appended to `news_audit_log`.

## 2. NEWS SCORE (0–100)

```
NEWS_SCORE =
 0.20 * client_usefulness +
 0.15 * business_relevance +
 0.15 * source_reliability +
 0.15 * fact_confidence +
 0.10 * timeliness +
 0.10 * novelty +
 0.10 * potential_impact +
 0.05 * search_potential
```

Each component is scored 0–100 before weighting:

- **client_usefulness** — does this change what a Ukrainian buyer/importer should do or expect? (0 = irrelevant, 100 = directly actionable)
- **business_relevance** — proximity to UA ART's stated priorities (import/export/auctions/logistics/ports/containers/law/registration/customs/market/EV-PHEV-Hybrid-LPG/safety/recalls; countries UA/KR/GE/JP/US/EU/CN)
- **source_reliability** — derived from `SOURCE_CONFIDENCE` (below)
- **fact_confidence** — derived from `FACT_CONFIDENCE` (below)
- **timeliness** — how recent the underlying event is relative to detection
- **novelty** — genuinely new information vs. a repeat of already-published facts
- **potential_impact** — scale of the effect (one model vs. an entire market; one buyer vs. an entire import corridor)
- **search_potential** — realistic organic-search relevance, never used to justify inventing content

### Publication bands

| NEWS SCORE | Outcome |
|---|---|
| 0–49 | Reject |
| 50–69 | Candidate archive (kept, not shown to the owner as an action item) |
| 70–84 | Owner approval queue |
| 85–100 | TOP NEWS (only band eligible for future autopilot, subject to §4) |

## 3. Supporting confidence metrics

- **SOURCE_CONFIDENCE (0–100).** Baseline by class: A≈90–100, B≈70–89, C≈50–69, adjusted down for any source currently blocked, challenged, or unverified per `source_registry.csv`, and adjusted up over time only by a documented accuracy track record (not implemented yet).
- **FACT_CONFIDENCE (0–100).** Increases with the number of independent corroborating sources, presence of a primary/official source for sensitive categories, and presence of direct quotes/structured data; a single-source claim about a sensitive category caps this low.
- **DUPLICATE_PROBABILITY (0–100%).** Output of the dedup pipeline in §1; low is good.
- **TEXT_ORIGINALITY (0–100%).** Overlap-distance between the generated UA/RU text and any source text (n-gram/embedding overlap); target ≥90% for autopilot eligibility, always computed per language.
- **LEGAL_RISK (NONE/LOW/MEDIUM/HIGH).** HIGH automatically for any of the sensitive categories in `editorial_policy_ua_ru.md` §6, regardless of score.
- **IMAGE_RIGHTS_CONFIDENCE (0–100).** Defaults to 0/UNKNOWN unless an explicit, recorded right to use the specific image is confirmed (owned, licensed, or clearly-marked reusable); never assumed from reachability.
- **UA_QUALITY / RU_QUALITY (0–100 each).** Independent language QA: grammar, natural phrasing, and factual parity with the neutral fact card (not with each other directly, but both must match the fact card).

## 4. AUTOPILOT_ELIGIBLE (boolean gate — specification only, feature remains disabled)

```
AUTOPILOT_ELIGIBLE = (
 NEWS_SCORE >= 85 AND
 FACT_CONFIDENCE >= 92 AND
 SOURCE_CONFIDENCE >= 85 AND
 DUPLICATE_PROBABILITY < 15 AND
 TEXT_ORIGINALITY >= 90 AND
 IMAGE_RIGHTS_CONFIDENCE == CONFIRMED AND
 source_is_currently_reachable AND
 UA_QUALITY_pass AND RU_QUALITY_pass AND
 LEGAL_RISK == NONE
)
```

Even when `AUTOPILOT_ELIGIBLE` is true, the master autopilot switch (see `sandbox_implementation_plan.md`) must independently be ON and owner-confirmed for any autopublication to occur. At this stage, the switch does not exist in any deployed system, so no autopublication can occur under any circumstance.

## 5. Explicit non-goal for this task

No scoring code, no dedup code, and no autopilot toggle were deployed anywhere by this task. This document is the specification to be implemented in a later, separately-approved SANDBOX/production step.
