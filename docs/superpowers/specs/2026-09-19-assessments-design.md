# Knowledge assessments — Design

**Date:** 2026-09-19
**Last amended:** 2026-10-16
**Status:** implemented — see §10 for the decisions the implementation added
**Issue:** belay#33
**Does not close:** belay#34, which stays open and narrower — see §9.

---

## 1. The problem

The runner assesses a learner through the workspace. A lesson declares `validators`, and
four of the five kinds inspect a file or run a program. A lesson also carries
`## Completion conditions`, checked individually with evidence.

That works when the learner produces an inspectable artifact. It does not reach knowledge
the repository does not hold: a theoretical concept, an architectural argument, a reading, a
trade-off the learner can state but has not yet built.

The one kind that could carry such a check is `manual` — *"the learner supplies evidence;
the tutor judges it"*. It defines no question, no scope, no standard and no outcome beyond
the judgement itself.

A learner also cannot ask to be tested. *"Quiz me on the last lesson"* has no defined
behaviour.

---

## 2. What an assessment is

**A lesson whose evidence is answers.**

It appears in `lessons` or `optional_lessons` like any other lesson. It reuses everything
that already works: ordering, `active_lesson`, cold resume, `resume_at`, advancement, and
the offer/defer/re-offer machinery for optional lessons. The only difference is that its
completion conditions are satisfied by what the learner *says* rather than by what is in the
workspace.

Three structures were considered. A block attached to a lesson leaves an assessment spanning
several lessons with no home. A new top-level object duplicates ordering, state and resume
machinery that `lessons` already has, and that duplication is where a format rots. Reusing
the lesson is the smallest new surface.

### 2.1 What marks one

**The presence of `assesses:` in its frontmatter. Nothing else.**

```yaml
---
id: durability-concepts
title: What durability actually guarantees
assesses: [write-ahead-log, fsync-boundaries, crash-recovery]
---
```

There is no `type: quiz`. The behaviour follows from the declaration that makes assessment
*possible* — an answer cannot be judged without knowing what it must demonstrate — rather
than from a label. That is what keeps this clear of belay#33's own non-goal about nominal
lesson types: remove `assesses` and there is nothing left to assess, whereas removing a
`type` field would change only a word.

### 2.2 The standard is a concept the course already declares

Every id in `assesses` resolves into the manifest's existing `covers` map, exactly as
`design_refs` resolves into `DESIGN.md` anchors. The concept's own `summary` is the standard
the answer is judged against.

So the author writes the standard **once**, in the place the course already maintains it. A
per-question rubric would be a second authoring language and would duplicate `covers` for
anything the course already declares; a model answer invites the tutor to drift toward
matching its wording, which is the string-equality non-goal arriving by the back door.

This choice earns its keep twice, and the second time was not foreseen: because the
assessment declares which concepts it tests, a weak result names exactly which concepts to
generate practice for (§4).

### 2.3 Where the questions come from

The lesson body, like every other lesson's content. An assessment lesson MAY carry a
`## Questions` section with questions the author wants asked verbatim; when it does not, the
tutor generates them from the concepts and the lesson's objectives.

That covers "fixed, from a bank, or generated from a rubric" with one mechanism, present or
absent — the same shape `teaching_method` and `## Optional deeper paths` already use.

`## Completion conditions` keeps its meaning and states what passing requires, in concepts
rather than artifacts.

### 2.4 Required versus optional needs nothing new

An assessment in `lessons` is on the main path. One in `optional_lessons` is offered,
deferred and re-offered by machinery that exists. `required_for` continues to gate on an
anticipated **failure**, not on the lesson, so the invariant that a course stays completable
for a learner who declines every offer is untouched.

An assessment lesson MAY still declare `validators`. A course may reasonably want a learner
to explain *and* to show, and forbidding it would be inventing a rule to keep a category
tidy.

---

## 3. The turn loop, and four answer outcomes

One question per turn, mirroring `one_task_at_a_time`. Ask, take the answer, classify,
respond, record only what was demonstrated. A conceptual aside gets an answer and does not
consume the question, exactly as it does not consume a task today.

Multiple choice may be used. It must not be the only form, because a question that can be
answered by recognition does not show that a concept can be applied.

### 3.1 The four outcomes do not collapse

