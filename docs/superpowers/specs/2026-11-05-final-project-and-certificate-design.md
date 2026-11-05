# Final project and certificate — Design

**Date:** 2026-11-05
**Last amended:** 2026-11-05
**Status:** designed, not implemented
**Issue:** belay#95
**Builds on:** the cohort-grading design (2026-11-03), whose `final.json` this reads; the levels
and modules-as-bundles design (2026-11-03), whose catalog holds the programme

---

## 1. The problem

A cohort programme ends with a final project: the participant chooses a use case from a curated
set and works on it alone. The programme then gives a certificate, based on the results of every
module and the final project.

Belay can already teach and grade each of those bundles. Nothing states what earns the
certificate, nothing brings the module results together, and nothing produces what the trainer
hands on.

### 1.1 Decisions taken in the design discussion

- **The final project needs no new format.** It is built from what exists (section 2).
- **A participant passes when they passed every module's gate, and reached a set share of the
  points on the final project, whose own gate they also passed.** Module scores count for nothing
  beyond the gate. Everyone continues from the best solution of each module, so a weak module does
  not follow a participant to the end, but the final project stands on its own.
- **How many further attempts a participant gets is the course's decision**, declared per bundle as
  `grading.retries` (section 3.1). With attempts left, a missed requirement stays open until the
  certificate is run, so nobody is told after an early module that the certificate is out of reach.
- **A further attempt is on the same task.** On a module, the participant has seen the best solution
  by then and could copy it; that is accepted, because a module's gate only asks that the requirement
  is met, and the final project is solo work with its own threshold.
- **The result rests on the trainer's confirmed grades**, never on the self-run assessments in a
  participant's repository, which are traceable and not tamper-proof (levels design, section 1.2).
- **The employer receives only passed or not passed.** Grades, levels, assessment results and
  rankings stay inside the training. (Agreed with the client on 2026-11-03; the client's legal team
  confirms it with the works council. Recorded on belay#94 and belay#95.)
- **The rule is computed, with no override.** A trainer who disagrees with a result changes the
  grade through `belay-grade confirm`, which records the reason, and runs the certificate again.
- **Belay produces a result list and a filled template.** It carries no branding and no PDF tool.

---

## 2. The final project

A curated use case is **a bundle in the programme's catalog**, chosen the way any course is chosen:

- every lesson that is the participant's own work declares `exam: true` (cohort-grading design,
  section 2.2), so help stops at rung 3 whatever their levels;
- it declares a `grading:` block with a gate, as a module does, and may declare `retries`
  (section 3.1);
- it may declare `starts_from: ref` or start empty, as the use case needs.

**Each use case is graded on its own**, with `belay-grade` on the branches `*/<bundle-id>` of the
cohort repository. The grader compares only branches of one bundle, so participants on different
use cases are never ranked against each other.

**A use case with one participant is a cohort of one.** `belay-grade` already handles it: the
ranking holds one entry. The protocol tells the tutor to skip the shared review in that case,
because there is nothing to compare and it would describe one person's work.

---

## 3. The rule: `certificate` in the catalog

```yaml
catalog_version: 1
certificate:                           # new, MAY
  title: Example Programme Certificate
  modules: [programme-m1, programme-m2, programme-m3]
  final_project: [final-lead-scoring, final-invoice-check]
  final_project_share: 60
goals: { ... }
tutorials: [ ... ]
```

| Key | Meaning |
|---|---|
| `title` | what `{{programme}}` becomes in a certificate; a non-empty string |
| `modules` | a non-empty list of tutorial ids; each participant must pass each one's gate |
| `final_project` | a non-empty list of tutorial ids; each participant must complete exactly one |
| `final_project_share` | a whole number from 1 to 100; the percent of the final project's points required |

**A participant passes when all of these hold:**

1. For every id in `modules`, **either** they are in that module's `final.json` under
   `participants` with a `gate` of true or null, **or** their latest confirmed further attempt at
   that module (section 3.1) has a `gate` of true or null. Null means the module declares no gate, so being
   graded is enough.
2. They are in the `final.json` of **exactly one** id in `final_project`.
3. In their latest confirmed attempt at it, the one in that file or a further attempt, their `gate`
   is true or null, and `total * 100 >= final_project_share * max_total`, compared in whole numbers.

**Anything else is not passed, with the reason recorded**: a gate not passed, a participant in
`not_graded` or absent from a module, in each case with no further attempt that passed; no final
project, two final projects, or too few points. Two final projects is a reason and not a guess, because Belay cannot know which one counts;
the trainer removes one through the grading steps.

**The set of participants** is everyone named in any of those `final.json` files, under
`participants` or `not_graded`, or holding a further attempt at a listed module. A participant is known by the part of their branch name before the
slash, so the same id must be used on every branch of the cohort.

### 3.1 Further attempts

```yaml
grading:
  retries: 1    # further attempts after the first; a whole number, absent means 0
```

