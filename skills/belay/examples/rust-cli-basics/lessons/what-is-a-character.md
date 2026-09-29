---
id: what-is-a-character
title: What a character is, and why `tally` counts neither
optional: true
design_refs: [subcommand-set, open-decisions]
validators: [explains-choice]
---

## Purpose

`DESIGN.md` leaves a `chars` command undecided, and says the reason is that nobody agrees
what a character is. This lesson is that argument, in full, with the three answers Rust
actually gives you.

Nothing in the course depends on it. It is here because the question turns up in every
program that handles text, and meeting it deliberately once is cheaper than meeting it by
accident in something that matters.

## Prerequisites

You can index and iterate a `String`, or you have tried to and the compiler stopped you.

## Learning objectives

- Name the three units Rust offers for "a character" and what each one measures.
- Explain why `String` cannot be indexed by an integer.
- Predict what `len()`, `chars().count()` and a grapheme count give for a string with an
  accent in it, and for one with a flag in it.
- Decide, with a reason, which unit a hypothetical `tally chars` would count.

## Theory

**A byte is what `len()` counts.** `"é".len()` is 2, because UTF-8 encodes that character
in two bytes. This is why `String` has no integer index: an index into the middle of a
multi-byte character does not name anything, so Rust refuses rather than returning half a
character.

**A `char` is a Unicode scalar value, and it is four bytes wide.** `"é".chars().count()`
is 1 — when the text holds the precomposed form. Written as `e` followed by a combining
acute accent it is 2, and the two forms look identical on screen and compare unequal.

**A grapheme cluster is what a reader would call a character.** It can be several scalar
values: a base letter with accents, a flag made from two regional indicators, a family
emoji made from five. The standard library does not count them, on purpose — the rules
are a Unicode annex and they change between Unicode versions, so they live in a crate.

**So the honest answer to "how many characters" is another question.** Counting bytes is
right for a buffer size. Counting `char`s is right for a text algorithm that works in
scalar values. Counting graphemes is right for anything a person will read, like a column
width. A `chars` command that does not say which one it means is wrong three ways.

## Concepts to teach

- `len()` measures bytes, and why that is the useful default for a `String`
- `char` as a Unicode scalar value, and why it is four bytes
- normalisation, just far enough to show two equal-looking strings comparing unequal
- grapheme clusters, and why the standard library leaves them alone

## Constraints

- No external crates, so grapheme counting is discussed and not implemented.
- Nothing in `src/main.rs` needs to change. This lesson adds no command.

## Suggested progression

1. Predict `len()` and `chars().count()` for `"naïve"`, then run both.
2. Build the decomposed form of the same word and compare the two counts again.
3. Say which unit a `tally chars` ought to count, and for whom.

## Completion conditions

The learner states which of the three units a `chars` command should count and names the
reader it would be right for. A different answer from the course's is fine; an answer that
does not distinguish the three is not.

## On completion, persist

Append to `DESIGN.md` under `{#open-decisions}` the learner's answer on the `chars`
command and the reason, whether or not they chose to build it.

## Optional deeper paths

If the learner wants the rules themselves, Unicode Annex #29 defines grapheme cluster
boundaries, and reading its first page is enough to see why this is a crate and not a
method.
