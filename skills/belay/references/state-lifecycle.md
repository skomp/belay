# State Lifecycle — `STATE.md` From Materialization to Completion

**Status:** normative for the runner. Load this when materializing a new instance, the
first time in a session you are about to change `STATE.md`, when a task completes, when a
lesson completes, when an offer of an optional lesson is accepted or deferred, when the
learner acknowledges the assumed-concept review, when you need to advance
`active_lesson`, when an assessment ends or is interrupted (section 11), when the
learner asks to update the course to a newer version (section 3.2), or when the learning
record is missing, broken or asked about (section 12).

`STATE.md` is the only place a learner's progress is recorded. Nothing in the bundle
records progress; nothing outside `STATE.md` in the instance records it either. If you
find progress recorded in a second place, the second place is wrong.

The learning record, `tutorial/EVENTS.jsonl` (section 12), is not a second place. It is
evidence of how the learner got there — attempts, hints, answer outcomes — and nothing in
the teaching loop decides anything from it that `STATE.md` does not also say. Where the two
disagree, `STATE.md` is right.

---

## 1. The governing rule

> **Progress is recorded only after it has been demonstrated.**

`STATE.md` is a log of what happened, not a plan of what is about to happen. The one
forward-looking field, *Next task*, is explicitly labelled as the next task and is never
treated as achievement.

Concretely, do not:

- mark a task complete because you are about to ask for the next one;
- advance `active_lesson` because the remaining work "is only" cleanup;
- record a concept as demonstrated because you explained it — the learner demonstrates
  concepts, you do not;
- record a decision the learner has not actually made.

The cost of this rule being broken is not cosmetic. `active_lesson` is what a cold
session resumes from. A lesson advanced early sends the next session to the wrong file
and loses the learner's real place.

---

## 2. Shape of `STATE.md`

Frontmatter is machine-checkable. The body is what the tutor reads.

```markdown
---
tutorial_id: rust-automaton-db
active_lesson: lessons/03-first-refactor.md
status: in-progress
updated: 2026-09-11
---

<!-- and, once a course that declares `assumes` has had its review acknowledged:
     assumes_reviewed: 2026-09-11        -->

## Last completed task

## Concepts demonstrated

## Decisions made in discussion

## Known intentional or incomplete state

## Accepted warnings

## Next task

## Deferred items
```

### Frontmatter fields

| Field | Meaning | Constraint |
|---|---|---|
| `tutorial_id` | which course this instance is | MUST equal `id` in the instance `tutorial.yaml` |
| `active_lesson` | the lesson file to load now | MUST be a path, and MUST appear in the manifest's `lessons` list — unless it names a generated lesson (section 8) or a key in the manifest's `optional_lessons` (section 9) |
| `resume_at` | the lesson to make active when a detour finishes | present **exactly** while `active_lesson` names a generated lesson or an optional lesson; see sections 8.3 and 9.3 |
| `status` | `not-started`, `in-progress`, `complete` | set by the runner |
| `updated` | date of the last change | update whenever you change the file |
| `assumes_reviewed` | the date the assumed-concept review was shown and the learner chose to continue | present **only** after that happened, and only in a course that declares a non-empty `assumes`; see section 10 |

**`active_lesson` is a path, never a description.** "Chapter 1, lesson 10" would force a
fresh session to read `COURSE.md` to resolve it, which defeats cold resume. A path is
directly openable. This single field is what makes a new conversation with no history
work.

### Body sections

All seven headings are always present, even when a section says "None". Three further
sections appear only once the instance needs them: *Generated lessons*, once a lesson has
been written into this instance (section 8.5), *Optional lessons*, once one has been
offered (section 9.1), and *Assessments*, once one has been taken (section 11.1).

| Section | Holds | Does not hold |
|---|---|---|
| Last completed task | the most recent task that was validated | anything still in progress |
| Concepts demonstrated | concepts the learner has shown they can use | concepts you explained |
| Decisions made in discussion | choices the learner made that later lessons depend on | decisions about the subject that belong in `DESIGN.md` |
| Known intentional or incomplete state | deliberate gaps, stubs, commented-out code; and the one entry that is about the course rather than the code, an uncertified bundle the learner chose to start anyway (section 3.1) | bugs the learner has not seen yet |
| Accepted warnings | the YAML list in section 6, with expiries | warnings nobody has accepted |
| Next task | the single task to ask for next | a plan for the rest of the lesson |
| Deferred items | work explicitly postponed, with why | vague intentions |

`STATE.md` never duplicates learner source code. The source is authoritative for
implementation state; `STATE.md` is authoritative for progress. A paste of the learner's
current types into `STATE.md` goes stale within one turn and then actively misleads.

---

## 3. Materialization

This happens once, when a learner starts a course. Load this section before creating any
file.

Preconditions:

- the learner has chosen a tutorial from the catalogue (see `catalogue-format.md`);
- the entry's `source` resolves to a readable bundle directory. `belay-catalogs materialize`
  resolves it itself, exactly as `belay-catalogs resolve` does, from what discovery left on
  disk, and refuses when it does not;
- the workspace root is known, and satisfies the bundle's `workspace_kind`;
- there is no existing `tutorial/` in that workspace. If there is, stop — `tutorial/` is
  singular, and materializing over it destroys a learner's progress. When the existing
  instance is this course and the learner wants its newer version, that is an update, and
  section 3.2 is the procedure. Otherwise ask.

**Steps 1, 2, 3 and 5 are one command, and you do not do them by hand.** From the workspace
root, run:

```
belay-catalogs materialize <id>
```

`<id>` is the tutorial id the learner chose. The bundle is outside the workspace — a Git
catalogue's bundle sits in its cache clone under `~/.cache/belay/`, and a local one is
usually a checkout beside the workspace — and under
`permissions.blockReadsOutsideWorkingDirectories` the host asks the learner before any read
or command that names it. The command reads it inside its own process, and its argument
names nothing outside the workspace. So do not copy, list or diff the bundle yourself, and
do not ask the learner to add its directory with `/add-dir`. Every later read of the source
goes through a command as well: `belay-catalogs place-supplies` (step 8) and
`belay-plan-update` (section 3.2, and the resume check in `runner-protocol.md` section 1).

The command fetches nothing, runs nothing the bundle declares, and builds the instance in a
hidden staging directory that it renames to `tutorial/` only when every file is in place, so
an interrupted run leaves no half-copied instance. It prints what it copied and the stamp it
wrote.

| Exit | Meaning | What the runner does |
|---|---|---|
| 0 | `tutorial/` was created, copied, converted and stamped | go on to step 4 |
| 2 | usage or I/O error, or the catalogue of catalogues is unusable | correct it and run again. Nothing was left in the workspace |
| 3 | refused: `tutorial/` already exists, no catalogue supplies the id, the bundle is not there or lacks `tutorial.yaml` or `STATE.template.md`, it is an instance rather than a bundle, or it holds a symbolic link leading outside itself | nothing was written. Say what the report names. An existing `tutorial/` is the precondition above; a missing bundle may be a cached catalogue naming one the last fetch did not carry |

What the command does, step by step:

1. **Create the instance directory** `tutorial/` at the workspace root.
2. **Copy the bundle's files into it**: `tutorial.yaml`, `COURSE.md`, `DESIGN.md`, and
   `lessons/` in full, including lesson folders and their material — the same file set the
   update compares (section 3.2). The instance is
   self-contained; teaching never reaches back into the bundle source afterwards. Two
   moments are outside teaching and read the source, and neither one changes this rule.
   A resume may read the source manifest's `version` and nothing else
   (`runner-protocol.md` section 1). An update the learner asked for reads the whole
   source (section 3.2).
3. **Convert the state file.** Copy `STATE.template.md` to `STATE.md` **in the instance**,
   and never copy `STATE.template.md` itself. This matters: an instance that
   still holds `STATE.template.md` is indistinguishable from a half-materialized bundle,
   and a validator in instance mode reports it.
4. **Initialise `STATE.md`** — yours, with the Edit tool. Set `status` to `in-progress` when the first lesson begins,
   set `updated` to today, and confirm `active_lesson` equals the manifest's `lessons[0]`
   and `tutorial_id` equals the manifest's `id`. The template should already satisfy
   both; if it does not, the bundle is defective — report it rather than silently
   correcting.
5. **Stamp the instance.** The command appends one block to the *instance's* copy of
   `tutorial.yaml`:

   ```yaml
   instance:
     materialized_from: local:../belay-bundles/rust-automaton-db
     materialized_version: "2.1"
     materialized_at: 2026-09-11
     runner_version: 1
   ```

   `materialized_from` records the resolved source in provider-qualified form
   (`local:` plus the path, and for future provider types the equivalent locator). The
   command writes the absolute path the entry resolved to — for a Git catalogue, the
   bundle inside the cache clone. A relative `local:` path, as in this example and in
   instances stamped by hand before the command existed, is relative to the workspace
   root, which is how the example reaches a `belay-bundles` checkout beside the workspace.
   `place-supplies` and `belay-plan-update` read the source from this key, and only a
   `local:` locator is one they can read.
   `materialized_version` records *which version* of that source this instance holds:
   the bundle's `version` exactly, in quotes, or `"1.0"` when the bundle
   declares none (`bundle-format.md` section 2, **Content version**). A path has no
   version, so without this key the only way to tell whether an instance is behind its
   bundle is to compare every file. With it, the instance is behind when the bundle's
   `version` is greater than `materialized_version`, the two compared as pairs of
   integers, MAJOR first — `"2.10"` is later than `"2.9"`.
   This block is **provenance only**. Nothing in the teaching loop reads it. It exists so
   a learner, a resume, or an update (section 3.2) can tell where the instance came from
   and which version of it. It never appears in a bundle. Section 3.1 adds three validation keys to this same
   block; those keys are the one part of the stamp anything ever reads, and what
   reads them is a session deciding whether this instance was ever checked — never a
   teaching turn.
