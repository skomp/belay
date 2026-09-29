# Bundle Relationships and Concept-Based Prerequisites — Design

**Date:** 2026-09-12
**Last amended:** 2026-09-29
**Status:** Approved, not started. **Blocked on the `supplies` branch merging.**
**Repository:** `belay`

---

## 0. The central rule

> **Named bundles are recommendations. Concepts are the educational contract.
> Neither one gates access to a tutorial or requires proof that another bundle was
> completed.**

Every decision below serves that sentence. A reader who keeps only one line should keep
this one.

---

## 1. Why this is blocked, and on what

Seven of the file groups this feature needs are held by the live `supplies` branch:

```
skills/belay/references/bundle-format.md      skills/belay/SKILL.md
skills/belay/references/runner-protocol.md    skills/belay/scripts/validate_bundle.py
skills/belay/references/state-lifecycle.md    tests/test_validate_bundle.py
the three plugin manifests
```

Free: `references/catalogue-format.md`, `scripts/catalogs.py`, `tests/test_catalogs.py`,
`skills/belay/examples/`.

**Merge `supplies` first, then build on the merged main.** Both features edit the same
normative documents, and a conflict resolved inside a contract is the worst place to
resolve one: a contract that silently reads two ways is the defect class this project
spends most of its effort eliminating.

---

## 2. Measured before starting — do not re-derive

| Fact | Value |
|---|---|
| Restricted YAML reader handles `covers`/`assumes`/recommendation shapes | **yes**, verified by parsing all four fields with `yamlite.load_yaml` |
| Nesting precedent in the manifest | `validators`, `optional_lessons` and `failure_modes` already nest map→map→list, so the "at most one level of nesting" claim in the runner spec was outdated. **Corrected**: the ceiling is three levels of container with scalars at the leaves — runner spec §4 and `bundle-format.md` section 2 |
| Highest validator check number on main | 21; `supplies` adds 22, so **this feature starts at 23** |
| `supplies` branch state at inspection | green, 292 assertions, all three real bundles valid, zero file overlap with main's then-HEAD |

---

## 3. Manifest fields

Four optional fields. Existing manifests stay valid unchanged.

```yaml
covers:
  retained-event-logs:
    summary: Records remain available and can be replayed from logical offsets.
    aliases: [append-only-log, replayable-log]

assumes:
  go-programming:
    level: working          # awareness | conceptual | working | advanced
    summary: >
      Write, test, and refactor ordinary Go programs using packages, goroutines,
      channels, errors, and contexts.

recommended_follow_ups:
  - bundle: distributed-log-broker
    because: >
      Extend the broker with multi-node placement, replication, acknowledgement
      policies, and failure recovery.

recommended_previous_bundles:
  - bundle: durable-event-broker
    because: >
      It teaches the retained-log, topic-partition, and offset model used here.
```

### Concept identifiers

`[a-z0-9-]+`. Stable once published. Name a technical concept, never a lesson filename.
Usable across independently authored bundles. **No central registry.**

### `covers`

What the bundle actually teaches. `summary` required; `aliases` optional.

Machine-readable discovery metadata, more precise than `subjects`, which keeps its current
meaning for broad classification. A `covers` concept should also appear recognisably in
`COURSE.md`'s coverage list; validation may warn conservatively but must not attempt
unreliable semantic proof. Not every minor topic belongs here — only concepts meaningful
for discovery and prerequisite matching.

### `assumes`

What the course uses without teaching from first principles. `level` and `summary` both
required; the summary is written for a prospective learner and must be specific enough for
self-assessment.

| Level | Means |
|---|---|
| `awareness` | recognise the concept and its purpose |
| `conceptual` | explain the model and major consequences |
| `working` | apply it in ordinary implementation or diagnosis |
| `advanced` | reason about difficult edge cases and trade-offs without introduction |

**`assumes` is never an access-control or completion gate.** A concept may appear in both
`covers` and `assumes` when a course assumes a baseline then teaches it deeper; that
overlap is legal.

### Recommendations

`bundle` and `because` both required. Advisory only — never implying ownership, purchase,
installation, or completion. A reference may be unresolved, and an unresolved reference
does not invalidate the declaring bundle. Duplicate bundle ids within one list are invalid;
self-recommendation is invalid. Reciprocity is neither required nor warned about. **Author
order is display order.**

`recommended_previous_bundles` is what lets a third party attach itself to an earlier
bundle **without modifying it**.

---

## 4. Discovery

Index: bundle id and title, `subjects`, bundle-level `aliases`, `covers` ids, per-concept
aliases, `covers` summaries, `assumes` ids and summaries, and both recommendation lists.

Ranking:

1. exact `covers` concept-id match
2. exact per-concept alias match
3. normalised textual match against id, alias, or summary
4. explicit recommended previous bundle **that covers the concept** — see the rule below
5. broader `subjects` or bundle-alias match
6. semantic match, only if the architecture already has it

