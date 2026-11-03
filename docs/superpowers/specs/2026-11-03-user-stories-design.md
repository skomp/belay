# Guiding a participant through user stories — Design

**Date:** 2026-11-03
**Last amended:** 2026-11-03
**Status:** designed, not implemented
**Issues:** belay#93, and belay#92 (story writing and its stages, folded in on 2026-11-03)
**Builds on:** the levels and modules-as-bundles design (2026-11-03), PR: belay#91
**Related:** belay#94 (module review and the module gate),
belay#100 (who runs an action, by level)

---

## 1. The problem

In a cohort programme every participant builds the same solution from the same prioritised
list of user stories, each on their own Git branch. The work is spec-driven: the participant
turns a story into a specification and splits it into tasks, and an agent implements it. The
participant then reads code they did not write and checks it against the story — reading
foreign code and finding defects in it are learning objectives in their own right.

Belay has no notion of a user story. A lesson's tasks come from its body; there is no way to
hand a participant a prioritised list of stories, to track each participant's progress on
them, or to let a later lesson ask the participant to write stories of their own.

### 1.1 Decisions taken in the design discussion

- **The given stories are part of the course.** They ship in the module bundle, because a
  bundle is one module and every participant gets the same stories. The trainer changes them
  by revising the bundle. (Decided 2026-11-03; this replaces the first decision of the same
  day, that stories live in the cohort repository.) Stories a participant writes at
  `self-cut` are the participant's work and live in their own branch.
- **A GitHub issue cannot track progress per participant**: every participant implements the
  same story, so an issue has one state for the whole cohort. Story *definitions* are shared
  files; story *progress* is per participant, in that participant's `STATE.md`.
- **The tutor coaches the process, never the content**: intake, specification, hand-off and
  review. The participant's level decides how closely it guides.
- **The tutor writes no code.** The specification is handed to a separate implementation
  session, started by the participant. The tutor never implements, and the implementation
  session never tutors. So the offer's "the AI implements" is met by that session, and the
  tutor's `ownership_policy` is unchanged.
- **Working with the implementation agent is what the course teaches**, not a way around it.
  The programme teaches participants to implement with Claude Code and a spec-driven workflow
  (the Superpowers plugin). The participant writes the specification with the tutor first,
  then gives it to Superpowers as the input to its own specification interview. That the
  implementation session could also do the participant's thinking is not a defect to guard
  against: the course's grading (the module's validators and the trainer's review) is where
  the participant's own work is judged.
- **The tutor never decides whether an implementation is correct for a story.** The module's
  validators and the trainer's review decide that.
- **The course keeps control of what is assessed**: the objectives a story lesson `teaches`,
  the module's validators, and the story stage.
- **Writing stories is part of the course, and the course decides when it starts.** A
  participant is first exposed to good stories and only writes stories after a lesson has
  taught it. So the early story lessons deliver finished stories, and only lessons after the
  one that teaches story writing hand out a use case for the participant to cut into stories.
  Story writing is a learning
  objective with a level and a review, like specification writing.
- **Belay supports two stages, not three.** A client's intermediate step — stories handed out
  with options for how to cut them — is course content: the trainer writes the options into
  the story's text, and the tutor treats it as an ordinary given story.

---

## 2. Format

### 2.1 Story files

Given story files live **in the story lesson's own folder** — the lesson is a folder lesson,
and its stories are in a subdirectory of it, for example
`lessons/04-build-the-scorer/stories/`. Materialization already copies `lessons/` in full, so
the stories arrive at `tutorial/lessons/04-build-the-scorer/stories/` with no change to
materialization or to the update path, and are **read-only there, like every lesson file**.

Measured on 2026-11-03, before choosing this: materialization copies only `tutorial.yaml`,
`COURSE.md`, `DESIGN.md` and `lessons/`, so a `stories/` directory at the bundle root would not
reach the instance; and a directory directly under `lessons/` without a `LESSON.md` is a check 4
finding. A
correction reaches a running instance through the existing update path (2026-09-11 spec,
section 15c): a changed story is a MINOR revision; a removed or renamed story is MAJOR, because
an instance's `## Stories` row may name it.

```markdown
---
id: 012-lead-scoring
title: Score incoming leads
priority: 1
---
As a member of the sales team I want incoming leads scored so that I call the best ones first.

## Acceptance criteria

- A lead with no company size scores 0, and the reason is shown.
- ...
```