6. **Verify the invariant**, by looking with Glob or Read rather than `test` or `ls`: the
   instance has `STATE.md` and does not have `STATE.template.md`. Say that you checked. **Then validate the instance, before
   step 7 and before anything is placed outside `tutorial/`: section 3.1.**
7. **Draw the banner, then report what was created.** This is the moment the learner
   first meets the course, and it is the only moment the banner is drawn: the manifest's
   `title` in large text — the runner writes Markdown to a terminal, so a large heading or
   ASCII art can carry the name — then `description`, then `teaching_method` when the
   manifest declares it (`bundle-format.md` section 2).

   **A resume never draws it.** The rule holds because of where it is written rather than
   because a session remembers to obey it: materialization runs exactly once per instance,
   so a step in this list cannot fire twice, and a resume never reaches this step at all.
   Written into the teaching loop instead, the same rule would become a condition to
   re-check every session and eventually to get wrong. It is also the right answer for the
   learner: the first words of a resume belong to where they are standing, not to the name
   of a course they chose weeks ago and have not forgotten.

   When the manifest declares no `teaching_method`, the banner is one sentence shorter.
   That is the whole of the difference — nothing warns, nothing is reported as missing, and
   nothing about the start of the course is blocked or delayed. `title` and `description`
   are MUST fields, so every bundle, including every one published before
   `teaching_method` existed, has a banner to draw without an edit.

   **Then the disclosure block, below the banner's sentences.** The learner is told at this
   step and the first command runs at step 9 — *disclose, then act*.

   **The validator derived it. Repeat it; do not work it out again.** The run at section
   3.1 prints a `disclosure:` section in its report, beside `target:` and `yaml reader:`,
   and that section *is* the block:

   ```
   disclosure:
     programs:    cargo, git
     unprompted:  cargo-check — confirms the placed skeleton compiles
   ```

   Say it to the learner in the banner's own words, adding nothing and dropping nothing:

   ```
   This course runs programs on your machine: cargo, git

   Before the first lesson it will run one itself:
     cargo-check — confirms the placed skeleton compiles
   ```

   `programs` is every program this course can run, and it is the part a learner can judge
   before reading a single lesson: `cargo, git` is unremarkable, `curl` is a reason to
   stop. `unprompted` is what you will run without being asked, each with the author's own
   `describe` line. **Draw only the parts the report printed** — the two are independently
   conditional, so a course with command validators and no setup step has only `programs`,
   and a course whose only setup check is `file-exists` has only `unprompted`. A report
   reading `disclosure:  nothing to disclose` means no block at all — the same pattern
   `teaching_method` already uses, where the banner is one sentence shorter and nothing
   warns.

   **Do not edit the list on the way through.** It deliberately names *every* `command`
   validator the manifest declares, not only the ones a lesson reaches, so it can name a
   program this course never runs. That was accepted deliberately, because the two errors
   are not symmetric — over-disclosure makes the block slightly noisy, while
   under-disclosure means a learner consented to something nobody told them about, and no
   later correction reaches a consent already given. Lesson-scope `setup_validators` are
   excluded for the same reason they always were: they are announced when the lesson opens,
   in the same breath as that lesson's supplies placement, using the same `describe` line.

   **The block states what happens. It never states that it is safe.** Nothing has checked
   a command, nothing can, and any wording shaped like *"these commands have been
   checked"* is a defect — see `runner-protocol.md` section 14.

   Then report what was created — the instance path, the course title, the first lesson.
   The banner names the course; this says where it now lives and what happens next.
8. **Place what the manifest supplies, then report it.** When `tutorial.yaml` declares
   `supplies` at the top level, place those entries now: the instance exists, no lesson
   has opened yet, and this is the one moment manifest-scope entries are placed. Run, from
   the workspace root:

   ```
   belay-catalogs place-supplies
   ```

   It takes no argument. It reads the source from the stamp's `materialized_from`, reads
   the declaration from the instance's `tutorial.yaml`, checks every entry by the rules of
   validator check 22 — and refuses the whole placement, before the first file lands, when
   one `from` leaves the bundle or does not resolve, a `to` leaves the workspace or begins
   with `tutorial/`, or a symbolic link leads out of either — then creates each missing
   target and never overwrites one. For each entry it prints the `describe` line, the
   targets `placed:`, the targets `already here:` and left alone, and any `NOT placed:`
   because a file of the learner's stands where a directory is needed. An entry whose
   targets were all there already says *say nothing about this entry*.

   | Exit | Meaning | What the runner does |
   |---|---|---|
   | 0 | placed what was missing, or there was nothing to place | report it by the four rules below |
   | 1 | placed what it could; some targets could not be created | report it, and name each `NOT placed` target and the file in its way. Never move the learner's file |
   | 2 | usage or I/O error, such as no `tutorial/` in the current directory | run it from the workspace root |
   | 3 | refused: the stamp is missing or names no readable `local:` source, or an entry is malformed or reaches outside the bundle or the workspace | nothing was placed. Report it as a bundle defect (`runner-protocol.md` section 13.3) |

   `from`
   is relative to the **bundle** root, and a trailing `/` means that directory's
   contents, recursively; `to` is relative to the **workspace** root and never inside
   `tutorial/`.

   **Each `from` is taken from the bundle source, not from the instance** — which is why the
   command reads the stamp rather than `tutorial/`. That is why step 8 is *inside* materialization rather
   than a step after it. Step 2 copies only `tutorial.yaml`, `COURSE.md`, `DESIGN.md` and
   `lessons/`, so a manifest-scope `from` such as `supplies/Cargo.toml` exists in the
   bundle and will never exist in the instance. Once the source is out of reach, a
   manifest-scope entry can no longer be placed at all, and the command refuses. This is also the reason a
   **lesson-scope** `from` MUST resolve inside `lessons/`: those entries are placed when
   the lesson opens, long after this step, and `lessons/` is the only thing the instance
   carries (`bundle-format.md` section 2, **Where a `from` may point**).

   Four rules govern the placement — the command keeps the first and prints what the other
   three need — and `bundle-format.md` section 2 states them in full:

   1. **Never overwrite.** A target that already exists is left exactly as it is.
   2. **Say nothing when every target of an entry already exists.** The entry has been
      applied already. This is what makes re-entry idempotent with **no new state**:
      nothing is written to `STATE.md`, nothing is consulted in the instance stamp, and
      the workspace itself is the only record of what has been placed.
   3. **When some targets were missing, place those, name them, and name the ones you
      left alone.** Report a partial placement in full — these are new, these were
      already here and were not touched. A learner must never be left wondering whether
      a file of their own was replaced.
   4. **Name it as setup, not as a lesson.** Placed files are not an accomplishment and
      are not progress; nothing about them goes into `STATE.md`.

   Say the entry's `describe` line when you report it — it is the author's sentence about
   what these files are, and telling the learner is the only reason the field exists.
   Under `ownership_policy: tutor-must-not-edit-learner-owned` **and under `on-request`**
   you MAY **create** a declared target that does not exist, even where it falls under a
   `learner_owned` glob, and under `on-request` you do not ask first: placing a declared
   supply is not the tutor being asked for a change, and a course using that policy would
   otherwise have to interrupt the learner for permission to unpack its own fixtures.
   `unrestricted` needs no exemption at all. Under **every** policy, `unrestricted`
   included, you may **never modify** a target that already exists — placement never
   rewrites a file that is already there, whatever the policy would otherwise allow. The
   exemption is create-only and covers declared paths only. A course written before the key
   existed gets one other, narrower exemption, and `runner-protocol.md` section 10.1 is
   where it is stated.
9. **Run the manifest's setup validators, if it declares any.** When `tutorial.yaml`
   declares `setup_validators` at the top level, run those checks now, in the order they
   are listed: step 8 has placed the supplies, and verifying the placed skeleton is the
   point. Say the entry's `describe` line before each one — the learner was told at step 7
   that this would happen, and this is it happening.

   **You run them yourself, as the agent, through your own host.** Nothing in this skill
   executes a validator, and nothing in it ever will: the moment a script here ran a
   bundle's command, the call would stop passing through the host's permission layer, and
   that layer is the only boundary there is. `runner-protocol.md` section 14 states the
   rule and why it is the one thing this design must not do.

   **Nothing about a setup validator is progress.** Same rule `supplies` carries: nothing
   is written to `STATE.md` for a setup check that passed, and none of it is a task the
   learner completed.

   **A setup validator that fails is not a learner failure**, and it never goes back as a
   correction — there is no learner work yet to correct. It means the bundle or the
   environment is wrong. Stop, and follow `runner-protocol.md` section 14.2: report it
   verbatim, say whether the cause looks like the bundle or the machine, and let the
   learner decide whether to go on. If they go on, **record the decision** as section 3.1
   below describes. Do not start teaching on a failed setup check without that record.
10. **Show the assumed-concept review, if there is one.** When the manifest declares a
   non-empty `assumes`, this is the moment: after the setup checks, before the first task.
   `runner-protocol.md` section 11 has what it looks like and what the three answers are;
   section 10 of this document has the stamp it leaves. A course that declares no
   `assumes` skips this step entirely and leaves no stamp. Then start teaching.

### 3.1 Validating the instance, between step 6 and step 7

The runner checks a course before it teaches from it, and this is the moment: the instance
exists, it is stamped, no file has been placed outside `tutorial/`, and no learner has
started. A defect found here costs a conversation. The same defect found at lesson 7 costs
a learner their place in a course they cannot finish.

