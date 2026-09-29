# Worked example — dispatching on a command word

This is a complete, compiling example of the shape this lesson asks for. It is a
*different* tool on purpose: it converts a temperature, so reading it does not hand over
the answer for `tally`. Read it for the shape, then write your own.

```rust
use std::env;

fn to_celsius(f: f64) -> f64 {
    (f - 32.0) * 5.0 / 9.0
}

fn to_fahrenheit(c: f64) -> f64 {
    c * 9.0 / 5.0 + 32.0
}

fn usage() -> ! {
    eprintln!("usage: convert <c-to-f|f-to-c> <number>");
    std::process::exit(2);
}

fn main() {
    let args: Vec<String> = env::args().collect();

    let command = match args.get(1) {
        Some(value) => value.as_str(),
        None => usage(),
    };

    let number = match args.get(2) {
        Some(value) => value.as_str(),
        None => usage(),
    };

    // Parsing is not this example's subject; a later lesson does errors properly.
    let number: f64 = number.parse().expect("that is not a number");

    let result = match command {
        "c-to-f" => to_fahrenheit(number),
        "f-to-c" => to_celsius(number),
        _ => usage(),
    };

    println!("{result}");
}
```

## Five things to notice

**The `match` produces a value.** `let command = match ... { ... };` is an expression, not
a statement. Every arm returns the same type, and the whole `match` evaluates to it. Rust
code uses this constantly; a chain of `if` statements assigning to a mutable variable is
the shape a Rust programmer would rewrite.

**`Some(value) => value.as_str()`.** `args.get(1)` hands back an `Option<&String>`. The
arm names the inside of the `Some` as `value` and turns the `&String` into a `&str`, so
that it can be compared against string literals in the next `match`.

**`_` is the arm for everything else.** The `match` on `command` must cover every possible
`&str`, and no list of literals can do that, so the final arm catches the rest. Leave it
out and the program does not compile — which is the compiler stopping you from shipping a
tool that silently ignores a mistyped command.

**`fn usage() -> !` never returns.** The `!` type says so. That is why `usage()` is legal
in an arm whose sibling arms produce a `&str` or an `f64`: an arm that never returns a
value is compatible with any type the other arms produce.

**The usage text goes to `eprintln!`, not `println!`.** Standard output carries the
answer; standard error carries everything else. That distinction is what lets someone
write `convert c-to-f 21 > out.txt` and get a file with a number in it and nothing else.

## The trap this example is here to prevent

The tempting first version is:

```rust
if args.len() < 3 {
    usage();
}
let command = &args[1];
let number = &args[2];
```

It works. But the check and the use are in two different places, and the compiler has no
idea they are related — so when a later edit adds a command that takes no file, the
`len() < 3` check stays behind and indexes a vector that is too short. Matching on
`args.get(n)` keeps the check and the use in the same expression, where they cannot drift
apart.