`runner-protocol.md` already refuses to reduce four validation outcomes to pass and fail.
Same discipline, different four:

| Outcome | What the tutor does |
|---|---|
| **demonstrated** | Say what specifically was right — that is the part that transfers. Move on. |
| **partial** | Ask a **narrower** question about the missing piece. Never the same question again. |
| **misconception** | Name the wrong model rather than merely correcting it. This is what targets remediation. |
| **not enough evidence** | Ask for more, or rephrase. |

**The fourth is about the answer's legibility, not the learner's knowledge.** Collapsing it
into failure punishes people for being terse and would teach the tutor that a short answer
is a wrong answer. It is the outcome most likely to be lost in implementation, and it is the
one to guard.

### 3.2 The help ladder changes shape inside an assessment

`runner-protocol.md`'s five rungs escalate help without escalating ownership, ending at
*"the smallest true statement that unblocks"*. Inside an assessment that rung **hands over
the thing being assessed**.

**Inside an assessment the ladder stops at rung 3** — name the concept and where it is
documented. Rungs 4 and 5 are unavailable.

This is a real exception and the protocol must state it, because a tutor following the
general rule would leak the answer while believing it was being helpful.

### 3.3 Revealing the answer reuses `solution_code`

`on-request-only` means do not reveal until the learner asks. `freely` means the tutor may.
No new knob: the question is identical to the one `solution_code` already answers, and a
second setting would drift out of step with the first.

### 3.4 Stopping, and what is not evidence

The learner may stop an assessment at any point. It is recorded as `stopped`, **never** as
`passed`. For an optional assessment that is the existing defer machinery; for a main-path
one the outcome is recorded and the course continues (§4.1).

**Self-confirmation is not evidence.** *"I understand it now"* records nothing.

---

## 4. Remediation, and the loop guard

### 4.1 An assessment never blocks

A weak result never prevents advancement. Every precedent in this runner points the same
way: `assumes` is *"never a gate"*, `required_for` gates on the failure rather than the
lesson, and a failed setup check reports and lets the learner decide rather than refusing.

What replaces blocking is a loop the learner opts into.

### 4.2 The loop

On a weak result the tutor:

1. names the concepts that were not demonstrated;
2. offers generated practice lessons **targeted at those concepts**;
3. leaves the choice to the learner — nothing is automatic;
4. allows the assessment to be retaken.

A practice lesson is a generated lesson with a third `kind`:

```yaml
kind: practice          # alongside side-lesson and main-path-draft
after: lessons/07-durability-assessment.md
resume_at: lessons/07-durability-assessment.md
```

`resume_at` pointing at the assessment is what makes the retake a returning detour rather
than a new thing.

### 4.3 An assessment's completion is not terminal

This is the one place assessment-as-a-lesson genuinely diverges from lesson behaviour, and
the divergence must be stated rather than discovered.

`complete` is terminal for an optional lesson, and *"nothing later in the course reverses
it"*. A retakeable assessment cannot work that way. Its state moves between the values in
§5 until the learner stops returning to it.

The loop-guard reasoning that made optional-lesson completion terminal still applies, and
§4.4 is how it is honoured here instead.

### 4.4 The guard is the offer changing, not a counter running out

**On a second failure of the same concept, the offer changes.** The tutor stops proposing
more practice of the same kind and says something different: that the course may assume
something the learner has not met, naming the relevant `assumes` concept or an entry from
`recommended_previous_bundles`.

A declared retry limit was rejected. It would put a number in a format that has avoided
them, and the right number depends on the learner — which is exactly what the author cannot
see. A learner-choice-only bound was also rejected, because this repository's own reasoning
is that the person inside a loop is the one least able to leave it, and a learner failing the
same concept a fourth time is that person.

This is why §5 records *which* concepts failed and how often, not merely the latest outcome.

---

## 5. What the instance records

### 5.1 `## Assessments`, in the shape that already exists

`## Optional lessons` is `` - `path` — state — one clause ``, parsed by check 21, under the
standing rule that nothing derivable from `tutorial.yaml` is repeated.

```markdown
## Assessments

- `lessons/07-durability-assessment.md` — partial — last taken 2026-09-19,
  attempt 2; not demonstrated: fsync-boundaries ×2, crash-recovery
- _scope:_ `lessons/06-retention.md` — partial — last taken 2026-09-19,
  attempt 3; not demonstrated: retention-windows ×3
```