Run `belay-validate --instance tutorial` from the workspace root; the argument is the
`tutorial/` directory step 1 created. `belay-validate` is a command the plugin puts on the
host's `PATH`, reached the same way as `belay-catalogs` (`catalogue-format.md` section 4;
`runner-protocol.md` section 1 has the fallback for a host without it). It needs Python 3
and nothing else, it reads only the instance, and it contacts nothing.

The position in the sequence is fixed at both ends. The run comes **after** step 5, because
instance mode reports a finding against check 7 when the `instance:` stamp is absent — an
earlier run would fail a correct bundle for a reason the runner created. It comes **before**
step 8, because step 8 writes files into the learner's workspace outside `tutorial/`, and a
course that cannot be certified must not scatter files there first.

#### The four outcomes

| Exit | What it means | What the runner does |
|---|---|---|
| 0, no warnings | every applicable check ran and found nothing | record the pass below, then go on to step 7 |
| 0, with warnings | the same result, plus notes addressed to the course author | start the course. A warning never blocks one |
| 1 | findings — the bundle is defective | do not start the course. Report it: `runner-protocol.md` section 13.3 |
| 3 | indeterminate — no findings, and some check could not run | not a pass. Stop before the first task and say what was not certified: `runner-protocol.md` section 13.3 |

Exit 2 is a fifth case and it is the runner's, not the bundle's: a usage or I/O error, a
wrong path, a directory that cannot be opened. Correct the invocation and run it again.
Never report a 2 to the learner as a defect in their course. When it persists, the
validator did not run, which leaves the course uncertified — handle that as exit 3.

**Findings stop the course, and warnings never do.** The validator keeps the two apart on
purpose: warnings live in a list the exit code cannot consult, so a quality signal can
never reject a bundle, however many of them a run produces. Do not add that coupling back
by counting warnings and stopping at some number of them.

#### What happens to a warning

A warning is addressed to the person who wrote the course, not to the person taking it.
Checks 23 and 25 are the two that raise them, and both are about vocabulary — an alias that
collides with a concept id, a `covers` concept that no phrase in `COURSE.md` resembles.
Neither one tells a learner anything they can act on, and neither one affects a single
lesson.

So: **do not narrate warnings at materialization**, and do not discard them either. Record
how many there were, in the stamp, and surface them verbatim at the three moments where
someone can use them:

- the learner asks about the state of the course, or about this check;
- the learner says they nearly missed this course, or could not find it by the words they
  used — check 25 and check 23's alias collisions are precisely that defect, and a warning
  that explains a learner's own experience is worth reading out;
- an author asks, in a session that is fixing the bundle rather than teaching it.

Copying the text into the instance is unnecessary, and that is the reason the count is
enough: the instance is what produced the warnings, the check is deterministic, and
re-running it on the same directory prints them word for word whenever they are wanted.

#### Recording the outcome

Extend step 5's block with the validation keys:

```yaml
instance:
  materialized_from: local:../belay-bundles/rust-automaton-db
  materialized_version: "2.1"
  materialized_at: 2026-09-11
  runner_version: 1
  validated: 2026-09-12
  validation: pass            # pass | not-certified
  validation_warnings: 2      # omit the key when there were none
  validation_unchecked: [1]   # only with not-certified: what did not run
```

`validation: not-certified` is written in **two** cases, and in no others:

1. **an exit 3 the learner decided to start on anyway** (section 13.2 of
   `runner-protocol.md`). `validation_unchecked` then holds the check numbers that did not
   run — `[1]` above is check 1;
2. **a manifest-scope setup validator that failed at step 9, which the learner decided to
   continue past** (section 14.2 of `runner-protocol.md`). `validation_unchecked` then
   holds an entry of the form `setup:<validator name>` for each failed setup check —
   `validation_unchecked: [setup:cargo-check]`. The `setup:` prefix is the spelling
   `failure_modes.signals` already uses for `validator:<name>`, and it is what keeps one
   key readable when it carries both kinds: a bare number is a validator check, a prefixed
   name is a setup validator.

Case 2 amends a stamp that already exists, because step 9 runs after 3.1 has written one.
An instance that passed validation and then failed a setup check has `validation` changed
from `pass` to `not-certified` and the `setup:` entry added; `validated` keeps the date of
the validator run, which is what it records.

**A run that produced findings leaves no record at all.** That absence is deliberate and it
is what closes the hole: an instance whose stamp carries no `validated` key has never been
certified, so the next session that opens it runs the check before teaching rather than
assuming a check that never happened.

Also write one line into `STATE.md` under *Known intentional or incomplete state* whenever
the outcome was `not-certified`, naming what did not run and the reason given — for case 1
the checks and the validator's own reason, for case 2 the setup validator and the failure
it reported. It is the one entry in that section that describes the course rather than the
learner's code, and it earns its place: when a defect surfaces at lesson 7, the instance
itself says why nothing caught it. A pass writes nothing into `STATE.md`.

```
## Known intentional or incomplete state

- Setup check `cargo-check` failed at materialization and the course was started anyway:
  `error: linker `cc` not found`. Nothing has confirmed the placed skeleton builds, so a
  build failure in any lesson may predate the learner's work.
```

**Recording is not optional, and reporting without recording is not this precedent.**
`not-certified` exists for the record, not for the permission: an instance whose stamp says
`not-certified` and whose `STATE.md` names what did not run is the thing that makes a later
failure legible. Continuing past a failed setup check without writing the record is this
precedent with the load-bearing half removed.

#### When the course does not start

For exit 1, and for an exit 3 the learner chose not to start on:

- leave `tutorial/` where it is. It holds no progress, no lesson has opened, and removing
  a directory is not the runner's call — offer it, and do it only if the learner asks;
- place nothing. Step 8 never runs, so the learner's workspace outside `tutorial/` is
  exactly as it was;
- write nothing into `STATE.md`, and leave `status` as the template set it;
- do not repair the instance, do not skip the lesson a finding names, and do not draft a
  replacement for it. Section 8 permits writing a lesson when the course works and the
  learner needs something it does not cover; it permits nothing when the course is broken.

A repair belongs in the bundle, not in the instance. An instance patched into shape leaves
the defect in the course everyone else takes, and leaves this learner taking a course
nobody else is taking. When the bundle is local and the learner's own, the way forward is
to correct it there and materialize again — which is this section from step 1, once the
learner has chosen to remove the `tutorial/` this attempt left, since the command never
materializes over one.

### Workspace kinds

| `workspace_kind` | What the runner needs |
|---|---|
| `existing-or-new-repository` | use the learner's current repository, or create a directory if they prefer a fresh start. Ask which. |
| `new-repository` | a fresh, empty repository. Do not materialize into a workspace that already holds a project. |
| `none` | any plain directory. `learner_owned` is empty; there is no code to protect. |

Creating the workspace itself — initialising a repository, creating a project skeleton —
is the learner's action unless they ask you to do it, with one qualification: files the
bundle **declares** in `supplies` are the runner's to place, not a skeleton the learner
builds, however much they look like one. Materializing `tutorial/` is yours.

### 3.2 Updating an instance from a newer bundle

**The learner starts this. The runner never does, and never applies any part of it by
itself** (design spec section 15c). `DESIGN.md` holds decisions the learner made during the
course, and `lessons.generated/` holds lessons written for this learner. No version of the
bundle can rebuild either. A resume may *say* that the course has a newer version
(`runner-protocol.md` section 1, **A resume may say the course has moved on**). This section
begins only when the learner asks for the update.

An update is a second, partial materialization into the same instance. It compares the file
set that step 2 copies, writes the stamp that step 5 writes, places supplies by step 8's
rules, and ends with the validation that 3.1 runs. That is why it is part of section 3 and
not a section of its own.

It never touches `STATE.md` beyond the lines named below, never touches
`lessons.generated/` or the learning record `EVENTS.jsonl` (section 12), and never touches
anything outside `tutorial/` except by step 8's create-only placement.

#### Plan it

From the workspace root, run:

```
belay-plan-update tutorial
```

The bundle is the source the stamp's `materialized_from` names, and the command reads it
inside its own process; you never name the bundle directory, for the reason section 3
gives. When the learner wants the update from somewhere else — a catalogue they added, or a
local checkout they registered — add `--from-catalogs`: the command then takes the bundle
the learner's catalogues offer for this course's `id`, resolved as `belay-catalogs resolve`
resolves it, without fetching. Run `belay-catalogs discover` first when the newer version
has to be fetched; for a Git catalogue that also refreshes the clone the stamp names.

The plan reads both directories and writes nothing. It prints the two versions, the bump
(`MINOR` or `MAJOR`), the review mode, and one class for every file that materialization
copies: `tutorial.yaml` (compared without the `instance:` block), `COURSE.md`, `DESIGN.md`,
and every file under `lessons/`.

| Exit | Meaning | What the runner does |
|---|---|---|
| 0 | nothing to do: the same version, and every file the same | tell the learner the instance is current |
| 1 | a plan | show it to the learner, below |
| 2 | usage or I/O error | correct the invocation. Never report it to the learner as a problem with their course |
| 3 | refused, or the source cannot be resolved: the stamp is missing or unparseable, it names no `local:` source, or the source is not there | copy nothing. Say what the report names |

The same command has three more modes, all from the workspace root and all with the same
`2` and `3`:

| Command | Does | Exit |
|---|---|---|
| `belay-plan-update tutorial --diff <file>` | prints a unified diff of one file the plan lists, the learner's copy against the bundle's; `tutorial.yaml` is compared without its `instance:` block. Writes nothing | 0 the same, 1 different |
| `belay-plan-update tutorial --apply [--take <file>]... [--take-replace]` | applies the update: below, **Apply it** | 0 applied, or nothing to apply |
| `belay-plan-update tutorial --check-version` | says whether the source's `version` is later than the stamp's; `runner-protocol.md` section 1. Writes nothing | 0 not behind, 1 behind |

`--from-catalogs` works with each of them.

