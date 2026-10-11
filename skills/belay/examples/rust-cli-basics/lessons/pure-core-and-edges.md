---
id: pure-core-and-edges
title: A pure core, and the edges around it
optional: true
design_refs: [io-boundary, counting-rules]
validators: [cargo-check, explains-choice]
---

## Purpose

`tally` has to do two different things: work out a number from some text, and get that
text off a disk. This lesson is about keeping those two things in separate functions, and
about what it costs when they are one function instead.

It exists because the cost does not arrive when the mistake is made. Counting and reading
fused into one function works perfectly until something needs to check the counting —
and then every test needs a real file, a real path, and clean-up afterwards.

## Prerequisites

You have written at least one counting function. It does not matter yet whether it takes
a path or a string; that is the question this lesson is about.

## Learning objectives

- State what makes a function pure, in terms a compiler could check.
- Explain why a function that takes `&str` can be tested with a string literal.
- Describe what a test must arrange when the function under test opens its own file.
- Identify, in your own code, which line is the edge.

## Theory

**A pure function's result depends only on its arguments.** Give it the same input twice
and it answers the same thing twice. Nothing it does can be observed from outside except
its return value. `fn count_words(text: &str) -> usize` is pure. `fn count_words(path:
&str) -> usize` is not, because the answer depends on what is on a disk at the moment it
runs.

**The edge is where the impurity lives.** Reading a file, printing, reading the clock,
reading the environment — each of those is an edge. The design in `DESIGN.md` puts every
edge of `tally` in `main`, and nowhere else. That is not tidiness for its own sake. It is
what makes the middle of the program testable without a fixture.

**A test of a pure function needs nothing.** `assert_eq!(count_words("  two   words \n"),
2)` is the whole test. It needs no file, no temporary directory, no clean-up, and it
cannot fail because of something another test did. A test of the impure version needs a
file that exists, with known contents, at a path the test can name — and now the test is
about the filesystem as much as about counting.

**The repair is a parameter change, and it is small while the program is small.** Change
the function to take `&str`, move the read into the caller, and pass the text in. The
longer the fused version survives, the more callers there are to change, which is the
whole reason this lesson is offered before the counting functions have callers rather
than after.

## Concepts to teach

- purity, stated as "the result depends only on the arguments"
- the edge of a program, and why edges collect in one place
- why a test of a pure function needs no setup and no clean-up
- `&str` as the parameter type that makes a string literal a valid argument

## Constraints

- No external crates, as everywhere else in this course.
- The counting functions take `&str` and return `usize`. They do not open anything, print
  anything, or exit.
- The file read stays in `main`.

## Suggested progression

1. Look at the counting function you have. Say out loud whether it is pure, and why.
2. If it opens a file, write the signature it would have if it did not.
3. Move the read out to the caller and pass the text in.
4. Write one assertion against a string literal and run it.

## Completion conditions

`cargo check` passes. Every counting function takes `&str` and returns `usize`, and no
counting function names a path, opens a file, prints, or calls `std::process::exit`. The
learner can say, in one sentence, what a test of the fused version would have had to
arrange that a test of this version does not.

## On completion, persist

Append to `DESIGN.md` under `{#io-boundary}` the decision the learner made about where
the read lives, in their words, and the signature the counting functions ended up with.

## Optional deeper paths

If the learner asks where this stops: the same split is what makes a program testable
without a database, a network or a clock, and the name for the pattern in the large is
"functional core, imperative shell". They do not need the name to use it.
