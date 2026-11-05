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
- **A missed module gate stays open until the certificate is run.** Nobody is told after an early
  module that the certificate is out of reach. The participant makes the gate up on the same task
  (section 3.1). They have seen the best solution by then and could copy it; that is accepted,
  because the gate only asks that the requirement is met, and the final project is solo work with
  its own threshold.
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
- it declares a `grading:` block with a gate, as a module does;
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
   `participants` with a `gate` of true or null, **or** they have a confirmed make-up of that module
   (section 3.1) with a `gate` of true or null. Null means the module declares no gate, so being
   graded is enough.
2. They are in the `final.json` of **exactly one** id in `final_project`.
3. In that file, their `gate` is true or null, and `total * 100 >= final_project_share * max_total`,
   compared in whole numbers.

**Anything else is not passed, with the reason recorded**: a gate not passed and not made up, a
participant in `not_graded` or absent from a module with no make-up, no final project, two final
projects, or too few points. Two final projects is a reason and not a guess, because Belay cannot know which one counts;
the trainer removes one through the grading steps.

**The set of participants** is everyone named in any of those `final.json` files, under
`participants` or `not_graded`, or holding a make-up of a listed module. A participant is known by the part of their branch name before the
slash, so the same id must be used on every branch of the cohort.

### 3.1 Making up a missed gate

A participant whose gate is open makes it up on the **same task**, on a branch of its own:
`<participant>/<module-id>-makeup`. "Open" means a gate of false, a place in `not_graded`, or no
branch at the checkpoint, so someone who was ill is covered too.

**The separate branch is required.** `belay-grade confirm` refuses when a module branch has moved
since the proposal, so a fix pushed to the module branch would block every later grade change in
that module. It would also leave the graded commit no longer at the branch's head. The participant
may start the make-up branch from their module branch; nothing requires it.

```
belay-grade makeup run     <repo> <module-id> <participant> --bundle <dir>
belay-grade makeup propose <repo> <module-id> <participant> --bundle <dir> --judgement <file>
belay-grade makeup confirm <repo> <module-id> <participant> --bundle <dir> --by <name>
                           [--change <criterion>=<points>:<reason>]
```

`belay-grade collect` fetches the branch as it fetches any other, and lists make-up branches under
their own heading. The steps then follow the grading run, with these differences:

- **Only the gate counts.** `run` runs only the gate validators, in the same container with the same
  rules. The tutor judges only the gate criteria. A module with no gate runs nothing, and the trainer
  confirms that the work exists.
- **The tutor judges this one branch against the standard**, with no comparison. Nothing is ranked.
- **A runtime fault records no result**, as in grading: it is not the participant's result.
- **`confirm` refuses when the make-up branch has moved** since the proposal.

**`makeup run` refuses, naming the problem, when:** the module has no confirmed `final.json`; the
participant already holds a gate of true or null in it, because there is nothing to make up; the
branch does not exist; or the bundle's `bundle_version` differs from the one in the module's
`final.json`, because the make-up must meet the standard the cohort met.

**It writes** to `<store>/<cohort>/<module>/makeup/<participant>/`: `run.json`, `proposal.json` and
`final.json`, the last holding `commit`, `gate`, the gate validators and criteria with their
evidence, `confirmed_by` and `confirmed_at`, and archiving an earlier attempt as module grading does.

**What it leaves alone:** the module's own `final.json`, and so the participant's score, the ranking,
and the best solution everyone continued from. A make-up changes only the certificate rule.

**There is no limit on attempts and no date in the tool.** The last moment is the trainer's
certificate run. A failed attempt records a gate of false, and a later attempt replaces it.

**What people see.** The participant's tutor already says a gate is "not met yet". The trainer's
feedback at a checkpoint says the same and names the make-up, and never says the participant failed.
`details.json` records that a gate was made up; `results.csv` and the certificate do not.

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

It reads only `final.json` files in the cohort's store, make-ups included. It fetches nothing and runs no participant
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
| `details.json` | per participant, each requirement with its result and reason, whether a gate was made up, and which `final.json` files were read, with their `confirmed_at` | the trainer only |
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
- an id in `modules` ending in `-makeup`, because its branches could not be told from make-up branches;
- `final_project_share` not a whole number from 1 to 100, a boolean included;
- a listed id whose bundle resolves on disk, as catalog check 6 already resolves it, and whose
  `tutorial.yaml` declares no `grading`.

A listed bundle that does not resolve on disk is not reported by this rule; check 6 speaks about
it. The trainer's first grading run also refuses a bundle with no `grading`.

`certificate` joins the catalog's known top-level keys, so an older validator warns and never
rejects.

---

## 7. Documents that change

| Document | Change |
|---|---|
| `catalogue-format.md` | `certificate`, the rule, and the new check |
| `bundle-format.md` | **Writing a final project**: a bundle in the catalog, exam lessons, a grading scheme |
| `runner-protocol.md` section 20 | the certificate step; the make-up steps, and "not met yet" as the wording for an open gate; the shared review is skipped for a cohort of one; what is handed to whom; the employer's view |
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
   failed gate made up; a failed make-up followed by a passed one; a make-up for a participant
   absent from the module.
4. `results.csv` is pinned to exactly two columns, with no reason, grade, rank or level anywhere in
   it, and that holds for a participant who did not pass. It reads the same for a participant who
   passed first time and one who made a gate up.
5. Each refusal in section 4 writes nothing. A template with `{{total}}` is refused. An HTML template
   escapes a name holding `<`.
6. Output goes through the work-tree refusal, and a re-run keeps the earlier output.
7. The tutor's handling of the step is added to the dry run in belay-authoring#43.
8. A make-up leaves the module's `final.json` byte for byte unchanged, and a grade change in that
   module still confirms after the make-up branch was collected. Each refusal in section 3.1 writes
   nothing, and a make-up branch that moved after the proposal is refused at `confirm`.

---

## 9. Non-goals

- **No PDF, no branding, no signature.** The trainer turns the filled template into the final
  document.
- **No override of the rule.** The trainer changes a grade, with a reason, and runs it again.
- **No grade on a certificate or in the result list**, and no option to add one.
- **No verification service.** A certificate is a document; nothing checks it later.
- **No sending.** The trainer hands the results on.
- **No use of self-run assessments or `## Levels`** in the result.
- **No separate make-up task.** It would cost one more task per module to write and grade, for a gate
  that only asks that the requirement is met.
- **No allowance of missed gates.** Every module's requirement is met in the end, first time or later.

---

## 10. Open question

**May a participant retry the final project?** Not decided. Until it is, section 3's rule stands: one
attempt, graded with the cohort of that use case. A retry differs from a module make-up, because the
final project counts points and not only the gate, so it needs its own decision and cannot reuse
section 3.1 unchanged.
