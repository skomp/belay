---
id: 03-shelf-stories
title: Working through the shelf stories
design_refs: [counting-rule, sheet-layout]
validators: [has-sheet, explains-count]
teaches: [shelf-labelling, reorder-points]
tasks: stories/
task_states: [specifying, handed-off, implemented, reviewed]
---

## Purpose

Work through a short, prioritised list of stockroom stories, one at a time: write down
what is wanted, have the change made, then check that it did what was asked.

## Learning objectives

- Label shelves so a count names where it was taken.
- Pick a reorder point for an item and say what it protects against.

## Theory

A story says who wants something and why. The acceptance criteria say how anyone would
know it was done. Writing those down before the work starts is what lets a second person
check the result.

## The stories

Work them in priority order, one at a time.

- stories/010-label-the-shelves.md - Label every shelf
- stories/020-count-by-label.md - Record each count against its label
- stories/030-set-reorder-points.md - Give each item a reorder point

## Specifying

Objective: `shelf-labelling`. Write `specs/<story-id>.md` in your workspace for the story
being worked. The row stays in `specifying` while you write it.

Spec criteria:

- [ ] Every acceptance criterion can be checked by looking at `stockroom.csv`.
- [ ] A limit the story implies, such as a maximum label length, is named.
- [ ] The work is split into steps small enough to finish in one sitting.

## Handed-off

Objective: `reorder-points`. You make the change to the sheet from your spec, on a branch
named for the story, and open a pull request into your module branch. The row stays in
`handed-off` until you are back with the pull request.

## Implemented

You return with the pull request. The tutor runs the module's validators and asks whether
the change altered the spec. The row is `implemented` from here through the review.

## Reviewed

Objective: `shelf-labelling`. While the row reads `implemented`, walk through the diff
against the acceptance criteria. When you have done that and the validators pass, the row
becomes `reviewed`. If a validator fails, the story goes back to `handed-off`.

## Completion conditions

Every story above is closed, and `stockroom.csv` has a count for the first shelf that
names its label.
