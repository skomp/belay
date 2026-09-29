---
id: 00-hello-args
title: Reading command-line arguments
design_refs: [argument-model, subcommand-set]
validators: [cargo-check]
---

## Purpose

A command-line tool that cannot see its own arguments has nothing to work on. This lesson
gets a Rust binary built, running, and printing back what it was given, so that every
later lesson has real input to react to.

It is also the lesson where the learner meets `Vec`, `String` and `&str` for the first
time — not as theory, but because the arguments arrive as a `Vec<String>` and the next
lesson will want to compare one of them against `"lines"`.

## Prerequisites

`cargo` and `rustc` are installed and on the path. No earlier lesson.

## Learning objectives

- Create a binary crate with `cargo new` and know what each generated file is for.
- Run it with `cargo run`, and pass arguments through the `--` separator.
- Read the process arguments and collect them into a `Vec<String>`.
- Explain why the first value is the program name and not the first argument.
- Handle "no arguments were given" without panicking.

## Theory

**The crate.** `cargo new tally` makes a binary crate: `Cargo.toml` (the manifest) and
`src/main.rs` (the entry point). `fn main()` is where the program starts. `cargo run`
compiles and then runs; `cargo check` compiles far enough to find errors and then stops,
which is much faster and is what the learner should use while iterating.

**Arguments.** `std::env::args()` returns an iterator over the arguments as `String`
values. An iterator is lazy: it produces values when asked. `.collect()` drains it into a
collection, and the collection type is the one you ask for:

```rust
let args: Vec<String> = std::env::args().collect();
```

The turbofish form `std::env::args().collect::<Vec<String>>()` says the same thing. Both
appear in real code; the learner should be able to read both.

**The program name.** `args[0]` is the name the program was invoked as. It is a
convention of the operating system, not a Rust decision, and every language sees the same
thing. The arguments the user meant start at index `1`. This trips up everyone once.

**`String` against `&str`.** A `String` owns its text and can grow. A `&str` is a
borrowed view into text somebody else owns. `args` holds `String` values because the
program owns them; the moment you compare one against the literal `"lines"` you need a
`&str`, which `as_str()` or `&args[1]` gives you. The learner does not need the full
ownership model today. They need to know that two types for text exist, and why.

**Indexing can panic.** `args[1]` on a `Vec` with one element ends the program with an
index-out-of-bounds panic. That is the wrong behaviour for a user who typed the command
wrongly, and the tool must not do it. `args.get(1)` returns an `Option<&String>` instead
— `Some(value)` or `None` — and a `match` or an `if let` turns that into a decision. This
is the first appearance of the idea that runs through the whole course: the absence of a
value is a value, and the compiler will not let you forget it.

**The `--` separator.** `cargo run -- words notes.txt` passes `words notes.txt` to the
program. Without `--`, cargo would try to interpret them itself.

## Concepts to teach

- Binary crate layout: `Cargo.toml`, `src/main.rs`, and what `target/` is.
- `cargo check` against `cargo run`, and when to reach for each.
- Iterators and `collect`, at the level of "it produces values, `collect` gathers them".
- `Vec<String>`, indexing, and `.get()` returning `Option`.
- `String` against `&str`: owned against borrowed.
- `println!` is a macro, and `{}` against `{:?}`.
- Argument 0 is the program name.

## Constraints

- No external crates. Not `clap`, not `structopt`, not `anyhow`. `Cargo.toml` has an
  empty `[dependencies]` section at the end of this lesson and at the end of the course.
- The program must not panic when it is run with no arguments at all.
- Do not use `unwrap()` on the argument list. Reach for `match` or `if let` instead. The
  course introduces `unwrap` and `expect` later, deliberately, in the one place where the
  panic is a placeholder that a later lesson removes.

## Suggested progression

1. Create the crate and run the generated program unchanged, so the learner sees the
   toolchain work before any of their own code is involved.
2. Print the full argument vector with `{:?}` and run it with two arguments. Let the
   learner discover the program name at index 0 rather than being told it first.
3. Print only the arguments after the program name, one per line.
4. Run it with no arguments, discover what happens, and make it print a short line
   instead of panicking or printing nothing.

## Completion conditions

- `cargo check` passes with no errors.
- `cargo run -- words notes.txt` prints `words` and `notes.txt`, and does not print the
  program name or its path.
- `cargo run` with no arguments prints a single short line and exits without a panic
  message.
- The learner can say, without looking, what `args[0]` holds and why indexing `args[1]`
  is a risk.

## On completion, persist

- In `STATE.md`, record that the crate exists, its name, and that arguments are read and
  echoed.
- Record the learner's chosen crate name if it is not `tally`, because later lessons name
  the binary in their example commands.

## Optional deeper paths

- `std::env::args_os` and why `args` panics on arguments that are not valid Unicode.
- What `cargo new` puts in `.gitignore`, and why `target/` is never committed.
- Iterator adaptors: the same result with `.skip(1)` instead of slicing the vector.
