---
tutorial_id: stockroom-forecasting
active_lesson: lessons/03-order-stories/LESSON.md
status: in-progress
updated: 2026-11-03
---

## Last completed task

Story `110-forecast-one-item` reviewed: `forecast.csv` has a row for the item with a demand
estimate and its likely error, the pull request is merged, and the validators pass.

## Concepts demonstrated

- `demand-forecasting`: estimated demand for one item and stated the likely error.
- `supplier-lead-times`: subtracted a lead time to get an order date.

## Decisions made in discussion

None yet.

## Known intentional or incomplete state

Story `120-order-date-from-lead-time` is being implemented on branch story-120, so its
acceptance criteria are not met yet, on purpose.

## Accepted warnings

None.

## Next task

Come back from the implementation session with the pull request for
`120-order-date-from-lead-time`, and work through the *Implemented* section.

## Deferred items

None.

## Assessments

- `lessons/01-placement.md` — passed — last taken 2026-10-21, attempt 1

## Levels

- `stock-counting` — B — placement 2026-10-01
- `demand-forecasting` — A — learner 2026-11-03
- `supplier-lead-times` — B — placement 2026-10-21

## Modules

- `stockroom-basics` — complete 2026-10-20 — branch module-1-complete; the sheet was left with 12 items

## Tasks

- `110-forecast-one-item` — reviewed — pull request merged 2026-11-03
- `120-order-date-from-lead-time` — handed-off — in the implementation session, branch story-120, 2026-11-03
- `130-flag-late-orders` — skipped — 2026-11-03 (this stockroom has no order deadlines yet, so nothing can be late)
