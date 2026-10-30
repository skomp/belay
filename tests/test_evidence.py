#!/usr/bin/env python3
"""Test suite for skills/belay/scripts/evidence.py - the learning record.

Run it with:  python3 tests/test_evidence.py

No pytest. Each case builds an instance of the rust-cli-basics fixture in a
temporary directory, writes tutorial/EVENTS.jsonl the way the tutor does -
one line per event - and asserts VALUES read back from it: counts, states,
exit codes, warnings. One case per acceptance criterion of belay#34, each
with the control that shows the assertion could fail.

The record is evidence only. STATE.md stays the authority for progress, so
nothing here may make a course stop: a broken record is a warning from
validate_bundle.py check 33, never a finding.
"""

from __future__ import annotations

import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "skills" / "belay" / "scripts"
SCRIPT = SCRIPTS / "evidence.py"
LIFECYCLE = REPO / "skills" / "belay" / "references" / "state-lifecycle.md"
PROTOCOL = REPO / "skills" / "belay" / "references" / "runner-protocol.md"
FIXTURE = HERE / "fixtures" / "rust-cli-basics"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import evidence as ev  # noqa: E402
import validate_bundle as vb  # noqa: E402

L00 = "lessons/00-hello-args.md"
L01 = "lessons/01-subcommands/LESSON.md"
L02 = "lessons/02-errors-and-tests.md"
PRACTICE = "lessons.generated/args-practice.md"

# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

_passed = 0
_failures: list[str] = []


def record(ok: bool, name: str, detail: str = "") -> None:
    global _passed
    if ok:
        _passed += 1
        print(f"  ok    {name}")
    else:
        _failures.append(f"{name}: {detail}" if detail else name)
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")


def make_instance(tmp: Path, active: str = L01, resume_at: str | None = None) -> Path:
    """An instance of rust-cli-basics, materialized as state-lifecycle.md section 3 does."""
    inst = tmp / "workspace" / "tutorial"
    shutil.copytree(FIXTURE, inst)
    template = inst / "STATE.template.md"
    state = template.read_text()
    state = state.replace("status: not-started", "status: in-progress")
    state = state.replace("updated: null", "updated: 2026-09-11")
    extra = f"\nresume_at: {resume_at}" if resume_at else ""
    state = state.replace(f"active_lesson: {L00}", f"active_lesson: {active}{extra}")
    (inst / "STATE.md").write_text(state)
    template.unlink()
    with (inst / "tutorial.yaml").open("a", encoding="utf-8") as handle:
        handle.write(
            "\ninstance:\n  materialized_from: local:../fixture\n"
            "  materialized_at: 2026-09-11\n  runner_version: 1\n"
        )
    return inst


class Writer:
    """Appends events as the tutor does: one line each, seq one more than the last."""

    def __init__(self, inst: Path) -> None:
        self.path = inst / ev.FILENAME
        self.seq = 0

    def __call__(self, date: str, lesson: str, etype: str, **fields) -> None:
        self.seq += 1
        event = {"seq": self.seq, "date": date, "lesson": lesson, "type": etype, **fields}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")


