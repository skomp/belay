# Design — `tally`

Durable decisions about the tool this course builds. Lessons reference these sections by
anchor and the tutor loads only the ones a lesson declares.

`tally` counts things in a text file. It is small on purpose: every decision below exists
so that some Rust concept has a real reason to appear.

## Argument model {#argument-model}

The tool takes a command word followed by exactly one positional argument:

```
tally <command> <file>
```

There are no flags in this version. Flags arrive only when a command needs one, and no
command in this course needs one. The program reads its arguments from the process
environment; it does not use an argument-parsing crate. The course uses no external
crates at all, so that every line in the workspace is one the learner wrote or read.

The first value the operating system supplies is the program name, not the first
argument. Everything the tool cares about starts one position later.

## Command set {#subcommand-set}

Two commands, both of which report a count:

| Command | Prints |
|---|---|
| `lines` | the number of lines in the file |
| `words` | the number of words in the file |

A successful count prints the number, and nothing else, on one line of standard output.

A missing command, an unknown command, or a missing file argument is a *usage* error, not
a runtime error. The tool prints the usage text on standard error and exits with status
`2`. It prints nothing on standard output.

Unresolved: whether to add a `chars` command. It costs one match arm and one function,
but a character count raises the question of what a character is — a byte, a `char`, or a
grapheme cluster — and that question is larger than this course. The decision is left
open rather than answered by accident.

## Counting rules {#counting-rules}

The rules are stated here so that a test can check them and an opinion cannot overrule
them.

**A line** is what `str::lines` calls a line. A trailing newline at the end of the file
ends the last line; it does not start an empty extra one. So `"a\nb\n"` has 2 lines, and
so does `"a\nb"`. Empty input has 0 lines.

**A word** is a run of characters with no whitespace in it. Any run of whitespace
separates words, however long, and whitespace at the start or the end of the file
separates nothing. So `"  two   words \n"` has 2 words. Empty input has 0 words.

These two rules are the whole specification of the tool. They are also the reason the
counting functions can be tested without a single file on disk.

## The input boundary {#io-boundary}

Counting is separated from reading:

- a counting function takes `&str` and returns `usize`, and does nothing else;
- reading the file happens in one place, at the edge of the program, in `main`.

This is the decision that makes the last lesson cheap. A test can call a counting
function with a string literal, so the test needs no fixture file, no temporary
directory, and no clean-up. If counting and reading were one function, every test would
need a file.

## Error model {#error-model}

Three outcomes, three exit statuses:

| Situation | Exit status | Goes to |
|---|---|---|
| The count succeeded | `0` | the count on standard output |
| The file could not be read | `1` | a message on standard error |
| The command line was wrong | `2` | the usage text on standard error |

A failure that the user can cause — a path that does not exist, a file with no read
permission, a directory named where a file was expected — is an ordinary result, not a
defect. It is carried as `Result` and reported as a sentence. The tool must never report
such a failure by panicking: a panic message with a backtrace hint is a report about the
program, and this failure is a report about the input.

The error message must name the path that failed. "No such file or directory" without the
path forces the user to guess which of their arguments was wrong.

Direction for the error type: start with the simplest type that lets `?` work in `main`,
and introduce a named error type only when the tool has two failure kinds that a caller
would want to tell apart. It has one.

## Open decisions {#open-decisions}

Decisions the course deliberately leaves to the learner. The tutor appends the answer
here, with its reason, when a lesson settles one.

- Whether `tally` reads standard input when the file argument is `-`.
- Whether a `chars` command is worth the definition of a character it forces.
- Whether the counting functions live in `src/main.rs` or move to `src/lib.rs`.
