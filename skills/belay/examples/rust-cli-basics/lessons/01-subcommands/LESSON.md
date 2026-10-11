---
id: 01-subcommands
title: Dispatching a command
design_refs: [argument-model, subcommand-set, counting-rules, io-boundary]
validators: [cargo-check, explains-choice]
---

## Purpose

The tool can see its arguments and does nothing with them. This lesson turns the first
argument into a decision and puts two real counting functions behind it. At the end
`tally words notes.txt` prints a correct number, which is the first point in the course
where the program is genuinely useful.

It is also where the learner meets `match` — the construct that does the most work in
idiomatic Rust — and where a deliberate panic is planted so that the next lesson has
something concrete to remove.

## Prerequisites

Lesson `00-hello-args` finished: the crate exists, `cargo check` passes, and the program
prints the arguments after the program name.

## Learning objectives

- Write a `match` that dispatches on a `&str` and explain why it needs a `_` arm.
- Use `match` as an expression that produces a value.
- Write functions that take `&str` and return `usize`, and call them from `main`.
- Use `str::lines` and `str::split_whitespace`, and know exactly what each counts.
- Send the answer to standard output and everything else to standard error.
- Recognise a placeholder panic as a debt, and mark it.

## Theory

**`match` is exhaustive.** A `match` must cover every value the matched type can hold, and
the compiler checks it. For an enum, that means every variant. For a `&str` — which has
infinitely many values — it means a final `_` arm. This is not bureaucracy: it is the
reason a mistyped command cannot silently do nothing.

**`match` is an expression.** It evaluates to a value, so it can sit on the right of a
`let`. Every arm must produce the same type, with one exception: an arm that never returns
at all, such as one that exits the process, is compatible with any of them.

**`Option` again, now pattern-matched.** `args.get(1)` gives `Option<&String>`. A `match`
with `Some(value)` and `None` arms takes it apart. There is no way to reach the inside of
the `Option` without acknowledging that it might be empty, which is the language's central
trick and worth naming out loud.

**Counting lines.** `text.lines()` yields each line without its newline, and a trailing
newline at the end of the text does not produce an extra empty line. `"a\nb\n".lines()`
and `"a\nb".lines()` both yield two items. `.count()` consumes the iterator and returns
how many there were.

**Counting words.** `text.split_whitespace()` yields the runs of non-whitespace text and
skips the whitespace between them, however much there is, including at the ends. It is not
`split(' ')`, which returns empty strings between consecutive spaces — that difference is
worth showing the learner on `"  two   words "` rather than describing.

**Taking `&str`, not `String`.** A function that takes `&str` can be called with a
`String`, a `&String` or a literal, because Rust will coerce them. A function that takes
`String` can only be called with an owned one, which forces callers to clone. Take the
borrowed form unless the function needs to own the data. In this tool no counting function
ever needs to own anything.

**Reading the file, for now.** The counting functions need text, and the text is in a
file. `std::fs::read_to_string(path)` returns a `Result`, and this lesson is not about
`Result`, so the tool reads the file with `.expect("...")` — which panics if the path is
wrong. That is wrong behaviour, it is known to be wrong, and lesson `02-errors-and-tests`
exists to remove it. Mark it in the code with a comment that says which lesson removes it,
and record it in `STATE.md` as intentional. An unmarked placeholder is indistinguishable
from a bug six hours later.

## Material in this lesson

- `dispatch-example.md` — a complete worked example of the same dispatch shape, written
  for a different tool (a temperature converter) so that it demonstrates the structure
  without giving away this tool's implementation. Offer it when the learner has tried a
  dispatch of their own and is stuck on the shape, or asks what idiomatic `match` looks
  like. It also names the mistake — an `args.len()` guard separated from the indexing it
  guards — that this lesson's design exists to avoid.
- `usage.txt` — the exact usage text the tool must print. Give it to the learner when
  they reach the usage-error task; the completion condition compares against it
  character for character, so paraphrasing it fails the lesson.

## Concepts to teach

- `match` on `&str`, and why the `_` arm is mandatory.
- `match` as an expression, and a never-returning arm.
- Destructuring `Option` with `Some` and `None` arms.
- `str::lines` and the trailing-newline rule.
- `str::split_whitespace` against `split(' ')`.
- Function parameters as `&str`, and `as_str()` on a `String`.
- `println!` against `eprintln!`: the answer against everything else.
- `std::process::exit` and a non-zero status.

## Constraints

- Still no external crates.
- The counting functions take `&str` and return `usize`, and they do no input or output.
  No `println!` inside them, no file reading inside them. The next lesson's tests depend
  on this, and the reason is in `DESIGN.md` under the input boundary.
- On a usage error the tool prints the text in `usage.txt` to standard error, prints
  nothing to standard output, and exits with status `2`.
- On success the tool prints the number alone, on one line, to standard output.
- Exactly one `expect` is permitted, on the file read, and it carries a comment naming
  the lesson that removes it.

## Suggested progression

1. Add the two counting functions with the bodies left as `todo!()`, and call them from
   `main` behind a `match` on the command word. Get `cargo check` passing before either
   function does anything. Compiling a skeleton first is a habit worth building.
2. Implement `count_lines`, then check it against a file the learner makes by hand.
3. Implement `count_words`. Show `split(' ')` against `split_whitespace` on a line with a
   double space in it, and let the learner choose with a reason.
4. Handle the missing and unknown command: print the usage text, exit `2`.
5. Add the file read with its marked `expect`, and confirm the end-to-end count.

## Completion conditions

- `cargo check` passes with no errors.
- `tally lines <file>` and `tally words <file>` print the correct counts for a file the
  learner makes, including a file whose last line has no trailing newline.
- `tally` with no arguments, and `tally frobnicate x`, both print the text of `usage.txt`
  on standard error, print nothing on standard output, and exit with status `2`. Check the
  status, with `echo $?` or equivalent — not only the message.
- `count_lines` and `count_words` take `&str`, return `usize`, and contain no input or
  output of any kind.
- The single `expect` is present, is on the file read, and has a comment naming the lesson
  that removes it.
- The learner can explain why the `match` needs its `_` arm, and what `split_whitespace`
  does that `split(' ')` does not. Judge this from what they say, not from the code.

## On completion, persist

- In `STATE.md`, record the two function names and their signatures, so the next lesson
  can name them without reading the source.
- In `STATE.md`, under intentional state, record the marked `expect` on the file read and
  that lesson `02-errors-and-tests` removes it.
- If the learner chose to handle a command this course did not ask for, append that
  decision to `DESIGN.md` under `{#open-decisions}` with their reason.

## Optional deeper paths

- Slice patterns: `match args.as_slice() { [_, cmd, path] => ..., _ => usage() }`.
- Why `split_whitespace` is not `split_ascii_whitespace`, and when the difference matters.
- `chars().count()` against `len()`, and why the course leaves a `chars` command undecided.
