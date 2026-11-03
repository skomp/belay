# Learning goals and per-concept levels — Design

**Date:** 2026-11-03
**Last amended:** 2026-11-03
**Status:** designed, not implemented
**Depends on:** PR: belay#72 (`sections`), which this design uses as the course's modules
**Related:** the assessments design (2026-09-19), whose assessment lessons set levels here

---

## 1. The problem

A Belay course teaches every learner the same way. It knows which concepts it teaches
(`covers`), and it can assess them (`assesses`), but nothing it learns about a learner
changes how the tutor guides them or what material they read.

The motivating case is a cohort programme: a group takes the same course, builds the same
project, and is graded on the same tasks, but arrives with very different prior knowledge,
and unevenly so. One participant can explain Git and has never seen a graph-based agent
framework; the next is the reverse. The programme describes its curriculum in three layers:

| The programme's term | Meaning |
|---|---|
| broad learning goal | a content area, taught across many modules rather than in one |
| fine-grained learning goal | one thing a participant can do or explain; the unit that is assessed |
| module | a stretch of the course, ending in a checkpoint |

and assigns every participant, **per fine-grained goal**, one of three levels:

| Level | Name | What it means for the participant |
|---|---|---|
| **A** | guided | the least prior knowledge, and the closest guidance |
| **B** | options | works by choosing between offered approaches |
| **C** | self-directed | works it out alone; the tutor helps only abstractly |

The level decides how closely the tutor guides and how deep the material goes. An entry
assessment sets the levels; assessments inside the course keep them current.

This design adds that to the format and the runner, subject-neutrally: nothing here knows
what the programme teaches.

### 1.1 What this design does not cover

The same programme needs four further pieces. Each is a separate design, built on this one:

1. **Module scaffolding** — a module's user stories arrive pre-cut, cut with options, or
   uncut, fading over the course regardless of the learner's levels.
2. **Use-case guidance** — a prioritised user-story list, and a hand-off to a spec-driven
   workflow in which the learner specifies and the agent implements.
3. **Cohort review and the module gate** — at a module's end, grade every participant's
   branch on the same criteria (validators for the deterministic share, a rubric judged
   against `covers` summaries for a capped share), explain the best solution and why the
   others convince less, and let every participant continue from the best solution while
   keeping their own `tutorial/` progress. A module is passed when its functional
   requirement is technically met, which is a gate on validators, not on assessments.
4. **Final project and certificate** — a capstone chosen from a curated set, worked
   entirely at level C, and a certificate built from the assessment results of every
   module.

Decisions already taken for (3), recorded here so they are not re-litigated: the grade is
**hybrid** (validators weighted, plus a capped rubric share), and a graded task runs in
**exam mode** (help ladder capped at rung 3, no solution revealed).

---

## 2. Decisions

### 2.1 The three layers map onto what the format already has

| Programme | Format | New? |
|---|---|---|
| module | a **section**, PR: belay#72 | no — reused unchanged |
| fine-grained goal | a **`covers` concept** | no — gains an optional `goal` field |
| broad goal | a **`goals`** map | yes |

A `covers` concept is already exactly a fine-grained goal: a stable id and a summary an
answer can be judged against. Assessments are already judged against it. Nothing new is
needed for the unit that is assessed.

A section is already exactly a module: a contiguous stretch of `lessons` with an id, a
title and objectives, which never changes the order. **A second grouping key would be a
second place to say the same thing**, so this design adds none. The section's own
`objectives` field is why the broad-goal map is not called `objectives`.

```yaml
goals:                                   # new, MAY
  llm-foundations:
    title: Foundations and how LLMs work
    summary: >
      Python and developer craft, how a language model produces text, prompting and
      context engineering.

covers:
  context-engineering:
    summary: >
      Choose what goes into a model's context, and in what order, so it can do the task
      with the least irrelevant material.
    goal: llm-foundations                # new, MAY; a key in `goals`
```

**A goal groups concepts, never lessons.** A broad goal is taught across modules, not in
one, so it cannot be a stretch of the course. A cross-cutting topic — data protection,
say — is a goal whose concepts are taught in several sections.

`goals` is a map of maps with scalars at the leaves — two levels, within the ceiling
`bundle-format.md` section 2 sets. `title` is required, `summary` optional.

### 2.2 A lesson says which concepts it teaches

```yaml
---
id: 03-context
title: Context engineering
teaches: [context-engineering, prompting]     # new, MAY; keys in `covers`
---
```

Today only `assesses` links a lesson to concepts. Section 2.6 needs to know which
concepts' levels apply to the active lesson, and the tutor holds only the active lesson's
frontmatter, so the link lives there. A lesson without `teaches` is guided at the course's
default (section 2.6).