| Field | Required | Meaning |
|---|---|---|
| `id` | MUST | `[a-z0-9-]+`, equal to the filename stem, unique in the directory, stable once published |
| `title` | MUST | non-empty string |
| `priority` | MUST | an integer; lower is earlier; ties are broken by `id` |

The body MUST carry a non-empty `## Acceptance criteria` section. The rest of the body is the
story, in whatever form the author writes it.

### 2.2 The story lesson

A story lesson is an ordinary lesson in the module bundle that declares `stories`:

```yaml
---
id: 04-build-the-scorer
title: Build the lead scorer
teaches: [spec-writing, code-review, pull-requests]
stories: stories/              # new, MAY: a directory inside this lesson's folder
specs: specs/                  # new, MAY: where specifications are written; default specs/
---
```

- **Its tasks are the story files in `stories`**, in priority order. Two story lessons in one
  bundle name two different directories.
- **Its body MUST carry a non-empty `## Spec criteria` section**: the checklist the tutor
  reviews each specification against (section 3, step 2). The criteria are the course's, so
  every participant's specification is held to the same standard.
- **Its body lists every story file by path**, one line each with the story's title — for
  example `- stories/012-lead-scoring.md — Score incoming leads`. The list is the prose an older
  runner teaches from (section 5), and it is what makes an older validator accept the files:
  its check 6 requires every file in a lesson folder to be named by `LESSON.md`. The new
  validator checks the list against the directory (section 4).
- **It completes when every story for this module is `reviewed`.** The module gate — the
  module's validators passing — is belay#94's, and this design leaves room for it rather than
  defining it.
- `stories` is relative to the lesson's folder; `specs` is relative to the workspace root.
  Neither contains a `..` segment or is absolute.

### 2.3 The story stage, and use cases

A story lesson declares how much of the story work the participant does:

```yaml
story_stage: given             # new, MAY: given | self-cut; default given
use_cases: use-cases/          # new: required at self-cut, not allowed otherwise; in the lesson folder
own_stories: stories/          # new, at self-cut: where the participant writes stories; workspace
```

| `story_stage` | The trainer provides | The participant does first (step 0, section 3) |
|---|---|---|
| `given` | finished story files, in the bundle | nothing; intake starts from them |
| `self-cut` | use case files, in the bundle | cuts each use case into story files, in the format of section 2.1 |

**A use case file** lives in the lesson's folder, in the directory `use_cases` names, and the
lesson body lists each one by path, as for stories: frontmatter `id`
and `title` (the same rules as section 2.1), and a body describing the goal, the users and the
constraints. At `self-cut` the lesson's input is its use cases; each one produces the stories
the five steps then run on.

**At `self-cut` the participant's story files are written to `own_stories` in their own
branch** — in the workspace, not in `tutorial/` — so they are the participant's work, not the
course's. The
trainer's review (belay#94) compares them across the cohort, as it compares the code.

**The body of a lesson at `self-cut` MUST carry a non-empty `## Story criteria`
section**: the checklist the tutor reviews a participant's story against
(section 3, step 0).

The stages are per lesson, so a course fades them over its modules by declaring `given` in the
early modules and `self-cut` in the late ones. **The stage is the course's, not the
participant's**: it does not change with the participant's level. The level changes how
closely the tutor guides inside the stage.

### 2.4 Specifications

The participant writes one specification per story, at `<specs>/<story-id>.md` in their own
branch. Its shape is the course's `## Spec criteria`, not the runner's.

### 2.5 Progress: `## Stories` in `STATE.md`

```markdown
## Stories

- `012-lead-scoring` — reviewed — spec specs/012-lead-scoring.md; PR #14; 2027-03-04
- `013-dedupe` — handed-off — spec specs/013-dedupe.md; 2027-03-05
- `014-export` — skipped — 2027-03-05 (depends on 013, which is not merged)
```

- One row per story, **updated in place**, in the shape and dash rules of `## Levels`:
  `` - `<id>` — <state> — `` then free text that ends in a date, and an optional parenthesis.
- **States:** `writing` (step 0, at `self-cut`), `specifying`, `handed-off`, `implemented`, `reviewed`, and `skipped`. A story with
  no row has not been started.
