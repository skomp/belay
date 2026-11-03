---
id: 02-forecasting
title: Forecasting one item
design_refs: [forecast-layout, error-statement]
validators: [has-forecast, explains-error]
teaches: [demand-forecasting, supplier-lead-times]
---

## Purpose

Estimate demand for one item and place its order early enough.

## Learning objectives

- Estimate next period's demand from the past counts.
- State the amount the estimate is likely to be wrong by.
- Subtract the supplier lead time to get the order date.

## Theory

An estimate without an error is a guess dressed as a fact. The error is what lets the
reorder date carry a margin.

## Completion conditions

`forecast.csv` has a row for one item, and you can explain how its error was chosen.