The script refuses when the learner's place would not survive the update. It refuses when
`active_lesson` or `resume_at` names a lesson file that the new bundle lacks, and when a
generated lesson's `after:` names a lesson that the new `lessons` list lacks. The report
names the file in each case. It also refuses when the bundle is a different course, when
the bundle's version is older than the instance's, when either manifest or the `STATE.md`
frontmatter does not parse, and when `active_lesson` is already inconsistent in the way
section 7 lists. Repair that first. A refusal over the active lesson usually clears when the
learner finishes that lesson. Until then, the learner can carry on unchanged.

#### Started and completed

The plan decides which lessons the learner has worked in from what `STATE.md` and the
instance's manifest already record. It applies this rule, and only this rule:

1. `status: not-started` — no lesson has been started.
2. `status: complete` — every entry in `lessons` is completed.
3. Otherwise, take the **anchor**. The anchor is `active_lesson` when that is an entry in
   `lessons`. While a detour is active (sections 8.3 and 9.3), the anchor is `resume_at`.
   An entry before the anchor in `lessons` is completed, the anchor is active, and an entry
   after the anchor is not started. `lessons` is the order, as in section 5 step 3.
4. The file that `active_lesson` names is active, whatever kind of path it is.
5. Anything else is **unrecorded**: an optional lesson that is not active, or a file that is
   in no list. The *Optional lessons* body section is prose, and this rule does not read it.

A file in a lesson folder takes its lesson's state. On a boundary detour the anchor has not
been begun yet. `STATE.md` cannot tell that case from a mid-lesson detour (the table in
section 8.3), so the anchor counts as active in both cases. Where the records cannot decide,
the answer is that the learner decides, never that the file is replaced.

#### The classes

| Class | The file | What happens to it |
|---|---|---|
| `unchanged` | is the same on both sides | nothing |
| `replace` | differs, and is `COURSE.md`, `tutorial.yaml`, or part of a lesson not started | taken from the bundle |
| `decide-completed` | differs, in a lesson the learner completed | the learner decides |
| `decide-active` | differs, in the active lesson | the learner decides |
| `decide-unrecorded` | differs, and is in a lesson the records cannot place, or in no lesson | the learner decides |
| `decide-design` | is `DESIGN.md`, and differs | the learner decides |
| `added` | exists only in the bundle | copied |
| `removed` | exists only in the instance | deleted |

**There is no common ancestor.** The instance keeps no copy of the bundle as it was at
materialization. When a file differs, the plan cannot tell whether the author changed it,
the tutor changed it, or both did, and it does not try. A `decide-*` file is reported as
*different*. Show the learner the difference itself, from
`belay-plan-update tutorial --diff <file>`, and do not describe which side made it.

#### Show it, and ask

Ask before anything is copied, whatever the bump is.

- **Review `one-change-set`** (a MINOR bump): show the whole plan in one message. One answer
  applies every `replace`, `added` and `removed` file, and the stamp.
- **Review `per-file`** (a MAJOR bump, or a MINOR bump whose `lessons` list lost or reordered
  entries — the plan says which): show each `replace`, `added` and `removed` file with its
  difference. The learner answers each `replace` file except `tutorial.yaml`.
- **Each `decide-*` file gets its own answer in both modes**, with its difference shown.
  The learner keeps their copy or takes the bundle's. For `DESIGN.md` there is a third
  answer: you draft a merged file, the bundle's text plus the learner's own additions, and
  the learner approves the draft before it is written. `DESIGN.md` is never overwritten
  without that answer.

`tutorial.yaml`, the `added` files and the `removed` files move together. Check 4 requires
the manifest and `lessons/` to agree, so the learner cannot keep the old manifest with new
lessons, or a lesson the new manifest no longer lists. When the learner declines those,
they decline the update. Nothing is copied, and the instance stays exactly as it was.

#### Apply it

Only what the learner accepted, in this order, while the bundle source is still in reach.
Steps 1 and 2 are one command:

```
belay-plan-update tutorial --apply --take <file> --take <file> ...
```

Name with `--take` each `replace` and `decide-*` file the learner took the bundle's copy of,
and only those. In a `one-change-set` review, `--take-replace` takes every `replace` file
instead of naming each. Do not name `tutorial.yaml`, an `added` file or a `removed` file:
they move together, so the command always applies them, and a learner who declined them
declined the update — do not run `--apply` at all. A `DESIGN.md` merge the learner approved
is not taken: write the approved draft into `tutorial/DESIGN.md` yourself, with the Edit
tool, after the command. The command makes the plan again first and applies nothing when it
is refused (exit 3), or when the plan names a file it may not take (exit 2). It writes only
inside `tutorial/`, and it prints what it took, deleted and kept, and the new stamp.

1. **Copy and delete.** It copies each accepted file from the bundle, every `added` file,
   and deletes each `removed` file, with any lesson folder the deletions left empty. Last,
   it writes the bundle's `tutorial.yaml` with the `instance:` block appended, so an apply
   interrupted part-way still carries the old stamp and the next plan shows what is left.
2. **Rewrite the stamp.** It sets `materialized_version` to the bundle's `version`, in quotes,
   or to `"1.0"` when the bundle declares none, and sets `materialized_at` to today. It sets
   `materialized_from` to the source it used, which changes it only under `--from-catalogs`.
   The instance's own `version` and
   `materialized_version` now hold the same value. Check 30 reports a finding when they
   differ, because that is what a half-applied update looks like. It removes `validated`,
   `validation`, `validation_warnings` and `validation_unchecked`, and keeps any `setup:`
   entry from `validation_unchecked` together with `validation: not-certified`, because an
   update re-runs no setup check. The stamp is the command's rather than yours because it
   is written from the same values as the copied manifest, in the same write: the two
   cannot then disagree, which is the defect check 30 exists to catch.
3. **Validate**, exactly as section 3.1 describes, and record the outcome there. A finding
   stops teaching, as at materialization. The defect is in the bundle, so report it and do
   not repair it in the instance.
4. **Place supplies** by step 8: `belay-catalogs place-supplies`, which reads the source
   from the stamp just rewritten. Step 8 never overwrites, so this
   places only an entry the new bundle added, and it says nothing about the entries
   already in place.
5. **Update `STATE.md`, and nothing else in it.** Set `updated` to today. When the plan
   printed a `note:` about an *Optional lessons* entry for a lesson the bundle no longer
   offers, remove that entry and say so. Do the same for each `note:` about an
   *Assessments* row: remove a row whose lesson is no longer an assessment, rewrite a
   scope that names a lesson the bundle no longer has in words, and say so. For each
   differing file the learner kept, add one
   line under *Known intentional or incomplete state*, for example "`lessons/00-hello-args.md`
   kept at its 1.0 text when the course moved to 1.1 on 2026-10-14, by the learner's
   choice". The next plan reports that file as different again, and this line explains
   why. `active_lesson`, `resume_at`, the completed lessons and every body section stay as
   they were. An update changes the course text and never changes the learner's progress.
6. **Say what changed**: the new version, which files were taken, and which were kept.
   When the active lesson was replaced, read it again before the next task. If its
   completion conditions changed, tell the learner before you state the next task.

---

## 4. What a completed task updates

After a task validates successfully, and not before:

1. **Last completed task** — replace with what was just demonstrated. One or two
   sentences, concrete enough that a fresh session knows what exists now. "Moved `Table`,
   `Row` and `Cell` into `src/lib.rs` with `pub` where the binary needs them;
   `cargo test` 5/5" beats "did the refactor".
2. **Concepts demonstrated** — append any concept the learner actually used. Do not
   append concepts you explained and they did not apply.
3. **Decisions made in discussion** — append a choice the learner made that later lessons
   depend on. A decision about the *subject* that is durable belongs in the instance's
   `DESIGN.md` instead; this section is for the smaller choices that shape the rest of
   this run.
4. **Known intentional or incomplete state** — add a deliberate gap, remove one that has
   been closed. This is where "`Table::get` is commented out on purpose" lives, so the
   next session does not report it as a bug.
5. **Accepted warnings** — add, expire or remove entries per section 6.
6. **Next task** — replace with the single next task.
7. **Deferred items** — add anything explicitly postponed, with the reason. An intention
   that exists only in the conversation is lost at the end of the session.
8. **`updated`** — set to today.

`active_lesson` does **not** change when a task completes. Only a completed lesson moves
it.

---

## 5. What a completed lesson updates

Only once the lesson's own completion conditions are met and confirmed — the procedure is
in `runner-protocol.md` section 6.

1. **Persist what the lesson names.** The lesson's *On completion, persist* section says
   what to append to the instance's `DESIGN.md`, under which anchor. Append; do not
   rewrite existing sections, and do not renumber or rename anchors — lessons reference
   them by name.
2. **Expire acceptances** whose `until_lesson` is the lesson being left or the lesson
   being entered. Remove them and say what they were covering.
3. **Advance `active_lesson`.** Find the current value in the manifest's `lessons` list
   and take the **next entry in that list**. The list is the order. Filename sort is not
   the order, lesson `id` is not the order, and the number prefix is a convention rather
   than a rule. When the instance has a `lessons.generated/` directory, an incomplete
   generated lesson whose `after:` is the lesson just finished comes first instead —
   section 8, and `runner-protocol.md` section 7.3. **An optional lesson is never reached
   by advancing.** It is not in `lessons`, so this step cannot arrive at one; the only way
   in is an accepted offer, section 9.3.
4. **Reset the body for the new lesson.** *Last completed task* becomes the lesson
   completion. *Next task* becomes the first task of the new lesson. *Concepts
   demonstrated* and *Decisions made in discussion* accumulate across lessons — do not
   clear them. *Known intentional or incomplete state* carries forward only what is still
   true.
5. **`updated`** — set to today.

### Reaching the end