**One row per assessment, updated in place** — not appended per attempt. Appending is how
this becomes the transcript belay#34 exists to keep out of a file read every turn.

**Four states:** `passed`, `partial`, `stopped`, `skipped`. `misconception` is an *answer*
outcome, not an assessment one; it surfaces as a concept under "not demonstrated", where it
is useful. **`skipped` and `passed` are distinct**, which is the requirement that a skipped
assessment is never silently treated as a passed one.

**The per-concept `×N` is what §4.4 reads.** It has to be recorded rather than derived:
`assesses` lives in lesson frontmatter, and the tutor loads only the *active* lesson's
frontmatter, so for any assessment that is not active this is the only place the information
exists.

**Concept ids, never answers.** The row records what was demonstrated, not what was said —
§16's signal-versus-content separation applied here, and it keeps the every-turn read cheap
as a consequence rather than as a goal.

### 5.2 No second file

`state-lifecycle.md` opens: *"`STATE.md` is the only place a learner's progress is
recorded."* That sentence stands. This design introduces no event log and no second file.

belay#34's attempt-level questions — hint counts, which checks failed repeatedly, whether
remediation improved the next result — are **not** answered here. §5.1 records per-concept
failure counts for assessments because §4.4 needs them, and nothing further.

### 5.3 Check 32

This section first called the record check "check 31" and the `assesses` check "check 30",
and said both numbers were provisional. belay#51's `version` check took 30, so `assesses`
is **check 31** and the record is **check 32**; the numbers are corrected throughout.

Instance mode, mirroring check 21: the `## Assessments` record is well-formed, every lesson
path names a lesson in the manifest, every state is one of the four, and every `×N` is an
integer greater than one.

---

## 6. Learner-requested assessments

*"Quiz me on the previous lesson."* *"Test what I have learned so far."*

These have no lesson file and no manifest entry. They are a conversation, not a lesson, and
this is where assessment-as-a-lesson stops applying.

### 6.1 They never rewrite the curriculum

The manifest's `lessons` list is never mutated — the rule from generated lessons holds
unchanged. No lesson file is written for the assessment itself.

### 6.2 Scope

The learner names it: the previous lesson, a named lesson or topic, or the course so far.
A generated question derives its scope from the objectives, the content and the concepts the
learner has demonstrated. It never introduces an expectation the course did not set.

"The current section" is not supported, because the format has no grouping concept.
belay#36 would add one; this design does not depend on it.

### 6.3 What they leave behind

A row in `## Assessments`, keyed by **scope** rather than by lesson path — the `_scope:_`
form in §5.1.

This was reconsidered during design. Recording nothing was rejected because a practice lesson
generated from a self-quiz would then have no recorded reason, and a cold resume could not
explain why `lessons.generated/` holds a file nobody asked about. Recording only when a
practice lesson resulted was rejected because it makes §4.4's escalation impossible for
exactly the learner who needs it: someone self-quizzing repeatedly on one weak concept is
the clearest case of a person who should be told the course may assume something they have
not met.

The cost, accepted: a learner-requested assessment is no longer free. Repeated self-quizzing
writes rows. That is the right trade, because the repetition *is* the signal.

Concepts genuinely demonstrated still go to `## Concepts demonstrated`, and any practice
lesson still appears under `## Generated lessons` with its `reason:`.

---

## 7. Acceptance criteria

- [x] `bundle-format.md` documents `assesses`, the `## Questions` section, and what
      `## Completion conditions` means for an assessment.
- [x] Check 31: `assesses` is a non-empty list of strings and every id resolves in `covers`.
      A test proves it fires on a misspelled id; controls prove it is quiet on a valid
      bundle and on a bundle declaring no `assesses` at all.
- [x] `runner-protocol.md` documents the turn loop, the four answer outcomes, the rung-3
      ceiling on the help ladder, and the reveal policy.
- [x] `runner-protocol.md` documents the remediation loop and §4.4's escalation.
- [x] `state-lifecycle.md` documents `## Assessments`, its four states and the `_scope:_`
      form, and states that an assessment's completion is not terminal.
