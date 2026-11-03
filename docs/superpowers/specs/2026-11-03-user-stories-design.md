# Lessons whose tasks come from task files — Design

**Date:** 2026-11-03
**Last amended:** 2026-11-03
**Status:** implemented — see §10 for the decisions the implementation added;
`bundle-format.md` §2, §6, §10, §13, `runner-protocol.md` §19, `state-lifecycle.md` §14,
validator checks 42-46 and `--tasks`, `tests/test_validate_bundle.py`
**Issues:** belay#93, belay#92
**Builds on:** the levels and modules-as-bundles design (2026-11-03), PR: belay#91
**Related:** belay#94 (cohort grading, PR: belay#102), belay#100 (who runs an action, by level)

---

## 1. The problem

A cohort programme hands its participants a prioritised list of user stories. Each
participant works through them one at a time, on their own branch, through a fixed process:
write a specification, hand it to an implementation session, come back with a pull request,
review it. Later in the programme the participants write stories themselves.

Belay has no way to do this. A lesson's tasks come from its body; there is no list of task
files, no per-participant progress through such a list, and no way for a participant to add
tasks of their own.

### 1.1 Decisions taken in the design discussion

- **Belay gets a generic feature; user stories are course content.** The runner must hold only
  what a course on any subject could need (2026-09-11 spec, section 2). "A lesson whose tasks
  come from a folder of task files, worked one at a time in priority order, with progress per
  participant" serves user stories, exercise sets, problem sets and labs alike. The stories, the
  specification and review process, the checklists, the hand-off to an implementation session,
  and when participants start writing stories are all written into the course's lessons.
- **The task files are part of the course.** They ship in the bundle, in the lesson's folder,
  because a bundle is one module and every participant gets the same tasks. (This replaces two
  earlier decisions of the same day: that stories live in the cohort repository, and that the
  runner has a story concept with stages.)
- **Progress is per participant**, in that participant's `STATE.md`. A shared tracker such as a
  GitHub issue cannot hold it: every participant works on the same task, so an issue has one
  state for the whole cohort.
- **The course decides when participants write their own tasks.** A participant is first
  exposed to good tasks and is asked to write tasks only once a lesson has taught it. A lesson
  opts in with `own_tasks`; without it the tutor does not offer it, though a participant who
  asks may still add one.
- **Two generic rules hold here as everywhere**: the tutor never writes the participant's
  learner-owned work, and a tutor's judgement never blocks.

---

## 2. Format

### 2.1 Task files

Task files live **in the lesson's own folder**, in the subdirectory the lesson's `tasks` key
names, for example `lessons/04-build-the-scorer/stories/`. The lesson is therefore a folder
lesson.

```markdown
---
id: 012-lead-scoring
title: Score incoming leads
priority: 1
---
As a member of the sales team I want incoming leads scored so that I call the best ones first.

## Acceptance criteria

- A lead with no company size scores 0, and the reason is shown.
```

| Field | Required | Meaning |
|---|---|---|
| `id` | MUST | `[a-z0-9-]+`, equal to the filename stem, unique in the directory, stable once published |
| `title` | MUST | non-empty string |
| `priority` | MUST | an integer; lower is earlier; ties are broken by `id` |

**The body is the course's.** A user story carries acceptance criteria; an exercise carries a
statement and a check; Belay requires nothing of it.

**Why the lesson's folder.** Measured on 2026-11-03: materialization copies only
`tutorial.yaml`, `COURSE.md`, `DESIGN.md` and `lessons/`, so a directory at the bundle root would
never reach the instance; and a directory directly under `lessons/` without a `LESSON.md` is a
check 4 finding. Inside the lesson's folder the files are copied by every materializer, arrive
read-only at `tutorial/lessons/<lesson>/<tasks>/`, and reach a running instance through the
existing update path (2026-09-11 spec, section 15c). A changed or new task file is a MINOR revision; a
removed or renamed one is MAJOR, because an instance's `## Tasks` row may name it.

### 2.2 The task lesson

```yaml
---
id: 04-build-the-scorer
title: Build the lead scorer
teaches: [spec-writing, code-review]
tasks: stories/                                               # new, MAY
task_states: [specifying, handed-off, implemented, reviewed]  # new, MAY
own_tasks: stories/                                           # new, MAY
---
```