When the completed lesson is the last entry in `lessons`, leave `active_lesson` on that
entry and set `status` to `complete`. Do not point `active_lesson` at a lesson that does
not exist, and do not invent an extra lesson. Say what the learner built and which
concepts they demonstrated.

Then offer what could come next (`runner-protocol.md` section 12). That offer writes
nothing here — section 10.4 — and a course with nothing after it, or with a recommended
course that is not on this machine, is still complete.

---

## 6. Accepted warnings

`accepted_warnings` lives in the body of `STATE.md`, as a YAML block:

```yaml
accepted_warnings:
  - pattern: "is never used"
    reason: "Engine unreachable from the binary while main() is empty"
    until_lesson: lessons/03-first-refactor.md
```

| Field | Meaning |
|---|---|
| `pattern` | text that identifies the warning |
| `reason` | why this is currently acceptable, in the learner's terms |
| `until_lesson` | the lesson path at which the acceptance expires |

Rules:

- **`until_lesson` is mandatory.** An acceptance with no expiry becomes permanent cover
  and makes the underlying rule unenforceable. Choose the lesson that removes the cause.
- **Never put this in `tutorial.yaml`.** Validator *definitions* are configuration and
  belong in the manifest. Which warnings are currently tolerated is progress, and belongs
  here.
- **The learner accepts, you record.** Do not accept a warning on the learner's behalf to
  make a validator quieter.
- **Expiry is checked against the active lesson.** The matching procedure is in
  `runner-protocol.md` section 4.

---

## 7. Repairing a stale or inconsistent `STATE.md`

`STATE.md` can fall behind the workspace — a learner works between sessions, or a session
ended without recording. When `STATE.md` and the source disagree, **the source wins**.

Procedure:

1. measure. Inspect the actual files and run the declared validators. Do not infer the
   state from what `STATE.md` claims, and do not infer it from what the lesson expected.
2. say what you found and how it differs from the record.
3. rewrite the affected sections to match what you measured, including `active_lesson` if
   the learner has plainly moved on or plainly not started what was recorded.
4. record nothing you did not measure.

The learning record (section 12) is never a source for this repair. It is evidence, not
progress, and it cannot be measured against the workspace.

The failure this avoids: a resume marker that describes work the learner finished two
lessons ago sends the tutor to re-teach it. A marker that describes work they have not
started lets the tutor assume it exists.

### Inconsistencies to report rather than repair

- `active_lesson` names a path that is in none of three places: the manifest's `lessons`
  list, the manifest's `optional_lessons` map, or `lessons.generated/` (sections 8.3 and
  9.3 permit the last two, and only with `resume_at` set);
- `active_lesson` names a generated lesson that is not there, or names one while
  `resume_at` is absent or is not an entry in `lessons`;
- `active_lesson` names an optional lesson while `resume_at` is absent, or while
  `resume_at` is not an entry in `lessons`;
- the *Optional lessons* section records a path that is not a key in the manifest's
  `optional_lessons`;
- an *Optional lessons* entry is recorded `in-progress` while `active_lesson` names
  something else. One of the two is wrong and nothing in the file says which;
- a file under `lessons.generated/` whose `after:` is not an entry in `lessons`, or which
  is missing any of the five provenance fields;
- an *Assessments* row names a path that is not a lesson declaring `assesses`, holds a
  state other than the four of section 11.2, appears twice, or records something other
  than concept ids under "not demonstrated";
- `tutorial_id` does not match the manifest's `id`;
- `STATE.template.md` is present in the instance;
- the manifest names a lesson file that does not exist.

Section 10.5 adds two more, for the assumed-concept stamp.

These are structural defects, not stale progress. Guessing at the intent will lose the
learner's place. Say what is wrong and let the learner decide.

---

## 8. Generated lessons

A tutor may write a lesson **during** a course, into `tutorial/lessons.generated/`. This
section is the mechanics. Whether to write one at all is the harder half, and it is in
`runner-protocol.md` section 7 — settle that question there before creating any file here.

### 8.1 Where they live

```
tutorial/
├── tutorial.yaml
├── COURSE.md
├── DESIGN.md
├── STATE.md
├── EVENTS.jsonl          the learning record, section 12; tutor-owned, may be absent
├── lessons/              the author's lessons, copied at materialization, read-only
└── lessons.generated/    lessons the tutor wrote during this course, tutor-owned
```

`lessons.generated/` exists **only in an instance**. It is never part of a bundle, it is
never created by materialization, and it does not exist until the first generated lesson
needs it.

It is tutor-owned in every instance, whether or not the manifest's `tutor_owned` lists it.
A bundle cannot list a directory that belongs to an instance it has never seen, so
ownership of this one path is settled by the runner and not by the manifest.

### 8.2 Creating one

1. **Settle the case for generating at all** — `runner-protocol.md` section 7.2. A defect
   in the bundle is reported, never drafted over.
2. **Create `tutorial/lessons.generated/`** if it is not already there.
3. **Choose a slug that names the concept** — `lifetimes-and-borrows`, not `03b` or
   `extra-lesson`. It SHOULD NOT reuse the `id` of a lesson in `lessons/`: the format
   permits the overlap, but two lessons with one `id` make the record in section 8.5 and
   any later promotion ambiguous. Give it no number prefix — position comes from `after:`,
   never from the name.
4. **Create `tutorial/lessons.generated/<slug>.md` with the ordinary lesson structure** —
   purpose, prerequisites, learning objectives, theory, concepts to teach, constraints,
   suggested progression, completion conditions, on completion persist.
   `bundle-format.md` section 6 defines that shape and a generated lesson does not get a
   lighter one. A lesson with no completion conditions is a lesson you cannot decide to
   leave.
5. **Add the provenance frontmatter** below, alongside the ordinary lesson fields.
6. **Record the way back before you teach a word of it.** Set `active_lesson` to the
   generated lesson and `resume_at` to the lesson the learner returns to — section 8.3.
   Record it now, while you still know where the learner was standing; a session that
   starts after the detour cannot recover it.
7. **Say what you wrote and why, before teaching it.** A lesson that appears in the
   learner's workspace unannounced is indistinguishable from the course changing
   underneath them. For a `main-path-draft` this is not optional and not a footnote:
   `runner-protocol.md` section 7.4 says what the learner must be told, and when.

A generated lesson SHOULD be a single file. It MAY be a folder containing `LESSON.md` when
it genuinely ships material, and every folder rule then applies unchanged: exact case, and
material is invisible until the body names it.

#### Provenance frontmatter

```yaml
---
id: lifetimes-and-borrows
title: Lifetimes, just enough to unblock the borrow
generated: true
generated_at: 2026-09-11
kind: side-lesson            # | main-path-draft | practice
reason: "The borrow in Table::get_cell_at cannot be explained without lifetimes"
after: lessons/03-first-refactor.md
design_refs: [row-cell-model]
validators: [cargo-check]
---
```

| Field | Required | Meaning |
|---|---|---|
| `id` | MUST | The slug: file stem, or folder name. Unique across `lessons/` and `lessons.generated/`. |
| `title` | MUST | Human-facing lesson name. |
| `generated` | MUST | Always `true`. Marks the file as an overlay rather than an authored lesson. |
| `generated_at` | MUST | The date it was written. Orders two detours that share one `after:`. |
| `kind` | MUST | `side-lesson`, `main-path-draft`, or `practice` — written after an assessment, on the concepts it found not demonstrated (section 11.5). |
| `reason` | MUST | One sentence, written for a bundle author who was not in the room. When the learner asked for this lesson rather than you judging it necessary, `reason` MUST say so and say what they asked for — the two mean different things about the course. This is the evidence `bundle-format.md` section 8 depends on. |
| `after` | MUST | Where this lesson belongs in the course sequence: the authored lesson it follows. MUST be an entry in the manifest's `lessons` list — an authored lesson, never another generated one. |
| `design_refs` | SHOULD | Anchors that already exist in the instance's `DESIGN.md`. |
| `validators` | SHOULD | Names already declared in the manifest's `validators` map. |

Never invent a validator name or a `DESIGN.md` anchor for a generated lesson. Either one
manufactures exactly the defect `runner-protocol.md` section 7.2 tells you to report, and
it would then be your own defect.

#### `after:` is placement, not the way back

`after:` answers one question only: **where does this lesson belong in the course?** A
bundle author reading the instance later uses it to decide where a promoted lesson goes
(`bundle-format.md` section 8), and the runner uses it to decide which detours are waiting
at which point in `lessons`.

It does **not** say where the detour returns to. That is `resume_at` in `STATE.md`, it is
a separate field, and section 8.3 sets it explicitly. Do not compute one from the other in
either direction.

How to choose `after:`:

| The detour starts | `after:` is |
|---|---|
| part-way through lesson L, because L needs a concept the course never taught | the last **completed** authored lesson — the detour belongs **before** L, because L depends on it |
| part-way through lesson L, on a topic L does not depend on (a learner asked for it) | L — nothing in L needs it, so it belongs after L |
| at a boundary, after L completed and before the next entry began | L |

When the learner is part-way through the **first** entry in `lessons`, no authored lesson
is complete and there is no earlier entry to name. Use that first entry.

### 8.3 `active_lesson` may point into `lessons.generated/`

While a detour is active, `STATE.md` looks like this:

```yaml
---
tutorial_id: rust-automaton-db
active_lesson: lessons.generated/lifetimes-and-borrows.md
resume_at: lessons/04-storage-engine.md
status: in-progress
updated: 2026-09-11
---
```

| Field | Meaning | Constraint |
|---|---|---|
| `resume_at` | the `lessons` entry to make active when the detour finishes | present exactly while `active_lesson` names a generated lesson or an optional lesson; absent otherwise |

