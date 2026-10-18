# Generic Tutorial Runner + Portable Tutorial Bundles — Design

**Date:** 2026-09-11
**Last amended:** 2026-10-18
**Status:** Design approved. Formats and first bundle implemented; runner in progress.
**Repositories:** `belay` (runner), `belay-bundles` (courses), `automaton-db` (a learner)

---

## 1. Purpose

Build a tutorial system whose runtime is an existing coding agent (Claude Code, Codex).
The agent supplies the model and the conversational loop. This project supplies the
protocol, the portable course format, and the state lifecycle.

No standalone application. No model API integration. No hosted service.

The design goal that justifies the whole system: **a tutor should hold one lesson in
context, not a whole course.** Every structural decision below serves that.

---

## 2. Four concepts, deliberately separate

| Concept | Lives | Mutable | Contains a learner? |
|---|---|---|---|
| **Runner** | installed plugin, outside learner repos | no | no |
| **Bundle** | a subfolder of `belay-bundles` (or any source) | no | **no** |
| **Instance** | `<workspace>/tutorial/` | yes | **yes, exactly one** |
| **Workspace** | the learner's own repository/directory | yes | learner-owned |

The runner contains no subject knowledge. The test applied to every proposed runner
feature: *would this still be needed if the tutorial taught Kubernetes, linear
programming, or compiler construction?* If no, it belongs in the bundle.

---

## 3. Bundle vs instance — the mechanical rule

Prose failed to convey this distinction to a bundle author. It is therefore expressed as
mutually exclusive **files**, which a script can check.

```
BUNDLE (distributable)            INSTANCE (<workspace>/tutorial/)
├── tutorial.yaml                 ├── tutorial.yaml      + instance stamp
├── COURSE.md                     ├── COURSE.md
├── DESIGN.md                     ├── DESIGN.md          (tutor appends)
├── STATE.template.md  ◄── only   ├── STATE.md      ◄── only here
└── lessons/                      └── lessons/
```

> A bundle **must** contain `STATE.template.md` and **must not** contain `STATE.md`.
> An instance **must** contain `STATE.md` and **must not** contain `STATE.template.md`.

### Ownership

| File | In bundle | In instance | Written by |
|---|---|---|---|
| `tutorial.yaml` | required | copied + `instance:` stamp | author; runner stamps |
| `COURSE.md` | required | read-only | author |
| `DESIGN.md` | required (seed) | tutor appends durable decisions | author seeds, tutor grows |
| `STATE.template.md` | **required** | **must be absent** | author |
| `STATE.md` | **must be absent** | **required** | runner creates, tutor updates |
| `lessons/**` | required | **read-only** | author |
| learner source | n/a | **learner-owned** | learner |

### The corollary authors get wrong

`COURSE.md` and `lessons/` describe the course for **every learner who will ever take
it**. They therefore contain no progress markers — no `Status: Complete`, no
`In progress`, no `Next`, no "current lesson".

All progress lives in `STATE.md`, in one place. The AutomatonDB source playbook violated
this in three places at once (a "Current tutorial state" section, per-lesson status
markers inside the curriculum, and a "Current resume marker" section), all of which had
to agree or the course misled. Those three collapsed into `STATE.md`. The validator
enforces it (§9, check 5).

---

## 4. `tutorial.yaml`

Shallow by default, because the author is more likely to err than the parser is. Most
fields are a scalar or a flat list.

**Corrected 2026-09-12, restated after measurement.** This section said "at most one level
of nesting". That was already wrong when it was written — `validators` has always been a
map of name to a definition carrying a `command` list — and `optional_lessons`,
`failure_modes`, `covers` and `assumes` are the same shape. **Five keys are a map of maps
reaching a flat list at the third level; measured across all six manifests in hand, nothing
reaches a fourth.** `bundle-format.md` section 2 carries the rule and the table that
replaced the old sentence: three levels of container with scalars at the leaves is the
ceiling, and a field that seems to want a fourth wants to be a list of mappings instead —
the shape `supplies` and the two recommendation lists already use. Anyone who read the old
sentence and shaped a manifest field around it should re-read that section.

```yaml
bundle_format: 1
id: rust-automaton-db
title: Learn Rust by Building AutomatonDB
subjects: [rust, databases, distributed-systems]
level: intermediate-to-advanced

lessons:
  - lessons/00-foundations.md
  - lessons/01-rows-cells-temporal.md
  - lessons/08-automaton-machinery/LESSON.md   # foldered form
  # ... ordered; lessons[0] is the entry lesson

workspace_kind: existing-or-new-repository   # | new-repository | none
tutor_owned:    [tutorial/STATE.md, tutorial/DESIGN.md]
learner_owned:  [src/**, tests/**, Cargo.toml]
ownership_policy: tutor-must-not-edit-learner-owned   # | on-request | unrestricted

validators:
  cargo-check: { kind: command, command: [cargo, check] }
  cargo-test:  { kind: command, command: [cargo, test] }
  has-lib:     { kind: file-exists, path: src/lib.rs }

one_task_at_a_time: true
solution_code: on-request-only
advance_on: validated-evidence-only
```

Validator `kind`s, all subject-neutral: `command`, `file-exists`, `file-contains`,
`git-diff`, `manual`. `cargo check` is a value, never a runner concept.

**`lessons` is the authoritative sequence.** It defines which lesson is first
(`lessons[0]` — there is no separate `entry_lesson` field) and what "the next lesson"
means on completion. It lives in the manifest rather than in `COURSE.md` frontmatter
because `COURSE.md` is deliberately not loaded in the steady state, and the runner needs
the sequence every time it advances. Filename sort is not the order; the list is.

**Stable vs mutable split.** `tutorial.yaml` declares validator *definitions*. Which
warnings are currently tolerated is progress, not configuration, and lives in `STATE.md`
with an expiry:

```yaml
accepted_warnings:
  - pattern: "is never used"
    reason: "Engine unreachable from the binary while main() is empty"
    until_lesson: lessons/03-first-refactor.md
```

The `until_lesson` expiry prevents "expected warnings" becoming permanent cover, which
would otherwise make the no-dead-code rule unenforceable.

**The expiry is exclusive**: acceptance is void once `active_lesson` reaches
`until_lesson`, not after it completes. The AutomatonDB case shows why — its dead-code
warnings expire at `lessons/03-first-refactor.md`, the lesson whose entire purpose is to
remove their cause. Holding acceptance *through* that lesson would suppress the warnings
exactly when they are the lesson's subject.

---

## 5. `STATE.md`

Frontmatter is machine-checkable; the body is what the tutor reads.

```yaml
---
tutorial_id: rust-automaton-db
active_lesson: lessons/03-first-refactor.md
status: in-progress
updated: 2026-09-11
---
```

Body sections: last completed task; concepts demonstrated; decisions made in discussion;
known intentional/incomplete state; accepted warnings; next task; explicitly deferred
items.

**`active_lesson` is a path, not a description.** "Chapter 1, lesson 10" would require
reading `COURSE.md` to resolve, which defeats cold resume. This is the single field that
makes a fresh agent session work.

`STATE.md` never duplicates learner source code. Source is authoritative for
implementation state; `STATE.md` is authoritative for progress.

### The instance stamp

Materialization appends one block to the instance's copy of `tutorial.yaml`, recording
where the instance came from. It is absent from every bundle:

```yaml
instance:
  materialized_from: local:../belay-bundles/rust-automaton-db
  materialized_version: "2.1"
  materialized_at: 2026-09-11
  runner_version: 1
```

Provenance only. Nothing in the teaching loop reads it; it exists so a learner, or a
future update mechanism, can tell which bundle an instance came from, and which version of
it (`materialized_version`, §15c).

---

## 6. Lessons

```yaml
---
id: 03-first-refactor
title: The first deliberate refactor
design_refs: [table-model, row-cell-model]
validators: [cargo-check, cargo-test, has-lib]
---
```

A lesson is **either** `lessons/<slug>.md` **or** `lessons/<slug>/LESSON.md` — a folder
when it ships material (diagrams, data, worked examples). Entries in `lessons` always
name the Markdown file, so every entry is directly readable, `active_lesson` keeps
meaning "the file to read", and the runner never branches on file-vs-directory. The `id`
equals the slug: the file stem, or the folder name.

**Foldered lessons are budget-positive, not a new risk.** The alternative to a folder is
material inlined in the lesson body, and the body is always loaded — so a long worked
example would cost its full length every turn of that lesson. As a sibling file it costs
nothing until the lesson asks for it. What makes this hold is a hard rule: **material
loads only when `LESSON.md` names it**, the same progressive-disclosure discipline skills
use. Two consequences, one of which the validator enforces rather than leaving to
judgement:

- material a `LESSON.md` never mentions is **unreachable** — the tutor cannot know it
  exists — so it is dead weight shipped to every learner. **Since `supplies:` landed this
  is no longer absolute: a file a bundle declares under `supplies` is placed by the runner
  and is exempt, and check 6 does not fire on it.** The rule still holds for material the
  lesson neither names nor supplies;
- a folder directly under `lessons/` with no `LESSON.md` hides its whole contents.

`LESSON.md` must match that name in **exact case**. macOS and Windows resolve `lesson.md`
case-insensitively, so a mis-cased body passes locally and fails on Linux; the validator
therefore compares directory entries by exact name rather than testing existence.

A lesson defines purpose, prerequisites, objectives, theory, concepts to teach,
constraints, suggested progression, completion conditions, and what to persist on
completion. It is **not** a script of conversational turns — the tutor generates each
task from objectives + state + workspace + the learner's last response.

