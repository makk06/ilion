# 2026-09-12 main integration

- Saved working implementation: `f5cd27a`; backup branch `codex/backup-before-main-20260912`.
- Incoming main: `556df2e` (recommendation/saved prototype).
- User selected preservation of Home / Companion / Reviews / My tabs, with personalized recommendations as a separate screen.
- Existing API-backed details, maps, guest persistence, reviews, companions and points dashboard remain the primary implementation.
- New recommendation engine and category/preference metadata are combined with the existing integer-ID API Place model. Missing or stale observations are not treated as live measurements.
- Personalized recommendations are available from My page and use paginated actual place data. Ranking describes the loaded candidate set, not every place in the database. No mock weather or distances are introduced.
- Recommendation saving delegates to AppSession; it does not introduce a separate in-memory saved list. The existing saved-places page remains the destination.
- Recommendation preferences persist separately for guests and through the existing account preferences API for authenticated users. Unrelated account settings are preserved.
- The incoming docs/frontend-recommend-saved.md and docs/recommend-saved-decisions.md describe the original prototype; the integration decisions above supersede conflicting architecture notes.
- Secrets remain in ignored backend .env. No push is part of this integration.

Validation: 75 Flutter tests and 73 Django tests passed; Flutter analyze reported no issues; web build passed. Browser confirmed retained tabs, points dashboard and actual API-backed personalized recommendations. Fixed map animation initialization on disposal discovered by full-suite testing.