### 2.3 Levels are opt-in

```yaml
levels: true                             # new, MAY; default false
```

Without it there is no ledger, no level-dependent guidance and no material selection, and
the course runs exactly as it does today. An explicit switch, rather than inferring levels
from the presence of `material` or `placement`, means a course cannot change behaviour by
accident, and an author can write material before turning levels on.

### 2.4 The ledger: `## Levels` in `STATE.md`

```markdown
## Levels

- `context-engineering` — B — placement 2026-11-03
- `agentic-patterns` — A — lessons/07-patterns-check.md 2026-12-10 (was B)
- `git-basics` — C — learner 2026-11-03 (assessed B)
```

One row per concept, **updated in place**, in the shape `## Assessments` and
`## Optional lessons` already use: `` - `id` — level — source date `` and an optional
parenthesis. The source is `placement`, the path of the assessment lesson that set it, or
`learner`.

**A concept without a row is level A.** No evidence of prior knowledge means the closest
guidance. Recording the absence would cost one line per concept per instance and say
nothing.

The ledger is progress, so it lives in `STATE.md`, which `state-lifecycle.md` keeps as the
only place progress is recorded. It is distinct from `## Concepts demonstrated`, which
records what a learner showed while working; the ledger records the level an assessment
assigned. The two will often agree and are not required to.

### 2.5 How a level is set

**Every assessment sets the level of each concept it assesses**, by one rule the runner
fixes. The rule is the runner's and not the author's because a cohort is compared across
participants, and a per-course threshold would make two courses' levels mean different
things:

| The concept's outcome in the assessment | Level |
|---|---|
| demonstrated | C |
| partial | B |
| misconception | A |
| not enough evidence after asking again, or the assessment stopped | unchanged (A if no row) |

The latest assessment wins, so a level moves up or down; the row records the level it
replaced. *Not enough evidence* never lowers a level, for the reason the assessments design
gives at section 3.1: it describes the answer's legibility, not the learner's knowledge.

**The entry assessment** is an ordinary assessment lesson marked `placement: true` in its
frontmatter, placed wherever the author lists it in `lessons` — typically right after a
setup lesson. It differs from other assessments in exactly three ways:

1. **it never remediates.** No practice is offered and no loop starts: the level it assigns
   *is* the response to a weak result, and a learner expected to know little would
   otherwise be offered practice on most of the course before starting it;
2. **it is not retaken.** In-course assessments move levels from then on;
3. **it is broad.** It assesses many concepts, so it asks one question per concept and one
   narrower follow-up only on a partial answer.

A course has at most one placement lesson. Its row in `## Assessments` is written as for
any assessment.

**The learner may ask for a different level** for a concept. The row then records
`learner` and, in the parenthesis, what the assessment had assigned. This keeps the
learner's say over their own route, decided in the design discussion, at the granularity
the programme needs. A course cannot forbid it in this design; if a programme needs
assessment-assigned levels only, that is a later, additive key.

### 2.6 What a level changes: guidance

The runner defines this, uniformly across courses:

| | A — guided | B — options | C — self-directed |
|---|---|---|---|
| Tasks | one small step at a time, the reason first | the goal and two or three approaches; the learner chooses and says why | the goal and its acceptance criteria only |
| Theory | offered before the task | on request, or when a mistake shows it missing | on request only |
| Help ladder | rungs 1–5 | rungs 1–5, starting from the learner's own attempt | rungs 1–3 |
| Checking understanding | after each step | at the end of the task | through the validators and the assessments |

**A task is guided at the level of the concept it exercises; across several, the lowest.**
Guide the least-prepared part. When the active lesson declares no `teaches`, or levels are
off, the course's existing behaviour applies unchanged.

**A learner at C who wants more help lowers that concept's level** (section 2.5). That keeps
"C helps only abstractly" true without leaving anyone stuck behind a rule.

**Inside an assessment every learner is at rung 3**, whatever their level — the assessments
design's ceiling, unchanged. A level changes how a learner is guided to the evidence, never
what evidence they must produce: lesson order, validators, `advance_on` and completion
conditions are the same at every level.

### 2.7 What a level changes: material

The lesson body is shared material for every level. A **folder** lesson MAY add material per
concept and level:

```yaml
---
id: 03-context
title: Context engineering
teaches: [context-engineering, prompting]
material:                                # new, MAY; folder lessons only
  context-engineering:
    A: material/context-engineering-A.md
    C: material/context-engineering-C.md
---
```