**This is one of the two exceptions to "`active_lesson` MUST appear in the manifest's
`lessons` list"** — the other is an optional lesson, and it works identically (section
9.3). A path under `lessons.generated/` is deliberately not in the list, and the
presence of `resume_at` is what says so. Everything else about the field is unchanged:
it is a path, it is the file a cold session opens, and it is still the single field that
makes a conversation with no history work.

**The field names the lesson to make active, not a lesson to move past.** `resume_at:
lessons/04-storage-engine.md` means lesson 04 becomes the active lesson. It does not mean
"the lesson after 04". The example above is a detour taken part-way through lesson 04: the
learner goes back into 04 and finishes it.

#### Recording it

**Set `resume_at` when the detour becomes active, not when it finishes**, and write the
value you already know rather than one you derive. `after:` records placement and
`resume_at` records the way back; they are independent fields and neither is computed from
the other.

| The detour starts | `resume_at` is |
|---|---|
| part-way through lesson L | **L** — the interrupted lesson. The learner has unfinished work in it |
| at a boundary, after L completed and before the next entry began | the entry **after** L in `lessons` |

`resume_at` MUST itself be an entry in `lessons`: a detour returns to the main path, never
to another detour. Recording it once, at the moment you know it, is what stops a later
session guessing.

When there is nothing further to return to — a boundary detour off the **last** entry in
`lessons` — set `resume_at` to that last entry anyway, so the field stays a real lesson
path, and when the detour completes set `active_lesson` to it with `status: complete` —
the course is finished, per section 5, "Reaching the end". Do not re-teach it.

> **Do not derive `resume_at` from `after:`.** An earlier revision of this document said
> the value was "the entry after the detour's `after:` in `lessons`". That rule silently
> skips work. A learner who is halfway through lesson L and needs a prerequisite has only
> one lesson they can be sent back to — L — and any rule that returns them to the entry
> *after* L throws away the rest of a lesson they never finished, with nothing in
> `STATE.md` recording that it happened. Mid-lesson detours are ordinary: being blocked on
> an untaught prerequisite happens mid-lesson by definition, and a learner may ask for a
> side lesson at any moment (`runner-protocol.md` section 7.1).

### 8.4 Completing a generated lesson

A detour completes like any other lesson, and then hands the learner back:

1. **Check the completion conditions you wrote**, individually and with evidence, per
   `runner-protocol.md` section 6. They bind because they are completion conditions, not
   because of who wrote them.
2. **Persist what the lesson's *On completion, persist* section names** into the
   instance's `DESIGN.md`, under an anchor that exists.
3. **Record the lesson complete** in `STATE.md`, per section 8.5. This is what lets a
   cold session answer "is this generated lesson incomplete?" without reading every file.
4. **Return to the main path.** Set `active_lesson` to `resume_at` and remove the
   `resume_at` field. One exception: when another incomplete generated lesson shares
   this detour's `after:` value, that one becomes `active_lesson` instead — oldest
   `generated_at` first — and `resume_at` carries over unchanged. The learner has not
   moved, so the place they come back to has not changed either.
5. **Set the body for wherever the learner lands.** *Concepts demonstrated* accumulates as
   usual either way; what the detour taught stays recorded.
   - **Returning into an interrupted lesson** — `resume_at` names the lesson that was
     active when the detour began. Do not reset the body. The learner has unfinished work
     in that lesson, and *Next task* is the task the detour interrupted, restated with
     whatever the detour changed about it.
   - **Returning to a lesson not yet started** — reset the body for a new lesson, per
     section 5 step 4.
6. **`updated`** — set to today.

**Never delete a generated lesson when it completes.** It stays in the instance as both
the record of what this learner needed and the evidence a bundle author acts on —
`bundle-format.md` section 8.

### 8.5 What `STATE.md` records

One extra body section, present only in an instance that has generated lessons. A fresh
instance does not have it, and `STATE.template.md` never does:

```markdown
## Generated lessons

- `lessons.generated/lifetimes-and-borrows.md` — side-lesson, after
  `lessons/03-first-refactor.md` — complete
- `lessons.generated/wal-recovery-draft.md` — main-path-draft, after
  `lessons/07-storage-engine.md` — pending
```

Each entry carries the path, the `kind`, the `after:` value, and `complete` or `pending`.
Nothing else: the reason lives in the lesson's own frontmatter, and a second copy here
would be a second thing to keep true.

This section exists because the advancement rule turns on the word *incomplete*
(`runner-protocol.md` section 7.3), and the lesson files deliberately carry no progress —
progress belongs in `STATE.md`, in one place, and a lesson that carries progress cannot be
promoted into a bundle.

### 8.6 The manifest's `lessons` list is NEVER mutated

When you write a generated lesson, do not add it to `lessons` in the instance's
`tutorial.yaml`. Do not reorder the list, do not remove an entry, and do not "fix" a path
in it. The temptation is real, and the damage arrives later, when nobody remembers.

`lessons` is the authored course. It stays identical for every learner who takes the
bundle, and that buys three things:

- **a later bundle revision stays reconcilable.** The instance's list and the bundle's
  list can be compared directly. Once a learner's list holds a private entry, nothing can
  tell an author's change from a tutor's;
- **two learners' courses do not diverge structurally.** They can take different detours
  and still be provably on the same course, because the overlay carries the difference and
  the list does not;
- **the overlay stays legible as an overlay.** A generated lesson merged into `lessons` is
  indistinguishable from an authored one within a session, and then nobody can tell what
  the course contains from what one tutor improvised.

The same holds for the rest of what the bundle wrote. In an instance, `COURSE.md` and
everything under `lessons/` are read-only. An update the learner asked for (section 3.2) is
the one thing that rewrites them. `DESIGN.md` is the one exception the format
already grants, and the tutor appends to it rather than rewriting it.

"Never mutated" includes the bundle source. Materialization copies once and teaching never
reaches back (section 3). Moving a generated lesson into a bundle is a separate,
deliberate authoring act with its own procedure — `bundle-format.md` section 8 — and
nothing in the teaching loop performs it.

---

## 9. Optional lessons

A bundle may ship **optional lessons**: authored lessons that live in `lessons/` with every
other lesson, are listed in the manifest's `optional_lessons` map rather than in `lessons`,
and are offered rather than sequenced (`bundle-format.md` section 2).

This section is the mechanics — what `STATE.md` records and what the frontmatter does.
Whether to offer, when to re-offer, and when to refuse are judgement, and they are in
`runner-protocol.md` section 8. Settle those there, exactly as section 8 above settles its
half in `runner-protocol.md` section 7.

### 9.1 What `STATE.md` records

One extra body section, present only once an optional lesson has been offered in this
instance. A fresh instance does not have it, and `STATE.template.md` never does:

```markdown
## Optional lessons

- `lessons/event-time-and-watermarks.md` — deferred — offered at
  `lessons/04-window-execution.md` on 2026-09-12
- `lessons/what-is-a-character.md` — complete — taken at
  `lessons/02-errors-and-tests.md` on 2026-09-14
```

Each entry carries the path, the state, and one clause saying where and when the last
decision happened and what prompted it. **Nothing else.** The risk the lesson addresses is
`offer_because`, the failures it anticipates are `anticipates`, and the lesson whose work
it repairs is `repair_in` — all three are in `tutorial.yaml`, which you load every turn. A
second copy here is a second thing to keep true, and it is the same argument section 8.5
makes about `reason:`.

When the last decision was a re-offer, the clause names the failure mode that prompted it:

```markdown
- `lessons/event-time-and-watermarks.md` — deferred — re-offered after
  `late-event-wrong-window` at `lessons/06-correctness-under-delay.md` on 2026-09-15
```

### 9.2 The five states

**Not yet offered is the absence of an entry.** Do not write a `not-offered` line: a course
carrying twelve optional lessons would then open this section with twelve lines saying that
nothing has happened, and the one question the section answers — *what has this learner been
offered?* — would be answered in noise.

The four that are written:

- **`offered`** — you asked and have no answer yet. It normally lives for part of one turn.
  Record it when the turn ends before the learner answers, so a cold session knows a
  question is outstanding rather than asking it a second time.
- **`deferred`** — the learner said not now. The clause MUST name the lesson the offer was
  made at and the date. Both the anti-nag rule and the re-offer depend on knowing that the
  offer happened and where (`runner-protocol.md` sections 8.3 and 8.5); an entry that omits
  either records a decision nobody can act on.
- **`in-progress`** — `active_lesson` names the lesson and `resume_at` is set. Both facts
  are in the frontmatter already. The record exists so that a cold session answers "what
  has this learner been offered" from one section, rather than by reasoning about which of
  three kinds of path `active_lesson` currently holds.
- **`complete`** — the lesson is finished. For an optional **assessment**, finished means
  passed: section 11.3. This is the state that stops it ever being
  offered again (`runner-protocol.md` section 8.8), so it MUST be written the moment the
  lesson completes, in the same step that records the completion.

  **`complete` is terminal, and nothing later in the course reverses it.** An anticipated
  failure that recurs after this lesson does not move the entry back to `deferred`, does
  not add a second entry, and does not license one more offer. Such a failure is ordinary
  coaching from then on, permanently. Recurrence is evidence that the author's lesson did
  not land — evidence for the quality checker and the dry-run harness, not something to act
  on against the learner mid-course. A `complete` entry that can be un-completed is a loop
  one iteration long, and the learner inside it is the person least able to leave it.

**Re-offering a `deferred` lesson updates the entry in place.** It never adds a second one.
This section records the current state of each offer, not a history of offers, and one
lesson has one entry for the life of the instance.

### 9.3 Accepting an offer

1. `active_lesson` becomes the optional lesson's path.
2. `resume_at` becomes the lesson the learner is standing in. That is section 8.3's rule
   and not a second one: the way back is recorded at the moment the detour starts, from
   where the learner actually is. Never derive it from `repair_in`, and never from
   `offer_at`.