> ### Rank 4 is a join of two declarations, and both halves are required
>
> **Rule R4, stated so that no summary of it can drop a clause:**
>
> > Bundle **P** qualifies at rank 4 for concept **C** only when **both** of these hold:
> >
> > 1. some bundle **Q** names **P** in its `recommended_previous_bundles`; **and**
> > 2. **P itself declares C in its own `covers`.**
> >
> > Condition 2 is not optional, not an optimisation, and not implied by condition 1.
> > Without it, rank 4 answers a `covers` query with a bundle that merely **assumes** C.
>
> **The route is for finding a teacher no other rank reaches.** Rank 4 exists because the
> learner may be searching in **Q's** wording — Q's `assumes` summary is where they read the
> concept's name — while the bundle that actually **teaches** it is P, whose own wording
> they never saw. Following Q's recommendation back to P is the only way to reach P from
> that query. Narrowing rank 4 to bundles that cover C keeps that route open and removes
> nothing from it.
>
> **Rank 4 is not an author recommendation for a `covers` query.** Neither author wrote the
> conjunction: Q's author recommended P, and P's author declared what P covers. Print P's
> `because` and attribute it to Q, but do not label the *match* as an author recommendation
> — the match is the runner's inference from two independent declarations.
>
> **Why this is written at this length.** Two sessions dropped the final clause of rank 4
> and shipped a real defect, fixed in commit `9e03c2c`: a `covers` query for `go-programming`
> returned `durable-event-broker`, which assumes Go at level `working` and teaches none of
> it, tagged as an author recommendation. A learner who could not write Go was sent to a
> course that assumes working Go — the first entry on `catalogue-format.md`'s own refusal
> list. The predicate is the one `prepare_for` already uses, so the two commands agree by
> construction rather than by coincidence; their disagreement is what found the defect.
>
> **Tier 4 is narrowed, not disabled**, and a test pins that: it proves the tier still finds
> a teacher no other tier reaches when the query matches the assuming author's wording.
> Sabotaging tier 4 to make a filter simpler fails that test.

**No semantic-search service may be required.** Exact identifiers and aliases work
deterministically.

Every result explains why it matched — `Exact concept match: partition-offsets`,
`Alias match: stream-offsets`, `Recommended by streaming-query-engine`,
`Related subject: event-streaming`.

**A query for bundles *covering* a concept searches `covers`, never `assumes`.** This
applies to every rank without exception, rank 4 included: `assumes` is read to find *who
needs* a concept, never to answer *who teaches* it. Return multiple suitable bundles; never
collapse to the single one named in `recommended_previous_bundles`.

### Provenance is preserved, always

Follow-ups for bundle A combine A's explicit `recommended_follow_ups`, available bundles
naming A in `recommended_previous_bundles`, and conceptually related bundles. Each result
keeps which of those it is. **Inferred matches are never presented as author
recommendations.** Duplicates merge without losing any provenance.

---

## 5. Runner: before the first task

If `assumes` is non-empty, present it before the first implementation task — compact,
grouped by level, and clear that these are assumed concepts rather than proof requirements.

The learner may continue immediately, ask about one concept, or ask for bundles covering
one or more assumed concepts; after either digression the pending course start is resumed.

**Never** ask whether another bundle was completed. **Never** inspect licences, completion
state, or prior course state to decide whether the learner may continue. **Never** start
teaching prerequisites unsolicited. **Never** show the review again after acknowledgement.

Record the acknowledgement with the smallest compatible extension to existing instance
state — a dedicated field or a canonical entry in an existing section — but unambiguous and
testable. Continuing acknowledges only the wish to proceed. It asserts no mastery and marks
no other bundle complete.

---

## 6. Runner: at completion

Candidates are the completed bundle's `recommended_follow_ups` first, in manifest order,
then available bundles naming it in `recommended_previous_bundles`. Deduplicate while
keeping all provenance. Show `because` text.

**Never** auto-start, install, purchase, or materialise anything. Never imply the learner
must continue. An unavailable forward-declared bundle must not fail course completion.
Conceptually inferred relatives go behind a separate "find more" action, never mixed
silently into the author-curated list.

Follow-ups can be asked for at any time, not only at completion.

---

## 7. Starting a recommended follow-up

Exactly like starting any other bundle. No completion proof, no earlier instance, no earlier
licence or installation. `assumes` is displayed and the learner decides.

Baseline source code is the **existing workspace/template contract's** job, never inferred
from recommendation metadata. `recommended_previous_bundles` says only *this is a good
course to take earlier* — never *copy that course's workspace into this one*. Recommendation
metadata must never overwrite or mutate an existing project.

**No `requires_completion`, `requires_bundle`, or equivalent gating field is introduced.**

If the format cannot express the baseline-versus-existing-project choice, report that
separately rather than overloading recommendation metadata to solve it.

---

## 8. Validation

**Reject:** invalid concept ids; missing or empty concept summaries; invalid
`assumes.level`; non-list `aliases`; empty aliases; duplicate aliases within one concept
after normalisation; duplicate bundle ids within one recommendation list; missing or empty
`because`; invalid referenced bundle ids; self-recommendation; malformed shapes.

