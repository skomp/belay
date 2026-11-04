# Learning goals, per-objective levels, and modules as bundles — Design

**Date:** 2026-11-03
**Last amended:** 2026-11-04
**Status:** implemented — see §7 for the decisions the implementation added;
`bundle-format.md` §2, §6, §10, §13, `catalogue-format.md` §5.3, `runner-protocol.md`
§15.10-15.11 and §18, `state-lifecycle.md` §13, validator checks 35-41 and catalogue checks
8-9, `tests/fixtures/levelled-programme/`
**Related:** the assessments design (2026-09-19), whose assessment lessons set levels here;
PR: belay#71, whose `remote` progress choice the carry-forward relies on

---

## 1. The problem

A Belay course teaches every learner the same way. It knows which concepts it teaches
(`covers`), and it can assess them (`assesses`), but nothing it learns about a learner
changes how the tutor guides them or what material they read.

The motivating case is a cohort programme: a group takes the same course, builds the same
project, and is graded on the same tasks, but arrives with very different prior knowledge,
and unevenly so. One participant can explain Git and has never seen a graph-based agent
framework; the next is the reverse.

The programme is built and delivered **one module at a time**: the next module is written
while the cohort works through the current one, and every module starts from the **best
solution of the previous module**, which is not known until that module's review. So the
programme cannot be shipped as one course up front.

### 1.1 Terms

| Term | Meaning | In the format |
|---|---|---|
| **programme** | the whole curriculum a cohort takes | a **catalog** |
| **learning goal** | a broad content area, taught across many modules rather than in one | a key in the catalog's `goals` |
| **learning objective** | one thing a participant can do or explain; the unit that is assessed | a **`covers` concept**, listed under its goal in the catalog |
| **module** | one stretch of the programme, ending in a checkpoint | a **bundle** |
| **level** | how closely the tutor guides a participant on one learning objective | a row in `## Levels` |

The three levels:

| Level | Name | What it means for the participant |
|---|---|---|
| **A** | guided | the least prior knowledge, and the closest guidance |
| **B** | options | works by choosing between offered approaches |
| **C** | self-directed | works it out alone; the tutor helps only abstractly |

A participant has a level **per learning objective**, not one for the whole programme. An
entry assessment sets the levels; assessments inside the modules keep them current, and
they carry from one module to the next.

The prose of this design and of the reference documents says *learning objective*; the
YAML says `covers` concept. They are the same thing, and no alias key is added for it.

### 1.2 What this design does not cover

The same programme needs further pieces. Each is a separate design, built on this one; items 1
and 2 became the one design `2026-11-03-user-stories-design.md`:

1. **Story scaffolding** (belay#92) — a module's user stories arrive pre-cut, cut with
   options, or uncut, fading over the programme regardless of the participant's levels.
2. **Use-case guidance** (belay#93) — the hand-off from a user story to a spec-driven
   workflow in which the participant specifies and the agent implements.
3. **Cohort review and the module gate** (belay#94) — at a module's end, grade every
   participant's branch on the same criteria, explain the best solution and why the others
   convince less, and publish the winning branch as the next module's start (section 2.2).
   A module is passed when its functional requirement is technically met, which is a gate on
   validators and gate rubric criteria, not on assessments.
4. **Final project and certificate** (belay#95) — a capstone chosen from a curated set,
   worked entirely at level C, and a certificate.

Decisions already taken for (3) and (4), recorded so they are not re-litigated:

- the grade is **hybrid**: validators weighted for a deterministic share, plus a capped
  share judged against a rubric of `covers` summaries;
- **exam mode is per lesson**: a lesson declaring `exam: true` caps the help ladder at rung 3,
  reveals no solution and applies no level, however many a bundle has
  (`2026-11-03-cohort-grading-design.md` section 2.2). This replaces "a graded task runs in exam mode";
- **a record in the participant's own repository is traceable, not tamper-proof.** Belay has
  no server, and the participant and their agent can edit anything in their workspace. A
  certificate therefore rests on the trainer-run reviews, recorded where the trainer
  controls them; the self-run assessments recorded here are learning, not proof.

---

## 2. Decisions

### 2.1 The programme is a catalog; a module is a bundle

A catalog already holds several bundles, and `recommended_previous_bundles` already links a
bundle to the one before it. A module as a bundle can be written, validated, published and
installed on its own, which is what building the next module while the current one runs
requires.

**Learning goals are declared once, in the catalog**, as a new top-level key:

```yaml
# catalogs.yaml of the programme
catalog_version: 1
goals:                                   # new, MAY
  llm-foundations:
    title: Foundations and how LLMs work
    summary: >
      Python and developer craft, how a language model produces text, prompting and
      context engineering.
    objectives: [python-basics, how-llms-work, prompting, context-engineering]
tutorials:
  - id: programme-m2
    title: Module 2 — Evals and error analysis
    # ... the usual entry fields ...
    recommended_previous_bundles:
      - bundle: programme-m1
        because: Module 2 starts from the best solution of module 1.
    start_from:                          # new, MAY; section 2.2
      repo: https://github.com/example-org/cohort-1
      ref: winner-m1
```

**A goal lists its learning objectives**, by the `covers` ids the modules use. The bundles
carry nothing new for it.

- **A goal groups learning objectives, never lessons or modules.** A learning goal is taught
  across modules, and a cross-cutting topic — data protection, say — is a goal whose
  objectives appear in several modules.
- **Objective ids are shared across the programme's bundles.** That is what lets a level set
  in module 1 apply in module 3. The format already treats concept ids as stable,
  cross-bundle identifiers (`bundle-format.md` section 2, **Concept identifiers**).
- **The link lives in the catalog, not on the concept.** A `goal` key inside a `covers`
  concept was considered and rejected: every released validator reports an unknown key
  inside a concept as a check 23 **finding**, so a module using it would fail validation on
  any participant whose installed Belay predates this design. Listing objectives under the
  goal leaves every bundle readable by every released runner and validator, and keeps the
  mapping in the one file the trainer already maintains.
- **The catalog validator checks the list**: every listed objective is a `covers` key of
  some entry in the same catalog, and an objective is listed under at most one goal. An
  entry's objective listed under no goal is allowed, and silent.
- An older reader warns about the unknown top-level key `goals` and keeps the catalog usable
  (`catalogue-format.md` section 5).

### 2.2 A module can start from a branch chosen after it was written

```yaml
# tutorial.yaml of module 2
starts_from: ref                         # new, MAY; the only value
```

`starts_from: ref` says: this module's starting code is not in the bundle and not in the
participant's workspace; it is the code at a Git ref named later. The **catalog entry's
`start_from`** names it — a `repo` URL and a `ref` — and the trainer sets it once the review
has chosen a winner. Who writes the module and who chooses the start stay separate, and the
catalog is the trainer's single place to say it.

**Starting the module:**

1. The runner reads `start_from` from the catalog entry that won the merge for the bundle's
   `id`. **With no `start_from`, the module cannot start yet**: the tutor says that the
   previous module's review has not published a starting point, and stops.
2. The tutor proposes, and the participant runs, the Git commands that create the
   participant's new branch from the ref — for example
   `git fetch <repo> <ref> && git switch -c <participant>/<module-id> FETCH_HEAD`. The runner
   never runs a Git operation that changes the participant's repository on its own, as
   `instance_git.py` already does not.
3. The tutor has the participant remove the `tutorial/` directory that came with the
   winner's code — only its tracked files, with `git rm -r -- tutorial/`. **The winner's
   code carries over; the winner's progress never does.** Before the branch switch and
   again before the removal, an untracked or ignored file in `tutorial/` (`git status
   --porcelain --ignored`) is the participant's own and stops the procedure until they
   decide what to do with it: `git switch` silently overwrites an ignored file the new
   branch tracks.
4. Materialization proceeds as for any bundle, then the carry-forward of section 2.4 runs.

One instance per workspace (2026-09-11 spec, section 15b) is unchanged: module n+1's instance
replaces module n's on a new branch, and module n's instance stays on the participant's
previous branch.

`starts_from` with any other value is a finding. A bundle without it starts as today.

### 2.3 A lesson says which learning objectives it teaches

```yaml
---
id: 03-context
title: Context engineering
teaches: [context-engineering, prompting]     # new, MAY; keys in `covers`
---
```

Today only `assesses` links a lesson to concepts. Section 2.6 needs to know which objectives'
levels apply to the active lesson, and the tutor holds only the active lesson's frontmatter,
so the link lives there. A lesson without `teaches` is guided as today.

### 2.4 Levels, and the record that carries them

```yaml
levels: true                             # new, MAY; default false; in tutorial.yaml
```

Without it there is no ledger, no level-dependent guidance and no material selection, and
the bundle runs exactly as it does today. An explicit switch means a course cannot change
behaviour by accident, and an author can write material before turning levels on.

**`STATE.md` stays the only place progress is recorded.** It gains two sections:

```markdown
## Levels

- `context-engineering` — B — lessons/04-check.md 2027-03-02 (was A)
- `agentic-patterns` — A — placement 2027-01-12
- `git-basics` — C — learner 2027-01-12 (assessed B)

## Modules

- `programme-m1` — complete 2027-02-26 — branch alice/m1; assessments: 6 passed,
  1 partial; not demonstrated: rag-chunking ×1
```

**`## Levels`** has one row per learning objective, updated in place, in the shape
`## Assessments` and `## Optional lessons` already use: `` - `id` — level — source date ``
and an optional parenthesis. The source is `placement`, the path of the assessment lesson
that set it, or `learner`. **An objective without a row is level A**: no evidence of prior
knowledge means the closest guidance, and recording the absence would say nothing.

**`## Modules`** has one row per finished module of the programme, appended when the next
module starts. It is a summary of that module's `## Assessments`, never a copy of it.

**The carry-forward**, run once when a `starts_from: ref` module is materialized (section
2.2, step 4):

1. The tutor asks the participant for their **own** previous branch and reads its
   `tutorial/STATE.md` through Git (`git show <branch>:tutorial/STATE.md`). It never reads the
   winner's.
2. It copies `## Levels` into the new `STATE.md` unchanged.
3. It copies `## Modules` and appends one row for the module just finished.
4. If the previous branch or its `STATE.md` cannot be read, the tutor says so, writes an
   empty `## Levels` (every objective at A) and an empty `## Modules`, and continues. It never
   borrows another participant's record.

The carry-forward needs the previous `STATE.md` to be committed and pushed: the `remote`
choice PR: belay#71 introduces. **A `starts_from: ref` module asks for `remote` and says
why**. `git show` reads only committed content, so a participant who keeps progress
`local` gets the empty-ledger path of step 4 on every machine, the one they worked on
included.

### 2.5 How a level is set

**Every assessment sets the level of each objective it assesses**, by one rule the runner
fixes. The rule is the runner's and not the author's because a cohort is compared across
participants, and a per-course threshold would make two modules' levels mean different
things:

| The objective's outcome in the assessment | Level |
|---|---|
| demonstrated | C |
| partial | B |
| misconception | A |
| not enough evidence after asking again, or the assessment stopped | unchanged (A if no row) |

The latest assessment wins, so a level moves up or down; the row records the level it
replaced. *Not enough evidence* never lowers a level, for the reason the assessments design
gives at section 3.1: it describes the answer's legibility, not the participant's knowledge.

**The entry assessment** is an ordinary assessment lesson marked `placement: true` in its
frontmatter, placed wherever the author lists it in `lessons` — typically right after a
setup lesson. **Any module may have one**, and it assesses **only the objectives in its
`assesses` that have no row in `## Levels` yet**: module 1 places everything it lists, and a
later module places only what is new to the participant. It differs from other assessments
in exactly three ways:

1. **it never remediates.** No practice is offered and no loop starts: the level it assigns
   *is* the response to a weak result;
2. **it is not retaken.** Ordinary assessments move levels from then on;
3. **it is broad.** One question per objective, and one narrower follow-up only on a partial
   answer.

A bundle has at most one placement lesson. Its row in `## Assessments` is written as for any
assessment. When every objective it lists already has a row, the tutor records it as
`skipped` with the reason, and moves on.

**The participant may ask for a different level** for an objective. The row then records
`learner` and, in the parenthesis, what the assessment had assigned. A bundle cannot forbid
it in this design; if a programme needs assessment-assigned levels only, that is a later,
additive key.

### 2.6 What a level changes: guidance

The runner defines this, uniformly across courses:

| | A — guided | B — options | C — self-directed |
|---|---|---|---|
| Tasks | one small step at a time, the reason first | the goal and two or three approaches; the participant chooses and says why | the goal and its acceptance criteria only |
| Theory | offered before the task | on request, or when a mistake shows it missing | on request only |
| Help ladder | rungs 1–5 | rungs 1–5, starting from the participant's own attempt | rungs 1–3 |
| Checking understanding | after each step | at the end of the task | through the validators and the assessments |

**A task is guided at the level of the objective it exercises; across several, the lowest.**
Guide the least-prepared part. When the active lesson declares no `teaches`, or levels are
off, the course's existing behaviour applies unchanged.

**A participant at C who wants more help lowers that objective's level** (section 2.5). That
keeps "C helps only abstractly" true without leaving anyone stuck behind a rule.

**Inside an assessment every participant is at rung 3**, whatever their level — the
assessments design's ceiling, unchanged. A level changes how a participant is guided to the
evidence, never what evidence they must produce: lesson order, validators, `advance_on` and
completion conditions are the same at every level.

### 2.7 What a level changes: material

The lesson body is shared material for every level. A **folder** lesson MAY add material per
objective and level:

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

- **The tutor loads one file per taught objective**: the one for the participant's level. The
  context budget becomes one lesson plus at most one file per objective in `teaches`.
- **A missing level falls back towards more guidance** — C to B to A — and then to the body
  alone. An author can write A first and add the rest later.
- **Declared material satisfies the folder naming rule**, as `supplies` already does: the
  declaration states strictly more than a prose mention.
- Every key under `material` is an objective in `teaches`; every level key is `A`, `B` or `C`.

### 2.8 The format number does not move

Every new key is additive and MAY: `goals` and `start_from` in a catalog; `levels` and
`starts_from` in `tutorial.yaml`; `teaches`, `material` and
`placement` in a lesson's frontmatter. `bundle_format` and `catalog_version` stay `1`.

| Reader | Sees a course using this design | Result |
|---|---|---|
| this runner, `levels` and `starts_from` absent | — | exactly today's behaviour |
| an older runner | unknown keys, ignored | the body for everyone, guided as today; the placement lesson runs as an ordinary assessment and offers practice; a `starts_from: ref` module starts in whatever workspace it is given, without the winner's code |
| an older validator | unknown top-level keys and entry fields; unknown lesson frontmatter keys | check 28 and catalog checks 1 and 3 **warn** and never reject; lesson frontmatter keys are read by name, so the new ones are not seen at all. Measured on 2026-11-03: nothing this design adds is inside a structure an older validator checks key by key |

An older validator accepts a folder lesson's `material` files for one reason only: its
check 6 (`names_file`) searches the whole `LESSON.md`, frontmatter included, so the
`material` declaration itself names each file. Making `names_file` skip the frontmatter
would turn every such file into a check 6 finding for every validator that does not read
`material`.

`bundle-format.md` section 13 gains the row for the older runner, as it has for every
additive key. The older runner's behaviour on `starts_from` is a real degradation, and the
section says so plainly: a programme that uses it needs a runner that knows it.

---

## 3. Validator

New checks take the next free numbers when this is implemented; on `main` today check 34
(`report`) is the last. Each is silent when its key is absent and reports a malformed
declaration as a finding.

| Check | Mode | Reports |
|---|---|---|
| levels | both | `levels` not a boolean |
| starts_from | both | `starts_from` with a value other than `ref` |
| teaches | both | `teaches` not a non-empty list; an id that is not a key in `covers` |
| material | both | `material` on a single-file lesson; an objective key not in that lesson's `teaches`; a level key other than `A`, `B`, `C`; a path that does not resolve inside the lesson's own folder |
| placement | both | `placement` not a boolean; `placement: true` without `assesses`; more than one placement lesson; a placement lesson listed in `optional_lessons` |
| level rows | instance | a `## Levels` row that does not parse, or carries a level other than `A`, `B`, `C` |
| module rows | instance | a `## Modules` row that does not parse |

A `## Levels` row may name an objective the current bundle does not cover, because it was
set in an earlier module; that is not a finding.

**Catalog checks:**

| Check | Reports |
|---|---|
| goals | `goals` not a map; a goal id not matching `[a-z0-9-]+`; a goal without a non-empty `title`; `objectives` not a non-empty list of strings; an unknown key inside a goal; an objective that no entry's `covers` declares; an objective listed under two goals |
| start_from | `start_from` without both `repo` and `ref`; a `repo` that is not an `https://`, `ssh://` or scp-style Git URL whose host (and any user) begins with a letter or digit, or that holds whitespace or a shell character; a `ref` outside `[A-Za-z0-9_][A-Za-z0-9._/-]*` or holding `..`, `//`, `/.`, or ending in `/`, `.` or `.lock`; an unknown key inside it |

Check 28's list of known top-level keys gains `levels` and `starts_from`; the catalog's
known top-level keys gain `goals`, and its known entry fields gain `start_from`. Lesson
frontmatter has no list of known keys today — `assesses` is read by name — so `teaches`,
`material` and `placement` are read by name too.

---

## 4. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 2: `levels`, `starts_from`; section 6: `teaches`, `material`, `placement`, and writing a placement lesson; section 13: the older-runner rows; section 10's self-check |
| `catalogue-format.md` | `goals` at the top level; `start_from` on an entry; the new checks |
| `runner-protocol.md` | a new section, **Levels**: reading the ledger, the guidance table, which level applies, material selection; section 15: the placement lesson's differences and the outcome-to-level rule; starting a `starts_from: ref` module |
| `state-lifecycle.md` | `## Levels` and `## Modules`: shape, when each is written, the absent-row rule, the carry-forward, repair |
| `SKILL.md` | the loading table: one material file per taught objective, at the participant's level |
| `2026-09-11-tutorial-runner-design.md` | section 18's status, and a pointer here |
| `README.md` | the feature list |

---

## 5. Acceptance criteria

1. **Existing courses are unaffected.** All suites pass unchanged, and the validator run
   with `BELAY_SWEEP_SIBLING_REPOS=1` over every published bundle in `skomp/belay-bundles`
   reports no new finding and no new warning.
2. Each new check has a fixture that trips it — proving the check can report a positive —
   and passes on a valid declaration.
3. A new fixture programme — a catalog with `goals` and two module bundles, the second with
   `starts_from: ref` and a `start_from` entry — validates clean. Module 1 has a placement
   lesson, `levels: true`, `teaches` on every lesson, and `material` with a missing level.
4. An instance with `## Levels` and `## Modules` sections validates; one with a bad row
   reports exactly that row; a `## Levels` row naming an objective from an earlier module is
   not reported.
5. The runner protocol states the outcome-to-level rule, the lowest-level rule, the C ceiling
   at rung 3, the material fallback order, that a placement lesson never remediates and places
   only objectives without a row, and the carry-forward with its never-borrow rule — each in
   one place, referenced from the others.

The tutor's behaviour under levels and the carry-forward are protocol text, not code, and no
suite here can execute them. A dry run of the fixture programme in `skomp/belay-authoring`'s
harness is the check for them, and is filed there as an issue rather than built here: belay-authoring#43.

---

## 6. Non-goals

- **No per-course level thresholds.** The outcome-to-level rule is the runner's (section 2.5).
- **No more than three levels**, and no renaming them per course.
- **No level gates anything.** A participant at A takes the same lessons, passes the same
  validators and reaches the same end as a participant at C.
- **No Git operation the runner performs on its own.** Section 2.2's commands are proposed and
  run by the participant.
- **No tamper protection.** Section 1.2 says where a trustworthy result comes from instead.
- **Nothing in section 1.2** — story scaffolding, use-case guidance, cohort review, the module
  gate, the final project and the certificate are designed separately.

---

## 7. Implementation notes

Implemented on 2026-11-03. Writing the protocol forced six decisions this design left open;
each is stated once, where the tutor reads it.

1. **The runner cannot see `starts_from` before materializing.** Discovery and `resolve`
   read the catalogue entry, never the bundle, and the learner's new branch has to exist
   before `tutorial/` is created. So the procedure keys on the entry: `resolve --json`'s
   `start_from` decides whether to propose a branch, and a module whose instance turns out
   to declare `starts_from: ref` with no `start_from` stops before its first task, the
   just-created `tutorial/` left for the learner to remove (`runner-protocol.md` §18.6). A
   later `resolve` that also printed the bundle's `starts_from` — it is allowed to open the
   bundle — would remove the second case.
2. **Git argument hygiene is the reader's and the protocol's.** The catalogue reader drops
   a `start_from` whose `repo` host or scp user does not begin with a letter or digit,
   whose `repo` holds whitespace or any of `` ` $ ; | & < > ( ) ' " \ ``, or whose `ref`
   is not `[A-Za-z0-9_][A-Za-z0-9._/-]*` free of `..`, `//`, `/.` and a trailing `/`, `.`
   or `.lock` (`catalogue-format.md` §5.3). The tutor still refuses a `repo` or `ref`
   beginning with `-` or holding those characters, puts `--` before them in `git fetch`,
   and never runs the commands itself (`runner-protocol.md` §18.6).
   The same rules cover the fetch of the learner's own previous branch when it is not in
   the checkout, which the carry-forward then reads as `<remote>/<branch>`
   (`state-lifecycle.md` §13.4).
3. **A quiz the learner asked for sets no level.** It has no lesson path to record as a
   source, which check 40 requires, and the learner already has a direct route: asking
   for a different level (`runner-protocol.md` §15.11, §18.5).
4. **An objective's outcome in an attempt** is *demonstrated* when any answer showed it;
   otherwise the last answer classified *partial* or *misconception*; and *not enough
   evidence* only when no answer was classified as anything else — so a terse reply after a
   misconception does not leave the level unchanged. An objective a stop left unasked is
   unchanged (`runner-protocol.md` §15.11). *Unchanged* means only that last table row and
   writes nothing; every other outcome writes a row, so a misconception on an objective with
   no row writes `A` and the next placement does not ask it again, and an outcome that
   confirms the existing level rewrites the source and date with no `(was …)`
   (`state-lifecycle.md` §13.2).
5. **No `## Modules` row for an unfinished module.** Check 41 requires `complete` and a
   date, so the carry-forward appends nothing for a previous module whose `status` is not
   `complete`, and says so (`state-lifecycle.md` §13.4).
6. **The `remote` requirement names PR: belay#71**, which introduces the choice, rather than
   a section of `state-lifecycle.md`: this design was implemented on a branch without it.
   Whatever the choice, the previous `STATE.md` reaches the next module only when it is
   committed, and pushed when the learner changes machine.