- [x] `kind: practice` joins `GENERATED_KINDS`, and checks 14 and 15 accept it.
- [x] Check 32 validates the `## Assessments` record, with a positive control per rule.
- [x] A worked example: a theoretical authored quiz needing no repository artifact.
- [x] A worked example: an optional knowledge check the learner declines.
- [x] A worked example: a partially correct answer leading to a narrower question.
- [x] A worked example: a misconception leading to an offered practice lesson, and a retake.
- [x] A worked example: a second failure of the same concept, where the offer changes.
- [x] A worked example: an interrupted assessment resuming in a cold session.
- [x] A test proves `skipped` and `passed` are distinguishable in the instance.
- [x] Every bundle valid today stays valid.
- [x] Both suites pass, in both PyYAML configurations.

---

## 8. Non-goals

- A general-purpose examination platform.
- Replacing the curated main curriculum with generated content.
- A quiz in every lesson.
- Grading a free-form answer by string equality, or by comparison with a model answer.
- A nominal lesson type such as `code`, `reading`, `quiz` or `reflection`.
- An assessment that blocks a learner, with or without an override (§4.1).
- A declared retry limit (§4.4).
- An event log or any second state file (§5.2).
- Analytics, telemetry, or transmission of anything off the machine.

---

## 9. Relationship to other issues

- **belay#34** — **stays open, and narrower.** §5.1 records per-concept failure counts
  because §4.4 needs them. Everything else that issue asks for — hint counts, repeated check
  failures, elapsed time, abandonment, whether remediation improved the next result — is
  untouched, and so is its question about whether a separate append-oriented record is the
  right home. Do not read this design as closing it.
- **belay#36** — sections. §6.2 supports three scopes and not "the current section",
  because the format has no grouping concept. This design does not depend on that issue.
- **belay-authoring#16** — the authoring tools, validation and dry-run scenarios for an
  assessment. That work follows this format and should not start before it lands.
- **belay#22 and belay#45** — the conversational behaviour in §3, §4 and §6 has the
  same testability problem those two issues describe: the structure can be validated and the
  conversation cannot. Nothing here closes that, and the worked examples in §7 are
  documentation rather than tests.

---

## 10. Implementation notes

Implemented on 2026-10-16 (belay#33). The worked examples of §7 live in
`references/runner-protocol.md` §15.10, where the tutor reads them, and the authored quiz
also in `references/bundle-format.md` §6, **Writing an assessment**, where an author does.
The record is `references/state-lifecycle.md` §11.

The design left these open, and the implementation settled them:

- **An optional assessment's *Optional lessons* entry becomes `complete` only when it is
  passed.** Any other result leaves it `deferred`. That keeps `complete` terminal, as
  §9.2 of the state lifecycle requires, while §4.3 makes the assessment retakeable. A
  deferred assessment may be offered again when a practice lesson on its concepts
  completes, which is one moment more than the anti-nag rule otherwise allows.
- **Declining an optional assessment's offer writes no `## Assessments` row.** It is a
  deferral, and `skipped` is for a main-path assessment declined outright.
- **The `×N` count runs across consecutive failures.** The row lists only what the last
  attempt did not show, so a concept demonstrated in between drops off it and a later
  failure starts again without a count.
- **A path row must name a lesson that declares `assesses`.** A quiz the learner asked for
  on an ordinary lesson is a `_scope:_` row. Check 32 enforces both, and checks a scope
  against the instance's lessons only when it reads as a path.
- **A practice lesson's `after:` is the assessment when it is on the main path**, as §4.2
  shows, and otherwise the `lessons` entry the learner stands in, because check 15
  requires `after:` to be an entry in `lessons`. For the same reason `resume_at` cannot
  name an optional assessment, so the retake of an optional one is a conversation, as is a
  retake of any assessment the learner has already left.
- **A quiz the learner asks for on a named lesson may open that lesson**, the one
  exception to the runner's rule against loading a lesson other than `active_lesson`.
  Without it, the questions could not be drawn from the objectives, as §6.2 requires.
- **The help ladder's ceiling and the theory rule.** belay#64's rule that a lesson's
  Theory is presented before its first task is in `runner-protocol.md` §2.3; §15.2 applies
  its "never the answer" clause to every question of an assessment.
- **`plan_update.py` notes an `## Assessments` row** that an update would leave naming a
  lesson that is no longer an assessment, so the learner can remove or reword it.