3. the *Optional lessons* entry becomes `in-progress`.
4. **`updated`** — set to today.

Do not reset the body. The learner has unfinished work in the lesson they were standing in,
and section 8.4 step 5 is the same situation with the same instruction.

An accepted offer and the generated-lesson advancement in section 8.4 cannot collide. An
accepted offer takes effect in the turn the learner accepts; generated-lesson advancement
applies when a lesson completes and no detour is active. Nor can the two name each other: a
generated lesson's `after:` MUST be an entry in `lessons`, and an optional lesson is never
in that list.

### 9.4 Completing one

Exactly section 8.4, with the *Optional lessons* entry in place of the *Generated lessons*
one:

1. **Check the completion conditions**, individually and with evidence, per
   `runner-protocol.md` section 6. The author wrote them; *optional* describes how the
   learner arrived, not how the lesson is left.
2. **Persist what the lesson's *On completion, persist* section names** into the instance's
   `DESIGN.md`, under an anchor that exists.
3. **Record the entry `complete`** (9.2).
4. **Return to the main path.** `active_lesson` becomes `resume_at`, and the `resume_at`
   field is removed.
5. **Do not reset the body.** `resume_at` always names the lesson the learner was standing
   in, and that lesson's body was set when they arrived in it — whether or not they had
   begun a task there. *Next task* becomes the repair `repair_in` names, stated in terms of
   the lesson that built the work (`runner-protocol.md` section 8.6); where there is nothing
   to repair, it is the task the detour interrupted. *Concepts demonstrated* accumulates as
   usual, and what the optional lesson taught stays recorded.
6. **`updated`** — set to today.

Step 4 carries no exception here. Section 8.4's exception is for a second generated lesson
sharing one `after:` value, and an optional lesson has no `after:`.

### 9.5 What this section does not hold

`repair_in` is in the manifest and is **never** copied into `STATE.md`. It is the same for
every learner, it does not change while a course is taken, and it is read at one moment —
when the detour completes and you state the first task on landing. The same holds for
`offer_because`, `anticipates` and `required_for`. `STATE.md` records what happened to this
learner; the manifest records what the course offers.

---

## 10. The assumed-concept acknowledgement

A course MAY declare `assumes` — the concepts it uses without teaching them from first
principles. The runner shows that list once, before the first task, and the learner
answers. Whether to show it, what the list looks like, and what the three answers are is
judgement, and it is in `runner-protocol.md` section 11. This section is the mechanics.

> **Named bundles are recommendations. Concepts are the educational contract. Neither one
> gates access to a tutorial or requires proof that another bundle was completed.**

### 10.1 One optional frontmatter field

```markdown
---
tutorial_id: streaming-query-engine
active_lesson: lessons/00-a-query-that-runs-forever.md
status: in-progress
updated: 2026-09-12
assumes_reviewed: 2026-09-12
---
```

| Field | Meaning | Constraint |
|---|---|---|
| `assumes_reviewed` | the date the assumed-concept list was shown and the learner chose to continue | a date. Present only after that happened; absent otherwise |

Its **absence** is the whole of "not yet acknowledged", and its **presence** is the whole
of "acknowledged". There is no third value, nothing to expire, and nothing to update
afterwards — unlike `resume_at`, which is set and later removed, this field is written
once and then stays.

Two rules hold it to one meaning:

- **A course that declares no `assumes`, or an empty one, never gets the field.** Do not
  write it to record that there was nothing to show. An absent field on such a course is
  read the same way by everything: there is no review due, because there is no list.
- **`STATE.template.md` never carries it.** A template describes a learner who has not
  started, so no review can have been shown. A bundle shipping a stamped template would
  suppress the review for every learner who ever takes the course. Materialization is
  where the field can first appear, and only once the learner has answered.
- **Never remove it, and never rewrite it.** Re-showing a review the learner already
  answered is the behaviour the field exists to prevent.

### 10.2 What it asserts, and what it does not

It asserts exactly one thing: **the list was shown, and the learner chose to continue.**

It does **not** assert that the learner knows any of the concepts. It records no mastery,
no completion of any other course, no entitlement, and no claim about anything outside
this instance. Continuing acknowledges the wish to proceed and nothing more, and section 1
of this document applies unchanged — progress is recorded only when it is demonstrated,
and nothing was demonstrated here.

This is why the field is a stamp rather than a body entry, and why nothing else in
`STATE.md` moves when it is written:

| Tempting | Why not |
|---|---|
| appending the assumed concepts to *Concepts demonstrated* | the learner demonstrated nothing. That section holds concepts they used, never concepts they were shown |
| recording "chose to continue" under *Decisions made in discussion* | that section holds choices later lessons depend on, and no lesson depends on this one. It would also have to be matched as prose to answer a yes-or-no question, which is what the frontmatter field avoids |
| a new body section for one fact | a whole heading, present in every instance of every course that declares `assumes`, to hold one date. Section 9.2 makes the same argument about writing `not-offered` lines |
| a `prerequisites_met` or `assumes_confirmed` field | both name a claim nobody made. The learner confirmed nothing about themselves |

### 10.3 Writing it

In the turn the learner chooses to continue:

1. set `assumes_reviewed` to today;
2. set `updated` to today;
3. state the first task.

Nothing else changes. `active_lesson` does not move, `status` follows materialization as
it always has, and no body section is touched.

A digression before the answer — a question about one concept, or a query for courses
covering some of them — writes **nothing at all**. That is deliberate, and it is what makes
the way back free: `active_lesson` still names the course's first lesson, so the pending
start is already recorded and needs no `resume_at`. Compare section 9.3, where accepting an
optional lesson *does* move `active_lesson` and therefore *must* record the way back.

### 10.4 Offering follow-ups records nothing

When a course finishes, or whenever the learner asks what could come next, the runner
offers follow-ups (`runner-protocol.md` section 12). **None of that touches `STATE.md`.**

There is no state to keep. Nothing was offered that the learner must answer, so nothing can
be outstanding; nothing expires; and asking again next session produces the same answer from
the same catalogues. This is the same reasoning section 3 gives for supplied files whose
targets already exist: where re-running the step is idempotent and the answer is derivable,
recording it creates a second thing to keep true.

In particular, a course that is `complete` stays exactly that. A follow-up the learner
declines, ignores, or never hears about changes nothing about the course they finished.

### 10.5 Inconsistencies to report rather than repair

Add these to section 7's list:

- `assumes_reviewed` is present while the instance's `tutorial.yaml` declares no `assumes`,
  or declares an empty one. Something wrote a stamp for a review that cannot have happened;
- `assumes_reviewed` holds something that is not a date.

Both are structural, both mean a record says something nobody can act on, and neither is
repaired by guessing. Say what is wrong and let the learner decide. Do not silently delete
the stamp: deleting it re-shows a review the learner may well have answered.

---

## 11. Assessments

An assessment is a lesson whose evidence is answers: its frontmatter declares `assesses`
(`bundle-format.md` section 6). A learner may also ask to be quizzed without one. How to
ask, judge and respond is in `runner-protocol.md` section 15; this section is what
`STATE.md` records. No second file is introduced: `STATE.md` stays the only place progress
is recorded.

### 11.1 What `STATE.md` records

One extra body section, present only once an assessment has been taken in this instance. A
fresh instance does not have it, and `STATE.template.md` never does:

```markdown
## Assessments

- `lessons/03-durability-check.md` — partial — last taken 2026-09-19,
  attempt 2; not demonstrated: fsync-boundaries ×2, crash-recovery
- _scope:_ `lessons/02-segments.md` — passed — last taken 2026-09-20, attempt 1
- _scope:_ `the course so far` — stopped — last taken 2026-09-21, attempt 1
```

**One row per assessment, updated in place.** Never append a row per attempt: that would
turn a section read every turn into a transcript.

- **The key.** An authored assessment is keyed by its lesson path, which MUST name a lesson
  in `lessons` or `optional_lessons` that declares `assesses`. A quiz the learner asked for
  has no lesson, so it is keyed by its scope after `_scope:_`: a lesson path when the scope
  is one lesson, otherwise the scope in words.
- **The state** — one of the four in 11.2.
- **The clause** — when it was last taken, the attempt number, and `not demonstrated:`
  followed by the concept ids the last attempt did not show. A `partial` row MUST name at
  least one.
- **The count.** `×N` after a concept counts the attempts in a row in which it was not
  demonstrated. Write it from the second such attempt on, as an integer greater than one;
  a concept that failed once carries no count. A concept the last attempt demonstrated is
  not listed, so a later failure of it starts again without a count.
  `runner-protocol.md` section 15.8 reads it, and it has to be recorded rather than
  derived: `assesses` lives in a lesson's frontmatter, and you load only the active
  lesson's, so for any other assessment this row is the only record.

**Concept ids, never answers.** The row records what was demonstrated, not what was said —
the signal kept apart from the content, as the design spec's section 16 requires. It also
keeps the every-turn read cheap.

Validator check 32 checks the shape of this section in an instance.

### 11.2 The four states

**Not yet taken is the absence of a row.**

- **`passed`** — the lesson's completion conditions were met.
- **`partial`** — at least one assessed concept was not demonstrated. A misconception is an
  answer outcome, not a state of the assessment; it appears as a concept under "not
  demonstrated", which is where practice reads it.
- **`stopped`** — the learner stopped before the end. **Never written as `passed`**, however
  much was demonstrated first.
- **`skipped`** — the learner declined a main-path assessment without taking it.

**`skipped` and `passed` are different states, and must never be written as each other.**
A skipped assessment read as a passed one is a record claiming evidence nobody gave.

Declining the offer of an optional assessment is *not* `skipped`. It is a deferral in
*Optional lessons* (section 9.2), and it writes no row here, because nothing was taken.