**The bundle decides.** With no `retries`, nobody gets a further attempt, and a course behaves as it
did. **A programme that wants a missed requirement to stay open must set it on every module**, and
all ids in `final_project` must declare the same value (section 6), so a use case is not chosen for
its retries. Modules may differ.

**What is open.** A further attempt is on the same task, and what it asks for depends on where the
bundle is listed in `certificate`:

| Listed in | Open when, in the latest confirmed attempt, the participant | What is graded |
|---|---|---|
| `modules` | has a gate of false, is in `not_graded`, or had no branch at the checkpoint | the gate only: gate validators and gate criteria, with no points and no comparison. A module with no gate runs nothing, and the trainer confirms that the work exists |
| `final_project` | is under `participants`, and has a gate of false or too few points | everything: every validator and criterion, so a new total, with no comparison |

So someone who was ill at a module's checkpoint is covered, and uses an attempt. A bundle not listed
in `certificate` has no further attempts, because nothing would read them.

**The branch.** The work goes on `<participant>/<bundle-id>-makeup`. **The separate branch is
required**: `belay-grade confirm` refuses when a module branch has moved since the proposal, so a fix
pushed to it would block every later grade change in that module. The participant may start it from
their own branch; nothing requires it.

```
belay-grade makeup run     <repo> <bundle-id> <participant> --bundle <dir> --catalog <file>
belay-grade makeup propose <repo> <bundle-id> <participant> --bundle <dir> --catalog <file> --judgement <file>
belay-grade makeup confirm <repo> <bundle-id> <participant> --bundle <dir> --catalog <file> --by <name>
                           [--change <criterion>=<points>:<reason>]
```

`belay-grade collect` fetches the branch as it fetches any other, and lists these branches under their
own heading. The steps follow the grading run, in the same container with the same rules, and a
runtime fault records no result and uses no attempt, because it is not the participant's result.
`confirm` refuses when the branch has moved since the proposal.

**`makeup run` refuses, naming the problem, when:**

- the catalog has no `certificate`, or does not list the bundle;
- the bundle has no confirmed `final.json`, or the participant has nothing open (the table above);
- the attempts are used up;
- the branch does not exist;
- the bundle's grading block differs from the one the cohort met.

**An attempt is a commit.** The count is the number of different commits with a confirmed result. A
trainer correcting a confirmed attempt confirms the same commit, which uses no further attempt.

**The latest confirmed attempt counts**, even with a lower total, so nobody has to choose between
attempts. An attempt is only open to someone who has not met the requirement, so a result that met it
is never replaced.

**Comparing the grading block.** `final.json` gains `grading_hash`, and that hash leaves out `retries`.
So a trainer can raise `retries` during a programme without a new version or a stale proposal, while
any change to what is graded still refuses.

**It writes** to `<store>/<cohort>/<bundle-id>/makeup/<participant>/`: `run.json`, `proposal.json` and
`final.json`, holding `commit`, `gate`, what was graded with its evidence, and for a final project the
`total` and `max_total`, with `confirmed_by` and `confirmed_at`. An earlier attempt is archived as in
module grading.

**What it leaves alone:** the bundle's own `final.json`, and so the first score, the ranking, and the
best solution everyone continued from. Further attempts change only the certificate result.

**What people see.** The participant's tutor already says a gate is "not met yet". The trainer's
feedback at a checkpoint says the same and names the attempts left, and never says the participant
failed. `details.json` records the attempts; `results.csv` and the certificate do not.

---

## 4. `belay-grade certificate`

```
belay-grade certificate <repo> --catalog <file> --names <file> [--template <file>]
```

**It refuses, naming the problem, and writes nothing, when:**

- the catalog has no `certificate`, or the catalog validator would report it;
- an id in `modules` has no confirmed `final.json`, because results over an unfinished programme
  would mislead. A use case in `final_project` with no `final.json` is normal, since nobody may have
  chosen it;
- no id in `final_project` has a confirmed `final.json`;
- a participant has no entry in the names file;
- the template has a placeholder other than the three in section 5.

It reads only `final.json` files in the cohort's store, further attempts included. It fetches nothing and runs no participant
code, so it needs no container runtime.

**The names file** is a local UTF-8 CSV of `participant,full name`, because a branch gives only an
id. It stays with the trainer and is never read from the cohort repository. A row for someone who
is not a participant is ignored and reported, because it is usually a typo.

**The reason `--template` is optional:** a trainer may want the result list before deciding on a
document. Without it, no certificates are written.

---

## 5. What it writes

To `<store>/<cohort>/certificate/`, under the store's existing rules: outside any Git work tree,
private modes, atomic writes.

