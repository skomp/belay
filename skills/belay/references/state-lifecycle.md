# State Lifecycle — `STATE.md` From Materialization to Completion

**Status:** normative for the runner. Load this when materializing a new instance, the
first time in a session you are about to change `STATE.md`, when a task completes, when a
lesson completes, when an offer of an optional lesson is accepted or deferred, when the
learner acknowledges the assumed-concept review, or when you need to advance
`active_lesson`.

`STATE.md` is the only place a learner's progress is recorded. Nothing in the bundle
records progress; nothing outside `STATE.md` in the instance records it either. If you
find progress recorded in a second place, the second place is wrong.

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

All seven headings are always present, even when a section says "None". Two further
sections appear only once the instance needs them: *Generated lessons*, once a lesson has
been written into this instance (section 8.5), and *Optional lessons*, once one has been
offered (section 9.1).

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
- the entry's `source` has been resolved to a readable bundle directory;
- the workspace root is known, and satisfies the bundle's `workspace_kind`;
- there is no existing `tutorial/` in that workspace. If there is, stop — `tutorial/` is
  singular, and overwriting it destroys a learner's progress. Ask.

Steps, in order:

1. **Create the instance directory** `tutorial/` at the workspace root.
2. **Copy the bundle's files into it**: `tutorial.yaml`, `COURSE.md`, `DESIGN.md`, and
   `lessons/` in full, including lesson folders and their material. The instance is
   self-contained; teaching never reaches back into the bundle source afterwards.
3. **Convert the state file.** Copy `STATE.template.md` to `STATE.md` **in the instance**,
   then delete `STATE.template.md` from the instance. Both steps matter: an instance that
   still holds `STATE.template.md` is indistinguishable from a half-materialized bundle,
   and a validator in instance mode reports it.
4. **Initialise `STATE.md`.** Set `status` to `in-progress` when the first lesson begins,
   set `updated` to today, and confirm `active_lesson` equals the manifest's `lessons[0]`
   and `tutorial_id` equals the manifest's `id`. The template should already satisfy
   both; if it does not, the bundle is defective — report it rather than silently
   correcting.
5. **Stamp the instance.** Append one block to the *instance's* copy of `tutorial.yaml`:

   ```yaml
   instance:
     materialized_from: local:../belay-bundles/rust-automaton-db
     materialized_version: "2.1"
     materialized_at: 2026-09-11
     runner_version: 1
   ```

   `materialized_from` records the resolved source in provider-qualified form
   (`local:` plus the path, and for future provider types the equivalent locator).
   `materialized_version` records *which version* of that source this instance holds:
   copy the bundle's `version` exactly, in quotes, or write `"1.0"` when the bundle
   declares none (`bundle-format.md` section 2, **Content version**). A path has no
   version, so without this key the only way to tell whether an instance is behind its
   bundle is to compare every file. With it, the instance is behind when the bundle's
   `version` is greater than `materialized_version`, the two compared as pairs of
   integers, MAJOR first — `"2.10"` is later than `"2.9"`.
   This block is **provenance only**. Nothing in the teaching loop reads it. It exists so
   a learner, or a future update mechanism, can tell where the instance came from and
   which version of it. It never appears in a bundle. Section 3.1 adds three validation keys to this same
   block; those keys are the one part of the stamp anything ever reads, and what
   reads them is a session deciding whether this instance was ever checked — never a
   teaching turn.
6. **Verify the invariant**, by looking: the instance has `STATE.md` and does not have
   `STATE.template.md`. Say that you checked. **Then validate the instance, before
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
   has opened yet, and this is the one moment manifest-scope entries are placed. `from`
   is relative to the **bundle** root, and a trailing `/` means that directory's
   contents, recursively; `to` is relative to the **workspace** root and never inside
   `tutorial/`.

   **Take each `from` from the bundle source, not from the instance, and finish this step
   before you release the source.** That is why step 8 is *inside* materialization rather
   than a step after it. Step 2 copies only `tutorial.yaml`, `COURSE.md`, `DESIGN.md` and
   `lessons/`, so a manifest-scope `from` such as `supplies/Cargo.toml` exists in the
   bundle and will never exist in the instance. Once the source is out of reach, a
   manifest-scope entry can no longer be placed at all. This is also the reason a
   **lesson-scope** `from` MUST resolve inside `lessons/`: those entries are placed when
   the lesson opens, long after this step, and `lessons/` is the only thing the instance
   carries (`bundle-format.md` section 2, **Where a `from` may point**).

   Four rules govern the placement, and `bundle-format.md` section 2 states
   them in full:

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

Run `scripts/validate_bundle.py --instance <the instance directory>`. The script path is
relative to this skill's directory, the same way `scripts/catalogs.py` is reached
(`catalogue-format.md` section 4); the argument is the `tutorial/` directory step 1
created. It needs Python 3 and nothing else, it reads only the instance, and it contacts
nothing.

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
to correct it there and materialize again — which is this section from step 1.

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
kind: side-lesson            # | main-path-draft
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
| `kind` | MUST | `side-lesson` or `main-path-draft`. |
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
everything under `lessons/` are read-only. `DESIGN.md` is the one exception the format
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
- **`complete`** — the lesson is finished. This is the state that stops it ever being
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
