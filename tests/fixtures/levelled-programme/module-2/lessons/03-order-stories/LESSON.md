---
id: 03-order-stories
title: Working through the ordering stories
design_refs: [forecast-layout, error-statement]
validators: [has-forecast, explains-error]
teaches: [demand-forecasting, supplier-lead-times]
tasks: stories/
task_states: [specifying, handed-off, implemented, reviewed]
own_tasks: stories/
---

## Purpose

Work through prioritised ordering stories, then cut a use case into stories of your own.

## Learning objectives

- Estimate demand for an item and state how wrong the estimate is likely to be.
- Turn a supplier lead time into the date an order must be placed.

## Theory

A good story is small enough to finish, and its acceptance criteria are checkable. You
have met stories in the previous module; here you write them as well.

## The stories

Work them in priority order, one at a time.

- stories/110-forecast-one-item.md - Forecast one item with its error
- stories/120-order-date-from-lead-time.md - Work out the order date from the lead time
- stories/130-flag-late-orders.md - Flag an order that is already late

## Specifying

Objective: `demand-forecasting`. Write `specs/<story-id>.md` in your workspace. The row
stays in `specifying` while you write it.

Spec criteria:

- [ ] Every acceptance criterion is testable against `forecast.csv`.
- [ ] The error the forecast is allowed is named.
- [ ] The work is split into tasks.

## Handed-off

Objective: `supplier-lead-times`. You hand the spec to an implementation session, work on
a story branch, and open a pull request into your module branch. In this lesson, use the
session's plan mode and read its plan before it starts. The row stays in `handed-off`
until you are back with the pull request.

## Implemented

You return with the pull request. The tutor runs the module's validators and asks about
any change the session made to the spec. The row is `implemented` from here through the
review.

## Reviewed

Objective: `demand-forecasting`. While the row reads `implemented`, walk through the diff
against the acceptance criteria. When that is done and the validators pass the row becomes
`reviewed`. A failing validator sends the story back to `handed-off`.

## Writing a story

Once the stories above are closed, cut this use case into stories of your own in
`stories/` in your workspace: the stockroom must never run out of its five fastest items.
Each story should be:

- [ ] one sentence naming who wants what and why;
- [ ] given acceptance criteria that can be checked;
- [ ] small enough to finish in one session.

## Completion conditions

Every story above is closed, you have written at least one story of your own and closed it,
and you can explain how the error of one forecast was chosen.