- **The tutor loads one file per taught concept**: the one for the learner's level. The
  context budget becomes one lesson plus at most one file per concept in `teaches`.
- **A missing level falls back towards more guidance** — C to B to A — and then to the body
  alone. An author can write A first and add the rest later.
- **Declared material satisfies the folder naming rule**, as `supplies` already does: the
  declaration states strictly more than a prose mention. Material the body names in prose
  stays reachable as before.
- Every key under `material` is a concept in `teaches`; every level key is `A`, `B` or `C`.

### 2.8 The format number does not move

Every new key is additive and MAY: `goals`, `levels` in the manifest; `goal` on a `covers`
concept; `teaches`, `material` and `placement` in a lesson's frontmatter. `bundle_format`
stays `1`.

| Reader | Sees a course using this design | Result |
|---|---|---|
| this runner, `levels` absent | — | exactly today's behaviour |
| an older runner | unknown keys, ignored | the body for everyone, guided as today; the placement lesson runs as an ordinary assessment and offers practice |
| an older validator | unknown top-level keys | check 28 **warns** and never rejects, so the course stays usable |

`bundle-format.md` section 13 gains the row for the older runner, as it has for every
additive key.

---

## 3. Validator

New checks take the next free numbers when this is implemented. On `main` today check 34
(`report`) is the last; PR: belay#72 adds check 35 (`sections`), so these start at 36 if it
lands first. Each check is silent when its key is absent and reports a malformed
declaration as a finding.

| Check | Mode | Reports |
|---|---|---|
| goals | both | `goals` not a map; a goal without a non-empty `title`; a `covers` concept whose `goal` is not a key in `goals`; an unknown key inside a goal |
| levels | both | `levels` not a boolean |
| teaches | both | `teaches` not a non-empty list; an id that is not a key in `covers` |
| material | both | `material` on a single-file lesson; a concept key not in that lesson's `teaches`; a level key other than `A`, `B`, `C`; a path that does not resolve inside the lesson's own folder |
| placement | both | `placement` not a boolean; `placement: true` without `assesses`; more than one placement lesson; a placement lesson listed in `optional_lessons` |
| level rows | instance | a `## Levels` row that does not parse, names a concept not in `covers`, or carries a level other than `A`, `B`, `C` |

Check 28's list of known top-level keys gains `goals` and `levels`. Lesson frontmatter has
no list of known keys today — `assesses` is read by name — so `teaches`, `material` and
`placement` are read by name too, each beside its constant.

---

## 4. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 2: `goals`, `levels`, `goal` on a concept; section 6: `teaches`, `material`, `placement`, and writing a placement lesson; section 13: the older-runner row; section 10's self-check |
| `runner-protocol.md` | a new section, **Levels**: reading the ledger, the guidance table, which level applies, material selection; section 15: the placement lesson's three differences and the outcome-to-level rule |
| `state-lifecycle.md` | `## Levels`: shape, when it is written, the absent-row rule, repair |
| `SKILL.md` | the loading table: one material file per taught concept, at the learner's level |
| `2026-09-11-tutorial-runner-design.md` | section 18's status, and a pointer here |

---

## 5. Acceptance criteria

1. **Existing courses are unaffected.** All suites pass unchanged, and the validator run
   with `BELAY_SWEEP_SIBLING_REPOS=1` over every published bundle in `skomp/belay-bundles`
   reports no new finding and no new warning.
2. Each new check has a fixture that trips it — proving the check can report a positive —
   and passes on a valid declaration.
3. A new fixture, `levelled-course`, declares `goals`, `sections`, `levels: true`, a
   placement lesson, `teaches` on every lesson, and `material` with a missing level, and
   validates clean in both modes.
4. An instance of that fixture with a `## Levels` section validates; one with a bad row
   reports exactly that row.
5. The runner protocol states the outcome-to-level rule, the lowest-level rule, the C
   ceiling at rung 3, the fallback order, and that a placement lesson never remediates — each
   in one place, referenced from the others.

The tutor's behaviour under levels is protocol text, not code, and no suite here can execute
it. A dry run of the `levelled-course` fixture in `skomp/belay-authoring`'s harness is the
check for it, and is filed there as an issue rather than built here.

---

## 6. Non-goals

- **No per-course level thresholds.** The outcome-to-level rule is the runner's (section 2.5).
- **No more than three levels**, and no renaming them per course.
- **No level gates anything.** A learner at A takes the same lessons, passes the same
  validators and reaches the same end as a learner at C.
- **No new grouping of lessons.** Modules are `sections`.
- **Nothing in section 1.1** — scaffolding, use-case guidance, cohort review, the module gate,
  the final project and the certificate are designed separately.
