# TASK099 — Site + CRM production approval

OWNER_APPROVED: YES
PRODUCTION_AUTHORIZED: YES
CARD_SCOPE: UA-0001..UA-0016
CONTRACT: UA-ART-16-SITE-CRM-COMPLETION-099-V1

Owner instruction received in the current work thread:

> Сейчас у нас 16 карточек исправь. И запускай, пожалуйста, исправление всех невыполненных работ по сайту и CRM немедленно. Качественно и в сроки.

Authorized production sequence is strictly bounded to backup → shadow → data canary evidence →
central CRM/site patch → explicit republish of the 16 already-approved cards → immediate and delayed
public checks → browser-rendered mobile/desktop checks. Primary CRM fields, purchase prices, media files,
card identifiers and publication approvals are protected. Any failed gate requires rollback and must write
`evidence/deploy.json` as `FAIL`; issue #35 must not be closed and no GitHub comment may be posted without
separate owner confirmation.
