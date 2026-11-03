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

Belay has no notion of a user story. A lesson's tasks come from its body, which the author
writes before the cohort exists; the stories come from the trainer's backlog, change during
the programme, and are not part of any course.

### 1.1 Decisions taken in the design discussion

- **Stories are not part of a course.** The trainer keeps them in the cohort repository.
- **A GitHub issue cannot track progress per participant**: every participant implements the
  same story, so an issue has one state for the whole cohort. Story *definitions* are shared
  files; story *progress* is per participant, in that participant's `STATE.md`.
- **The tutor coaches the process, never the content**: intake, specification, hand-off and
  review. The participant's level decides how closely it guides.
- **The tutor writes no code.** The specification is handed to a separate implementation
  session, started by the participant. The tutor never implements, and the implementation
  session never tutors. So the offer's "the AI implements" is met by that session, and the
  tutor's `ownership_policy` is unchanged.
- **The tutor never decides whether an implementation is correct for a story.** The module's
  validators and the trainer's review decide that.
- **The course keeps control of what is assessed**: the objectives a story lesson `teaches`,
  the module's validators, and the story stage.
- **Writing stories is part of the course.** Early modules hand the participant finished
  stories; later modules hand out stories with options; the late modules hand out a use case
  and the participant cuts it into stories. Story writing is a learning objective with a level
  and a review, like specification writing.

---

## 2. Format

### 2.1 Story files

Story files live in the cohort repository, outside every bundle, in a directory the story
lesson names (section 2.2). They arrive in each participant's branch with the module's
starting code (levels design, section 2.2). Participants treat them as read-only.

```markdown
---
id: 012-lead-scoring
title: Score incoming leads
module: programme-m2
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
| `module` | MUST | the `id` of the module bundle this story belongs to |
| `priority` | MUST | an integer; lower is earlier; ties are broken by `id` |

The body MUST carry a non-empty `## Acceptance criteria` section. The rest of the body is the
story, in whatever form the trainer writes it.

### 2.2 The story lesson

A story lesson is an ordinary lesson in the module bundle that declares `stories`:

```yaml
---
id: 04-build-the-scorer
title: Build the lead scorer
teaches: [spec-writing, code-review, pull-requests]
stories: stories/              # new, MAY: the directory holding the story files
specs: specs/                  # new, MAY: where specifications are written; default specs/
---
```

- **Its tasks are the stories in `stories` whose `module` is this bundle's `id`**, in priority
  order. Stories for other modules in the same directory are ignored.
- **Its body MUST carry a non-empty `## Spec criteria` section**: the checklist the tutor
  reviews each specification against (section 3, step 2). The criteria are the course's, so
  every participant's specification is held to the same standard.
- **The body MUST also describe the work in prose**, for a runner that predates this design
  (section 5).
- **It completes when every story for this module is `reviewed`.** The module gate — the
  module's validators passing — is belay#94's, and this design leaves room for it rather than
  defining it.
- Both paths are relative to the workspace root, contain no `..` segment, and are not absolute.

### 2.3 The story stage, and use cases

A story lesson declares how much of the story work the participant does:

```yaml
story_stage: given             # new, MAY: given | options | self-cut; default given
use_cases: use-cases/          # new: required at self-cut, not allowed otherwise
```

| `story_stage` | The trainer provides | The participant does first (step 0, section 3) |
|---|---|---|
| `given` | finished story files | nothing; intake starts from the trainer's stories |
| `options` | story files that each carry a `## Options` section with two or three ways to cut the story | chooses one option for each story and says why |
| `self-cut` | a use case file per module | cuts the use case into story files, in the format of section 2.1 |

**A use case file** lives in the cohort repository, outside every bundle, like a story file:
frontmatter `id`, `title` and `module` (the same rules as section 2.1), and a body describing
the goal, the users and the constraints. At `self-cut` the lesson's input is the use cases for
its module; each one produces the stories the five steps then run on.

**At `self-cut` the participant's story files are written to the lesson's `stories` directory
in their own branch**, so they are the participant's work, not shared definitions. The
trainer's review (belay#94) compares them across the cohort, as it compares the code.

**The body of a lesson at `options` or `self-cut` MUST carry a non-empty `## Story criteria`
section**: the checklist the tutor reviews a chosen option or a participant's story against
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
- **States:** `writing` (step 0, at `options` or `self-cut`), `specifying`, `handed-off`, `implemented`, `reviewed`, and `skipped`. A story with
  no row has not been started.