### 11.3 An assessment's completion is not terminal

An assessment can be retaken, so its row moves between the four states for as long as the
learner keeps returning to it. This is the one place an assessment diverges from other
lessons.

**On the main path**, leaving an assessment — whatever the result — completes it in
section 5's sense: write the row, then advance `active_lesson`. A weak result never holds
the learner back (`runner-protocol.md` section 15.7).

**In `optional_lessons`**, section 9.2 makes `complete` terminal, and that stays true here
by writing `complete` **only when the assessment is passed**. Leaving it at any other
result records the *Optional lessons* entry `deferred`, with a clause naming the result:

```markdown
- `lessons/retention-check.md` — deferred — left partial at
  `lessons/06-retention.md` on 2026-09-21
```

Returning to the main path is section 9.4 otherwise unchanged.

### 11.4 An interrupted assessment

An assessment in progress has no state of its own. Its row holds the result of the last
**finished** attempt, or is absent before the first, and is not touched until the current
attempt ends. The attempt in progress lives where any lesson's progress lives:

- *Last completed task* — the attempt number and what it has shown so far, by concept:
  "Assessment attempt 1: write-ahead-log demonstrated; fsync-boundaries partial, narrower
  question pending";
- *Next task* — the next question to ask;
- *Concepts demonstrated* — each concept as it is demonstrated, as for any lesson.

A session that ends here has interrupted the assessment, not stopped it. A cold session
opens `active_lesson`, reads those two sections, does not present the Theory again, and
asks the next question. Only the learner choosing to stop writes `stopped`.

### 11.5 A practice lesson

A practice lesson is a generated lesson (section 8) with `kind: practice`, written only when
the learner accepts practice after a weak result (`runner-protocol.md` section 15.7). Its
`reason:` names the assessment row and the concepts, for example "Practice on
crash-recovery after `lessons/03-durability-check.md`, attempt 1, partial".

- **`after:`** is the assessment, when it is in `lessons`. Otherwise — an optional
  assessment, or a quiz the learner asked for — it is the `lessons` entry the learner is
  standing in: `resume_at` while an optional lesson is active, else `active_lesson`.
- **`resume_at`** follows section 8.3. From a main-path assessment it is the assessment
  itself, so the detour returns into it for the retake. From an optional assessment the
  practice lesson takes over `active_lesson` and `resume_at` keeps its value, the main-path
  lesson the learner left; the *Optional lessons* entry becomes `deferred` first (11.3).
  From a quiz the learner asked for, it is the lesson they are standing in.
- It is recorded under *Generated lessons* with its kind, like any other.

---

## 12. The learning record

`tutorial/EVENTS.jsonl` records how the learner got where `STATE.md` says they are: how
many attempts a check needed, which checks failed repeatedly, which hints were given and
how far up the ladder, how each assessment answer was judged, and whether practice was
offered and taken. `STATE.md` records outcomes; this records attempts. When to write it and
when to read it is `runner-protocol.md` section 16.

### 12.1 Evidence, never progress

- **`STATE.md` stays the only authority for progress.** Nothing here moves
  `active_lesson`, completes a lesson or a task, or fills a section of `STATE.md`. When the
  two disagree, `STATE.md` is right and the record is simply incomplete.
- **It is tutor-owned in every instance**, like `lessons.generated/`, whether or not
  `tutor_owned` lists it. Materialization does not create it; the first event does. An
  update (section 3.2) never touches it.
- **It holds learning evidence, never a transcript.** Concept ids, validator names, lesson
  paths, enumerated values, counts and dates. No field holds free text, so learner code,
  answers and conversation cannot be written into it. This is the signal layer of the
  design spec's section 16; the content layer stays out.
- **The learner may read it, and may delete it,** at any time. Deleting it loses the
  evidence and nothing else: the course carries on from `STATE.md`.
- **Committing it** is belay#35's question, which also covers `STATE.md`. The provisional
  answer: the learner may commit it, since it holds no content.

### 12.2 Events

One JSON object per line, appended. Every event has four fields:

- `seq` — an integer, strictly increasing through the file, one more than the last;
- `date` — the calendar date, `YYYY-MM-DD`. No clock time: with `seq` a date orders the
  events, and a clock time says more about the learner than a course needs;
- `lesson` — the lesson path the event belongs to: an entry in `lessons`, a key in
  `optional_lessons`, or a path under `lessons.generated/`;
- `type` — one of the types below, which decides every other field. No other field is
  allowed.

| `type` | Fields beyond the four | Written when |
|---|---|---|
| `lesson_started` | none | a lesson becomes active, including a detour and a return into an assessment for a retake |
| `lesson_completed` | none | the lesson is completed in section 5's sense, an assessment left at any result included |
| `check` | `validator` (its name in the manifest), `result`, which is pass or fail | a lesson's validator has run; a validator that could not run writes nothing |
| `hint` | `rung` (1 to 5) | a rung of the help ladder is given |
| `answer` | `concept` (a concept id), `outcome`, and `requested` | an assessment answer is classified |
| `assessment` | `state`, `attempt`, `not_demonstrated` (concept ids), and `requested` | an attempt ends and its *Assessments* row is written |
| `practice_offered` | `concepts` (concept ids) | practice is offered after a weak result |
| `practice_accepted` | `concepts`, `practice_lesson` (its path under `lessons.generated/`) | the learner accepts it and the lesson is written |
| `summary` | `first_date`, `events`, `started`, `completed`, `checks`, `hints`, `answers`, `attempts`, `practice_offered`, `practice_lessons` | written only by compaction, 12.3 |

- **`outcome`** is one of the four answer outcomes of `runner-protocol.md` section 15.4:
  `demonstrated`, `partial`, `misconception`, `not-enough-evidence`.
- **`state`** is one of the four states of section 11.2: `passed`, `partial`, `stopped`,
  `skipped`. `skipped` and `passed` are different values here exactly as in `STATE.md`.
- **`requested`** is written, as `true`, only for a quiz the learner asked for (section
  11.1's `_scope:_` rows). Its `lesson` is the lesson the learner stands in, and the scope
  in words stays in `STATE.md`.
- **A `summary` holds counts:** `checks` maps a validator name to its `attempts` and
  `failures`; `hints` maps a rung to how often it was given; `answers` maps a concept id to
  a count per outcome; `attempts` lists each assessment attempt as its `state`, `attempt`,
  `not_demonstrated` and `requested`; `events`, `started` and `completed` count what was
  replaced; `first_date` and `date` are the first and last dates.

```json
{"seq":12,"date":"2026-09-14","lesson":"lessons/01-subcommands/LESSON.md","type":"check","validator":"cargo-test","result":"fail"}
{"seq":13,"date":"2026-09-14","lesson":"lessons/01-subcommands/LESSON.md","type":"hint","rung":2}
```

`scripts/evidence.py` holds this definition, and validator check 33 reads the record with
it.

### 12.3 Retention and compaction

**The cap is 2,000 lines.** An event is 90 to 160 bytes, so a full record is at most about
320 KB. A course of 23 lessons at 30 to 60 events each fits uncompacted; the cap is reached
by a learner who struggles long or retakes often. Nobody reads the file whole into a
conversation: `belay-evidence summary` reads it and prints counts.

At each lesson completion, after writing `lesson_completed`, run
`belay-evidence compact tutorial`. Under the cap it changes nothing but repairs
(12.4). Over the cap it replaces every event of each **completed** lesson by one `summary`
event, placed where that lesson's last event was, with its `seq` and `date`, so the file
stays in order without renumbering. A lesson is completed when it has a
`lesson_completed` event and is neither `active_lesson` nor `resume_at` in `STATE.md`. The
events of a lesson still in progress are kept as written. A lesson re-entered after
compaction, an assessment's retake, merges into its summary again at the next one.

After compaction the record is valid under the same check, and every question in 12.5
can still be answered for a completed lesson, at the precision of counts per lesson and
one entry per assessment attempt. When the events left are all of lessons in progress and
still exceed the cap, they are kept and the script says so.

### 12.4 Repair

Nothing about this record ever stops a course. Validator check 33 reports a malformed one
as a warning, never a finding.

| The record is | What happens |
|---|---|
| missing | normal before the first event. The next event starts the file, at `seq` 1 or wherever you are counting from |
| empty | normal; it holds no events yet |
| truncated — the last line has no line end and does not parse | an interrupted write. Run `belay-evidence compact tutorial` before the next append: it drops that line. Appending without it would join the new line to the fragment and lose both |
| inconsistent — a line is not an event, or `seq` does not increase | `compact` drops lines that are not events and renumbers from 1 in file order, and says so. Read the last line again before the next append |

When you would have used the record and it cannot answer — it is missing, or `summary`
reports lines it could not read — say what you cannot know, in a sentence, and carry on
from `STATE.md`.

### 12.5 What it answers

- **Attempts a check needed, and which failed repeatedly** — the `check` events, per
  validator and lesson.
- **Whether hints were used, and how far the ladder went** — the `hint` events' rungs.
- **How an assessment went** — its `assessment` events: `passed`, `partial`, `stopped` or
  `skipped`, per attempt, with what was not demonstrated.
- **Which misconceptions appeared** — `answer` events with the outcome `misconception`,
  by concept.
- **Whether practice improved the next result** — a `practice_accepted` event, then the
  next `answer` and `assessment` events on the same concepts, in `seq` order.
- **Elapsed time per lesson**, at date precision — from its `lesson_started` to its
  `lesson_completed`.
- **Where a course was abandoned** is not an event: nobody writes "I stopped". It is
  derived from the date of the last event and `STATE.md`'s `status` and `active_lesson`.
  A course `in-progress` whose last event is long past was left at `active_lesson`. There
  is no heartbeat, and you do not write one.
