# Rust Fundamentals Through a Command-Line Tool

## What you build

`tally`, a command-line tool that counts the lines or the words in a text file:

```
$ tally words notes.txt
127
```

That is the whole tool. It is deliberately small, because the point is not the tool — it
is that every part of it forces one piece of core Rust into the open. Arguments force
`Vec`, `String` and `&str`. A second command forces `match`. A file path the user typed
forces `Result` and `?`. A stated counting rule forces a test.

By the end you will have written, run and tested a Rust program of about eighty lines,
using no external crates, and you will be able to explain every line of it.

## Who this is for

Someone who can program in some language and has not written Rust. You need `cargo` and
`rustc` installed, and a terminal. You do not need to have read the Rust book. Borrowing
and ownership appear here only where the compiler makes them appear, and they are
explained where they do.

## How this course teaches

- **You write the code.** The tutor sets one task at a time, reads what you wrote, and
  responds to that. It does not write your program for you.
- **Solutions on request.** If you ask for the answer you get the answer, with the
  reasoning. Asking is not failing. But the default is a hint, not a patch.
- **Evidence, not assertion.** A lesson finishes when `cargo check` or `cargo test` says
  so, or when you can explain a thing you were asked to explain. "I think it works" does
  not advance the course.
- **One tool, three passes.** Each lesson changes the same program rather than starting a
  new file, so you see code you wrote yesterday turn out to be wrong, and fix it.
- **Rules before code.** The counting rules and the exit statuses are written down in
  `DESIGN.md` before you implement them. A test can check a written rule; it cannot check
  an intention.

## The lessons

**00 — Reading command-line arguments.** Create the project, run it with `cargo run`, and
get it to see its own arguments. Meet `Vec<String>`, `String` against `&str`, and the
fact that the first value is the program name. The tool ends this lesson printing back
what it was given.

**01 — Dispatching a command.** Turn the first argument into a decision with `match`, and
implement the two counting functions behind it. Meet exhaustive matching, `Option`, and
functions that take `&str`. This lesson ships a worked example and the exact usage text
the tool must print. It ends with a working `tally` that still panics on a bad path —
knowingly, and with the panic marked for removal.

**02 — Errors with Result, and a test.** Remove the panic. Meet `Result`, the `?`
operator, `main` returning a `Result`, and exit statuses. Then write the tests that hold
the counting rules to the letter — the empty file, the missing trailing newline, the
double space.

## Optional lessons

Two lessons in this course sit off the main path. The tutor offers them at the point they
become relevant and you decide whether to take them; declining one costs you nothing, and
the course finishes either way.

- **A pure core, and the edges around it.** Offered during lesson 01. Whether a counting
  function opens its own file or is handed a string decides how much work lesson 02's
  tests turn out to be. If you decline it and the tests later need a file on disk, the
  tutor will connect the two and offer the lesson again.
- **What a character is, and why `tally` counts neither.** Offered during lesson 02.
  Enrichment, and nothing depends on it: the three answers Rust gives for "a character",
  and why `DESIGN.md` leaves the `chars` command undecided.


## Checkpoints

There are two points where the tool works from a terminal, and they are the ones worth
stopping at:

1. **After lesson 01** — `tally words <file>` prints a correct count for a file that
   exists.
2. **After lesson 02** — `tally` behaves for a file that does not exist, and `cargo test`
   proves the counting rules.

## Where to go after this

The course leaves three questions open in `DESIGN.md` on purpose: reading standard input,
a `chars` command and the definition of a character, and whether the counting functions
belong in a library crate. Each is a good first thing to build alone.