**Allow:** missing or empty new fields; the same concept in both `covers` and `assumes`;
unresolved bundle ids; one-way recommendations; two bundles covering one concept;
overlapping aliases across authors.

**Warn, never reject:** an alias colliding with another concept id in the same bundle; a
`covers` concept with no obvious corresponding phrase in `COURSE.md`, if checkable
conservatively.

**Not the validator's warning at all: an unavailable recommended bundle.** An earlier
draft of this section listed it here, and that was wrong.

Availability is not a property of a bundle. It is a property of one learner's
configuration — the same bundle is complete for someone whose catalogues carry the target
and incomplete for someone whose do not. A validator reads one bundle and no catalogue, so
it would be asserting something it cannot know, and it would fail a correctly authored
bundle for a reason its author cannot fix. That is the independent-distribution rule in
§3 turned inside out.

It belongs where the catalogues are, and `catalogs.py` already reports it there, in the
right register:

> `unresolved: durable-event-broker recommends 'distributed-log-broker' under
> recommended_follow_ups, and no configured catalogue carries it. Say so; it is a pointer,
> not a requirement.`

The validator's own limitations text states the complement, so the two cannot drift:
**an unresolved bundle id is correct and is never reported.**

Cross-catalogue validation may report contradictory or malformed available targets but
**must never fail an otherwise valid independently distributed bundle because another
bundle is missing.**

---

## 9. Backward compatibility

Existing bundles, manifests, `subjects`, bundle-level `aliases`, `COURSE.md` coverage lists,
optional lessons, failure modes and instance state all keep their exact current behaviour.
Older runners ignore the new fields and still execute the tutorial.

Keep `bundle_format: 1` if the versioning policy treats additive optional metadata and state
as backward-compatible. If a version change is required, migrate deliberately and document
it.

---

## 10. Normative example

Three bundles, as manifest excerpts in `bundle-format.md` and as minimal fixtures in
`tests/`. **Not** three full materialisable bundles in `examples/` — that would bloat every
plugin install for a documentation example.

- **`durable-event-broker`** covers at least `retained-event-logs`, `partition-offsets`,
  `topic-partitions`, `group-commit`; recommends `distributed-log-broker` and
  `streaming-query-engine`.
- **`streaming-query-engine`** names `durable-event-broker` as a previous bundle; assumes at
  least `go-programming`, `retained-event-logs`, `partition-offsets`, `topic-partitions`,
  `consumer-offsets`; covers at least `stream-query-parsing`, `bounded-stream-queries`,
  `continuous-stream-queries`, `windowed-aggregation`.
- **A fictional third-party bundle** naming `durable-event-broker` under
  `recommended_previous_bundles` although the broker does not name it. Follow-up discovery
  must still find it **through the reverse index** — this is the case the whole open-ended
  design exists for.

---

## 11. Out of scope — do not build

Completion gating; dependency resolution; package-manager semantics; automatic installation
or purchase; copying a previous learner's workspace from relationship metadata; a central
concept registry; replacing `subjects` with `covers`; treating broad subject similarity as
an author recommendation; inferring a learner lacks knowledge because no completion is
recorded; an unrelated recommendation engine; any change to optional-lesson or
anticipated-failure semantics.

---

## 12. Deliverables

Updated: bundle-format specification, runner-protocol and state-lifecycle documentation,
manifest parser and types, validator, catalogue index and query behaviour, runner start and
completion behaviour, examples, tests. Plus test results, a design summary, and the complete
diff.

Before finishing, grep the implementation and documentation for `covers`, `assumes`,
`recommended_follow_ups` and `recommended_previous_bundles`, and confirm where each is
parsed, validated, indexed, documented and exercised by tests. List any renamed field with
its exact replacement and rationale.

---

## 13. Where the validation lists are — a correction

**Added 2026-09-12.** This specification has never had a section 13. It ended at section
12, and two dispatch prompts nevertheless cited "section 13" as the home of the
reject / allow / warn lists. An agent following either one found nothing, which is the
worst outcome a cross-reference can produce: it reads as authoritative and resolves to
silence.

**The lists are in section 8, "Validation".** There are three of them and they are
different instruments:

| List | Section 8 heading | Effect on the bundle |
|---|---|---|
| what the validator rejects | **Reject** | a finding; exit code 1; the bundle is invalid |
| what it accepts in silence | **Allow** | nothing reported; these shapes are correct, not tolerated |
| what it reports without rejecting | **Warn, never reject** | a warning; the exit code cannot see it; the bundle stays valid |

Section 8's closing paragraph carries the rule that outranks all three: cross-catalogue
validation **must never fail an otherwise valid independently distributed bundle because
another bundle is missing.**

This section exists so that a reader arriving at "section 13" lands on a correct pointer
rather than off the end of the document. Cite **section 8** in anything written from here
on.
