# Editorial policy — Ukrainian and Russian versions (specification only, not yet built)

## 1. Core principle

UA ART's future news module is an **independent editorial desk**, not a translator or an aggregator. Facts are captured once, in a neutral, language-agnostic "fact card" tied to one STORY ID. The Ukrainian and Russian articles are then **each independently written** from that fact card, answering the same central question:

> What happened, and what does it mean for a person in Ukraine who is choosing, buying, shipping, clearing customs for, registering, or operating a car?

Word-for-word machine translation between UA and RU is prohibited. Mixed-language text is prohibited. The two language versions must reach the **same factual conclusion**, in **natural, separately-edited prose** for each language.

## 2. STORY ID and URL model

- One real-world event = one STORY ID, regardless of how many sources or languages reported it.
- Each STORY ID has exactly two public URLs when published: one Ukrainian, one Russian.
- Each URL is **self-canonical** (its `<link rel="canonical">` points to itself, not to the other language).
- The two URLs carry **reciprocal** `hreflang="uk"` and `hreflang="ru"` link tags pointing at each other.
- Both language versions share: `datePublished`, the same set of numbers (dates, amounts, percentages, document numbers), the same source list, and the same factual conclusion.
- Updating a story updates the existing URLs' facts, sources, and `dateModified`; it never creates a third URL or a duplicate STORY ID.
- A visible correction log is attached to the Story Dossier component (see `design_system_grand_touring.md`) whenever a published fact is corrected.

## 3. Manual mode workflow (the only mode enabled at this stage)

For every fact card the system prepares, the owner sees, at minimum:

1. UA headline and RU headline.
2. Short description (both languages).
3. "Why this matters to the client" (both languages).
4. Country and category/rubric.
5. Event date and detection date.
6. NEWS SCORE (see `dedup_scoring_autopilot.md`).
7. Fact confidence, duplicate probability, text originality.
8. Source list with click-through links.
9. Proposed UA and RU URLs.
10. Image and its rights status.
11. Buttons: **ОПУБЛИКОВАТЬ**, **УДАЛИТЬ**, plus **ОТЛОЖИТЬ** and **АУДИТ**.

No automatic publication occurs in manual mode. The owner's click is the only trigger.

## 4. Future autopilot (specified, disabled)

Autopilot is a separate, explicitly-toggled mode that the owner must turn on and confirm. Even when on, it may only auto-publish a story classified as TOP NEWS (NEWS SCORE 85–100) that also passes every protective gate defined in `dedup_scoring_autopilot.md`. Any story in a sensitive category (see §6) always goes to the owner, never to autopilot, regardless of score. **Autopilot is not enabled by this task and is not enabled by any future task without a separate, explicit owner toggle-and-confirm action.**

## 5. Editorial prohibitions (binding on both languages)

The future system must never:

- Translate and publish someone else's full article.
- Rewrite paragraph-by-paragraph with synonym substitution.
- Copy images without a confirmed right to use them.
- Publish a rumor as a fact.
- Publish a legal/regulatory claim without an official primary source.
- Create more than one public URL for the same event.
- Publish a local traffic accident without a demonstrable transport/import/client impact.
- Pull in motorsport results, crime blotters, promotional press releases, or entertainment content unless it has a clear business connection (import, export, logistics, registration, market, safety).
- Present UA ART's own editorial conclusion as if it were the source's own statement.
- Invent a deadline, price, or impact that is not supported by the fact card.

## 6. Sensitive categories — mandatory-manual, official-source-required, at every stage

Regardless of NEWS SCORE, the following categories are never eligible for autopilot and always require an official primary source before publication:

- Taxes, duties, customs clearance, mandatory payments.
- Import/export bans.
- Registration and certification.
- Court rulings and formal accusations.
- Model safety and mass recalls.
- Fatalities and injuries.
- Sanctions and bankruptcies.

## 7. Correction and versioning workflow

- Every published fact card is versioned; corrections are appended to an immutable audit log (`news_audit_log`, see `data_model_pipeline.md`), never silently overwritten.
- `dateModified` changes on every correction; `datePublished` never changes.
- The Story Dossier component always shows "last updated" and links to the correction history.

## 8. Tone and voice (EDITORIAL GRAND TOURING)

- Calm, precise, premium — never clickbait, never alarmist, never a bare translation of a press release.
- Every headline states what happened and, where established, why it matters to a client — not a vague teaser.
- Numbers are only ever stated when the fact card actually contains them; qualitative language ("may increase", "currently under review") is used when the fact card does not contain a precise figure.
