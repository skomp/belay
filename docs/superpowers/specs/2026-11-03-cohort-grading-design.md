# Grading a cohort's module, on the trainer's machine — Design

**Date:** 2026-11-03
**Last amended:** 2026-11-05
**Status:** implemented — `skills/belay/scripts/grade.py` and `bin/belay-grade`, validator
checks 47-51, `bundle-format.md` §2 **Cohort grading** and §6 **Writing an exam lesson**,
`runner-protocol.md` §15.14 and §20, `tests/test_grade.py`. **The manual run is outstanding:** the
real container path has never run, because neither docker nor podman is on the development
machine; `runner-protocol.md` §20.9 lists what to check.
**Issue:** belay#94
**Builds on:** the levels and modules-as-bundles design (2026-11-03, PR: belay#91); the
task-lessons design (PR: belay#101), whose participant-written files can be graded here
**Related:** belay#95 (final project and certificate), which reads the grades this stores

---

## 1. The problem

In a cohort programme every participant builds the same module on their own branch. At the
module's checkpoint the solutions are graded on the same criteria, the best one is explained
and the others are told why they convince less, and everyone continues from the best solution.

Belay has one learner per instance and nothing that looks across participants. It also has no
grade: an assessment records outcomes, not points.

### 1.1 Decisions taken in the design discussion

- **The trainer grades, on their own machine.** A command such as "grade module programme-m1
  from the cohort repository" collects every participant's branch and grades it there.
- **Grades never leave the trainer's machine** except as feedback the trainer sends. They are
  never written to the cohort repository.
- **The employer receives only the certificate result** — passed or not passed. Grades, levels,
  assessment results and rankings stay inside the training. (Agreed with the client on
  2026-11-03 to keep the works-council question small; the client's legal team confirms it.
  Recorded on belay#94 and belay#95.)
- **The grade is hybrid**: validators give a deterministic share, a rubric judged by the AI
  gives the rest, and the deterministic share is the larger.
- **The AI proposes and the trainer decides.** Only grades the trainer confirms are final. This
  is also the human decision GDPR Art. 22 asks for.
- **Participant code runs in a container**, with the network as declared: a module that teaches
  agents calling external services turns it on.
- **The module gate** (a module is passed when its functional requirement is technically met)
  is its gate validators and any gate criteria of its rubric (section 2.3). It never blocks the
  participant; it is recorded at the checkpoint.
- **Exam mode is a per-lesson flag**, as many per bundle as a course needs. Outside an exam
  lesson the participant's levels decide how much the tutor helps.

---

## 2. Format

### 2.1 `grading:` in a module bundle's `tutorial.yaml`

```yaml
grading:
  image: registry.example/programme/python-grading:3.12  # the validators run in it; holds their tools
  network: true                    # default false
  env: [ANTHROPIC_API_KEY]         # the only environment variables passed in
  timeout_minutes: 15              # per branch, for all validators together
  validators:                      # deterministic share: the points if the validator passes
    own-tests-pass: { points: 20, gate: true }  # the participant's own test suite
    coverage-60:    { points: 10 }              # a coverage tool with a threshold
    coverage-80:    { points: 10 }
    mutation-60:    { points: 20 }              # mutation testing with a threshold
  rubric:                          # judged share
    - id: failure-handling
      points: 15
      standard: Every external call has a timeout and a handled failure path.
      paths: [src/**]              # where the grader looks; default: the whole branch
    - id: exam-design
      points: 10
      standard: The design choice is justified against the stated non-functional requirement.
      paths: [exam/07/**]          # the folder lessons/07-exam.md tells the participant to use
    - id: spec-quality
      points: 10
      standard: Each acceptance criterion is testable and traced to a task.
      paths: [specs/**]
```

- **A validator earns its points when it passes and none when it does not.** There is no partial
  credit for a validator; a module that wants finer points splits a validator into several.
- **The deterministic share is at least 60% of the total points.** The runner fixes the
  proportion so that every module and every cohort means the same thing by "hybrid".
- **A rubric criterion's `standard` is one checkable sentence**, in the spirit of a `covers`
  summary. The grader judges a branch against it and quotes the evidence.
- **`paths` says where the grader looks**: a list of workspace globs. A course that grades
  specifications or participant-written task files points a criterion at them — for example
  `specs/**` or the `own_tasks` directory of a task lesson. Without `paths` the grader looks at the
  whole branch. **This format has no glob dialect today**: the ownership dialect this bullet once
  named exists only on unmerged PR: belay#69. So check 49 applies the path rules of `own_tasks` (check
  45) and leaves wildcards unvalidated, and the tutor reads each entry as a Git `:(glob)` pathspec.
- **Only `command`, `file-exists` and `file-contains` validators can earn points.** `manual` needs
  a learner to supply evidence, and no learner is present during grading; `git-diff` inspects
  uncommitted changes, and a fresh checkout has none. Only `command` runs in the container
  (section 4); the two file kinds are checked directly on the checkout and run no code.
- **A branch does not record which lesson produced which file**, so a criterion cannot name a
  lesson. An exam lesson tells the participant which folder to put the work in, and the criterion
  points there with `paths`.
- `grading:` is in `tutorial.yaml`, so **participants can read the criteria from the start.**
  They never see anyone's grades.

### 2.2 Exam lessons

```yaml
---
id: 07-exam
title: Exam — design under a latency budget
exam: true                         # new, MAY
---
```

In an exam lesson, whatever the participant's level:

- the help ladder stops at rung 3, and the tutor reveals no solution;
- the tutor says at the start that the lesson is an exam, and what that means for help;
- levelled material and level-dependent guidance do not apply; the tutor presents what the lesson
  body states and adds no explanation of its own;
- `ownership_policy` is narrowed: the tutor does not write the work under `on-request` or
  `unrestricted`, because that hands over a solution. Placing `supplies` stays;
- no generated or side lesson on what the exam's work uses, no optional lesson offered or re-offered,
  and no `required_for`, until the exam lesson has ended.

A bundle may have any number of exam lessons, or none. A final-project bundle is a bundle whose
lessons are exam lessons; there is no separate final-project concept here.

### 2.3 The gate

A validator with `gate: true` is a gate validator. The gate of a module is passed when all its
gate validators pass.

**The rubric can gate too.** `gate: true` is allowed on a rubric criterion, which then must earn its
full points. A module uses this for the two things no validator can show: that every acceptance
criterion has a passing test with an assertion, and a simple quality review ("a reader can follow
this code, and nothing in it is a stub or a placeholder"). The gate is passed when every gate
validator passes and every gate criterion earns full points. The AI proposes the criterion's points
and the trainer confirms them, so a person decides.

**A course ships no tests for grading.** Decided on 2026-11-04: shipped tests would fix the
participant's interface, and a module's code base is not known when the module is written. The
deterministic share measures the participant's own tests instead: that they pass, how much code
they reach (a coverage tool with a threshold), and whether they detect a change (mutation testing
with a threshold). Each is an ordinary `command` validator, so a course names its own tools; finer
points come from several thresholds, because a validator has no partial credit. Whether the tests
cover the specification is a rubric criterion.

**The limit, stated plainly:** a participant owns the branch, so they can exclude files, add pragmas
or fake a tool's result. Commands pass their settings explicitly, and a rubric criterion looks for
exclusions. This raises the cost of cheating and does not remove it, which is one reason a person
confirms every grade.

- **The participant's tutor** runs gate validators like any other validator. When one fails it
  says the module's gate is not met yet. It never blocks.
- **The grader** records gate passed or not passed for each participant at the checkpoint, from the
  confirmed points.
- **Everyone continues from the winning branch either way.** "Not passed" is an input to the
  certificate (belay#95).

---

## 3. The grading run

The trainer asks, in their own Claude Code session with Belay, to grade a module from a cohort
repository. The tutor runs a new script, `belay-grade`, step by step, and shows each step's
result before the next.

1. **Collect.** `belay-grade collect <repo> <module-id>` fetches the cohort repository into a
   local cache and lists the branches matching `*/<module-id>`: participant (the part before
   the slash), branch, last commit and its date. The trainer confirms the list or removes
   entries: `run --only` names those kept, and `confirm --exclude` names those removed, because
   `confirm` otherwise refuses while the cache holds a branch of the module that the proposal does
   not cover. Branches that match no convention are listed separately and never graded.
2. **Run.** For each confirmed branch, `belay-grade run` checks out a fresh temporary copy and
   runs the bundle's `grading.validators` in a container (section 4). It records, per
   validator, passed or failed, its output (truncated to a fixed size), and whether it is a gate
   validator. This step has no AI judgement. A run takes far longer than a tutor's shell tool
   allows, so its warnings come before the first branch starts, its output is line-buffered, and
   `run.json` grows after each branch; the protocol has the tutor run it in the background.
3. **Judge.** The tutor judges **every branch against every rubric criterion in one pass**,
   side by side, so the standard does not drift from one participant to the next. Per criterion
   and branch it records points (an integer from 0 to the criterion's points), and evidence:
   quoted code, specification text or validator output, with file and line.
4. **Propose.** The tutor writes the draft into the judgement, and `belay-grade propose` writes the proposal: per participant the validator
   points, the rubric points with evidence, the gate result and the total; the ranking; and a
   draft of why the best solution is best and what the others lack. Nothing is final.
5. **Confirm.** The trainer goes through the proposal and may change any criterion's points,
   with a reason. `belay-grade confirm` writes the final grades only when the trainer confirms,
   and records who confirmed, when, and every change with its reason.
6. **Draft the outputs**, only after confirmation:
   - **the shared module review**, for the cohort repository: the winning solution and what
     made it best, and the weaknesses several solutions shared — with no participant names and
     no grades;
   - **private feedback** per participant: their own points per criterion with evidence, their
     gate result, and what would have earned more;
   - **the suggested start** for the next module: the cohort repository and the winning branch.

**The grader never publishes, sends or pushes anything.** Committing the shared review, sending
each participant their feedback, and setting the next module's start are the trainer's actions.

---

## 4. Running participant code

Grading executes code the trainer has not reviewed, much of it written by agents. Isolation
therefore comes from what the code cannot reach on the trainer's machine:

- **A container per `command` validator**, from the bundle's `grading.image`, using docker or
  podman, all sharing the branch's one mount. So a file written to the mount reaches the next
  validator, and a `pip install` outside it does not. `file-exists` and `file-contains` run first and
  need no container. **Without a container runtime, step 2 stops and says so.** It never falls back
  to running the code directly.
- **Limits on every container:** `--pids-limit 512`, `--memory 4g`, `--security-opt
  no-new-privileges`, so that one branch cannot take the machine down or gain privileges. A mutation
  validator may hit them, or need a larger `timeout_minutes`, and that reads as a failure.
- **Only the checkout is mounted**, at a fixed path (`/workspace`). Nothing of the trainer's — no home
  directory, no `~/.ssh`, no Git or GitHub credentials, no Claude login — is mounted or copied.
- **Network as declared**: on only when `grading.network` is true.
- **Environment as declared**: only the variables named in `grading.env` are passed, taken from
  the trainer's environment. The grader warns when one is missing and never passes an
  undeclared one. The protocol tells the trainer to use a separate key for grading, with a
  spending limit, because participant code can read and send anything it is given.
- **A time limit per branch** (`grading.timeout_minutes`). A branch that exceeds it has its
  remaining validators recorded as failed, with the reason.

---

## 5. Where grades live

```
~/.local/share/belay/grading/<cohort>/
├── .repo.git/                       # the cache of the repository: every branch, refreshed by collect
└── <module-id>/
    ├── run.json                     # the validator results, per branch
    ├── judgement.json               # the tutor's points and evidence, the input to propose
    ├── proposal.json
    ├── final.json
    ├── final.<date>.json            # a previous confirmation, kept when re-graded
    ├── review.md                    # the shared module review, draft
    └── feedback/<participant>.md    # private feedback, draft
```

- `<cohort>` is derived from the repository URL. The base directory follows `XDG_DATA_HOME`.
- **`belay-grade` refuses to write inside any Git work tree**, so grades cannot be committed by
  accident.
- **Re-grading** writes a new proposal. `final.json` is replaced only by a new confirmation, and
  the previous one is kept beside it with its date. A confirmation starts from the proposal, so the
  trainer's earlier changes are not carried over; `confirm` prints each one it does not repeat.
- **`belay-grade forget <cohort>`** deletes a cohort's grades, its working files and the cache. How long grades are kept is the
  trainer's decision; the protocol says so, because it is a data-protection question.
- The certificate (belay#95) reads the `final.json` of every module of a cohort from here.

The `final.json` shape is the contract belay#95 builds on: per participant `commit`, per validator
`{passed, points}`, per criterion `{points, proposed_points, max, evidence, changed_by_trainer, reason}`, `gate`,
`total`, `max_total`; and at the top `module`, `bundle_version`, `confirmed_by`, `confirmed_at`,
`not_graded`.

- **`commit` is the commit that was graded**, the value `proposal.json` holds under the same key, so a
  grade can be traced to the code it judged after the branch has moved.
- **`proposed_points` is always the AI's proposed value**, whether or not the trainer changed the
  criterion, because `proposal.json` is overwritten by a later proposal and the record exists to
  audit a human decision. `points` is the confirmed value.
- **A runtime fault is not a result.** A participant whose branch failed to check out, or whose
  validator ended with exit status 125, 126 or 127 or no status, is marked ungradable in the
  proposal, with the reason: no total, no rank, gate `null`. A timeout is the participant's own
  result and stays gradable. `confirm` refuses while any participant is ungradable, unless the
  trainer passes `--exclude <participant>`; an excluded participant is absent from `participants`
  and listed in `not_graded` as `{participant: {reason, commit}}`. The usual fix is to repair the fault and run
  again. `--exclude` also takes a participant with a branch the proposal does not cover, the entries
  removed at step 1, with a reason saying the trainer excluded them. It refuses a gradable participant
  the proposal covers.
- **Gate** is `true`, `false`, or `null` when the module has no gate validator and no gate criterion.

---

## 6. Validator

New checks take the next free numbers. All are silent when the key is absent.

| Check | Mode | Reports |
|---|---|---|
| grading shape | both | `grading` not a mapping; an unknown key; `image` not a non-empty string; `network` not a boolean; `env` not a list of valid variable names; `timeout_minutes` not a positive integer |
| grading validators | both | a name that is not a declared validator; a validator of kind `manual` or `git-diff`; `points` not a positive integer; `gate` not a boolean; a validator of kind `command` with no `image` |
| grading rubric | both | a criterion without `id`, positive integer `points`, or a non-empty `standard`; a duplicate `id`; an `id` that is not `[a-z0-9-]+` or that equals the name of a validator in `grading.validators`, because `confirm --change` could not address it; `paths` not a non-empty list of entries that pass the path rules of check 45, wildcards unvalidated; `gate` not a boolean |
| grading share | both | the validator points less than 60% of the total |
| exam | both | `exam` not a boolean |

---

## 7. Compatibility

`grading` and `exam` are additive; `bundle_format` stays `1`. A course without `grading` is
unchanged, and `belay-grade` refuses it with a message naming the missing key. An older runner
ignores `grading` — gate validators are still ordinary validators — and ignores `exam`, so an
exam lesson is taught as an ordinary lesson; `bundle-format.md` section 13 says so.

---

## 8. Documents that change

| Document | Change |
|---|---|
| `bundle-format.md` | section 2: `grading`, and the `file-contains` pattern; section 6: `exam`, and **Writing an exam lesson**; section 10: the self-check; section 13: the older-runner rows |
| `runner-protocol.md` | a new section 20, **Grading a cohort**: the six steps, the never-publish rule, the separate grading key; section 15: exam lessons (rung 3, no solutions, levels not applied); section 19: a task lesson keeps an exam lesson's cap; section 3: the gate as the participant's tutor reports it; section 14: `belay-grade run` as the one script that starts a validator |
| `SKILL.md` | the load conditions, and the exam lesson in the teaching contract |
| `README.md` | `belay-grade` and the feature list |
| `bin/` | a `belay-grade` wrapper, as for the other scripts |
| the levels spec (2026-11-03) | section 1.2: exam mode is per lesson, replacing "a graded task runs in exam mode" |

---

## 9. Acceptance criteria

1. Existing courses are unaffected: all suites pass unchanged, and the sibling sweep reports no
   new finding and no new warning.
2. Each new check has a fixture that trips it and a silent control.
3. A fake cohort — a local bare Git repository with three participant branches for a fixture
   module (one passing everything, one failing a gate validator) and one branch outside the
   naming convention — is collected, run, proposed and confirmed end to end. The suites never
   need docker: the container runtime is replaceable through an environment variable, and a
   stub runtime records the arguments it receives.
4. A test asserts, from the stub's record, that only the checkout is mounted and only the
   declared variables are passed; that no runtime stops step 2; that the grader refuses to write
   inside a Git work tree; that a confirmation with a changed criterion records its reason; and
   that re-grading keeps the previous `final.json`.
5. The judging step and the drafted texts are AI output; their behaviour is added to the dry
   run in belay-authoring#43.

---

## 10. Non-goals

- **No upload, no sending, no push.** The trainer publishes and sends.
- **No grades in the cohort repository, and none to the employer.**
- **No partial credit for a validator.**
- **The certificate** — belay#95.
- **The participant's tutor asking for the starting branch** — a separate change, PR: belay#103;
  the levels design, section 2.2, states it.