**The tutor teaches a concept before a task uses it** (belay#64, 2026-10-16). When a lesson
opens, the tutor presents its Theory before the first task — shortened if it likes, with
every concept the first task uses kept in — and before each later task explains any concept
that task uses and was not yet explained. A lesson with no Theory section is taught from its
other sections; the section stays optional and the validator does not require it. Theory
never states the outcome a prediction question or a seeded trap keeps for the learner. At
lesson start the order is Theory, then the first task's prediction question, then its steps
(`runner-protocol.md` section 2.3). Observed with 0.9.0: a one-sentence introduction
followed by a task built on concepts nobody had explained.

`design_refs` is the mechanism for partial `DESIGN.md` loading. `DESIGN.md` uses stable
section anchors; a lesson declares only the anchors it needs; the tutor reads only those.
A `lib.rs` refactor lesson structurally cannot pull in WAL recovery or quorum design.

### Generated lessons

A tutor may write a lesson **during** a course. Two situations call for it, and they
produce the same artifact:

- **A side lesson.** The learner hits a concept the main path does not reach — lifetimes,
  trait objects, interior mutability — and needs a compact detour before continuing. The
  AutomatonDB course rules explicitly ask for this.
- **A main-path draft.** `COURSE.md` maps a chapter that has no lesson file yet. Rather
  than stopping, the tutor drafts it on arrival, informed by what the learner actually
  built.

Generated lessons live in **`tutorial/lessons.generated/`**, which is tutor-owned and
**exists only in an instance — never in a bundle.** They follow the ordinary lesson format
and add required provenance frontmatter:

```yaml
---
id: lifetimes-and-borrows
title: Lifetimes, just enough to unblock the borrow
generated: true
generated_at: 2026-09-11
kind: side-lesson            # | main-path-draft
reason: "Lifetimes: a borrow error at cargo-check cannot be explained without them"
after: lessons/03-first-refactor.md
---
```

**The manifest's `lessons` list is never mutated.** It is the authored course, identical
for every learner; a generated lesson is a learner-specific overlay discovered by listing
`lessons.generated/` and reading `after:` to place it. This keeps a later bundle revision
reconcilable, and stops two learners' courses diverging structurally.

`STATE.md`'s `active_lesson` may point into `lessons.generated/`. When it does, a
`resume_at:` field records where to return, so completing a detour resumes the main
path rather than guessing.

**`after:` and `resume_at` are independent, and neither is derived from the other.**
`after:` is placement — where the lesson belongs in the course sequence. `resume_at` is
the way back — the `lessons` entry to make active when the detour finishes. The runner
writes `resume_at` at the moment the detour becomes active.

| The detour starts | `after:` | `resume_at` |
|---|---|---|
| part-way through lesson L, on a prerequisite L needs | the last **completed** authored lesson | **L** — the interrupted lesson |
| part-way through lesson L, on a topic L does not depend on | L | **L** |
| at a boundary, after L completed | L | the entry **after** L |
| at a boundary off the last entry | that last entry | that last entry |

> **Correction, 2026-09-12.** An earlier revision of this spec and of
> `state-lifecycle.md` section 8.3 derived the return target: "the entry after the
> detour's `after:` in `lessons`". **That rule was wrong and it silently lost work.**
> A mid-lesson detour is the ordinary case, not an edge case — being blocked on an
> untaught prerequisite happens inside a lesson by definition, and a learner may ask
> for a side lesson at any moment. Under the derived rule the only placement the text
> permitted for a detour taken during lesson L was `after: L`, which made the return
> target the entry after L. The learner came back from the detour past the rest of the
> lesson they had been in the middle of, with nothing recorded anywhere saying it had
> been skipped. Recording the return target explicitly, when the detour starts, is what
> fixes it. Do not reintroduce the derivation, and do not add a validator check that
> asserts a relationship between the two fields. In the mid-lesson case `resume_at` is
> the same entry as `after:` or a LATER one; at a boundary it is a later one or, off
> the last entry, the same one. The table above is the whole rule.

The field is named `resume_at`, not `resume_after`. It names the lesson to **make
active**, and `resume_after: lessons/04` reads as "resume after lesson 04" — that is,
lesson 05. A tutor reading the contract that way skips a lesson. The rename happened
before anything shipped and before any real instance carried the field.

**Ownership is a runner rule, not a manifest field.** `tutorial/lessons.generated/` is
tutor-owned in **every** instance, whatever the manifest says. It cannot be a `tutor_owned`
entry: every bundle authored before this feature existed omits it, and under
`tutor-must-not-edit-learner-owned` the default for an unlisted path is learner-owned — so
the tutor would be unable to write the directory the feature requires. `tutorial/lessons/`
is correspondingly read-only in every instance regardless of the manifest.

**Completion is tracked in `STATE.md`, not in the lesson file.** The provenance frontmatter
records where a generated lesson came from, never how far the learner got — progress never
lives in a lesson. An instance that has generated at least one lesson therefore gains an
eighth `STATE.md` body section:

```markdown
## Generated lessons

```yaml
- path: lessons.generated/lifetimes-and-borrows.md
  kind: side-lesson
  after: lessons/03-first-refactor.md
  status: pending        # | complete
```
```

The section is absent until an instance has one, which is why `STATE.template.md` does not
carry it.

**Advancement** on completing a lesson: if a generated lesson is `pending` and declares
`after:` equal to the lesson just finished, it becomes active next; otherwise the next entry
in `lessons`. A detour can also start **part-way through** a lesson, which completes
nothing: the lesson is interrupted, and `resume_at` names it so the learner comes back
into it.

**`active_lesson` may name a generated lesson** — it resolves either to an entry in
`lessons` or to a file under `lessons.generated/`. It must resolve to one of the two; a path
resolving to neither is a finding.

**A detour off the final lesson** sets `resume_at` to that final entry. Completing the
detour returns there, finds it already complete, and completes the course. `resume_at` is
therefore always present and always names an authored lesson, which keeps the rule uniform
rather than adding an optional-field case.

**`after:` names an authored lesson, never another generated one.** Detours do not nest.

**Promotion is a deliberate authoring act, not automatic.** Nothing flows from an instance
back into a bundle on its own. Promoting one means:

1. copy the file into the bundle's `lessons/`, renaming it to the numbered slug convention
   of its neighbours;
2. **reset `id` to the new slug** — generated slugs carry no number prefix, and `id` must
   equal the slug, so promotion without a rename silently breaks that check;
3. strip **all five** provenance fields: `generated`, `generated_at`, `kind`, `reason`,
   `after`;
4. add it to `lessons` at the right position;
5. **re-check `design_refs`.** This is the step authoring alone never needs: an instance's
   `DESIGN.md` grows during a course, so a generated lesson may cite an anchor that exists
   in that learner's instance and has never existed in the bundle.

Promotion leaves the originating instance holding its draft, so the two share a slug. This
surfaces only when that learner takes a bundle revision: at re-materialization the draft is
a duplicate of an authored lesson and is reported, and the tutor deletes it then. Until
then the learner works from their copy and nothing breaks.

This is also the course's only quality signal from real use. Three learners all needing a
lifetimes detour after lesson 03 is not three side lessons; it is a missing lesson, and the
generated files are the evidence.

**Improvising around a broken bundle remains forbidden.** A missing lesson file that
`lessons` *does* list, an undeclared validator, a dangling `design_ref` — these are defects
to report, not to paper over. Generation is a recorded, provenanced act for a course that
is working as intended.

#### Decision: a coverage list decides whether "stuck" is a gap

An earlier draft listed "the learner is stuck" as a flat non-reason to generate a lesson,
alongside "you would rather teach something else". That is too blunt, and it is wrong in
one of the two situations it covers. **Stuck because a prerequisite concept was never
taught is exactly the case a side lesson exists for. Stuck because the exercise is hard is
the learning itself, and a lesson written to relieve it takes the exercise away.** The two
present identically — a learner who cannot proceed — so a rule that resolves them by the
tutor's judgement resolves them differently for every learner and every tutor.

The oracle is a list the course already declares. AutomatonDB's `COURSE.md` carries a
"Rust coverage requirements" section naming the topics the main path must eventually
exercise; the runner tests the **blocking concept** against it:

| Blocking concept | Reading | Action |
|---|---|---|
| in the coverage list, not yet taught by a completed lesson | a genuine prerequisite gap | generate a side lesson |
| in the coverage list, already taught | ordinary difficulty | coach; generate nothing |
| absent from the coverage list | outside the course's scope | tell the learner; do not widen the course silently |

Three things make this the right shape:

- **it is the course's own declaration, not the tutor's opinion.** The author said what
  the course covers. The rule only reads it back;
- **it gives the format a mechanical use for a section that had none.** Coverage
  requirements were previously prose a learner might read. The rule makes writing one pay
  off, so `bundle-format.md` raises it from MAY to SHOULD;
- **"already taught" is answered from `STATE.md`**, from *Concepts demonstrated* and the
  *Generated lessons* record — never by opening completed lesson files, which would
  violate the context budget §8 exists to protect. Where `STATE.md` does not settle it,
  the tutor asks the learner, who is a cheaper and better witness than a reconstruction.

A bundle with no coverage list is still valid — hence SHOULD, not MUST; the shipped
`examples/rust-cli-basics` has none. The tutor then falls back to its own judgement and
states which reading it took, so the learner can disagree.

#### Decision: a learner may request a side lesson, with one guard

A learner asking for a side lesson outright ("give me a side lesson on lifetimes") is
first-class, and it sidesteps the judgement problem above entirely by putting the person
who knows what they do not know in charge of the call.

**The single guard: a learner may not request a side lesson on the active lesson's own
declared objectives.** "Teach me lifetimes" during a lifetimes lesson is a request for the
answer with extra steps — the lesson exists to make the learner arrive at that concept, and
delivering it as a lesson hands over the exercise in a form that looks legitimate. This is
the same rule as `solution_code`, applied to a longer vehicle. Everything outside the
active lesson's declared objectives is permitted, including topics the coverage list never
names: the third row of the table above forbids widening the course *silently*, and a
learner's explicit request is the opposite of silent.

A requested lesson is an ordinary generated lesson — same structure, same provenance, same
completion conditions, same placement. `reason:` records that the learner asked. That
distinction matters downstream: `bundle-format.md` reads generated lessons as the course's
only quality signal from real use, and a lesson the learner chose is evidence about that
learner's interest, not about a hole in the course. Without the marker in `reason:` an
author would count it as a hole.

#### Decision: a `main-path-draft` announces itself to the learner

A drafted chapter occupies the same position in the course, uses the same structure, and
reads in the same voice as a lesson an author wrote and reviewed — and it carries none of
the same warrant. It was written that morning, by the tutor, against one learner's code,
reviewed by nobody. **The learner currently has no way to tell.**

So: when a `kind: main-path-draft` lesson becomes active, the tutor states plainly, in one
sentence at the start, that this chapter was not written yet and is being drafted from
where the learner has got to. Not in a closing note, not parenthetically, not only in
`STATE.md`.

Two reasons, both the learner's rather than the system's:

- **it changes how a confident claim in that lesson should be read.** Authored prose and
  drafted prose are indistinguishable on the page; the learner is entitled to weigh them
  differently and to push back harder on the draft;
- **the learner will want to know which lessons were drafted.** Drafts are the raw material
  of promotion, described earlier in this section, and the learner who took one is the
  only person who can
  say whether it worked. They can only answer that if they knew at the time.

A `side-lesson` is deliberately exempt. Its nature is already evident — either the learner
asked for it, or the tutor announced the detour when proposing it — and a second
announcement is noise that makes the one that matters easier to miss.

> **A rejected design, recorded so it is not retried.** An earlier draft made `COURSE.md`
> the lesson index and cross-referenced it against `lessons/` by scanning its prose for
> lesson paths. On a real bundle that check was **inert**: the course map names lessons as
> prose headings, so the scan matched nothing and reported clean without examining
> anything. An explicit list in the manifest removes the need to parse prose at all.

### Optional lessons

**Added 2026-09-12.** A course can carry authored lessons that are *offered* rather than
sequenced. They live in `lessons/` beside every other authored lesson, are listed in a new
manifest map `optional_lessons` instead of the ordered `lessons` list, and carry
`optional: true` in their own frontmatter.

The motivating case is not enrichment. It is a mistake the author can see coming: the
learner is about to key a window on arrival time, or write a counting function that opens
its own file, and the failure that follows is recognisable, specific, and several lessons
away. The tutor warns in one sentence, offers a lesson, and lets the learner **defer** it.
When the anticipated failure actually arrives, the tutor connects the observed failure to
the deferred topic and offers the lesson again — which makes this an adaptive branch that
re-enters the main path when its relevance becomes observable, not a reading list.

Two manifest maps carry it:

```yaml
optional_lessons:
  lessons/event-time-and-watermarks.md:
    offer_at:      [lessons/04-window-execution.md]   # where it may first be offered
    offer_because: >                                   # what the tutor says when offering
      Windows keyed on arrival time put a delayed record in whichever window is
      open when it arrives, not the one it belongs to.
    anticipates:   [late-event-wrong-window]           # omit for plain enrichment
    repair_in:     lessons/04-window-execution.md      # whose work gets repaired
    required_for:  [lessons/06-correctness-under-delay.md]

failure_modes:
  late-event-wrong-window:
    summary: >
      A record that arrives after its window closed is counted in whichever
      window is open when it arrives.
    signals: [validator:late-events, token:LATE_EVENT_MISBINNED, diagnosis]
```

**Three layers stay separate, and that separation is the design.** Evidence is what was
observed — a named validator failed, a token appeared in its output, the tutor read the
code. A failure mode is what the tutor *concluded*, and it has a stable id. The lesson is
what addresses that conclusion. `signals` says which observations are worth weighing and
never decides; diagnosis stays with the tutor, exactly as every other judgement in this
format does. That is why there is no field matching raw compiler output: a rule built on
an error string breaks when a toolchain rewords it, and it cannot express the cases that
matter most — a named test failing, a fault-injection run behaving as designed, or a
design that is visibly wrong before it has failed anything.

**`anticipates` doubles as the re-offer trigger; there is no separate `reoffer_when`.**
The failure mode carries its own evidence, so a second field would be a second place for
the same fact. An author who wants to warn about one failure and re-offer on another can
declare both in `anticipates`; nothing yet needs them to differ, and §15 records that as
open.

**`repair_in` is not the way back, and the distinction is load-bearing.** The lesson a
detour returns to is `resume_at`, recorded in `STATE.md` when the detour starts, from
where the learner is actually standing — the existing rule, and the one an earlier
revision of `state-lifecycle.md` got wrong by deriving it from a declared field. An
anticipated failure surfaces *later* than the code that caused it, so the two genuinely
differ: a learner who defers at lesson 04 and trips the failure in lesson 06 returns to
**06**, and repairs what **04** built. `repair_in` names the second thing only.

**The learner's decisions are progress**, so they live in the instance: a `## Optional
lessons` section in `STATE.md` recording `offered`, `deferred`, `in-progress` or
`complete`. *Not yet offered* is the absence of an entry, because a course with twelve
optional lessons would otherwise carry twelve lines saying nothing happened. Four rules
keep it from looping: a `complete` lesson is never offered again; a `deferred` one is
re-offered only on newly observed evidence, and reaching another `offer_at` entry is not
evidence; a failure that persists after the lesson is an ordinary failure to coach through;
and an `in-progress` lesson is the active one and is not offered at all.

**Reuse, not new machinery.** Taking an optional lesson *is* the existing detour:
`active_lesson` moves to it, `resume_at` records the way back, and the same exception that
lets `active_lesson` leave the `lessons` list for a generated lesson covers this one. The
only genuinely new concepts are the failure-mode registry and the offer metadata, and both
live in the manifest rather than in lesson frontmatter for one reason: **the tutor loads
the manifest every turn and opens exactly one lesson file.** Metadata the tutor needs in
order to decide whether to *offer* a lesson cannot live inside that lesson without costing
one file open per optional lesson per turn, which is the cost this whole format exists to
avoid.

**`bundle_format` stays `1`.** The two keys are additive, and every bundle written before
them is valid unchanged. The degradation is stated in `bundle-format.md` §13 rather than
signalled by a version: a runner that predates the feature ignores both keys, so every
optional lesson goes unoffered and every `required_for` gate unenforced — which is
identical to a learner who declines every offer, a case an author has to support anyway.
The invariant that makes it safe is an authoring obligation no validator can check: **the
course must be completable by a learner who declines everything.** An older copy of the
validator additionally reports each optional lesson as unlisted; that is a stale checker,
not a defect in the bundle.

---

## 7. Catalogue and the provider boundary

**Revised 2026-09-12.** The earlier design read exactly two files: the catalogue shipped
with the plugin, and one user file. It is replaced by a configurable list of catalogues,
any of which may be a Git repository. The two-file model survives as the *implied
default*, so nothing a user already has stops working.

### 7.1 Three layers

| Layer | File | Ships | Contains |
|---|---|---|---|
| catalogue of catalogues | `~/.config/belay/catalogs.yaml` | no | which catalogues, in priority order |
| catalogue | `skills/belay/catalog/builtin.yaml` | yes | only bundles shipped with the plugin |
| catalogue | `~/.config/belay/catalog.yaml` | no | the user's registrations |
| catalogue | any `catalog.yaml` in a bundles repository | no | that repository's own bundles |
| cache | `~/.cache/belay/catalogs/<id>/` | no | the last successful copy, and any clone |

```yaml
catalogs_version: 1
catalogs:
  - id: mine
    source: { type: file, path: ~/tutorials/catalog.yaml }
  - id: skomp
    source:
      type: git
      url: git@github.com:skomp/belay-bundles.git
      ref: main
      path: catalog.yaml          # repository root, or any subfolder
  - id: builtin
    source: { type: bundled }
```

Catalogue source types: `bundled`, `file`, `git`. **When `catalogs.yaml` is absent, the
runner behaves as though it listed `~/.config/belay/catalog.yaml` followed by
`bundled`** — which is the old model exactly, so an existing user catalogue needs no
migration.

A catalogue entry keeps the shape it had:

```yaml
catalog_version: 1
tutorials:
  - id: rust-automaton-db
    title: Learn Rust by Building AutomatonDB
    description: >
      Project-driven Rust taught by building a serious automaton-native,
      partitioned database with storage-engine and distributed-systems depth.
    subjects: [rust, databases, distributed-systems, automata, storage-engines]
    aliases: [cassandra-like, key-value-store, database-internals]
    level: intermediate-to-advanced
    style: [project-driven, interactive, long-form]
    scope: "23 lessons; months of work"
    workspace_kind: existing-or-new-repository
    source:
      type: local            # | git | archive
      path: rust-automaton-db
```

**`source` is still the entire provider boundary for a bundle**, and `git`/`archive`
remain declared but unimplemented *there*. Remoteness was added one layer up instead: a
**catalogue** may be remote, and it brings its bundles with it.

> **A bundle path resolves relative to its own catalogue's root — the directory that
> holds the catalogue file.**

That rule is what makes a bundles repository install with one entry: it ships a
`catalog.yaml` at its root naming its own bundles by relative path, and adding the
repository adds the courses. For a `git` catalogue the root is inside the cache clone, so
a resolved bundle path is an absolute path under `~/.cache/belay/`.

A catalogue fetched from a repository may not name a bundle outside its own directory —
no absolute path, no `..` escape. Such an entry is skipped with a reason. A local
catalogue is the user's own file and may name anything; that is the existing behaviour and
several real entries depend on it.

### 7.2 `scripts/catalogs.py`

Fetching, caching, merging, precedence and staleness are deterministic, error-prone, and
exactly the kind of work an agent does inconsistently across sessions — the same argument
that justified `validate_bundle.py`. **This script runs on a learner's machine at runtime**,
so it is stdlib-only plus the `git` binary. No third-party packages. The validator has the
same constraint for the same reason — it too runs on a learner's machine (§9) — and the two
differ in *when*: `catalogs.py` runs at discovery, `validate_bundle.py` at materialization.

| Command | Runs when | Does |
|---|---|---|
| `discover` | a discovery request starts | refreshes every catalogue, prints the merged catalogue and per-source status |
| `status` | explaining the configuration or a failure | reports from disk; fetches nothing |
| `resolve <id>` | the learner has chosen | prints the entry and the bundle directory, and checks the bundle is there |

Options: `--config`, `--cache-dir`, `--timeout`, `--offline`, `--json`. Exit codes: `0`
all current, `1` partial (something cached or unavailable), `2` the configuration is
unusable, `3` nothing to serve.

**`discover` never touches a bundle path** — it does not open, list or stat one. That is
what keeps the provider boundary real rather than aspirational, and it is tested by
offering an entry whose bundle directory does not exist. `resolve` is the step allowed to
look, and it is the step that runs after the learner has chosen.

The restricted YAML reader moved to `scripts/yamlite.py`, shared by both scripts. Two
hand-written YAML parsers would drift apart, and a fix applied to one of them is the
classic half-fix.

### 7.3 Refresh, and failure

**Refresh every catalogue when a discovery request starts. Once.** Never per turn. Never
during a resume — a resume reads no catalogue at all, so continuing a course costs
nothing.

**A failed refresh never fails discovery.** Serve the catalogues that answered, name the
one that did not, fall back to its last successful cached copy, and state that those
results are cached and how old they are. Stale results are never presented as current: the
cache records that the last attempt failed, so a later `status` or `resolve` — which fetch
nothing — cannot read the old success timestamp and call it current.

**The failure kinds are reported distinctly**, because they have different repairs:

| Kind | Repair |
|---|---|
| `unreachable` | the network, or a mis-spelt host |
| `no-access` | credentials, or the repository name |
| `no-ref` | the `ref` field |
| `no-catalogue` | the `path` field |
| `missing-file` / `unreadable` / `malformed` | the local file |
| `no-git` | install git |
| `unclassified` | git's own message, printed verbatim, uninterpreted |

Classification order is load-bearing and was the single most delicate part of this work.
An SSH transport failure prints **both** the transport error **and** "Could not read from
remote repository. Please make sure you have the correct access rights" — the same words a
refused key prints. Testing the access patterns first therefore reports every unreachable
host as a permissions problem and sends the learner to fix credentials that are already
correct. The transport patterns are tried first, and that case has its own test.

`unclassified` exists so the script can decline to guess. A classifier that always returns
one of the three kinds cannot be wrong out loud, only quietly.

**Authentication:** the runner uses the Git credentials the user already has — SSH key,
credential helper, `gh`. No tokens, no stored secrets, no prompting: `GIT_TERMINAL_PROMPT=0`
and SSH `BatchMode=yes` turn a credential prompt into a fast, classifiable `no-access`
rather than a process waiting for a human who is not there. A private repository installs
by the same mechanism as a public one.

### 7.4 Matching

Agent judgement against `subjects`/`aliases`/`title`/`description`/`level`/`style` — not
a scoring function. Rules:

- Never silently choose when more than one entry plausibly matches.
- A single match is offered, never auto-started.
- State **why** each candidate matched, so ranking is inspectable.
- Show title, description, level, scope, `workspace_kind` — not the lesson list.
- Do not discard weak-but-valid alternatives; rank them lower.
- Say "nothing matched" only when no catalogue was cached or unavailable.

**Discovery loads metadata only.** The runner must not read anything under a bundle path
until the learner has chosen.

Registration is the one deliberate exception: adding a course to a catalogue requires
reading its `tutorial.yaml` to build the entry. The learner is pointing at that specific
bundle, so no provider boundary is crossed.

### 7.5 Precedence and authority

**First match wins, by tutorial `id`, in `catalogs.yaml` order.** The implied default puts
the user's catalogue before `builtin`, so a user can override a shipped tutorial — the
same precedence the two-file model had.

**The runner must say which catalogue supplied an entry and which were shadowed.**
Silently substituting a different bundle for a known course name is exactly the kind of
hidden choice the matching rules forbid everywhere else. `discover` prints an `OVERRIDES`
line and lists the shadowed entries rather than dropping them.

Catalogue entries duplicate manifest metadata (`title`, `subjects`, `level`,
`workspace_kind`, …) by necessity, because discovery must not open the bundle. The copy
can therefore drift. **The bundle's `tutorial.yaml` is authoritative once resolved**; the
catalogue entry is a discovery-time hint. If they disagree after resolution, the runner
uses the manifest and should say so.

`scope` is the exception: it exists only in the catalogue, has no manifest field, and is
derived at registration time from the length of the `lessons` list.

### 7.6 Presenting the choice — a selection, and leveled narrowing

**Added 2026-09-12, from an observed session.** The learner asked "i want to learn
something. which tutorials are available?" and the runner answered with a prose list of
all three courses. Two defects, and they are separate:

1. **The choice was prose, not a selection.** The learner had to read paragraphs and then
   type a title back. Choosing from a list is the interaction; describing a list is not.
2. **A broad request got a flat dump.** "I want to learn something" carries no subject, no
   level and no budget, and the runner had all three facets in the catalogue it had just
   loaded.

**A choice is offered as a selection.** The candidates go in front of the learner as
options to pick from, through whatever interactive selection the host provides, and as a
numbered list when it has none. The rule is stated as an *action*, and the skill names no
host-specific tool for it — the §10 host-neutrality rule, which is what lets one
`SKILL.md` serve both hosts: on Claude Code the instruction resolves to the interactive
picker, and on Codex it degrades to a numbered list instead of breaking.

**Narrowing is triggered by the candidate count, never by the shape of the question.**
"I want to learn WebGL" already lands on one entry; narrowing there interrogates someone
who has already answered. Phrasing is a poor signal and a learner pays for a wrong guess
with a round of questions; the count is exact and free.

When more candidates remain than fit one comfortable question, the runner narrows **one
facet at a time, in the order people choose a course: subject, then level, then time
commitment (`scope`)**. That order matches how the decision is actually made — nobody
picks a difficulty before a topic — and each answer makes the next question smaller.

**Every facet's options are derived from the loaded catalogue, never hardcoded.** Subject
options come from the candidates' `subjects` and `aliases`, level options from their
distinct `level` values, time options from their distinct `scope` values. This is the
same argument as §7.4's: the runner holds no subject knowledge. A new bundle in any
catalogue therefore appears in the first question by itself, with no edit to the skill —
and a facet on which every candidate agrees is skipped, because it separates nothing.

Three guards, all of which matter more than the narrowing itself:

- **Stop at four or fewer candidates**, then present the real choice with the metadata a
  learner decides on — title, description, level, scope, workspace kind, and why it
  matched. Never the lesson list: §7.4's provider boundary is unchanged, and nothing
  under a bundle path is opened before the learner chooses.
- **Never narrow to zero.** A filter that would empty the list is not applied; the runner
  says that no course carries that combination and keeps the previous set. This is §7.3's
  honesty rule in a second place — "nothing matched" is as false after a self-inflicted
  empty filter as it is when a catalogue failed to refresh.
- **Always offer an escape hatch** — an option showing everything, at any point, and a
  free-text answer honoured as written. A learner who knows what they want must never be
  walked down a tree to reach it.

Narrowing shortens a list and never chooses from it. Every §7.4 rule survives intact: a
single survivor is offered and never auto-started, more than one plausible match is
presented rather than silently resolved, each candidate says why it matched, and
weak-but-valid alternatives are ranked lower rather than dropped.

`catalogs.py discover --json` already returns every field this needs — `subjects`,
`aliases`, `level`, `scope`, `workspace_kind`, `title`, `description` — so the facets are
a judgement over data the runner already holds, and the script did not change.

**Where it is written.** The normative procedure is `catalogue-format.md` §9, because
that is the document a discovery loads; `runner-protocol.md` §1 carries the rule for a
mid-course "what else is available?" and points at it, and `SKILL.md` keeps one paragraph
as a control plane. Putting the procedure in `runner-protocol.md` alone would hide it
from the only phase that needs it, since that document is loaded before the first
teaching task — after the choice has been made.

---


---


## 8. Runner protocol

```
ORIENT
  ├─ <cwd>/tutorial/tutorial.yaml exists (walking up to repo root)?
  │    ├─ yes + "continue" / no subject named ──────────► RESUME
  │    └─ yes + different subject named ────────────────► ask
  └─ no ─────────────────────────────────────────────────► DISCOVER
                       catalogs.py discover (refresh once, merge, report)
                            → catalogue metadata → match → choice
                                                        ↓
                                                  MATERIALIZE
                       catalogs.py resolve <id> → copy → STATE.template.md
                                    → STATE.md → stamp instance
                                                        ↓
                                  ┌───────────────► TEACH LOOP ◄──────┐
                                  │  read tutorial.yaml, STATE.md      │
                                  │  read ONE lesson file              │
                                  │  inspect learner workspace         │
                                  │  teach what the next task uses     │
                                  │  → exactly one task                │
                                  │  ← learner evidence                │
                                  │  validate                          │
                                  │  update STATE.md ──────────────────┘
```

### Context budget (the reason this project exists)

| Loaded every turn | Never loaded routinely |
|---|---|
| `SKILL.md` | `COURSE.md` |
| `tutorial.yaml` | `DESIGN.md` in full (only declared anchors) |
| `STATE.md` | any other lesson |
| **one** lesson body | any completed lesson |
| learner files relevant to the task | lesson-folder material not named by `LESSON.md` |

### Teaching contract (bundle-overridable defaults)

- Exactly one actionable task per turn. A conceptual question is answered and does
  **not** advance the task.
- The learner writes the code. No solution code unless explicitly requested.
- Validate against declared completion conditions before advancing. "Looks plausible" is
  not evidence.
- On failure: decide whether it is the intended lesson, explain the concept, hand back
  one correction. Do not repair the learner's work.
- **Update `STATE.md` only after demonstrated progress**, never to record intent.
- Do not edit learner-owned paths. Do not silently complete exercises.

Validation outcomes are distinguished: `failure` / `success` / `success with relevant
warning` / `known accepted warning` (matched against `STATE.md`'s `accepted_warnings`).

---

## 9. Validator script

`skills/belay/scripts/validate_bundle.py` — **written for authors, and run by the runner
too.**

**Corrected 2026-09-12.** This section said "authoring-time only. Never in a learner's
path; running a tutorial does not invoke it." That was true when it was written and stopped
being true when the runner began validating the instance at materialization (issue #9). The
claim that replaced it:

- an **author** runs it over a bundle or a catalogue before shipping;
- a **runner** runs it over the instance it has just materialized, before the first task,
  and at the five further moments `references/runner-protocol.md` section 13.1 names;
- **no teaching turn runs it**, which is the cost rule in `runner-protocol.md` section 1,
  and **no learner invokes it by hand**.

So the distinction is *when* it runs and *who* triggers it, never *whether* a learner's
machine runs it. Both scripts do. `scripts/catalogs.py` (§7.2) runs at discovery;
this one runs at materialization. Both are therefore stdlib-only, and both share
`scripts/yamlite.py` and nothing else. Anyone who read the old sentence and concluded the
validator may depend on an authoring-only toolchain should re-read this section.

Its justification is the same as the runner's: **checking a bundle must not require
reading the bundle into context.** For a 23-lesson course, verifying every lesson's
`design_refs` by agent means loading 23 lesson files plus `DESIGN.md`. A script answers
it with zero context.

**Checks that need a script** (cross-file, all-lessons):

1. every `design_refs` entry resolves to a real `DESIGN.md` anchor
2. every lesson `validators` entry is declared in `tutorial.yaml`
3. every lesson has `id` + `title` frontmatter, and `id` equals its slug
4. every `lessons` entry resolves; every lesson in `lessons/` (top-level `.md` plus
   folders with `LESSON.md`) is listed exactly once, in `lessons` **or** in
   `optional_lessons`; every lesson folder has a `LESSON.md` named in exact case
5. no progress markers anywhere in `COURSE.md` or `lessons/`
6. every file in a lesson folder is mentioned by that folder's `LESSON.md`

**Catalogue mode** (added 2026-09-12): `--catalog <file>` checks a catalogue file, and
`--catalog <file> --portable` additionally checks that every bundle path stays inside the
catalogue's own directory — which is what a `catalog.yaml` shipping inside a bundles
repository must satisfy, and what a user's own catalogue must not be held to. Catalogue
mode has its own seven checks and its own numbering, because a catalogue is not a bundle
and a shared table in which most numbers never apply teaches nobody anything. The mode
stays explicit on the command line for the same reason bundle and instance do.

**Cheap checks** (free once the script exists):

7. `STATE.template.md` present / `STATE.md` absent — reversed in instance mode
8. `tutorial.yaml` parses; `bundle_format` known; required fields present
9. `COURSE.md`, `DESIGN.md` exist; `lessons` is non-empty
10. `workspace_kind` and `ownership_policy` are known values; `tutor_owned` is non-empty;
    `learner_owned` is non-empty **unless** `workspace_kind: none`, since a course that
    builds no software owns none of the learner's files; and every ownership glob parses
    in the dialect of §15e

**Optional-lesson checks** (added 2026-09-12, with the feature in §6):

18. `optional_lessons` is well-formed — every key resolves to a lesson under `lessons/`
    and is not also in `lessons`; `offer_at` is non-empty and every entry is a `lessons`
    entry; `offer_because` is present; every `anticipates` id is declared; `repair_in`
    and `required_for` name `lessons` entries; `required_for` requires a non-empty
    `anticipates`, because a gate with nothing to gate on can never open or close
19. `failure_modes` is well-formed — ids are shaped, `summary` is present, every
    `signals` entry is one of `validator:<declared name>`, `token:<TOKEN>` or
    `diagnosis`, and every declared mode is anticipated by some optional lesson
20. `optional: true` in a lesson's frontmatter agrees with the `optional_lessons` list,
    in both directions
21. [instance] `STATE.md`'s `## Optional lessons` record is well-formed — known states
    only, paths that are declared optional lessons, no duplicates, and `in-progress`
    agreeing with `active_lesson` both ways

Checks 18, 19 and 21 report `n/a` when the bundle uses none of this, which is the normal
case and is **not** the same as passing. Check 20 runs on every bundle, because "no
main-path lesson declares `optional`" is a claim worth checking whether or not the course
has optional lessons.

**What none of them check**, and it is the invariant that matters most: that the course
can be finished by a learner who declines every offer (`bundle-format.md` §13). It is an
authoring obligation, a green run does not certify it, and `LIMITATIONS` says so.

Mode is explicit, never inferred: `validate_bundle.py <path>` checks a bundle,
`validate_bundle.py --instance <path>` checks an instance. Inferring the mode from which
state file is present would make check 7 unable to fail, since a mis-shaped bundle would
simply be validated as the other kind.

Two further checks follow from §3 and §5 rather than from the list above:

11. instance mode — `STATE.md` frontmatter well-formed, `tutorial_id` matches the
    manifest, and `active_lesson` resolves **either** to an entry in `lessons` **or** to a
    file under `lessons.generated/` (see "Generated lessons" in §6); a path resolving to
    neither is a finding
12. bundle mode — `STATE.template.md` agrees with the manifest (`tutorial_id` equals
    `id`, `active_lesson` equals `lessons[0]`, `status` is `not-started`)

The `instance:` stamp is asserted in both directions: absent from a bundle, present in an
instance.

Exit codes are `0` pass, `1` findings, `2` usage, and **`3` indeterminate** — no findings,
but some check could not run. A `DESIGN.md` that is not valid UTF-8 reaches this: check 1
cannot run while nothing else complains, and printing green there would be a false
oracle.

**Explicitly out of scope**, stated in the docs so a green run is not over-read:
pedagogical quality, lesson ordering, whether `DESIGN.md` is *accurate*, whether
completion conditions are checkable, anything about learner code. Green means
"structurally well-formed and executable by a runner", not "good course".

Two limits are narrower than the rules they serve, and the script says so on every run
rather than looking stronger than it is:

- **Check 6 verifies that a `LESSON.md` names its material, not that it says *when* to
  use it.** Intent cannot be distinguished from a filename inside a code fence without
  crying wolf.
- **"No learner source code in the bundle" is not checked at all.** It cannot be told
  apart from a legitimate code example. It stays an author-judgement item on the
  contract's self-check list.

Progress-marker detection (check 5) is anchored to **structural positions** — headings,
`Status:`-style labels, ticked checklist boxes, bold labels, table cells, lesson
frontmatter — and is case-sensitive where the word is a label. An earlier free-text,
case-insensitive match rejected valid bundles for ordinary prose such as "while the
refactor is in progress".

### A check that was removed, and why

A reverse material check — "`LESSON.md` references a file that does not exist" — was
implemented and then deleted. It cannot distinguish a material reference from an ordinary
prose mention: it immediately flagged `DESIGN.md` and `STATE.md` because a lesson says
"record those in `DESIGN.md`", and lesson 03 alone mentions `src/lib.rs`, `main.rs` and
`Cargo.toml`. The exclusion list is unbounded. **A validator that cries wolf gets
ignored, which is worse than not having the check.** The forward direction (check 6)
survives because it walks files that actually exist.

### Test strategy

Every check gets a deliberately broken fixture, and the suite asserts **that specific
error fires**. A validator that can only be shown passing is a false oracle. The suite
must demonstrate each check reporting a positive before any bundle is called clean. The
parser reports which checks ran; it never silently skips a check and prints green.

Fixtures must not rely on filesystem behaviour that differs by platform. A fixture that
renamed `LESSON.md` to `lesson.md` silently tested nothing on macOS, because the rename
was a no-op on a case-insensitive filesystem.

**Parsing.** YAML, chosen for its two real readers — the author and the agent. The only
mechanical consumer is this script, and it always parses with the restricted reader in
`scripts/yamlite.py`, which **rejects** constructs outside its subset rather than guessing.
PyYAML is never used, even where it is importable: it accepts an anchor, silently collapses
a duplicate key, resolves `no` and `2026-09-13` to a bool and a date, and describes its
scanner's state where the restricted reader names the cause and the line. Preferring it
when present made the verdict a property of the machine (belay#29). (Verified 2026-09-13
on Python 3.11.9 with PyYAML 6.0.3 installed and, as a control, with `import yaml` made to
fail: both suites green, and the parse identical.)

---

## 10. Packaging

One shared `skills/` directory, sibling per-host manifests. Proven shape: superpowers
6.3.0 ships `.claude-plugin/`, `.codex-plugin/` and others over a single `skills/`.

```
belay/
├── .claude-plugin/{plugin.json,marketplace.json}
├── .codex-plugin/plugin.json          "skills": "./skills/", "hooks": {}
├── hooks/hooks.json                   Claude Code only: the ownership guard (§15e)
├── skills/belay/
│   ├── SKILL.md
│   ├── references/{bundle-format,catalogue-format,runner-protocol,state-lifecycle}.md
│   ├── scripts/{validate_bundle.py,catalogs.py,plan_update.py,evidence.py,yamlite.py,
│   │            ownership.py,ownership_guard.py,instance_git.py}
│   ├── catalog/builtin.yaml
│   └── examples/rust-cli-basics/
├── tests/{fixtures/,conformance/,test_validate_bundle.py,test_catalogs.py,test_plan_update.py,
│          test_evidence.py,test_ownership.py,test_instance_git.py}
├── docs/superpowers/specs/
└── README.md
```

Install:

```
Claude Code:  /plugin marketplace add skomp/belay ; /plugin install belay@belay
Codex:        codex plugin marketplace add <repo> ; codex plugin add belay
```

### Host-neutrality rules (all verified, see §13)

- Frontmatter: `name` + `description` only. Both hosts accept this; anything more is
  host-specific enrichment.
- **The skill body names no host-specific tool.** Describe actions ("read the file", "run
  the configured command"), never `Read`, `Bash`, `Task`, `apply_patch`. This one rule
  makes the body portable, and it is the same rule that keeps bundles portable.
- **No `${CLAUDE_PLUGIN_ROOT}`** — Claude-only. Both hosts resolve skill-body paths
  relative to the skill directory, so everything needed at runtime lives under
  `skills/belay/` and is referenced relatively.
- **Trigger words go at the front of `description`** — Codex truncates descriptions under
  a 2%-of-context / 8,000-char budget, shortest-first, and a truncated description stops
  triggering.
- **No file-backed slash command on Codex.** Invocation there is `$belay` or implicit
  description match. The runner must be discoverable by description, not by command name.

---

## 11. Repositories and current state

Three repositories, deliberately separate.

### `belay` — the runner

The plugin. Contains no course content. Ships the skill, the reference documents, the
validator, and a small example bundle.

### `belay-bundles` — the courses

Each subfolder is one self-contained bundle. Not shipped with the plugin; registered in a
user's catalogue. Currently holds `rust-automaton-db/`.

That bundle was authored separately from the full course history and imported verbatim,
then corrected in three ways: an ordered `lessons` list replacing `entry_lesson`;
`workspace_kind` from `new-repository` to `existing-or-new-repository`, because the course
resumes in a repository that already exists; and `ownership_policy` from `on-request` to
`tutor-must-not-edit-learner-owned`, because the looser value would permit a tutor to
perform the pending refactor on the learner's behalf.

Its lesson numbering differs from the original playbook: what older notes call "Chapter 2,
the first refactor" is `lessons/03-first-refactor.md`, because the original Chapter 1 was
split into `01-rows-cells-temporal` and `02-typed-keys-table-hierarchy`.

### `automaton-db` — a learner workspace

Holds the Rust implementation and one instance at `tutorial/`, materialized from the
bundle. It was uncommitted when this section was written, and the owner committed it on
2026-09-12, instance and `STATE.md` included (§15, decision 1). Which instance files a
learner commits in general is now a policy rather than a per-workspace decision: §15f.
Its first resume under that policy asks the learner the question once.

Its `STATE.md` was written from `src/main.rs` and from measured build output, not from the
playbook's resume marker, which was stale: the marker named "introduce a provisional
scalar `Key`" as the next task and described `Database { entries: BTreeMap<String, Row> }`.
The actual source had moved well past that:

```
KeyValue{Utf8,Int64}  KeyType  KeyColumn  PartitionKey  ClusteringKey
Cell{value,valid_from,expires_at}  Row{cells,expires_at}
Partition{rows}  Table{partition_key_columns,clustering_key_columns,partitions}
TableError{InvalidPartitionKey,InvalidClusteringKey}
Table::put -> Result<Option<String>, TableError>   (validates count, then type)
5 tests inline in `mod tests`; main() empty; Table::get commented out
```

Measured 2026-09-11: `cargo test` passes 5/5; `cargo check` emits 17 warnings, of which
16 are dead-code consequences of `main()` being empty (accepted, expiring at
`lessons/03-first-refactor.md`) and one is a genuine unused-imports cleanup, explicitly
not accepted.

**The pending task is lesson `03-first-refactor`: `main.rs` → `lib.rs`. It has not been
started, and the tutor must not perform it.** `src/lib.rs` does not exist. This is the
single most important fact for any session picking the work up.

---

## 12. Scenarios

- **A — discovery with choice.** `"I want to learn Rust"` → catalogue metadata read →
  candidates presented with match reasons → learner chooses. Only one tutorial ships with
  the plugin, so two matches require the user's catalogue to register a second;
  documentation states this rather than implying the shipped state demonstrates it.
- **B — start.** Resolve definition → resolve/create workspace → materialize instance →
  `STATE.template.md` becomes `STATE.md` → load `lessons[0]` → exactly one task.
- **C — resume.** Active instance detected; no selection; `STATE.md` read; `active_lesson`
  loaded; pending task presented.
- **D — validation.** Tutor inspects diff/source, runs configured commands, classifies the
  outcome, does not rewrite source; success advances state, failure is explained.
- **E — cold thread.** New conversation, no chat history: `tutorial.yaml` + `STATE.md` +
  one lesson is sufficient. This is what `active_lesson`-as-path buys.

---

## 13. Verified host facts

Measured 2026-09-11 against installed versions and source, not recalled. Implementers
should not re-derive these.

| Fact | Value |
|---|---|
| Codex version probed | `codex-cli 0.136.0` |
| Codex canonical skills dir | `~/.agents/skills/` (user), `<repo>/.agents/skills/` |
| `~/.codex/skills` | works, non-canonical, characterised as deprecated |
| Codex skill frontmatter | requires `name` + `description`; runtime ignores unknown keys |
| Codex authoring linter | allows only `{name, description, license, allowed-tools, metadata}` |
| Claude Code frontmatter | **all** fields optional; `name` ≤64 `[a-z0-9-]`, `description` ≤1024 |
| Shared `SKILL.md` on both hosts | **verified working** — a Claude-flavoured skill loaded normally on Codex |
| Codex skills context budget | 2% of window, or 8,000 chars; descriptions truncated first |
| Codex file-backed slash commands | **do not exist**; `~/.codex/prompts/*.md` is inert |
| Codex skill invocation | `$name` popup, or implicit description match; `/skills` is management only |
| Codex implicit-invocation opt-out | `agents/openai.yaml` → `policy.allow_implicit_invocation: false` |
| Codex plugin manifest | `.codex-plugin/plugin.json`; needs `"hooks": {}` to suppress hook discovery, which since §15e also keeps Codex off the Claude Code `hooks/hooks.json` |
| Claude Code plugin hooks | `hooks/hooks.json` at the plugin root, loaded with no manifest key; PreToolUse output `hookSpecificOutput.permissionDecision` (`allow`/`deny`/`ask`/`defer`) and `permissionDecisionReason`. Verified 2026-10-16 against code.claude.com/docs/en/hooks and plugins-reference, and end to end on Claude Code 2.1.301 with `--plugin-dir` |
| Claude Code plugin manifest | `.claude-plugin/plugin.json`; `skills/` auto-discovered |
| Path resolution in skill body | relative to skill directory, **both hosts** |
| `project_doc_fallback_filenames` | real, but ambient-instructions only — **not** a skills mechanism |
| Local filesystem | case-insensitive; `lesson.md` resolves as `LESSON.md` |
| Local toolchain | Python 3.11.9, `jq` 1.8.2, no `yq`, cargo/rustc 1.98.0, PyYAML 6.0.3 (installed 2026-09-13, and unused: `yamlite` always parses with its own reader — belay#29) |

---

## 14. Non-goals (v1)

Standalone UI; web/desktop app; hosted backend; any model API client; accounts; cloud
state; marketplace; recommendation ML; embedding search; ratings; payments; a full remote
catalogue service; autonomous coding mode; a workflow engine; a custom DSL.

Remote trust and signing, and bundle updates after a learner has started, are documented
as future concerns, not solved. **Offline caching and catalogue mirrors are now solved**
for catalogues (§7): every catalogue is cached, a failed refresh falls back to its last
successful copy, and the result is reported as cached rather than as current. Nothing
caches a *bundle* that a learner has not chosen.

---

## 15. Open decisions

1. ~~**`automaton-db` has zero commits.**~~ **Settled 2026-09-12.** Committed as one
   initial commit and pushed to its private remote: the Rust source, the tutorial instance,
   and the legacy playbook, with `target/` excluded. `src/lib.rs` is confirmed absent on the
   remote, so the pending refactor is still the learner's to do.
2. ~~**Fate of `TUTORIAL.md` / `TUTORIAL.updated.md`.**~~ **Settled 2026-09-12.** Moved to
   `docs/legacy/` in `automaton-db`, each opening with a header stating that it is
   superseded, that its resume marker is stale, that lesson numbering changed during
   migration, and that `STATE.md` and the source win. Kept for history rather than deleted,
   and out of the repository root where they were its most prominent documents.
3. ~~**Bundle update after a learner has started.**~~ **Settled 2026-09-12: detect and
   report, never apply.** See "Bundle revisions" below.
4. ~~**Multiple concurrent tutorials in one workspace.**~~ **Settled 2026-09-12: one
   workspace, one course.** See "One instance per workspace" below.
5. ~~**Remote repositories.**~~ **Settled 2026-09-12.** All four repositories exist as
   private GitHub repositories and are pushed, except `automaton-db`, whose remote exists
   but is deliberately empty (see decision 1). A `git` catalogue therefore has no real remote to point at
   yet; it is exercised against local repositories over `file://` URLs, which uses the
   same clone, fetch and checkout path.
6. ~~**`belay-bundles` has no `catalog.yaml` of its own.**~~ **Settled 2026-09-12.**
   It has one, generated by `belay-authoring`'s `catalog.py`, which validates its own
   output with `--catalog --portable` before it exits. The repository is installable with
   a single `catalogs.yaml` entry.
7. ~~**Whether an optional lesson ever needs to warn about one failure and be re-offered
   on a different one.**~~ **Settled 2026-09-12: one field, deliberately.** `anticipates`
   keeps both roles. No course has needed them separated, and a second field now would be a
   guess about a case nobody has met — in a contract an LLM reads as requirements, an unused
   field is a field it will eventually use wrongly. The escape hatch, if a course ever asks:
   add an optional `reoffer_on` that defaults to `anticipates`. That is additive, so nothing
   authored against the current format breaks. The motivating case would be a lesson that
   warns about one thing and is best re-offered on a different observable symptom — warning
   about stale reads, re-offering on a flaky suite.
8. ~~**What happens when a `required_for` gate blocks a lesson and the learner refuses the
   lesson anyway.**~~ **Settled 2026-09-12: the tutor teaches the repair inline.** See
   "A `required_for` gate is on the failure" below.
9. ~~**An anticipated failure that persists after its lesson was taken.**~~ **Settled
   2026-09-12: ordinary coaching, permanently.** A complete lesson is never re-offered,
   whatever recurs. A failure that persists is a teaching problem in the moment and is
   handled inside the current lesson. **The loop guard is the feature, not a limitation** —
   a course that may re-open a completed lesson on recurrence has a loop one iteration long
   instead of none, and the learner experiencing it is the one least able to escape it.

   An author whose lesson does not land should fix the lesson. Recurrence is evidence about
   the *lesson*, not about the learner, and the places to act on it are the quality checker
   and the dry-run harness — not the tutor, mid-course, against the person in front of it.

   **Where this is written normatively** (added 2026-09-12, closing issue #3):
   `runner-protocol.md` section 8.8, the first two of the four guards; and
   `state-lifecycle.md` section 9.2, under the `complete` lesson state, which states that
   `complete` is terminal and that nothing later in the course reverses it.
10. ~~**`optional: true` duplicates the manifest.**~~ **Settled 2026-09-12: keep it.** A
    lesson must be readable on its own. The runner opens one lesson file and does not open
    the manifest's optional block to teach it, so without the flag an opened lesson cannot
    say whether it is on the main path — and the tutor frames an optional lesson
    differently from a required one. Consulting a second file to learn what kind of lesson
    is already in hand defeats the loading discipline the whole format exists to protect.

    It is redundancy of the same class as `id` restating the slug, and it is handled the
    same way: **checked, and a disagreement is an error rather than something to reconcile.**
    Neither side wins a merge, because there is no way to know which one the author meant.

    The argument against is real and will be made again: one fact, two places. The answer is
    that the second place is the only one a reader has when it matters.

---

## 15a. A `required_for` gate is on the failure, not on the lesson

**Decided 2026-09-12.** A gate blocks a lesson while an anticipated **failure stands**. It
does not block it until a particular lesson has been taken. The two readings produce
opposite behaviour and the first is correct.

So when a learner has declined the optional lesson and meets the gate, the tutor **addresses
the failure inline** — ordinary coaching inside the current lesson, no transition, no fresh
offer. When the failure clears, the gate opens.

**Why.** The alternative is a dead end whose only exit is taking a lesson the learner has
already refused twice, which contradicts the rule that a course must be completable by a
learner who declines every offer. Teaching the repair inline costs the learner depth — the
optional lesson remains the better route and stays available — but never costs them
progress.

It also keeps `required_for` a real dependency rather than an advisory one. The author's
claim is "this failure genuinely blocks that lesson", and that claim is honoured. What is
not honoured is the stronger claim "only my lesson may fix it", which no author should be
making.

**Where this is written normatively** (added 2026-09-12, closing issue #3): the author's
side is `bundle-format.md` section 2, the `required_for` paragraph and the `required_for`
row of the `optional_lessons` field table, with the worked example in section 12; the
tutor's side is `runner-protocol.md` section 8.7, under *When the learner declines the
gating lesson*. Section 13 of `bundle-format.md` now states that the completability
invariant has **no** exception — an earlier wording called `required_for` "the single
exception", which is the reading this decision rejects.

**A gate on an optional lesson is a quality problem.** An author who writes `required_for`
on an optional lesson has declared something load-bearing and then made it skippable. The
runner copes, but the course would usually be better with that material on the main path.
This is not a validator error — the format permits it and the runner handles it — so it
belongs in a quality checker that scores a bundle rather than in a check that rejects one.
Recorded as a first scoring signal in `belay-authoring`.

---

## 15b. One instance per workspace

**Decided 2026-09-12.** A workspace holds exactly one tutorial instance, at `tutorial/`.
This is a deliberate constraint, not an unexamined default.

**Why.** A course owns the shape of its workspace. It declares `workspace_kind`, which
globs are `learner_owned`, which are `tutor_owned`, what `ownership_policy` applies, and
which validators may run. Two courses in one workspace would disagree on all five, and every
disagreement lands on the same files:

- one course says `src/**` is learner-owned and must never be edited; the other allows
  editing on request
- one runs `cargo test`; the other runs `npm run typecheck` in the same directory
- `tutor_owned` paths collide, because both want `tutorial/STATE.md`

There is no reading of those conflicts that is obviously right, and resolving them would put
policy in the runner that properly belongs to a bundle.

**The cost of the constraint is close to zero.** A learner who wants a second course makes a
second directory. Nothing prevents taking two courses at once; they simply do not share a
workspace. For a course with `workspace_kind: none` — one that builds no software — a
directory is all it ever needed.

**What this rules out**, stated so it is not rediscovered: a short side course taken inside
the same repository as a long one, sharing its code. If that case ever becomes real, the
change is `tutorial/` becoming `tutorials/<id>/` with one marked active, and the hard part
is not the paths but deciding which instance "continue the tutorial" means.

---

## 15c. Bundle revisions reaching a live instance

**Decided 2026-09-12.** A runner detects that the bundle an instance came from has changed,
reports it, and stops. It never reconciles on its own.

**Why detection has to come first.** Until 2026-10-14 the instance stamp recorded where an
instance came from but not *which version*:

```yaml
instance:
  materialized_from: local:../belay-bundles/rust-automaton-db
  materialized_at: 2026-09-11
```

So a runner could not tell that an update existed at all.

**Superseded 2026-09-19, and the original proposal was wrong.** This entry first proposed
stamping a revision and a content hash:

```yaml
  source_revision: 76dcdce          # a commit for a git source; absent for a local path
  content_hash: sha256:...          # over the bundle's files, so a local source works too
```

Neither answers the question this entry exists to make answerable. **"Is this instance
behind its bundle?" is an ordering question.** Two shas do not order, and a content hash
says only *different*, never *behind*. A sha is also noisy in a way a course does not care
about: editing the README of a bundles repository changes it while nothing about the course
changed.

The replacement is an ordered version the author sets, `version: "MAJOR.MINOR"` in
`tutorial.yaml`, stamped into the instance as `materialized_version`. belay#51 carries
the field and its semantics; the two parts compare **as integers**, so 2.10 is later than
2.9 and a float parse is wrong. Nothing else in this entry changes: detection still comes
first, and the runner still never reconciles on its own.

**Shipped 2026-10-14 (belay#51), in this shape:**

- **The value is a quoted string**, `version: "2.1"` and `materialized_version: "2.1"`.
  The issue first wrote it unquoted. Measured on 2026-10-14, both `yamlite` and PyYAML
  6.0.2 read `version: 2.10` and `version: 2.1` as the same float 2.1, so the unquoted
  form loses the digit before any comparison runs — the 2.10-against-2.9 trap one layer
  earlier. Neither part may have a leading zero: `"02.1"` would compare equal to `"2.1"`.
- **REQUIRED in the contract, optional in the validator.** `bundle-format.md` section 2
  requires it of every new bundle; validator check 30 reads an absent `version` as `"1.0"`
  and stays quiet, so every bundle published before the field stays valid. Check 30 refuses
  any other string and any number, and reports the value it read in the header of both
  modes. In instance mode it checks `materialized_version` with the same rule and is quiet
  when the stamp has none.
- **MINOR means a live instance can take the change as one set, accepted with one answer;
  MAJOR means the learner reviews it file by file.** Either way the learner asks for the
  update first (belay#50, below). The table is in `bundle-format.md` section 2,
  **Content version**. A MAJOR bump resets MINOR to `0`. *Corrected 2026-10-14: this bullet
  and that table first said MINOR is accepted "without review" and MAJOR "stops and asks",
  which read as an update that applies by itself. That contradicts the rule this entry
  keeps.*
- **The materialization step writes it** (`state-lifecycle.md` section 3 step 5): the
  bundle's `version`, or `"1.0"` when the bundle declares none. An instance is behind its
  bundle when the bundle's `version` is greater than `materialized_version`, compared as
  integer pairs.
- **What it does not do.** The validator sees one bundle and cannot check that a version
  increases. That belongs where two versions are visible at once, in the authoring toolkit
  and the catalogue generator (belay-authoring#24, belay-authoring#25). The two values are
  read side by side by a resume and by the update operation (belay#50, below).

**Why it must not apply automatically.** `DESIGN.md` and `lessons/` are not purely bundle
content once materialized. The tutor appends durable decisions to `DESIGN.md` as the learner
makes them, and generated lessons accumulate beside the authored ones. An overwrite destroys
the learner's own design history — the record of what *they* decided — which no upstream
revision can reconstruct.

**What a resume does.** Name what changed and stop. The instance is behind when the bundle's
`version` is greater than the stamp's `materialized_version`, compared as integer pairs:

> This course was revised upstream since you started. Two lessons you have not reached
> changed (`04`, `07`), and `DESIGN.md` gained a section. Your `DESIGN.md` has three local
> additions. Update, review the differences, or carry on unchanged?

*As shipped (belay#50, below), a resume reads only the source's version. It says one
sentence and teaching continues. The per-file account in this example is what the update's
plan gives once the learner asks for it.*

**What is out of scope for now.** *Superseded 2026-10-14 by belay#50, below.* The three-way
merge — silently updating unreached lessons, leaving completed ones alone, preserving local
`DESIGN.md` additions while appending upstream ones. That is the correct end state and
considerably more to build and test. Detection is what has to exist before any policy can be
chosen, and reporting is useful on its own.

**Shipped 2026-10-14 (belay#50): the learner-started update.** Not a three-way merge, and
nothing silent. The rule above stands: the runner reports and never applies.

- **Detection on resume** (`runner-protocol.md` section 1, **A resume may say the course
  has moved on**). Once per session, a resume MAY read the `version` of the source's
  `tutorial.yaml`, and nothing else. It does this only for a `local:` source, so no host is
  contacted. It says one sentence when the instance is behind, and says nothing when the
  source cannot be read. This is the one read of the source outside materialization and
  update, and `state-lifecycle.md` section 3 step 2 says so beside "teaching never reaches
  back".
- **The update** (`state-lifecycle.md` section 3.2). It starts only when the learner asks.
  `scripts/plan_update.py` reads the instance and the bundle, writes nothing, and classifies
  every file that materialization copies. A file in a lesson not started is replaced. A
  differing file in a completed, active or unrecorded lesson, and a differing `DESIGN.md`,
  get the learner's own answer. Added and removed files move with the manifest. The script
  refuses when `active_lesson`, `resume_at`, or a generated lesson's `after:` would name a
  lesson the new bundle lacks. The tutor shows the plan, the learner answers, and the tutor
  copies, rewrites the stamp, re-validates (3.1), and places new supplies (step 8).
  `STATE.md` keeps the learner's progress unchanged.
- **Which version the instance claims.** An update rewrites both the instance's own
  `version`, by copying the new `tutorial.yaml`, and the stamp's `materialized_version`.
  After an update the two match, and check 30 now reports a finding when they differ.
- **The limit, stated rather than hidden:** the instance keeps no copy of the bundle as it
  was at materialization, so there is no common ancestor. A differing file is reported as
  different. The plan cannot say which side changed it.
- **"Started" comes from the existing records.** `status`, then the position of
  `active_lesson`, or of `resume_at` during a detour, in `lessons`. An optional lesson that
  is not active cannot be placed by those records, so a change to it goes to the learner.
  The rule is written once, in section 3.2.

**Implementation note.** The stamp and the update are defined in `state-lifecycle.md`
(section 3 step 5, section 3.2), and the resume-time detection is in `runner-protocol.md`
section 1.

---

## 15d. The `SKILL.md` size limit, and how it is measured

**Decided 2026-09-12.** `SKILL.md` has a word limit, and the limit is meaningless without
the command that checks it. Both are fixed here.

### The method

```
wc -w skills/belay/SKILL.md
```

**The whole file, frontmatter and tables included. One command, no script, no exclusions.**

This is the whole of the rule, and the reason is that the alternatives cannot be reproduced.
Measured at `a5e8b5a`, the same file gives three different answers:

| Method | Words at `a5e8b5a` |
|---|---|
| `wc -w` on the whole file | **2841** |
| body only, frontmatter dropped | 2711 |
| prose only — body, less table rows and fenced code | 2360 |

The third is the one an earlier session used, and it is why issue #7 exists. It is a
defensible measure of reading effort and it is not reproducible without shipping the script
that computes it, so nobody could check the limit and nobody did. A limit that needs a
private script is not a limit. The frontmatter and the tables are loaded into the host's
context like everything else, so counting them is also the more honest measure of the cost
the limit exists to control.

### The correction

**The previously stated ceiling of "about 2100 words" was never a measurement of this
file.** By no method did the file ever hold about 2100 words. Before the work that prompted
issue #7 it held 2542 by `wc -w`, 2412 as body, and 2084 as prose — and 2084 is a *floor*
that was already reached, not a ceiling with room in it. The figure was wrong when it was
written; it did not drift.

### The limit

> **`SKILL.md` MUST NOT exceed 3,000 words by `wc -w`.**

At the time of writing it holds **2,744**, which is 256 words of headroom — reached by
compressing two passages that restated a reference file the surrounding text had already
told the tutor to load (`catalogue-format.md` sections 6, 7 and 9; `runner-protocol.md`
sections 11 and 12). Nothing normative was removed, and no rule now lives only in the
compressed text.

**When the limit binds, move a section into a reference rather than raising the number.**
`SKILL.md` is the control plane: a host loads it every time the skill fires, whatever the
learner asked for. The references load on demand, so a word moved out of `SKILL.md` and
into one of them costs nothing until it is needed.

**The one thing that may not be moved is a load condition.** A reference is only reachable
if `SKILL.md` names the circumstance that reaches it. Delete the sentence that says a course
may declare `assumes`, and the row in *Reference files, and when to load each* that fires on
`assumes` can never fire. So a section may be compressed to its trigger and its pointer; it
may not be removed.

---

## 15e. Ownership, resolved by one function and guarded where a host can

Decided 2026-10-16, for belay#32. `runner-protocol.md` section 5 stays the rule on every
host. Underneath it:

- **One resolver.** `scripts/ownership.py` resolves a workspace path and an operation
  (create or modify) against the manifest to an owner (tutor, learner, read-only,
  supplies target, outside), a verdict (allow, refuse, needs-learner-request) and the rule
  that decided it. Precedence: outside the workspace; `tutorial/lessons/**` read-only;
  `tutorial/lessons.generated/**` and `tutorial/EVENTS.jsonl` tutor-owned; the rest of
  `tutorial/` is the instance and the tutor's; a declared supplies target (create allowed,
  modify refused, under every policy); `tutor_owned`; `learner_owned`; unlisted is the
  learner's. No second path list: the manifest is the only source.
- **The rest of `tutorial/` is not the learner's.** Read literally, "unlisted is the
  learner's" made `tutorial/tutorial.yaml` learner-owned, and a guard built on that would
  deny the validation record that `state-lifecycle.md` section 3.1 writes into the stamp
  after the stamp exists. `bundle-format.md` already says `tutorial/` is not the learner's
  workspace; section 5 now says so too.
- **The glob dialect** is in `bundle-format.md` section 2: anchored, `*` and `?` within a
  segment, `**` only as a whole segment, dotfiles ordinary, case-sensitive, `..` never
  escapes. All 123 globs in the published bundles and fixtures parsed under it on the day,
  and none changed meaning in effect: the root-only `*.py` style in two bundles matches
  less than an author might guess, but an unmatched path is the learner's anyway.
- **Directory supplies** resolve by listing the source: the instance's `lessons/` copy
  for a lesson-scope entry, the bundle the stamp's `local:` source names otherwise. When
  neither can be listed, no path under the entry counts as a target, so a create there is
  judged by the manifest and may be refused. That matches the protocol: a manifest-scope
  entry cannot be placed once its source is out of reach.
- **The Claude Code guard** is a PreToolUse hook on `Write|Edit|MultiEdit|NotebookEdit`.
  Silent unless the workspace holds a stamped instance; fails open on any error. A
  refused write is denied; a learner-owned write under `on-request` asks, because the
  learner's request is in the conversation the hook cannot read and the host's prompt is
  where the learner gives it; `unrestricted` and tutor-owned get no decision.
  `tutorial/lessons/**` **asks rather than denies**, because the one legitimate write
  there is an update the learner asked for (`state-lifecycle.md` section 3.2). A create
  whose content is byte-identical to a file under `tutorial/lessons/` gets no decision,
  because section 10.1's fallback may permit it and only the tutor can judge the lesson
  prose. Shell writes are not intercepted, and no attempt is made.
- **Not enforced by any host:** keeping the tutor active, one actionable step per turn,
  and every rule about what the tutor says. `tests/conformance/ownership-scenarios.md`
  writes them as scenarios for the dry-run harness.

## 15f. Which instance files a learner commits

Decided 2026-10-18, for belay#35, replacing the 2026-10-16 answer. `state-lifecycle.md`
section 3.3 is normative.

- **One learner per repository.** A course repository is never shared by two learners. The
  learner builds software in it, which is an individual task, so where their progress is
  kept is theirs to choose (the owner's reasoning, 2026-10-18).
- **Course material is always ordinary committed content:** `tutorial.yaml`, `COURSE.md`,
  `DESIGN.md`, `lessons/**`, `lessons.generated/**`.
- **Progress is asked, once.** At materialization, after validation, the tutor asks one
  question with two options (`AskUserQuestion` in Claude Code, plain text elsewhere):
  *remote*, where `STATE.md` and `EVENTS.jsonl` are committed with the learner's work and
  pushed, so progress follows them to another machine, or *local*, where they stay on this
  machine. The tutor never decides alone. A resume with no recorded choice asks the same
  question once.
- **Local is the checkout's exclude file, never `.gitignore`.** The path comes from
  `git rev-parse --git-path info/exclude`, so a linked worktree and a submodule resolve
  correctly. The choice is recorded there, not in the `instance:` stamp: `tutorial.yaml` is
  committed, so a stamp key would reach every clone. Remote records one marker line, so
  it is not asked again. `scripts/instance_git.py` applies both.
- **Rejected: a default without asking,** in either direction. Local by default (the
  2026-10-16 answer) and remote by default each decide for the learner something that is
  theirs, and one question costs less than being wrong.
- **The tutor never stages, commits or pushes.** A workspace that is not a git repository
  gets one sentence and no question.
- **A generated lesson's `reason` stays free of quotes and personal detail,** because the
  repository may be pushed to a public remote and the `reason` is read by a bundle author
  (`state-lifecycle.md` section 8.2).
- **A missing `STATE.md`** in a stamped instance means the learner chose local and opened
  another checkout, never committed it, or deleted it. It is reported as a structural
  defect, not repaired.

---

## 16. Deferred: telemetry feedback

Generated lessons are the course's only quality signal from real use. A later version
should be able to emit them, **optionally and opt-in**, to a webhook so a course author
sees where learners actually stall.

Not built, and no backend exists. Recorded because one decision has to be made now and is
expensive to retrofit.

**Nothing needs to be built to start collecting.** Generated lessons are already files on
disk in each learner's workspace, with structured provenance. The signal accrues whether
or not anything transmits it, so a webhook added later works against accumulated history
rather than starting from zero. Collect locally, transmit later.

**The decision to make now: separate the signal from the content.** A generated lesson's
`reason` field, and its body, can contain the learner's code, their misunderstanding, and
the shape of the system they are building. Transmitting that is a disclosure, and a course
author usually does not need it. The two layers:

| Layer | Example | Sensitivity |
|---|---|---|
| **Signal** | `after: lessons/03-first-refactor.md`, `kind: side-lesson`, `id`, `generated_at` | low — no learner content |
| **Content** | `reason` prose, the lesson body, any material | high — learner code and context |

The provenance frontmatter already isolates the signal layer, which is what makes an
"anonymous signal only" opt-in cheap later. Keep it that way: **do not move learner context
into a frontmatter field**, and do not add frontmatter that quotes learner code. If
`reason` needs to stay human-readable, that is fine — it simply belongs to the content
layer and is not transmitted by default.

Other signals worth emitting eventually: which lesson a learner stalls on, repeated
validation failures per lesson, elapsed time per lesson, and the lesson at which a course
is abandoned. Abandonment is probably the single most valuable number.

**Amended 2026-10-16 (belay#34).** These were first described as "already present or
derivable in `STATE.md`". They were not: a repeated failure left no trace once the task
passed, and an abandoned course looked like one in progress. They are now collected
locally, in the learning record `tutorial/EVENTS.jsonl` (`state-lifecycle.md` section 12;
design in `2026-10-16-learning-evidence-design.md`). It holds only this table's signal
layer — concept ids, validator names, lesson paths, enumerated outcomes, counts and dates,
never learner content — and it is evidence only: `STATE.md` stays the authority for
progress. Abandonment is still not an event; it is derived from the last event's date and
`STATE.md`. Transmitting any of it stays unbuilt, and the open questions below are
unchanged.

Open questions, none urgent: consent and its revocation; whether an instance carries a
stable anonymous id or is unlinkable between reports; whether a self-hosted receiver is
supported; and what happens when transmission fails (it must never block a lesson).

---

## 17. Known issue: Codex plugin distribution

Claude Code installs cleanly from the GitHub repo: `claude plugin marketplace add
skomp/belay` then `claude plugin install belay@belay`. Measured cost, ~255 tokens
always-on and ~3.5k on invoke — the four reference documents are ~11k words and cost
nothing until loaded, which is the progressive-disclosure design paying off.

Codex is installed via `~/.agents/skills/belay`, its documented user scope, verified by
rendering the model-visible prompt and confirming the skill is injected. The plugin route
does not work, for two reasons found by probing:

- **A marketplace entry whose `source.path` is the marketplace root is silently ignored.**
  `"./"`, `"."`, `""` and `"./."` all register the marketplace and then enumerate zero
  plugins, with no error. A probe marketplace in the subdirectory shape lists correctly, so
  the root path is the cause, not the manifest.
- **A subdirectory plugin whose `skills/` is a symlink to the shared directory installs
  nothing.** `codex plugin add` reports success; only `.codex-plugin/` is copied into the
  cache, and the installed plugin contains no skill at all. A false success.

Resolving it means either duplicating `skills/` into a Codex subdirectory with a sync step,
or publishing through a marketplace that hosts the plugin as a subdirectory of its own
repository — which is what superpowers does. Neither is warranted for v1, and the skills
directory works today.

The structural conflict is worth recording: Claude Code wants the plugin at the repository
root and accepts `source: "./"`; Codex's marketplace requires it in a subdirectory with
real files. One repository cannot satisfy both without duplication.

---

## 18. Implementation status

| Deliverable | State |
|---|---|
| Bundle format contract (`references/bundle-format.md`) | **done** |
| Design spec (this document) | **done** |
| `belay-bundles` repository | **done** — holds five bundles and its own `catalog.yaml` |
| `rust-automaton-db` bundle | **done** — imported, corrected, verified |
| `automaton-db/tutorial/` instance + `STATE.md` | **done** — committed 2026-09-12 (§15, decision 1) |
| Validator (`skills/belay/scripts/validate_bundle.py`) | **done** — 33 bundle checks + 7 catalogue checks |
| Validator test suite | **done** — 846 assertions on a clean checkout, the same on any machine; every check proven firing or warning. `BELAY_SWEEP_SIBLING_REPOS=1` adds the published bundles, counted separately (belay#37) |
| Optional lessons (`optional_lessons`, `failure_modes`) | **done** — 2026-09-12, §6; checks 18-21 |
| First-load banner + `teaching_method` | **done** — 2026-09-13, released in 0.6.0; `state-lifecycle.md` §3 step 7, check 27; belay#23 |
| Offer / defer / re-offer behaviour | **untested** — no harness exercises it; belay#22 |
| Knowledge assessments (`assesses`, `## Assessments`, `kind: practice`) | **done** — 2026-10-16, belay#33; `runner-protocol.md` §15, `state-lifecycle.md` §11, checks 31-32. The question-and-answer loop is untested, as above |
| Learning-evidence record (`tutorial/EVENTS.jsonl`, `skills/belay/scripts/evidence.py`) | **done** — 2026-10-16, belay#34; `state-lifecycle.md` §12, `runner-protocol.md` §16, check 33 (warning only); `tests/test_evidence.py`, 65 assertions. Whether the tutor writes the events in conversation is untested, as above |
| Ownership resolution and the Claude Code guard (`skills/belay/scripts/ownership.py`, `ownership_guard.py`, `hooks/hooks.json`) | **done** — 2026-10-16, belay#32, §15e; `tests/test_ownership.py`. Conformance scenarios for what no host enforces are written in `tests/conformance/ownership-scenarios.md` and run by nothing yet: belay-authoring#5 |
| Version-control policy for instance files (`skills/belay/scripts/instance_git.py`) | **done** — 2026-10-18, belay#35, §15f; `state-lifecycle.md` §3.3; `tests/test_instance_git.py` |
| Multi-catalogue support (`skills/belay/scripts/catalogs.py`) | **done** — 2026-09-12, §7 |
| Catalogue test suite (`tests/test_catalogs.py`) | **done** — 338 assertions; every failure kind proven firing |
| Instance update (`skills/belay/scripts/plan_update.py`, `state-lifecycle.md` §3.2) | **done** — 2026-10-14, belay#50, §15c; `tests/test_plan_update.py`, 67 assertions |
| Shared YAML reader (`skills/belay/scripts/yamlite.py`) | **done** — the only reader; the PyYAML preference was removed 2026-09-13, belay#29 |
| `catalog.yaml` inside `belay-bundles` | **done** — 2026-09-12, §15 item 6; generated by `belay-authoring`'s `catalog.py` |
| `SKILL.md` (the runner control plane) | **done** |
| `references/catalogue-format.md` | **done** |
| `references/runner-protocol.md` | **done** |
| `references/state-lifecycle.md` | **done** |
| `catalog/builtin.yaml` | **done** |
| `examples/rust-cli-basics/` example bundle | **done** |
| `.claude-plugin/` + `.codex-plugin/` manifests | **done** |
| `README.md` | **done** |
