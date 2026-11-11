# Half-day and quarter-day leave

The shared leave application form for HR, employee self-service and platform tenant administration has a duration selector: full day(s), half day (0.5), and quarter day (0.25).

Partial leave is for a single date; the form keeps its end date equal to its start date. Working-day leave still excludes weekends and public holidays. Calendar-day leave retains its existing date rules. Existing approval, balance, identity and overlap checks apply. The form does not assign time slots: overlapping requests for the same date remain blocked.

Balances reserve/use the exact decimal fraction. Request lists display the fraction clearly. No database migration is needed because leave days and balances already use decimal storage.

The HR/self/supervisor creation APIs accept `duration` with `FULL_DAY` (default), `HALF_DAY` or `QUARTER_DAY`. Platform HR creation supports the same input. Full-day date ranges keep their existing calculation.