- **The section belongs to the module.** A new module starts with no `## Stories` rows; the
  carry-forward (levels design, section 2.4) does not copy them. The trainer's review
  (belay#94) reads them from each participant's branch before the next module starts.

---

## 3. The protocol: one story, five steps, and a step 0

`one_task_at_a_time` holds: one story is active at a time.

0. **Story writing** — only at `options` and `self-cut`. The tutor writes the row as `writing`.
   - At `options`: the participant chooses one of the story's options and says why.
   - At `self-cut`: the participant cuts the module's use case into story files. The tutor
     guides by the participant's level for the story-writing objective (section 3.1) — at A
     one story at a time, with an example; at B by offering ways to cut the use case; at C only
     reviewing the result.

   At both stages the tutor then reviews the result against `## Story criteria`, names what is
   not met, and records the result as evidence for the story-writing objective. **Nothing
   blocks.** At `self-cut` each new story gets its own row, and intake (step 1) then runs over
   them in the priority the participant gave.

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
   second Claude Code session in the same repository, give it the specification's path, and
   have it work on a story branch `<participant-branch>/<story-id>` and open a pull request into
   the participant's module branch. **The tutor writes no code and starts no session.** Who
   creates the story branch follows belay#100; until that lands, the participant does.
4. **Return.** The participant comes back with the pull request. The tutor reads the diff
   through Git — reading is always allowed — runs the module's validators, and writes the row
   as `implemented` with the pull request's number.
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
| stories | both | `stories` not a string; an absolute path or a `..` segment; a lesson declaring `stories` without a non-empty `## Spec criteria` section |
| specs | both | the same path rules for `specs`; `specs` without `stories` |
| story stage | both | `story_stage` other than `given`, `options`, `self-cut`; `story_stage` without `stories`; `use_cases` missing at `self-cut`, present at another stage, or breaking the path rules; a lesson at `options` or `self-cut` without a non-empty `## Story criteria` section; a name in `## Objectives by step` that is not in `teaches` |
| story rows | instance | a `## Stories` row that does not parse, an unknown state (`writing`, `specifying`, `handed-off`, `implemented`, `reviewed`, `skipped`), or two rows for one id |

Story ids in `## Stories` are not checked against anything: the story files are outside the
bundle and outside `tutorial/`.

**A story-file mode**, `belay-validate --stories <dir> --module <id>`, for the trainer to run
before publishing stories. It reports:

- frontmatter missing `id`, `title`, `module` or `priority`, or `priority` not an integer;
- an `id` that does not match `[a-z0-9-]+` or does not equal the filename stem;
- two stories with one `id`;
- a story without a non-empty `## Acceptance criteria` section;
- with `--stage options`, a story without a `## Options` section that lists at least two
  options;
- with `--use-cases`, the same frontmatter rules for use case files, and a use case without a
  body;
- and, informationally, how many stories carry `module: <id>` — zero is a warning, because a
  story lesson for that module would have nothing to do.

The participant can run the same mode on the story files they wrote at `self-cut`.

---

## 5. Compatibility

`stories`, `specs`, `story_stage` and `use_cases` are additive lesson keys; `bundle_format` stays `1`. A course without
`stories` is unchanged.

An **older runner** reads a story lesson as an ordinary lesson and teaches from its body. That
is why section 2.2 requires the body to describe the work in prose: `bundle-format.md`
section 13 gains this as an authoring obligation, in the pattern optional lessons already use
("the course must be completable by a learner who declines everything").

An **older validator** ignores both keys: lesson frontmatter keys are read by name.

---

## 6. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 6: `stories`, `specs`, `story_stage`, `use_cases`, `## Spec criteria`, `## Story criteria`, `## Objectives by step`, and **Writing a story lesson**; section 13: the older-runner obligation; section 10's self-check |
| `runner-protocol.md` | a new section, **User stories**: step 0 at each stage, the five steps, the level effects, the never-blocks rule, the hand-off text |
| `state-lifecycle.md` | `## Stories`: shape, states, when each is written, that it is not carried forward |
| `SKILL.md` | the loading table: during a story lesson, the active story file and its specification |
| `README.md` | the feature list and the `--stories` mode |

---

## 7. Acceptance criteria

1. Existing courses are unaffected: all suites pass unchanged, and the sibling sweep reports no
   new finding and no new warning.
2. Each new check, and each story-file finding, has a fixture that trips it and a silent
   control.
3. The `levelled-programme` fixture gains a story lesson at `given` in module 1, and one at
   `options` and one at `self-cut` in module 2. Module 2's starting code gains a `stories/`
   directory with three stories (one of them for another module, one with `## Options`) and a
   `use-cases/` directory with one use case. An instance of module 2 has a `## Stories` row in
   each state, and validates clean.
4. `belay-validate --stories` on that directory reports two stories for module 2 and none for
   an unknown module id, with the warning.
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
