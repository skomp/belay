---
id: 02-errors-and-tests
title: Errors with Result, and a test that holds the rules
design_refs: [error-model, counting-rules, io-boundary]
validators: [cargo-check, cargo-test, has-test, explains-choice]
---

## Purpose

The tool works and then panics at the first typo in a path. This lesson replaces the
panic with a `Result`, which is the type the rest of Rust is built around, and then writes
the tests that hold the counting rules to exactly what `DESIGN.md` says they are.

These two things belong in one lesson because they are the same idea seen twice: a
failure that a user can cause is data to be handled, and a rule that is written down is a
claim to be checked. Neither is an opinion.

## Prerequisites

Lesson `01-subcommands` finished: both commands work, the usage error exits `2`, the
counting functions take `&str`, and exactly one marked `expect` remains on the file read.

## Learning objectives

- Explain what `Result<T, E>` holds and how it differs from `Option<T>`.
- Replace an `expect` with `?` and let the caller decide.
- Return a `Result` from `main`, and state what the process does when it returns `Err`.
- Add context to an error so the message names the path that failed.
- Write unit tests in a binary crate with `#[cfg(test)]` and `#[test]`.
- Choose test cases from a written rule rather than from the implementation.

## Theory

**`Result<T, E>` is an enum with two variants**, `Ok(T)` and `Err(E)`. Where `Option` says
a value may be absent, `Result` says an operation may have failed and carries the reason
why. `std::fs::read_to_string` returns `Result<String, std::io::Error>`, and the `io::Error`
knows a kind — not found, permission denied, is a directory — and a message.

**`expect` throws the reason away and ends the program.** It is right in a test and in a
case that genuinely cannot happen. It is wrong for a path a user typed, because that is
not a defect in the program; it is a normal Tuesday.

**`?` is early return for failures.** In a function returning `Result`, `let text =
read_to_string(path)?;` unwraps the `Ok` or returns the `Err` to the caller immediately.
It also converts the error type on the way out, using the `From` conversions the standard
library provides — which is what makes `Box<dyn Error>` work as a catch-all return type
with no conversion code at all.

**`main` can return `Result`.** `fn main() -> Result<(), Box<dyn std::error::Error>>`.
Returning `Ok(())` exits `0`. Returning `Err(e)` prints `Error: ` followed by the
`Debug` form of the error on standard error, and exits `1`. The exit status is `1` and
cannot be chosen — which is exactly why the usage error in the previous lesson called
`std::process::exit(2)` directly instead of returning an error. The learner should be able
to say why those two failures are handled by two different mechanisms.

**The message must name the path.** `No such file or directory (os error 2)` does not say
which file. The fix is to build a message that includes the path before returning it —
`format!("cannot read {path}: {source}")` is enough at this size. This is the whole
motivation behind the error-context crates the learner will meet later; meeting the
problem first makes those crates obvious instead of magical.

**Tests live next to the code.** In a binary crate, unit tests go in `src/main.rs` in a
module marked `#[cfg(test)]`, which means it is compiled only under `cargo test` and
costs the shipped binary nothing. Each test is a function marked `#[test]` that panics to
fail — usually through `assert_eq!(actual, expected)`, which prints both values when they
differ.

**Test the rule, not the code.** The cases worth writing come from the counting rules in
`DESIGN.md`, and they are the ones where a plausible implementation is wrong: empty
input, the missing trailing newline, and a run of several spaces. A test that asserts
`count_words("one two") == 2` passes against almost any wrong implementation and proves
close to nothing.

## Concepts to teach

- `Result<T, E>` against `Option<T>`.
- `?` and the early return it compiles to.
- `Box<dyn Error>` as the simplest error type that lets `?` work, and its cost: the caller
  can no longer tell failures apart.
- `main` returning `Result`, the `Error:` prefix, and exit status `1`.
- Why the usage error uses `exit(2)` while the read failure uses `Err`.
- `#[cfg(test)]`, `#[test]`, `assert_eq!`.
- Choosing cases from a specification.

## Constraints

- Still no external crates. `Box<dyn Error>` is in the standard library; `anyhow` is not,
  and is not permitted here.
- No `unwrap` and no `expect` anywhere outside the test module when the lesson finishes.
- The counting functions keep their signatures. If a test needs a file on disk, the
  boundary in `DESIGN.md` has been broken and the fix is in the source, not in the test.
- At least three tests, each named for the rule it holds, not `test1`.
- A failing read prints its message on standard error and nothing on standard output.

## Suggested progression

1. Change `main` to return `Result<(), Box<dyn std::error::Error>>` and make it end with
   `Ok(())`. Get `cargo check` passing before touching the read.
2. Replace the `expect` with `?`, delete the comment that marked it, and try a path that
   does not exist. Look at the message together and decide it is not good enough.
3. Add the path to the message. Run it again on a directory rather than a missing file,
   and see a second failure reported by the same path.
4. Add the test module with one test, and run `cargo test` to see it pass and to see what
   the output looks like.
5. Write the remaining tests from the counting rules. For at least one of them, break the
   implementation on purpose, watch the test fail, and put it back. A test that has never
   failed has not been tested.

## Completion conditions

- `cargo check` and `cargo test` both pass.
- `src/main.rs` contains a `#[cfg(test)]` module with at least three `#[test]` functions,
  covering at least: empty input, text with and without a trailing newline giving the same
  line count, and a run of two or more spaces counting as one separator.
- `grep -n 'unwrap\|expect' src/main.rs` returns nothing outside the test module.
- `tally words no-such-file.txt` prints a message that contains the string
  `no-such-file.txt`, prints it on standard error, prints nothing on standard output, and
  exits with status `1`.
- `tally frobnicate x` still exits with status `2`, unchanged by this lesson.
- The learner can explain, in their own words, why the missing file returns an `Err` while
  the unknown command calls `exit(2)`. Judge this from their answer, not from the code.
- The learner has seen at least one of their own tests fail and then pass.

## On completion, persist

- In `STATE.md`, record that the tool handles read failures and that no placeholder panic
  remains, and clear the intentional-state entry that lesson `01-subcommands` wrote.
- In `STATE.md`, record the names of the tests, so that a later session knows which rules
  are already held.
- Append to `DESIGN.md` under `{#open-decisions}` any decision the learner made about the
  error message wording or a named error type, with the reason they gave.

## Optional deeper paths

- A named error type: an enum with `Usage` and `Read` variants, `impl Display`, and
  `impl std::error::Error`. Worth doing once, by hand, to see what the crates generate.
- `std::process::ExitCode` as a return type for `main`, and choosing the status directly.
- Integration tests in `tests/`, and why a binary crate makes them awkward until the
  counting functions move to `src/lib.rs` — the third open decision in `DESIGN.md`.
- `io::Error::kind()` and reacting differently to a missing file and a permission failure.