| Key | Meaning |
|---|---|
| `tasks` | a directory inside this lesson's folder holding the task files; relative, no `..` segment |
| `task_states` | the states a task passes through, in order; default `[in-progress, done]`. **The last state means done.** Each is `[a-z0-9-]+`; `skipped` is reserved and always available; at least one state |
| `own_tasks` | a directory in the **workspace** where the participant writes task files of their own; relative to the workspace root, no `..` segment |

**The body lists every task file by path**, one line each with its title — for example
`- stories/012-lead-scoring.md — Score incoming leads`. The list is what an older runner teaches
from (section 5), and it is what makes an older validator accept the files: its check 6 requires
every file in a lesson folder to be named by `LESSON.md`.

**The body says what happens in each state.** For a user story that is the course's process —
what a good specification needs, how to hand it to the implementation session, what to check on
return, how to review. The tutor follows the body; the runner knows only the state names and
their order.

**The lesson completes when every task is in its last state or `skipped`.** Nothing else about
completion changes: a task lesson may still declare validators and completion conditions.

### 2.3 Progress: `## Tasks` in `STATE.md`

```markdown
## Tasks

- `012-lead-scoring` — reviewed — PR #14; 2027-03-04
- `013-dedupe` — handed-off — 2027-03-05
- `014-export` — skipped — 2027-03-05 (depends on 013, which is not merged)
```

- One row per task, **updated in place**, with the separators and wrapping rules of `## Levels`:
  `` - `<id>` — <state> — `` then free text that ends in a date, and an optional parenthesis.
- The state is one of the active lesson's `task_states`, or `skipped`. A task with no row has not
  been started.
- **The section belongs to the module.** A new module starts with no `## Tasks` rows; the
  carry-forward (levels design, section 2.4) does not copy them. The trainer's grading reads them
  from each participant's branch.
- Rows are not checked against the bundle's task files, because a row may name a task the
  participant wrote.

---

## 3. The protocol

`one_task_at_a_time` holds: one task is active at a time.

1. **Offer.** The tutor lists the open tasks in priority order — the lesson's task files and the
   participant's own task files (section 3.1) — and proposes the first. Taking a later one first,
   or skipping one, needs a reason the participant states; the tutor records it (`skipped`,
   reason in the parenthesis).
2. **Work.** The tutor writes the row in the first state and follows the lesson body for what
   that state asks of the participant. A row enters a later state only once the body's condition
   for that state's work is met (section 10, item 1), and goes back to an earlier one when the body
   says so.
3. **Guide by level.** Inside each state the participant's level for the objective the body
   names for that state decides how closely the tutor guides (`runner-protocol.md` section 18).
   An exam lesson (cohort-grading design) caps help at rung 3 as everywhere.
4. **Review without blocking.** Where the body gives a checklist for a state, the tutor reviews
   the participant's work against it, names what is not met, and records the result as evidence
   for that state's objective. It never refuses to move on because of it.
5. **Never do the work.** The tutor writes no learner-owned file. When the body sends the
   participant to another tool or session — an implementation agent, a notebook, a lab machine —
   the tutor says what to do there and does not do it.

### 3.1 Participant-written tasks

- **When the lesson declares `own_tasks`**, the participant writes task files there, in the
  format of section 2.1, and the tutor reviews them against the body's checklist for writing a
  task, if it has one. They join the offer in their own priority order.
- **When it does not**, the tutor does not offer it. If the participant asks to add a task of
  their own, the tutor lets them: the file goes to `own_tasks` of the nearest later lesson that
  declares it, or to `tasks/` in the workspace otherwise, and the tutor reviews it against the
  format of section 2.1. The lesson's own tasks stay the default path.

---

## 4. Validator

New checks take the next free numbers. Each is silent when its key is absent.

| Check | Mode | Reports |
|---|---|---|
| tasks | both | `tasks` on a single-file lesson; not a string; absolute or with a `..` segment; a directory that does not exist in the lesson's folder or holds no `.md` file |
| task files | both | for each file in a `tasks` directory: frontmatter missing `id`, `title` or `priority`; `priority` not an integer; an `id` that does not match `[a-z0-9-]+` or does not equal the filename stem; two files with one `id`; a file the lesson body does not list; a listed path that does not exist |
| task states | both | `task_states` without `tasks`; not a non-empty list; an entry not matching `[a-z0-9-]+`; a duplicate; `skipped` listed |
| own tasks | both | `own_tasks` without `tasks`; not a string; absolute or with a `..` segment |
| task rows | instance | a `## Tasks` row that does not parse; two rows for one id. The state is not checked against `task_states`, because a row may outlive the lesson that declared them |