def run_cli(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout + proc.stderr


def check33(inst: Path) -> tuple[int, list, list]:
    report = vb.validate(inst, "instance")
    return (
        report.exit_code(),
        [f for f in report.findings if f.check == 33],
        [w for w in report.warnings if w.check == 33],
    )


def tmpcase(fn: Callable[[Path], None]) -> Callable[[], None]:
    def wrapper() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fn(Path(tmp))
    wrapper.__name__ = fn.__name__
    return wrapper


def write_lesson_00(w: Writer) -> None:
    """Lesson 00: cargo-test fails twice then passes; hints at rungs 1 and 3."""
    w("2026-09-11", L00, "lesson_started")
    w("2026-09-11", L00, "check", validator="cargo-check", result="pass")
    w("2026-09-11", L00, "check", validator="cargo-test", result="fail")
    w("2026-09-11", L00, "hint", rung=1)
    w("2026-09-11", L00, "check", validator="cargo-test", result="fail")
    w("2026-09-12", L00, "hint", rung=3)
    w("2026-09-12", L00, "check", validator="cargo-test", result="pass")
    w("2026-09-12", L00, "lesson_completed")


# --------------------------------------------------------------------------
# Acceptance criteria
# --------------------------------------------------------------------------


@tmpcase
def test_attempts_failures_and_hints_are_recoverable(tmp: Path) -> None:
    """AC: an attempt count, a repeated check failure and a hint use."""
    print("\nattempt count, repeated failure and hint use are recoverable:")
    inst = make_instance(tmp)
    w = Writer(inst)
    write_lesson_00(w)
    w("2026-09-12", L01, "lesson_started")
    w("2026-09-12", L01, "check", validator="cargo-test", result="pass")
    counts = ev.tally(ev.read_record(inst).events)
    record(counts[L00]["checks"]["cargo-test"] == {"attempts": 3, "failures": 2},
           "cargo-test needed 3 attempts in lesson 00, 2 of them failed",
           repr(counts[L00]["checks"]))
    record(counts[L00]["checks"]["cargo-check"] == {"attempts": 1, "failures": 0},
           "cargo-check passed first time", repr(counts[L00]["checks"]))
    repeated = [n for n, c in counts[L00]["checks"].items() if c["failures"] >= 2]
    record(repeated == ["cargo-test"], "the check that failed repeatedly is named",
           repr(repeated))
    record(counts[L00]["hints"] == {"1": 1, "3": 1},
           "hints were used, and the ladder went as far as rung 3",
           repr(counts[L00]["hints"]))
    record(counts[L01]["hints"] == {} and
           counts[L01]["checks"]["cargo-test"] == {"attempts": 1, "failures": 0},
           "control: lesson 01's counts are its own", repr(counts[L01]))
    code, out = run_cli("summary", str(inst))
    record(code == 0 and "check cargo-test: 3 attempts, 2 failed" in out
           and "hints: rung 1 x1, rung 3 x1" in out,
           "the summary command prints the same counts", out)


def _assessment_instance(tmp: Path, state: str) -> Path:
    inst = make_instance(tmp)
    w = Writer(inst)
    w("2026-09-12", L02, "lesson_started")
    if state != "skipped":
        w("2026-09-12", L02, "answer", concept="error-propagation", outcome="demonstrated")
    w("2026-09-12", L02, "assessment", state=state, attempt=1, not_demonstrated=[])
    w("2026-09-12", L02, "lesson_completed")
    return inst


@tmpcase
def test_skipped_and_passed_are_distinguishable(tmp: Path) -> None:
    """AC: skipped is not passed, and the difference survives a cold read."""
    print("\nskipped and passed are distinguishable on a cold read:")
    states = {}
    for state in ("skipped", "passed"):
        inst = _assessment_instance(tmp / state, state)
        # A cold read: a new process, nothing but the file.
        code, out = run_cli("summary", str(inst))
        match = re.search(r"assessment attempt 1: (\w+);", out)
        states[state] = match.group(1) if match else None
        record(check33(inst)[0] == 0, f"{state}: the instance validates clean")
    record(states == {"skipped": "skipped", "passed": "passed"},
           "each record reads back as the state that was written", repr(states))
    record(states["skipped"] != states["passed"],
           "a skipped assessment does not read as a passed one", repr(states))


@tmpcase
def test_missing_record_does_not_stop_a_course(tmp: Path) -> None:
    """AC: a missing record is harmless, and the tutor can say what it cannot know."""
    print("\na missing record does not stop a course:")
    inst = make_instance(tmp)
    code, findings, warnings = check33(inst)
    record(code == 0 and not findings and not warnings,
           "no record: the validator exits 0 with no finding and no warning",
           f"exit {code}, {findings}, {warnings}")
    code, out = run_cli("summary", str(inst))
    record(code == 0 and "unknown: there is no EVENTS.jsonl" in out
           and "STATE.md still holds" in out,
           "no record: summary exits 0 and says what is not known", out)
    code, out = run_cli("compact", str(inst))
    record(code == 0 and "normal state" in out and not (inst / ev.FILENAME).exists(),
           "no record: compact exits 0 and creates nothing", out)
    # Deleting the record mid-course: the next append simply starts the file.
    w = Writer(inst)
    write_lesson_00(w)
    (inst / ev.FILENAME).unlink()
    w.seq = 41
    w("2026-09-13", L01, "lesson_started")
    code, findings, warnings = check33(inst)
    record(code == 0 and not warnings,
           "a record deleted and restarted at a later seq validates quietly",
           f"exit {code}, {warnings}")


@tmpcase
def test_truncated_record_does_not_stop_a_course(tmp: Path) -> None:
    """AC: a truncated record warns, is repaired by compact, and appending resumes."""
    print("\na truncated record does not stop a course:")
    inst = make_instance(tmp)
    w = Writer(inst)
    write_lesson_00(w)
    with (inst / ev.FILENAME).open("a") as handle:
        handle.write('{"seq":9,"date":"2026-09-1')
    code, findings, warnings = check33(inst)
    record(code == 0 and not findings and len(warnings) == 1
           and "truncated write" in warnings[0].message,
           "truncated: one check-33 warning, no finding, exit 0",
           f"exit {code}, findings {findings}, warnings {warnings}")
    code, out = run_cli("summary", str(inst))
    record(code == 0 and "1 line(s) could not be read" in out and "lower bound" in out
           and "check cargo-test: 3 attempts, 2 failed" in out,
           "truncated: summary counts what it can and says the rest is a lower bound",
           out)
    code, out = run_cli("compact", str(inst))
    record(code == 0 and "dropped line 9" in out,
           "compact drops the truncated line", out)
    text = (inst / ev.FILENAME).read_text()
    record(text.endswith("\n") and len(text.splitlines()) == 8,
           "the file is the eight good lines again, ending in a newline",
           repr(text[-80:]))
    last = json.loads(text.splitlines()[-1])
    w.seq = last["seq"]
    w("2026-09-13", L01, "lesson_started")
    code, findings, warnings = check33(inst)
    record(code == 0 and not warnings and ev.read_record(inst).events[-1]["seq"] == 9,
           "the next append continues from the last good seq, quietly",
           f"exit {code}, {warnings}")
    # Control: had the tutor appended without the repair, the new line would
    # have been glued to the fragment and lost with it.
    inst2 = make_instance(tmp / "control")
    w2 = Writer(inst2)
    write_lesson_00(w2)
    with (inst2 / ev.FILENAME).open("a") as handle:
        handle.write('{"seq":9,"date":"2026-09-1')
    w2("2026-09-13", L01, "lesson_started")
    events = ev.read_record(inst2).events
    record(not any(e["lesson"] == L01 for e in events),
           "control: appending over an unrepaired fragment loses the new event",
           repr(events[-1]))


def _long_record(inst: Path) -> Writer:
    """Two completed lessons, a practice detour, and lesson 02 in progress."""
    w = Writer(inst)
    write_lesson_00(w)
    w("2026-09-13", L01, "lesson_started")
    for _ in range(4):
        w("2026-09-13", L01, "check", validator="cargo-test", result="fail")
        w("2026-09-13", L01, "hint", rung=2)
    w("2026-09-14", L01, "check", validator="cargo-test", result="pass")
    w("2026-09-14", L01, "answer", concept="subcommand-dispatch", outcome="misconception")
    w("2026-09-14", L01, "assessment", state="partial", attempt=1,
      not_demonstrated=["subcommand-dispatch"])
    w("2026-09-14", L01, "practice_offered", concepts=["subcommand-dispatch"])
    w("2026-09-14", L01, "practice_accepted", concepts=["subcommand-dispatch"],
      practice_lesson=PRACTICE)
    w("2026-09-14", PRACTICE, "lesson_started")
    w("2026-09-15", PRACTICE, "lesson_completed")
    w("2026-09-15", L01, "answer", concept="subcommand-dispatch", outcome="demonstrated")
    w("2026-09-15", L01, "assessment", state="passed", attempt=2, not_demonstrated=[])
    w("2026-09-15", L01, "lesson_completed")
    w("2026-09-16", L02, "lesson_started")
    for _ in range(3):
        w("2026-09-16", L02, "check", validator="has-test", result="fail")
    return w


@tmpcase
def test_compaction_keeps_the_record_valid_and_the_counts(tmp: Path) -> None:
    """AC: the retention rule; compaction keeps the record valid and the counts."""
    print("\ncompaction keeps the record valid and every count:")
    inst = make_instance(tmp, active=L02)
    w = _long_record(inst)
    before_lines = (inst / ev.FILENAME).read_text().splitlines()
    before = ev.tally(ev.read_record(inst).events)
    active_before = [ln for ln in before_lines if json.loads(ln)["lesson"] == L02]

    under = ev.compact(inst)  # the real cap: far under it, so only repair runs
    record(not under.compacted and not under.written,
           f"under the cap of {ev.CAP} lines nothing is compacted or written",
           repr(under))

    result = ev.compact(inst, cap=10)
    after_lines = (inst / ev.FILENAME).read_text().splitlines()
    record(sorted(result.compacted) == sorted([L00, L01, PRACTICE]),
           "the three completed lessons were compacted, the active one was not",
           repr(result.compacted))
    record(len(after_lines) == 3 + len(active_before),
           "one summary line per completed lesson, plus the active lesson's events",
           f"{len(before_lines)} -> {len(after_lines)}")
    record([ln for ln in after_lines if json.loads(ln)["lesson"] == L02] == active_before,
           "the active lesson's events are kept byte for byte")
    rec = ev.read_record(inst)
    record(not rec.problems and rec.seq_ordered,
           "the compacted file reads with no problem and seq still increases",
           repr(rec.problems))
    code, findings, warnings = check33(inst)
    record(code == 0 and not warnings, "check 33 is quiet on the compacted file",
           f"exit {code}, {warnings}")
    after = ev.tally(rec.events)
    record(after == before, "every lesson's counts are equal before and after",
           f"before {before!r}\nafter {after!r}")
    record(after[L01]["attempts"] == [
        {"state": "partial", "attempt": 1, "not_demonstrated": ["subcommand-dispatch"]},
        {"state": "passed", "attempt": 2, "not_demonstrated": []},
    ] and after[L01]["practice_lessons"] == [PRACTICE],
           "whether practice improved the next result survives: partial, practice, passed",
           repr(after[L01]))

    # A retake after compaction: the lesson re-enters, then completes again.
    w.seq = rec.events[-1]["seq"]
    w("2026-09-17", L01, "lesson_started")
    w("2026-09-17", L01, "assessment", state="passed", attempt=3, not_demonstrated=[])
    w("2026-09-17", L01, "lesson_completed")
    before = ev.tally(ev.read_record(inst).events)
    result = ev.compact(inst, cap=5)
    rec = ev.read_record(inst)
    lines_l01 = [e for e in rec.events if e["lesson"] == L01]
    record(result.compacted == [L01] and len(lines_l01) == 1
           and ev.tally(rec.events) == before and not rec.problems,
           "a summary and later events of one lesson merge into one line, counts kept",
           f"{result.compacted}, {lines_l01}")
    record(result.over_cap, "still over a cap the active lesson alone exceeds: reported",
           repr(result))

    # Control: STATE.md that names no lesson stops compaction, not the course.
    inst2 = make_instance(tmp / "nostate", active=L02)
    _long_record(inst2)
    (inst2 / "STATE.md").write_text("no frontmatter here\n")
    text = (inst2 / ev.FILENAME).read_text()
    result = ev.compact(inst2, cap=10)
    record(not result.compacted and "no frontmatter" in result.skipped_reason
           and (inst2 / ev.FILENAME).read_text() == text,
           "control: without STATE.md's active lesson nothing is compacted",
           repr(result))

    # Control: resume_at is in progress too, and is kept.
    inst3 = make_instance(tmp / "detour", active=PRACTICE, resume_at=L01)
    _long_record(inst3)
    result = ev.compact(inst3, cap=10)
    record(L01 not in result.compacted and L00 in result.compacted,
           "a lesson a detour will return to (resume_at) is not compacted",
           repr(result.compacted))


@tmpcase
def test_renumbering_repairs_an_inconsistent_record(tmp: Path) -> None:
    print("\nan inconsistent seq is repaired by renumbering:")
    inst = make_instance(tmp)
    w = Writer(inst)
    write_lesson_00(w)
    w.seq = 2  # a second session that misread the last line
    w("2026-09-13", L01, "lesson_started")
    code, findings, warnings = check33(inst)
    record(code == 0 and len(warnings) == 1 and "does not follow" in warnings[0].message,
           "inconsistent: a warning, exit 0", f"{warnings}")
    before = ev.tally(ev.read_record(inst).events)
    result = ev.compact(inst)
    rec = ev.read_record(inst)
    record(result.renumbered and rec.seq_ordered and not rec.problems
           and [e["seq"] for e in rec.events] == list(range(1, 10)),
           "compact renumbers 1 to 9 in file order", repr([e["seq"] for e in rec.events]))
    record(ev.tally(rec.events) == before, "renumbering changes no count")


@tmpcase
def test_fields_are_limited_to_the_declared_set(tmp: Path) -> None:
    """AC: no transcript; the written fields are limited to the declared set."""
    print("\nwritten fields are limited to the declared set:")
    inst = make_instance(tmp, active=L02)
    _long_record(inst)
    ev.compact(inst, cap=10)  # summaries are written events too
    rec = ev.read_record(inst)
    types = {e["type"] for e in rec.events}
    record({"summary", "check", "lesson_started"} <= types,
           "the record under test holds raw and summary events", repr(types))
    for event in rec.events:
        required, optional = ev.EVENT_FIELDS[event["type"]]
        allowed = set(ev.COMMON_FIELDS) | set(required) | set(optional)
        if not set(event) <= allowed:
            record(False, f"seq {event['seq']} holds only declared fields",
                   repr(set(event) - allowed))
            break
    else:
        record(True, "every written event holds only declared fields")

    good = {"seq": 1, "date": "2026-09-11", "lesson": L00, "type": "hint", "rung": 2}
    record(ev.event_problem(good) is None, "control: a declared event is accepted")
    rejected = {
        "an undeclared field": {**good, "note": "learner was frustrated"},
        "learner code": {**good, "type": "check", "validator": "cargo-test",
                         "result": "fail", "output": "error[E0308]"},
        "an answer as a concept": {**good, "type": "answer", "concept":
                                   "args start at one", "outcome": "partial"},
        "a clock time": {**good, "date": "2026-09-11 14:02"},
        "an unknown type": {**good, "type": "conversation"},
        "an unknown outcome": {**good, "type": "answer", "concept": "x",
                               "outcome": "wrong"},
        "a rung past five": {**good, "rung": 6},
        "a non-lesson path": {**good, "lesson": "src/main.rs"},
        "requested: false": {**good, "type": "answer", "concept": "x",
                             "outcome": "partial", "requested": False},
    }
    for label, event in rejected.items():
        record(ev.event_problem(event) is not None, f"rejected: {label}",
               repr(event))
    # And through the validator: one undeclared field is one check-33 warning.
    with (inst / ev.FILENAME).open("a") as handle:
        handle.write(json.dumps({**good, "seq": 999, "transcript": "..."}) + "\n")
    code, findings, warnings = check33(inst)
    record(code == 0 and not findings and len(warnings) == 1
           and "undeclared field 'transcript'" in warnings[0].message,
           "an undeclared field written to the file is a warning, exit 0",
           f"exit {code}, {warnings}")


def _documented_events() -> dict[str, set[str]]:
    """The event table in state-lifecycle.md section 12, as type -> fields."""
    text = LIFECYCLE.read_text()
    start = text.index("### 12.2")
    end = text.index("### 12.3")
    table: dict[str, set[str]] = {}
    for line in text[start:end].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not cells[0].startswith("`") or cells[0] == "`type`":
            continue
        etype = cells[0].strip("`")
        table[etype] = set(re.findall(r"`([a-z_]+)`", cells[1]))
    return table


def test_the_documented_table_is_the_code() -> None:
    print("\nthe documented event table matches the code:")
    documented = _documented_events()
    record(set(documented) == set(ev.EVENT_TYPES),
           "state-lifecycle.md 12.2 documents exactly the event types the code accepts",
           f"documented {sorted(documented)}, code {sorted(ev.EVENT_TYPES)}")
    for etype, (required, optional) in ev.EVENT_FIELDS.items():
        fields = set(required) | set(optional)
        record(documented.get(etype) == fields,
               f"{etype}: documented fields equal the declared fields",
               f"documented {sorted(documented.get(etype, set()))}, code {sorted(fields)}")


@tmpcase
def test_validator_quiet_on_valid_record(tmp: Path) -> None:
    """AC: the validator reports a malformed record; a control proves it is quiet on a valid one."""
    print("\nthe validator is quiet on a valid record and warns on a malformed one:")
    inst = make_instance(tmp, active=L02)
    _long_record(inst)
    report = vb.validate(inst, "instance")
    record(report.exit_code() == 0 and not report.warnings
           and report.status.get(33, ("", ""))[0] == vb.RAN,
           "a valid record: check 33 ran, no warning at all, exit 0",
           f"{report.status.get(33)}, {[str(x) for x in report.warnings]}")
    with (inst / ev.FILENAME).open("a") as handle:
        handle.write("not json\n")
    code, findings, warnings = check33(inst)
    record(code == 0 and len(warnings) == 1 and "is not JSON" in warnings[0].message,
           "the same record plus one bad line: exactly one warning, exit 0",
           f"{warnings}")


@tmpcase
def test_cli(tmp: Path) -> None:
    print("\nthe command line:")
    code, _ = run_cli("compact", str(tmp / "nowhere"))
    record(code == ev.EXIT_USAGE, "a missing instance directory exits 2", str(code))
    code, _ = run_cli("rewrite", str(tmp))
    record(code == 2, "an unknown subcommand exits 2", str(code))
    inst = make_instance(tmp)
    (inst / ev.FILENAME).write_text("")
    code, out = run_cli("summary", str(inst))
    record(code == 0 and "holds no events yet" in out, "an empty record: summary says so", out)
    w = Writer(inst)
    write_lesson_00(w)
    with (inst / ev.FILENAME).open("a") as handle:
        handle.write('{"seq":9,"date":"2026-09-1')
    ev.compact(inst)
    raw = (inst / ev.FILENAME).read_bytes()
    record(raw.isascii(), "a rewritten record is ASCII")


@tmpcase
def test_compaction_size_bound(tmp: Path) -> None:
    """The cap's justification: a full record stays well under half a megabyte."""
    print("\nthe cap bounds the record's size:")
    inst = make_instance(tmp)
    w = Writer(inst)
    long_lesson = "lessons.generated/" + "a" * 60 + ".md"
    for n in range(ev.CAP):
        w("2026-09-11", long_lesson, "check", validator="v" * 40, result="fail")
    size = (inst / ev.FILENAME).stat().st_size
    record(size < 500_000, f"{ev.CAP} long events take {size} bytes, under 500 KB",
           str(size))


@tmpcase
def test_reported_events(tmp: Path) -> None:
    """belay#86: the `reported` event, which stops a report being offered twice."""
    print("\nthe reported event:")
    good = {"seq": 1, "date": "2026-10-30", "lesson": L01, "type": "reported",
            "defect": "undeclared-validator", "subject": "cargo-tset"}
    record(ev.event_problem(good) is None,
           "a reported event with a known defect and a subject is accepted",
           repr(ev.event_problem(good)))
    for subject in ("lessons/01-subcommands/LESSON.md", "check-22", "supplies[2]",
                    "state-merge"):
        event = {**good, "subject": subject, "target": "course"}
        record(ev.event_problem(event) is None,
               f"subject {subject!r} with target course is accepted",
               repr(ev.event_problem(event)))
    runner = {**good, "defect": "runner-error", "subject": "belay-catalogs",
              "target": "runner"}
    record(ev.event_problem(runner) is None, "target runner is accepted",
           repr(ev.event_problem(runner)))
    for label, event, needle in (
        ("an unknown defect", {**good, "defect": "typo"}, "'defect'"),
        ("an empty subject", {**good, "subject": ""}, "'subject'"),
        ("a subject that is a sentence",
         {**good, "subject": "the lesson is wrong"}, "'subject'"),
        ("a subject that is not a string", {**good, "subject": 7}, "'subject'"),
        ("an unknown target", {**good, "target": "author"}, "'target'"),
        ("no subject at all",
         {k: v for k, v in good.items() if k != "subject"}, "'subject'"),
        ("a free-text field beside it", {**good, "note": "learner said so"},
         "undeclared field 'note'"),
    ):
        why = ev.event_problem(event)
        record(why is not None and needle in why, f"rejected: {label}", repr(why))

    inst = make_instance(tmp, active=L02)
    w = _long_record(inst)
    # A report offered in lesson 00, which is completed, and one in the
    # active lesson. Both must outlive compaction.
    lines = (inst / ev.FILENAME).read_text().splitlines()
    done = json.dumps({"seq": 0, "date": "2026-09-12", "lesson": L00, "type": "reported",
                       "defect": "dangling-anchor", "subject": "state-merge"})
    lines.insert(3, done)
    rewritten = [json.loads(ln) for ln in lines]
    for number, event in enumerate(rewritten, start=1):
        event["seq"] = number
    (inst / ev.FILENAME).write_text("".join(json.dumps(e) + "\n" for e in rewritten))
    w.seq = len(rewritten)
    w("2026-09-16", L02, "reported", defect="runner-error", subject="belay-evidence",
      target="runner")
    report = vb.validate(inst, "instance")
    record(report.exit_code() == 0 and not [x for x in report.warnings if x.check == 33]
           and report.status.get(33, ("", ""))[0] == vb.RAN,
           "check 33 accepts a record holding reported events: ran, no warning, exit 0",
           f"{report.status.get(33)}, {[str(x) for x in report.warnings]}")
    # Control: the same record with an unknown defect is a check-33 warning.
    bad = inst.parent.parent / "bad"
    shutil.copytree(inst.parent, bad)
    with (bad / "tutorial" / ev.FILENAME).open("a") as handle:
        handle.write(json.dumps({**good, "seq": 999, "defect": "typo"}) + "\n")
    code, findings, warnings = check33(bad / "tutorial")
    record(code == 0 and len(warnings) == 1 and "'defect'" in warnings[0].message,
           "control: one reported line with an unknown defect is one warning, exit 0",
           f"exit {code}, {warnings}")

    reported_before = [ln for ln in (inst / ev.FILENAME).read_text().splitlines()
                       if '"reported"' in ln]
    before = ev.tally(ev.read_record(inst).events)
    record(before[L00]["reports"] == [{"defect": "dangling-anchor", "subject": "state-merge"}]
           and before[L00]["events"] == 8,
           "a report is listed per lesson and is not counted among its events",
           repr(before[L00]))
    result = ev.compact(inst, cap=10)
    after_lines = (inst / ev.FILENAME).read_text().splitlines()
    rec = ev.read_record(inst)
    record(L00 in result.compacted
           and [ln for ln in after_lines if '"reported"' in ln] == reported_before,
           "compaction keeps every reported event byte for byte, a completed "
           "lesson's included",
           f"{result.compacted}\n{after_lines}")
    l00 = [e["type"] for e in rec.events if e["lesson"] == L00]
    record(sorted(l00) == ["reported", "summary"],
           "lesson 00 is now its report and one summary", repr(l00))
    record(not rec.problems and rec.seq_ordered and ev.tally(rec.events) == before,
           "the compacted record is valid, in seq order, and every count is equal",
           f"{rec.problems}")
    again = ev.compact(inst, cap=10)
    record(not again.compacted and not again.written,
           "a second compaction finds lesson 00 already compact: nothing rewritten",
           repr(again))
    code, out = run_cli("summary", str(inst))
    record(code == 0 and "report offered: dangling-anchor at state-merge" in out
           and "report offered: runner-error at belay-evidence (to the runner)" in out,
           "summary lists each report offered", out)


def test_the_defect_kinds_are_documented() -> None:
    """runner-protocol.md section 17's table of kinds is the code's closed set."""
    print("\nthe documented defect kinds match the code:")
    text = PROTOCOL.read_text()
    start = text.index("### 17.2 ")
    section = text[start:text.index("### 17.3 ")]
    kinds = re.findall(r"^\| `([a-z-]+)` \|", section, re.M)
    record(len(kinds) >= 5, f"the table parse is a live instrument ({len(kinds)} rows)",
           repr(kinds))
    record(tuple(kinds) == ev.DEFECT_KINDS,
           "section 17 lists exactly the defect kinds evidence.py accepts, in order",
           f"documented {kinds}, code {list(ev.DEFECT_KINDS)}")


def main() -> int:
    print("evidence.py test suite")
    print(f"  script: {SCRIPT}")
    for test in (
        test_attempts_failures_and_hints_are_recoverable,
        test_skipped_and_passed_are_distinguishable,
        test_missing_record_does_not_stop_a_course,
        test_truncated_record_does_not_stop_a_course,
        test_compaction_keeps_the_record_valid_and_the_counts,
        test_renumbering_repairs_an_inconsistent_record,
        test_fields_are_limited_to_the_declared_set,
        test_the_documented_table_is_the_code,
        test_validator_quiet_on_valid_record,
        test_cli,
        test_compaction_size_bound,
        test_reported_events,
        test_the_defect_kinds_are_documented,
    ):
        try:
            test()
        except Exception:  # pragma: no cover
            record(False, test.__name__, "raised:\n" + traceback.format_exc())

    print()
    if _failures:
        print(f"FAILED - {len(_failures)} of {_passed + len(_failures)} assertions:")
        for text in _failures:
            print(f"  - {text}")
        return 1
    print(f"OK - {_passed} assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
