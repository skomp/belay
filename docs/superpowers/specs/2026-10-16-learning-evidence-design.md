# The learning-evidence record — Design

**Date:** 2026-10-16
**Last amended:** 2026-10-18
**Status:** implemented — `state-lifecycle.md` §12 (format), `runner-protocol.md` §16 (when
to write and read), `scripts/evidence.py`, validator check 33, `tests/test_evidence.py`
**Issue:** belay#34

---

## 1. The problem

`STATE.md` records outcomes, not attempts. A check that failed four times and then passed
leaves the same trace as one that passed first time; a hint leaves none; a course
abandoned at lesson 6 looks like a course in progress at lesson 6. The runner design
spec's §16 called those signals "already present or derivable in `STATE.md`". They were
not. Writing them into `STATE.md` would make the file the tutor reads every turn into a
transcript, which the assessments design already refused (§5.1, §5.2 there).

## 2. Decisions

### 2.1 Representation: `tutorial/EVENTS.jsonl`, evidence only

One JSON object per line, appended between compactions. **`STATE.md` stays the only
authority for progress**; nothing in the teaching loop decides anything from the record
that `STATE.md` does not also say. `state-lifecycle.md` states this next to its opening
rule, so the two sentences do not read as a contradiction, and §7 there says the record is
never a source for repairing `STATE.md`. The assessments design's §5.2 ("no second file")
stands for the same reason: §4.4's escalation still reads the *Assessments* row.

The file is tutor-owned in every instance, like `lessons.generated/`, settled by the
runner rather than the manifest. Materialization does not create it; the first event does.
An update never touches it, and `plan_update.py` reports it as kept.

### 2.2 A closed field set

Every event has `seq` (integer, strictly increasing), `date` (calendar date, no clock
time), `lesson` (lesson path) and `type`. The type decides the rest:

| `type` | Further fields |
|---|---|
| `lesson_started`, `lesson_completed` | none |
| `check` | `validator`, `result` (`pass`, `fail`) |
| `hint` | `rung` (1 to 5) |
| `answer` | `concept`, `outcome` (the four of the assessments design §3.1), optional `requested` |
| `assessment` | `state` (the four of §5.1 there), `attempt`, `not_demonstrated`, optional `requested` |
| `practice_offered` | `concepts` |
| `practice_accepted` | `concepts`, `practice_lesson` |
| `summary` | counts, written only by compaction (§2.4) |

No field holds free text. Every value is a concept id, a validator name, a lesson path, an
enumerated value, an integer or a date, and none of their shapes admits a space, so the
content layer of the runner spec's §16 cannot be written in. `scripts/evidence.py` holds
the definition; check 33 and the script read with the same code, and a test asserts that
the table in `state-lifecycle.md` §12.2 lists exactly the types and fields the code
accepts.

`requested: true` marks a quiz the learner asked for. Its scope in words stays in
`STATE.md`'s `_scope:_` row, because a scope like "the course so far" is free text. A
validator that could not run writes no `check` event: it was not an attempt.

### 2.3 Abandonment is derived, never written

Nobody writes "I quit". Abandonment is the date of the last event together with
`STATE.md`'s `status` and `active_lesson`. There is no heartbeat event. Elapsed time per
lesson is `lesson_started` to `lesson_completed`, at date precision.

### 2.4 Retention: a 2,000-line cap, and compaction per completed lesson

An event is 90 to 160 bytes, so a full record is at most about 320 KB; a test writes 2,000
long events and asserts the file stays under 500 KB. The largest course measured has 23
lessons, and at 30 to 60 events a lesson a whole course fits under the cap uncompacted.

Compaction replaces the events of each **completed** lesson — one with a
`lesson_completed` event that is neither `active_lesson` nor `resume_at` — by one
`summary` event holding: attempts and failures per check, hints per rung, outcomes per
concept, one entry per assessment attempt, practice offered and the practice lessons
accepted, the events, starts and completions replaced, and the first and last dates. The
summary takes the place, `seq` and `date` of the lesson's last event, so the file stays in
order without renumbering, and the tutor's running `seq` stays right. A lesson re-entered
after compaction (a retake) merges into its summary at the next compaction. Events of a
lesson in progress are kept byte for byte. Without a readable `active_lesson`, nothing is
compacted.