**`belay-validate --tasks <dir>`** applies the task-file rules (except the listing rule) to any
directory, so the tutor and the participant can check task files the participant wrote.

---

## 5. Compatibility

`tasks`, `task_states` and `own_tasks` are additive lesson keys; `bundle_format` stays `1`. A
course without them is unchanged.

An **older runner** teaches a task lesson as an ordinary lesson, from its body — which lists
every task and says what each state asks — so the course stays usable; it records no
`## Tasks` rows. `bundle-format.md` section 13 says so, and states the authoring obligation that
the body must make sense without the task machinery.

An **older validator** ignores the keys, because lesson frontmatter keys are read by name, and
accepts the task files because the body names each one. An **older materializer** copies them,
because they are inside `lessons/`.

---

## 6. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 6: `tasks`, `task_states`, `own_tasks`, the task-file format, the listing rule, and **Writing a task lesson** with the worked user-story example of section 7; section 13: the older-runner row and authoring obligation; section 10's self-check |
| `runner-protocol.md` | a new section, **Task lessons**: offer, states, level, review without blocking, never doing the work, participant-written tasks |
| `state-lifecycle.md` | `## Tasks`: shape, when rows are written, not carried forward |
| `SKILL.md` | the loading table: during a task lesson, the active task file |
| `README.md` | the feature list and `--tasks` |

---

## 7. Worked example: a user-story lesson, as course content

This is not runner behaviour; it is what the cohort programme writes into its lessons, and it
belongs in `bundle-format.md` as the worked example.

- `tasks: stories/`, `task_states: [specifying, handed-off, implemented, reviewed]`.
- The body's **Specifying** section: the participant writes `specs/<story-id>.md`; a `## Spec
  criteria` checklist (testable acceptance criteria, non-functional requirements named, split
  into tasks); the objective for this state is `spec-writing`.
- The body's **Handed-off** section: what the participant does in the implementation session.
  The programme varies this by lesson — the first two story lessons use Claude Code's plan mode;
  a later lesson has the participant install Superpowers, ask it to rate the specification, and
  improve it with its help before implementing. The implementation works on a story branch and
  opens a pull request into the participant's module branch.
- The body's **Implemented** section: the participant returns with the pull request; the tutor
  runs the module's validators and asks about any change the session made to the specification.
- The body's **Reviewed** section: while the row reads `implemented`, the participant walks
  through the diff against the acceptance criteria; the objective is `code-review`; the row
  becomes `reviewed` when that is done and validators pass; failing validators send the story
  back to handed-off.
- A later lesson that has taught story writing declares `own_tasks: stories/` and gives a
  `## Writing a story` checklist; from then on participants cut a use case (listed in the body)
  into stories of their own.

---

## 8. Acceptance criteria

1. Existing courses are unaffected: all suites pass unchanged, and the sibling sweep reports no
   new finding and no new warning.
2. Each new check has a fixture that trips it and a silent control.
3. The `levelled-programme` fixture's module 1 gains a folder task lesson with a `stories/`
   subdirectory of three listed tasks and the four story states; module 2 gains a task lesson
   with `own_tasks`. An instance of module 2 has `## Tasks` rows in several states and validates
   clean. Main's validator (exported with `git archive`) accepts both bundles with no finding.
4. `belay-validate --tasks` reports each task-file finding on a bad directory and is silent on a
   valid one.
5. The protocol states offer, states, review-without-blocking, never-doing-the-work and
   participant-written tasks each in one place. The tutor's behaviour on the worked example is
   added to the dry run in belay-authoring#43.

---

## 9. Non-goals

- **No user-story concept in the runner.** Stories, specifications, hand-offs, criteria and
  stages are course content.
- **No GitHub integration.** A pull request is named in a row's free text; nothing calls `gh`.
- **The tutor does not judge whether a participant's work is correct.** Validators and the
  trainer's grading do.