| File | Contains | For |
|---|---|---|
| `details.json` | per participant, each requirement with its result and reason, the further attempts, and which `final.json` files were read, with their `confirmed_at` | the trainer only |
| `results.csv` | a header and one row per participant: full name, `passed` or `not passed`. **Nothing else** | what the trainer hands on |
| `certificates/<participant>.md` (or the template's extension) | the template filled in, for each participant who passed | the participant |

**`results.csv` holds no reason, grade, rank or level.** That is what keeps the employer's view to
passed or not passed, and a test pins the exact columns.

**The template** may use only `{{name}}`, `{{programme}}` and `{{date}}`, the last being the date of
the run. Any other placeholder is refused, so a grade cannot reach a certificate by accident. A
template's values are substituted as plain text; an HTML template is escaped, chosen by the
template's extension.

**Re-running** moves the previous output to `certificate.<date>/` (then `-2`, `-3` on one day), so an
earlier result is never overwritten. `belay-grade forget <cohort>` removes all of it, and how long it
is kept is the trainer's decision.

**The tool never sends anything.** Handing `results.csv` to the employer and certificates to
participants are the trainer's actions.

---

## 6. Validator

**A new catalog check** (the next free number; on `main` today catalog check 9 is the last), silent
when `certificate` is absent:

- `certificate` not a mapping; an unknown key; a missing key;
- `title` not a non-empty string;
- `modules` or `final_project` not a non-empty list of strings;
- an id that is not an entry in this catalog; an id in both lists, or twice in one;
- an id in `modules` or `final_project` ending in `-makeup`, because its branches could not be told
  from the branches of further attempts;
- `final_project_share` not a whole number from 1 to 100, a boolean included;
- a listed id whose bundle resolves on disk, as catalog check 6 already resolves it, and whose
  `tutorial.yaml` declares no `grading`;
- ids in `final_project` whose bundles resolve on disk and declare different `retries`, absent
  counting as 0.

A listed bundle that does not resolve on disk is not reported by this rule; check 6 speaks about
it. The trainer's first grading run also refuses a bundle with no `grading`.

`certificate` joins the catalog's known top-level keys, so an older validator warns and never
rejects.

**Bundle check 47 takes `retries`** as a known key of `grading`: a whole number from 0, a boolean
refused. Check 47 reports unknown keys, so a course that sets it needs a Belay with this change.

---

## 7. Documents that change

| Document | Change |
|---|---|
| `catalogue-format.md` | `certificate`, the rule, and the new check |
| `bundle-format.md` | **Writing a final project**: a bundle in the catalog, exam lessons, a grading scheme; `grading.retries` and check 47 |
| `runner-protocol.md` section 20 | the certificate step; the steps of a further attempt, and "not met yet" as the wording for an open requirement; the shared review is skipped for a cohort of one; what is handed to whom; the employer's view |
| `README.md` | the commands, the feature list, and test totals |
| `2026-09-11-tutorial-runner-design.md` | section 18's status |
| `2026-11-03-levels-and-course-structure-design.md` | section 1.2: item 4 points here, and the certificate no longer "rests on the trainer-run reviews" as a future statement |

---

## 8. Acceptance criteria

1. Existing courses and catalogs are unaffected: all suites pass unchanged, and the sibling sweep
   reports no new finding and no new warning.
2. The catalog check has a firing case per finding and a silent control.
3. An end-to-end test on a fake cohort, with written `final.json` files for two modules and two
   use cases, covers: a participant who passes; one who failed a gate; one in `not_graded`; one
   absent from a module; one with no final project; one with two; one exactly at the share and one
   just under it; a module with no gate; a changed grade flipping a result on the next run; a
   failed gate made up; a failed attempt followed by a passed one; an attempt by a participant absent
   from the module; a final project retried over the share; a final project retried with a lower total.
4. `results.csv` is pinned to exactly two columns, with no reason, grade, rank or level anywhere in
   it, and that holds for a participant who did not pass. It reads the same for a participant who
   passed first time and one who needed a further attempt.
5. Each refusal in section 4 writes nothing. A template with `{{total}}` is refused. An HTML template
   escapes a name holding `<`.
6. Output goes through the work-tree refusal, and a re-run keeps the earlier output.
7. The tutor's handling of the step is added to the dry run in belay-authoring#43.
8. A further attempt leaves the bundle's `final.json` byte for byte unchanged, and a grade change in
   that bundle still confirms after the attempt's branch was collected. Each refusal in section 3.1
   writes nothing, and a branch that moved after the proposal is refused at `confirm`.
9. With `retries` absent or 0, `makeup run` refuses. With `retries: 1`, a second commit is refused and a
   trainer's correction of the first is not. Raising `retries` opens an attempt with no version change
   and leaves an open proposal valid.

---

## 9. Non-goals

- **No PDF, no branding, no signature.** The trainer turns the filled template into the final
  document.
- **No override of the rule.** The trainer changes a grade, with a reason, and runs it again.
- **No grade on a certificate or in the result list**, and no option to add one.
- **No verification service.** A certificate is a document; nothing checks it later.
- **No sending.** The trainer hands the results on.
- **No use of self-run assessments or `## Levels`** in the result.
- **No separate task for a further attempt.** It would cost one more task per bundle to write and
  grade, for a module gate that only asks that the requirement is met.
- **No allowance of missed gates.** Every module's requirement is met in the end, first time or later.
- **No first-attempt grade changed by a further attempt**, and no new ranking from one.
