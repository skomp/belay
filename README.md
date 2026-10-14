# Belay

**Structured, adaptive courses that run inside your coding agent.**

It catches you. It doesn't climb for you.

Build real software yourself, with an agent that follows a deliberate curriculum, inspects
what you actually wrote, and only moves on once the step is genuinely done.

Ask a coding agent for help and it will optimise for finishing the task. Belay gives it
a different job: hand you one task at a time, read the code you wrote in your own project,
teach when it fails, and refuse to write the exercise for you.

| A written tutorial | A general coding agent | Belay |
|---|---|---|
| Reliable, but the same route for everyone | Flexible, but inclined to solve the task | An authored curriculum, taught adaptively |
| Static text you read | Drifts without a learning plan | Authored side trails, and detours it records |
| Snippets, disconnected from your work | Produces the implementation quickly | You build the project; the tutor inspects it |

The agent you already use — Claude Code or Codex — is the runtime. Belay supplies the
teaching protocol, a portable course format, a validator and a progress lifecycle. There is
no app, no server, and no model API key.

**Start here: [Quick start](#quick-start).**

---

## Quick start

**Prerequisites:** Claude Code or Codex, Python 3 and `git` — the scripts need nothing
beyond the standard library — plus whatever toolchain the course you pick requires.

### Install — Claude Code

```
/plugin marketplace add skomp/belay
/plugin install belay@belay
```

### Install — Codex

Codex has no working plugin route (see [Installing on Codex](#installing-on-codex)). Use
its documented user skills scope, which follows symlinks:

```
git clone git@github.com:skomp/belay.git ~/.local/share/belay
mkdir -p ~/.agents/skills
ln -s ~/.local/share/belay/skills/belay ~/.agents/skills/belay
```

Update it with `git -C ~/.local/share/belay pull`.

### Start a course

One course ships with the plugin: **Rust Fundamentals Through a Command-Line Tool**. It
wants a new repository, so begin in an empty directory and say, in ordinary words:

```
I want to learn Rust.
```

The tutor lists the courses that match and waits for you to choose — it never picks for
you, even when only one matches. When you choose, it copies the course into `tutorial/`
inside your directory, validates the copy before teaching anything, prints the course
banner, and gives you the first task.

To reach the other five courses, register the bundles repository as a catalogue — one
conversational request, covered under [Available courses](#available-courses).

### Come back to it

From the directory holding the course:

```
Continue the tutorial.
```

No catalogue is read and no choice is offered. The runner finds `tutorial/`, reads your
progress file, and resumes at the pending task — in a brand new conversation, weeks later.

---

## How a session works

1. **You pick a course.** The tutor shows the matches and you choose one.
2. **It is copied into your project** as `tutorial/`, alongside the code you are about to
   write. Everything after this reads the copy, never the original.
3. **You get exactly one actionable task.** A conceptual question gets an answer and does
   not advance the task.
4. **You implement it** in your own files. The tutor does not touch them.
5. **The tutor inspects the result** — it reads your source and runs the checks the lesson
   declares (`cargo test`, a file check, whatever the course configured). "It works" is not
   evidence when the course asks for validated evidence.
6. **It classifies the outcome** as failure, success, success with a warning it cares
   about, or a warning you previously agreed to accept. On failure it explains the concept
   and hands back one correction, and does not repair the work.
7. **Progress is written down** once you have demonstrated it, and the loop repeats.

Two things interrupt that loop on purpose. The tutor may **offer a side trail** the author
wrote for the moment you have reached, which you can decline and still finish the course.
And if you are blocked on something the course never teaches, it may **write a detour** and
then send you back to the exact lesson you left, progress intact. Being stuck on the
current lesson's own subject is different, and deliberately so: asking for a lesson on what
the exercise exists to make you work out is the answer with extra steps. What you get
instead is help that escalates while ownership does not — the goal restated, then what you
expected against what happens, then the concept named, then the one line that is wrong,
then the smallest true statement that unblocks. If that runs out, the tutor says plainly
that it can show you the solution and waits for you to ask; whether it may answer at all is
the course's `solution_code` setting.

Two further properties fall out of this. Progress lives in your repository rather than in a chat
log, so a fresh session resumes correctly. And the tutor holds one lesson at a time — not
the course — so a 23-lesson course costs the same per turn as a 3-lesson one.

---

## A curated path with an adaptive teacher

Three layers, and they are not equal. The author's curriculum is the dependable path; the
rest exists to keep a learner on it.

**1. The authored main path.** An ordered list of lessons in the course manifest. Everyone
walks it, in order.

**2. Authored optional lessons.** Lessons the author wrote but did not sequence. Each one
names where it is offered and the risk to state when offering it, and some anticipate a
named *failure mode* — a recognisable way the work goes wrong. The tutor warns you in a
sentence, offers the lesson, and if you say "not now" it leaves it alone. Should the
anticipated failure actually turn up later, it connects the failure to the thing you set
aside and offers again. Declining every offer must still leave the course finishable; that
is an invariant on authors.

**3. Recorded detours, when the course does not reach where you are.** If you are blocked
on a concept the course never teaches, or you ask for a detour outright, the tutor may
write a lesson into `tutorial/lessons.generated/` with frontmatter recording why, and then
send you back to the exact lesson you left. The manifest's lesson list is never edited: a
detour is an overlay on one learner's copy.

The bounds matter as much as the behaviour:

- **A detour may not cover the active lesson's own learning objectives.** Asking for a
  lesson on the thing the current exercise exists to make you work out is a request for the
  answer with extra steps, and the tutor says so instead.
- **A bundle that contradicts itself is reported, never drafted over.** A missing lesson
  file, an undeclared validator, a dangling design anchor — those stop the course. Writing
  a replacement would hide the defect from the only person who can fix it.
- **A detour is not the cure for a hard exercise.** The tutor tests the blocking concept
  against the course's own coverage list; a concept the course already taught gets
  coaching, not a new lesson.

Belay is not a course generator. Adaptation supplements an authored curriculum and is
bounded by its learning objectives.

---

## Available courses

Six courses exist today. One ships with the plugin; the other five live in
[`skomp/belay-bundles`](https://github.com/skomp/belay-bundles) and arrive when you
register that repository as a catalogue.

`Scope` comes from the catalogue entry, not from the course manifest, which has no field
for it. Its lesson count is derived from the manifest's lesson list; the rough duration
beside it is the author's own estimate. There is no other duration figure anywhere, and
none is implied.

| Course | What you build | Language | Level | Scope | Where |
|---|---|---|---|---|---|
| Rust Fundamentals Through a Command-Line Tool | A tool that counts the lines or words in a file — arguments, one subcommand, `Result`, a unit test. No crates. | Rust | beginner | 3 lessons; a few hours | [ships with the plugin](skills/belay/examples/rust-cli-basics) |
| Build a Durable Event Broker in Go | A persistent, partitioned event broker from first principles, then batching, retention, observability and a deliberately limited follower. | Go | intermediate-to-advanced | 15 lessons; a few weeks | [`belay-bundles`](https://github.com/skomp/belay-bundles) |
| Make Music with Integer Arithmetic | A Bytebeat synthesiser that turns integer expressions into a valid WAV file. | TypeScript, JavaScript, Python, Go or Kotlin | beginner-to-intermediate | 4 lessons; a few days | [`belay-bundles`](https://github.com/skomp/belay-bundles) |
| Build a Fixed-Window Rate Limiter | A small in-memory rate limiter with an explicit contract and deterministic time. | your choice | intermediate | 3 lessons; a few hours | [`belay-bundles`](https://github.com/skomp/belay-bundles) |
| Learn Rust by Building AutomatonDB | An automaton-native, partitioned database with storage-engine and distributed-systems depth. | Rust | intermediate-to-advanced | 23 lessons; months of work | [`belay-bundles`](https://github.com/skomp/belay-bundles) |
| Learn WebGL 2 by Building a 3D Scene | An interactive, lit and textured 3D scene, from the rendering pipeline up to a loaded glTF model. | TypeScript | intermediate | 18 lessons; months of work | [`belay-bundles`](https://github.com/skomp/belay-bundles) |

### Registering the bundles repository

Ask the tutor, in the agent you installed it into:

```
Add git@github.com:skomp/belay-bundles.git as a course catalogue.
```

It follows the procedure in
[`catalogue-format.md`](skills/belay/references/catalogue-format.md) section 10: read
what is already configured, write the entry above the bundled catalogue, refresh, and show
you what arrived. A catalogue may also be a plain file on disk, and a private repository
needs no extra setup — fetching uses the Git credentials you already have. Belay stores
no tokens and never prompts for one.

The tutor can show you what is registered at any point, and from a checkout of this
repository you can run the same thing yourself without fetching anything:

```
python3 skills/belay/scripts/catalogs.py status
```

An installed plugin carries the same scripts inside its own directory rather than at that
path, so ask the tutor unless you have the repository cloned.

`discover` refreshes and lists; `resolve`, `covers`, `follow-ups` and `prepare` answer
"which course is this", "who teaches this concept", "what comes next" and "what should I
know first". Catalogues refresh once when a discovery request starts — never per turn, and
never during a resume. A catalogue that cannot be reached is served from its last
successful copy and reported as cached, and the other catalogues still answer.

---

## How Belay works

Two artefacts, and one mechanical rule separating them.

A **bundle** is a course. It is written once and taken by many learners, so it holds no
progress. This is the shipped example, in full:

```
rust-cli-basics/
├── tutorial.yaml        manifest: id, subjects, ordered lessons, optional lessons,
│                        failure modes, validators, ownership
├── COURSE.md            goal, teaching philosophy, chapter map, coverage list
├── DESIGN.md            durable subject decisions, anchored per section
├── STATE.template.md    the shape a fresh learner starts in
└── lessons/
    ├── 00-hello-args.md
    ├── 01-subcommands/          a lesson that ships material alongside it
    │   ├── LESSON.md
    │   ├── dispatch-example.md
    │   └── usage.txt
    ├── 02-errors-and-tests.md
    ├── pure-core-and-edges.md   optional: offered, not sequenced
    └── what-is-a-character.md   optional: offered, not sequenced
```

An **instance** is your copy, inside your own project, and the only place progress exists:

```
my-project/
├── src/                 yours; the tutor never edits it
└── tutorial/
    ├── tutorial.yaml    stamped with where it was materialised from
    ├── COURSE.md
    ├── DESIGN.md
    ├── STATE.md         ← your progress
    ├── lessons/
    └── lessons.generated/   detours, if any were written
```

> A bundle contains `STATE.template.md` and never `STATE.md`.
> An instance contains `STATE.md` and never `STATE.template.md`.

A script enforces that pair, and the runner runs it on the instance it has just created,
before the first task — so a defect in a course is found by the runner rather than by a
learner five lessons in.

**Ownership is declared, not assumed.** The manifest names tutor-owned and learner-owned
paths and an `ownership_policy`, which every course must state — there is no default. Under
`tutor-must-not-edit-learner-owned`, the normal choice and what four of the six courses
above declare, the tutor will not edit a learner-owned path: not when it would be faster,
not when you are stuck, not for a trivial one-line fix. A compiler error is part of the
course.

The other two values relax that deliberately. `on-request` lets the tutor edit your files
when you ask it to — the two portable courses use it so the tutor can build the project
skeleton once you have chosen a language, and each states in its own lesson exactly how far
that reaches. `unrestricted` needs no asking at all and is for courses where you are not
writing the artefact. Whatever the policy, a file the bundle declares it `supplies` (a
dataset, a starting config) is placed as setup rather than assigned as your work, and
placement never overwrites a file that already exists.

**What loads each turn** is the runner file, the manifest, your `STATE.md`, the one active
lesson, the design sections that lesson cites by anchor, and the files in your workspace the
current task actually concerns. Not `COURSE.md`, not a completed lesson, not the rest of the
course. That budget is the reason the format exists.

The normative detail is in the reference documents, which the tutor loads only when it
needs them:

| Document | Covers |
|---|---|
| [`SKILL.md`](skills/belay/SKILL.md) | the control plane — orient, resume or discover, the teaching contract |
| [`bundle-format.md`](skills/belay/references/bundle-format.md) | the normative bundle contract, for authors |
| [`catalogue-format.md`](skills/belay/references/catalogue-format.md) | catalogues, precedence, failure handling, presenting a choice |
| [`state-lifecycle.md`](skills/belay/references/state-lifecycle.md) | materialisation, what a completed task and lesson record |
| [`runner-protocol.md`](skills/belay/references/runner-protocol.md) | the turn loop, validation outcomes, ownership, detours, offers |
| [design specification](docs/superpowers/specs/2026-09-11-tutorial-runner-design.md) | the architecture, the measured host facts, and the designs that were rejected |

---

## Write a course

[`bundle-format.md`](skills/belay/references/bundle-format.md) is the normative
contract. It is self-contained: hand it to a person, or paste it into another model, and it
is enough on its own.

[`skills/belay/examples/rust-cli-basics/`](skills/belay/examples/rust-cli-basics) is
a small worked example carrying both lesson forms and two optional lessons.

Check your work before you ship it:

```
python3 skills/belay/scripts/validate_bundle.py path/to/bundle
python3 skills/belay/scripts/validate_bundle.py --instance path/to/project/tutorial
python3 skills/belay/scripts/validate_bundle.py --catalog path/to/catalog.yaml
```

29 bundle checks and 7 catalogue checks. Your run and the runner's run are the same checks
over the same files, which is the point: a bundle that passes here starts cleanly there. It
checks structure — that references resolve, that no progress leaked into the course, that
every lesson is reachable. It says nothing about whether the course is any good.

One thing it cannot check is worth knowing before you ship: a course carrying optional
lessons must still be finishable by someone who declines every offer. Nothing enforces
that, and section 13 of `bundle-format.md` explains why it is the invariant that keeps an
older runner — which ignores the offers entirely — from teaching a broken course.

[`skomp/belay-authoring`](https://github.com/skomp/belay-authoring) holds an
interview-driven skill and toolkit for writing and maintaining bundles, and a course-quality
checker. It calls this repository's validator, so install the runner first.

If you have built something worth teaching, the format is how you hand it over: the
sequence you would put someone through, the mistakes worth anticipating, and the checks
that say a step is genuinely done. What you get back is not a document people skim, but a
course that walks a learner through building it themselves.

---

## Project status

Version 0.9.0. Early, in active use, and honest about its edges.

**What works today.** Discovery across many catalogues, local or Git-hosted, with caching
and per-source failure reporting. Materialising a course into a workspace and validating it
before teaching. The teaching loop, ownership enforcement, validation outcomes and progress
recording. Authored optional lessons and failure modes. Generated detours with provenance.
Assumed-concept review, and follow-up recommendations at the end of a course.

**Known gaps.**

- **The offer / defer / re-offer behaviour for optional lessons is specified and
  implemented, but no harness exercises it**
  ([belay#22](https://github.com/skomp/belay/issues/22)). The structural checks on
  `optional_lessons` and `failure_modes` are tested; the conversational behaviour around
  them is not.
- **Bundle updates after a learner has started are not solved.** An instance is a copy, and
  nothing refreshes it.
- **Remote trust and signing are not solved.** A catalogue you register is a repository you
  have decided to trust. A course's validators are programs, and **nothing here checks what
  they do**: the validator checks that a `command` is a well-formed argument list, the
  runner tells you which programs a course will run before it runs one, and every call goes
  through your own agent host's permission prompt — which is the only boundary there is.
  Nothing in this project executes a bundle's command itself, and nothing here will ever
  tell you a course is safe.
- **Only catalogues are cached, not bundles.** A course you have not chosen is not on your
  machine.
- **The three repositories are currently private.** The install commands above need access
  to them.

**Not goals for v1:** a standalone UI, a hosted backend, any model API client, accounts,
cloud state, a marketplace, payments, or an autonomous coding mode.

### Installing on Codex

Two things are worth knowing rather than discovering.

**`codex plugin add` does not work here, and fails silently.** A marketplace entry whose
source path is the marketplace root registers the marketplace and then enumerates zero
plugins with no error; putting the plugin in a subdirectory whose `skills/` is a symlink
installs a plugin containing no skill at all, and reports success. Both were measured;
section 17 of the design specification has the detail. The `~/.agents/skills/` symlink is
the supported route until that is resolved.

**The two hosts do not run the same copy.** Claude Code installs a published version from
the marketplace: it changes only when you update it, and it never contains uncommitted
work. Updating takes both commands — `claude plugin marketplace update belay && claude
plugin update belay@belay` — because the second alone compares manifest *versions*,
not commits, and will report you are already current while the new work sits unreachable
behind the old version number. Codex follows the symlink into a checkout, so it
runs whatever is currently checked out there — including a half-finished edit mid-save.
That is why the Codex instructions above clone to `~/.local/share/belay` rather than to
a directory you work in. If you *are* developing the runner, point the symlink at your
working checkout deliberately.

One skill body serves both hosts.

### Tests

No pytest; two plain scripts, run from a checkout of this repository.

```
python3 tests/test_validate_bundle.py     # 735 assertions
python3 tests/test_catalogs.py            # 338 assertions
```

**Those two numbers are properties of this commit, not of your machine.** A clean
checkout reports them on any machine. Nothing outside the checkout is validated by
default, so a number you see that differs from a number printed here is a defect and
not a missing directory.

The deeper sweep is still available and still finds real defects. Setting
`BELAY_SWEEP_SIBLING_REPOS=1` also validates the published bundles in
[`skomp/belay-bundles`](https://github.com/skomp/belay-bundles) and the learner
workspace in `skomp/automaton-db`, when the machine holds them:

```
BELAY_SWEEP_SIBLING_REPOS=1 python3 tests/test_validate_bundle.py
```

Those are separate checkouts at their own revisions, so what they contribute is
reported on its own line and never added to the total above — `and 22 more against
sibling repositories outside this commit` on the machine this was measured on. The
headline stays 735 either way. Run it before publishing a bundle; a plain `python3
tests/test_validate_bundle.py` is the check that a commit of *this* repository is
sound.

Every validator check and every catalogue failure kind is proven firing — or, for the two
that only ever warn, proven warning — because a check that cannot report a positive is
worse than no check.

**Both suites pass whether or not PyYAML is installed.** The scripts parse YAML with the
built-in restricted reader in `yamlite.py` and never use PyYAML, even where it is
importable, so the verdict a bundle gets is a property of the bundle and not of the
machine. `test_yaml_reader_ignores_the_environment` asserts that, by parsing an anchor, a
duplicate key, a tab used for indentation and six ambiguous scalars in two subprocesses —
one of them with `import yaml` made to fail — and comparing the answers.

PyYAML is still the reference for what the reader returns. Where PyYAML is importable,
`test_yaml_reader_differential` compares the two readers on a seeded set of generated
lines and asserts that the restricted reader never returns a value PyYAML would not — it
returns the same value, or refuses the line. Those assertions are reported on their own
line and, like the sibling sweep, never added to the total; without PyYAML the test prints
a `SKIP` line instead.

### Contributing

There is no `CONTRIBUTING.md` yet. Work is tracked as
[GitHub issues](https://github.com/skomp/belay/issues). This repository holds the runner,
the bundle format, the validator and discovery; courses belong in
[`skomp/belay-bundles`](https://github.com/skomp/belay-bundles) and authoring tools in
[`skomp/belay-authoring`](https://github.com/skomp/belay-authoring).

### Licence

MIT. The full text is in [`LICENSE`](LICENSE) at the repository root, and both plugin
manifests (`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json`) declare the same
`"license": "MIT"`.