- **No change to who runs a Git command** (belay#100).

---

## 10. Implementation notes

Implemented on 2026-11-03. Writing the validator and the protocol forced these decisions, which
this design left open, and the branch review ruled on others. Each is stated once, where its
reader reads it. §3 item 2, §2.1 and §7 are corrected in place to agree with them.

**Rulings of the branch review (fix round 1):**

1. **A row enters a state only once the work the body names for that state is done.** While that
   work goes on, the row stays in the previous state, so the last state means done with its work
   finished. A closed task stays closed unless the participant asks to reopen it. The first state
   is written on taking the task, so its work and the second's share it, and *Next task* says
   which is under way. A lesson with one state writes no row until the work is done
   (`runner-protocol.md` §19.2, `bundle-format.md` §6).
2. **A state the body says nothing about is no defect report.** The tutor says the lesson does not
   describe it, and moves the row when the participant says that work is done. A last state with no
   section has no work of its own. `DEFECT_KINDS` does not change (§19.2).
3. **A review is a row write of its own**, updating an existing row's free text. A review of a file
   not yet taken has no row, and is only spoken (`state-lifecycle.md` §14.2).
4. **Open and active are scoped** to the tasks the current offer can list, plus a request-written
   task taken in this lesson, which the row's parenthesis names. A request-written task left open
   when its lesson ends is not active in the next. A row closed under an earlier lesson's states
   stays closed, and a row in a state the active lesson does not declare is never active: it counts
   as closed. Only a row for a file in the active lesson's own `tasks` directory is reported for
   this (§19, `state-lifecycle.md` §14.4).
5. **The own-task id comparison is a step of the tutor's review.** `--tasks` compares inside one
   directory. On a clash the participant renames the file, and it stays out of the offer until
   then (§19.6).
6. **A new task file is a MINOR revision**: additive, like a new optional lesson
   (`bundle-format.md` §2).

**Decisions taken while writing:**

7. **`--tasks` has its own check table**, numbered like a catalogue's: at least one `.md` file,
   which only warns; each file well-formed; no id twice. A missing directory exits 2, like
   `--instance` and `--catalog`.
8. **A malformed id in a `## Tasks` row is a finding** (check 46), and so is a malformed state or
   date. An id is still never looked up.
9. **"Records the result as evidence" (§3 item 4) has no event to use.** The learning record's
   event types are a closed set, and none holds a review. So the result goes in the row's free
   text, and in *Concepts demonstrated* when the work shows the objective used, with no validator
   needed because the review is the evidence. A review sets no level (`state-lifecycle.md` §14.2,
   §19.3).
10. **The offer reads three frontmatter lines per task, and the active task's file whole**, so a
    task lesson still costs one lesson plus one file. The only other body it reads is a task file
    under review (§19.1).
11. **Taking a later task first passes over nothing for good.** The reason goes in the taken task's
    parenthesis, which survives a state change, and the tasks passed over stay open. Only skipping
    writes `skipped` (§19.1).
12. **A task written on request does not join the offer of the lesson it was written in, and does
    not hold up that lesson's completion**, which is what "stay the default path" comes to. Taking
    it there and then is taking a later task first. In a lesson with no `tasks` it waits (§19.6).
13. **Finding the nearest later `own_tasks` searches for one frontmatter line** over the instance's
    lessons and opens none of them, the one thing §1's "never another lesson" gives way to. During
    a detour the count starts from `resume_at`, which itself counts (§19.6).
14. **The format review runs before each offer in a lesson with `own_tasks`**, as well as when a file
    is reviewed, because nothing records which files passed. A file that fails stays out of the offer
    and holds up nothing else. `--tasks` is therefore the one validator mode a teaching turn may run
    (§13.1, §19.6).
15. **The section 5 reading.** "Writes no learner-owned file" keeps section 5's exemptions: section 5
    applies unchanged, its exemptions included, and a task lesson adds none (§19.5).
16. **A checklist worded as a body's condition never holds a row.** That keeps "never refuses to move
    on" true against "moves when the body's condition is met" (§19.4).
17. **Ids should be distinct across a bundle's task lessons**, because rows belong to the module and
    check 46 reports two rows for one id. No check compares directories (`bundle-format.md` §6).
18. **Moving a row keeps its earlier review results in the free text**, because the row is updated
    in place and the trainer reads it (`state-lifecycle.md` §14.2).