Per-attempt assessment entries are kept, rather than outcome counts alone, because "did
practice improve the next result" needs the order of attempts, and there are only a few.

### 2.5 Repair, and the learner's control

A missing, empty, truncated or inconsistent record never stops a course. `compact` drops
any line that is not a well-formed event — a truncated last write among them — and
renumbers a record whose `seq` does not increase, and says what it did. When the tutor
would have used the record and it cannot answer, it says what it cannot know, in a
sentence, and carries on. The learner may read or delete the file at any time.

### 2.6 When the tutor writes and reads

At the point in the turn where the event happens (`runner-protocol.md` §16.1): a check run
(§2.5 there), a rung given (§5), an answer classified (§15.3), an attempt ended, practice
offered or accepted, a lesson started or completed (§6). The tutor learns `seq` by reading
only the last line, once per session. Reading is on demand, through
`scripts/evidence.py summary`: the learner asks how they have done, or a weak assessment
result where earlier practice matters. `SKILL.md` gains that load trigger, the
tutor-owned path and one sentence on the script, and stays at 2,978 words by `wc -w`,
paid for by compressing a catalogue passage `catalogue-format.md` §6 and §7 already hold.

### 2.7 Version control

Decided in belay#35 (2026-10-18; `state-lifecycle.md` section 3.3): `EVENTS.jsonl` follows
`STATE.md`, and the learner chooses once whether both are committed and pushed or stay
local.

## 3. Where this departs from the brief it was built to

The rulings for this issue were given before implementation. Four were changed, each
for a reason found while building it.

- **When compaction runs.** The ruling was "when appending would exceed the cap". The
  tutor appends by writing a line and never reads the file, so it cannot know the line
  count without a command per append. Compaction instead runs at each lesson completion
  and does nothing under the cap. The file can therefore exceed the cap by at most the
  lesson in progress, which compaction must keep in any case.
- **A missing record is not a warning.** The ruling listed missing among the cases the
  validator warns about. The record does not exist until the first event, and the
  validator runs right after materialization, so a warning there would fire on every new
  instance and teach the reader to ignore check 33. Missing reports n/a; empty is quiet;
  truncated and malformed records warn.
- **"Dropped on the next append".** The tutor cannot drop a line by appending one; a line
  appended after a fragment joins it and is lost with it (a test shows this). The protocol
  instead says: when the last line does not parse, run `compact` before appending.
- **Reading goes through a script.** The ruling had the tutor read the file on demand. A
  full record is up to 2,000 lines, so reading it into a conversation would cost what this
  design exists to save. `evidence.py summary` reads it and prints counts per lesson,
  with what it cannot know.

Two additions the rulings did not ask for: several events from one turn may go in one
append, in order; and compaction renumbers an inconsistent `seq`, telling the tutor to
read the last line again.

## 4. What is tested, and what is not

`tests/test_evidence.py` asserts values: three attempts and two failures of one check,
hints at rungs 1 and 3; `skipped` and `passed` read back as themselves from a new process;
a missing record gives exit 0 with no warning and a summary saying what is not known; a
truncated one gives one warning and exit 0, and `compact` repairs it so the next append
continues; compaction leaves a file check 33 is quiet on, with every per-lesson count
equal before and after, the active lesson's lines unchanged, and a retake merged; an
undeclared field, a sentence in a concept id and a clock time are each rejected; and the
validator is quiet on a valid record. `test_validate_bundle.py` proves check 33 warning
and never firing; `test_plan_update.py` proves an update plan leaves the file as it was.

Not tested: whether a tutor writes the right events in conversation. The structure can be
validated and the conversation cannot, as belay#22 and belay#45 describe.

## 5. Known limits

- **A lesson left without completing is never compacted** — an optional lesson the learner
  walked away from, say. Its events stay raw. That is right, since nothing says it is
  finished, and it is bounded by how much one lesson produces.
- **`lesson` paths are checked for shape, not against the manifest.** An update that
  removes a lesson would otherwise turn old, correct evidence into warnings.
- **Each append is a write the host may ask permission for.** How cheap that is depends on
  the host, and allowing several events per append is the only mitigation here.