- **The section belongs to the module.** A new module starts with no `## Stories` rows; the
  carry-forward (levels design, section 2.4) does not copy them. The trainer's review
  (belay#94) reads them from each participant's branch before the next module starts.

---

## 3. The protocol: one story, five steps, and a step 0

`one_task_at_a_time` holds: one story is active at a time.

0. **Story writing** — only at `self-cut`. The tutor writes the row as `writing`. The
   participant cuts the module's use case into story files. The tutor guides by the
   participant's level for the story-writing objective (section 3.1) — at A one story at a
   time, with an example; at B by offering ways to cut the use case; at C only reviewing the
   result.

   The tutor then reviews the result against `## Story criteria`, names what is not met, and
   records the result as evidence for the story-writing objective. **Nothing blocks.** Each
   new story gets its own row, and intake (step 1) then runs over them in the priority the
   participant gave.

   **At `given` the tutor does not offer step 0**: it works from the bundle's story files, and
   the lesson that teaches story writing is where story writing starts. If the participant
   asks to write a story of their own, the tutor runs step 0 for that one story, reviewing it
   against the lesson's `## Story criteria` when the lesson has them and against the story
   format of section 2.1 otherwise. The story goes to `own_stories` when the lesson declares it
   and to `stories/` in the workspace otherwise. The bundle's stories stay the default path.

1. **Intake.** The tutor lists the open stories for this module in priority order and proposes
   the first. Taking a later one first, or skipping one, needs a reason the participant states;
   the tutor records it in the row (`skipped`, with the reason in the parenthesis). The tutor
   writes the row as `specifying`.
2. **Specification.** The participant writes the specification. How the tutor guides depends
   on the participant's level for the spec-writing objective (section 3.1):
   - **A** — one part at a time, with an example of each part;
   - **B** — two or three ways to split the story; the participant chooses and says why;
   - **C** — the tutor only reviews the finished specification.

   At every level the tutor then reviews the specification against `## Spec criteria`, names
   each criterion that is not met, and records the result as evidence for that objective.
   **Nothing blocks**: the participant may hand off a specification with gaps, and the gaps are
   noted in the row. This is the assessments design's rule that a tutor's judgement never
   blocks, applied here.
3. **Hand-off.** The tutor writes the row as `handed-off` and tells the participant to open a
   second Claude Code session in the same repository, start the spec-driven workflow there
   with the specification as its input, and have it work on a story branch
   `<participant-branch>/<story-id>` and open a pull request into the participant's module
   branch. The workflow interviews the participant about the specification before it plans;
   the participant answers from their specification, and a decision that changes it is written
   back into the specification file, so the file stays the record of what was asked for.
   **The tutor writes no code and starts no session.** Who creates the story branch follows
   belay#100; until that lands, the participant does.
4. **Return.** The participant comes back with the pull request. The tutor reads the diff
   through Git — reading is always allowed — runs the module's validators, and writes the row
   as `implemented` with the pull request's number. It also compares the specification file
   with the one handed off and asks the participant about each change: why the interview
   changed it, and whether the change was theirs to make.
5. **Review.** The participant walks through the diff against the story's acceptance criteria.
   This is assessment-shaped: one question per turn, the help ladder stops at rung 3, and the
   outcome sets the level of the code-review objective (section 3.1; by the
   outcome-to-level rule of `runner-protocol.md` section 15.11).
   - **Validators pass:** the participant merges the pull request (who runs the merge follows
     belay#100). The row becomes `reviewed`.
   - **Validators fail, or the participant finds a gap:** the row goes back to `handed-off`,
     and the participant's findings are the input for the next implementation round. The tutor
     never fixes the code.

### 3.1 Which objective each step assesses

A story lesson's body names, in a `## Objectives by step` section, which of its `teaches`
objectives is the story-writing, the spec-writing and the code-review objective. Without that
section, the tutor uses the first objective in `teaches` for every step.

A theory question in the middle of a story is answered from the lesson's material at the
participant's level, as in any lesson.

---

## 4. Validator

New checks take the next free numbers (on `main` today the last bundle check is 41). Each is
silent when its key is absent.

| Check | Mode | Reports |
|---|---|---|
| stories | both | `stories` on a single-file lesson; `stories` not a string; an absolute path or a `..` segment; a directory that does not exist in the lesson's folder or holds no story file; a story file the lesson body does not list, or a listed path that does not exist; a lesson declaring `stories` without a non-empty `## Spec criteria` section |
| story files | both | for each file in a `stories` directory: frontmatter missing `id`, `title` or `priority`; `priority` not an integer; an `id` that does not match `[a-z0-9-]+` or does not equal the filename stem; two stories with one `id`; no non-empty `## Acceptance criteria` section |
| specs | both | the same path rules for `specs`; `specs` without `stories` |
| story stage | both | `story_stage` other than `given`, `self-cut`; `story_stage` without `stories`; `use_cases` or `own_stories` missing at `self-cut`, present at another stage, or breaking the path rules; a `use_cases` directory with no use case file, a use case without `id`, `title` or a body, or a use case file the body does not list; a lesson at `self-cut` without a non-empty `## Story criteria` section; a name in `## Objectives by step` that is not in `teaches` |
| story rows | instance | a `## Stories` row that does not parse, an unknown state (`writing`, `specifying`, `handed-off`, `implemented`, `reviewed`, `skipped`), or two rows for one id |

Story ids in `## Stories` are not checked against the bundle's stories, because a row may
name a story the participant wrote at `self-cut`.

**The participant's own stories** are outside the bundle and outside `tutorial/`, so the bundle
and instance modes do not see them. A small mode, `belay-validate --stories <dir>`, applies the
story-file rules above to any directory, so the tutor can check the participant's stories in
step 0 and the participant can run it themselves.

---

## 5. Compatibility

`stories`, `specs`, `story_stage`, `use_cases` and `own_stories` are additive lesson keys; `bundle_format` stays `1`. A course without
`stories` is unchanged.

An **older runner** reads a story lesson as an ordinary lesson and teaches from its body. That
is why section 2.2 requires the body to list the stories, in prose an older runner can teach from: `bundle-format.md`
section 13 gains this as an authoring obligation, in the pattern optional lessons already use
("the course must be completable by a learner who declines everything").

An **older validator** ignores the keys, because lesson frontmatter keys are read by name. It
accepts the story and use case files because the lesson body names each one, which is what its
check 6 asks of every file in a lesson folder. An **older materializer** copies them, because
they are inside `lessons/`.

---

## 6. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 6: `stories`, `specs`, `story_stage`, `use_cases`, `own_stories`, `## Spec criteria`, `## Story criteria`, `## Objectives by step`, and **Writing a story lesson**; section 13: the older-runner obligation; section 10's self-check |
| `runner-protocol.md` | a new section, **User stories**: step 0 at each stage, the five steps, the level effects, the never-blocks rule, the hand-off text |
| `state-lifecycle.md` | `## Stories`: shape, states, when each is written, that it is not carried forward |
| `SKILL.md` | the loading table: during a story lesson, the active story file and its specification |
| `README.md` | the feature list and the `--stories` mode for a participant's own stories |

---

## 7. Acceptance criteria

1. Existing courses are unaffected: all suites pass unchanged, and the sibling sweep reports no
   new finding and no new warning.
2. Each new check, and each story-file finding, has a fixture that trips it and a silent
   control.
3. The `levelled-programme` fixture's module 1 gains a folder story lesson at `given` with a
   `stories/` subdirectory of three listed stories; module 2 gains a folder story lesson at
   `self-cut` with a `use-cases/` subdirectory of one listed use case. Main's validator
   (exported with `git archive`) accepts both bundles with no finding. An instance of module 2 has a `## Stories` row in
   each state, and validates clean; both bundles validate clean.
4. `belay-validate --stories` on a directory of participant-written stories reports each
   story-file finding, and is silent on a valid directory.
5. The protocol states the five steps, the never-blocks rule and the never-writes-code rule each
   in one place. The tutor's behaviour across the five steps is added to the dry run in
   belay-authoring#43.

---

## 8. Non-goals

- **The tutor does not implement, and does not start the implementation session.**
- **The tutor does not judge whether an implementation is correct for a story.**
- **No GitHub integration.** Pull requests are named by number in the row; the tutor reads
  them through Git. Nothing here calls `gh`.
- **The stage does not follow the participant's level.** It is the course's; the level only
  changes how closely the tutor guides inside it.
- **No module gate and no cohort review** (belay#94),
  **no change to who runs a Git command** (belay#100).
