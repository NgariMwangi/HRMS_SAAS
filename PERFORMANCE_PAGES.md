> Historical documentation for the previous module. The replacement workflow is documented in [APPRAISALS.md](APPRAISALS.md).

# Performance navigation

Performance is a separate sidebar section, alongside Organisation and Payroll. Its pages use the existing role permissions.

- `/app/performance/overview`: current reviews, completion and next tasks.
- `/app/performance/reviews`: create reviews, assign participants, manage review tasks and edit dates. Extra settings stay collapsed.
- `/app/performance/team`: employee reviews with search and optional employee filters.
- `/app/performance/my`: personal goal and review cards for linked employee accounts.
- `/app/performance/improvement-plans`: support plans with structured objective fields, search and follow-ups.
- `/app/performance/reports`: completion, rating distribution, employee results and CSV exports; detailed breakdowns are optional disclosures.
- `/app/performance/notifications`: unread updates and previous messages.
- `/app/performance/settings`: scoring defaults, required steps and employee visibility.
- `/app/performance/rating-scales`, `/competencies`, `/calibration`: focused configuration and rating confirmation pages, linked from Settings.

Employee review records have independent URLs under `/app/performance/appraisals/{id}/goals`, `/check-ins`, `/assessment`, `/results`, `/development`, and `/history`. Back links preserve the originating page and review filter. Existing `/app/performance?appraisal={id}` links redirect to the new record page. Employee accounts continue to use their own portal; deep links preserve the record and section during that redirect.

Data loads are limited to the current page. Existing server permissions and employee/manager scopes remain authoritative. No review records, scoring rules or database schema were changed for this navigation update.
