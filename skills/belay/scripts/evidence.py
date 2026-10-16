#!/usr/bin/env python3
"""The learning-evidence record: tutorial/EVENTS.jsonl.

Usage:
    evidence.py compact <instance-dir>   repair the record, and compact it
                                         when it holds more than CAP lines
    evidence.py summary <instance-dir>   print what the record can answer,
                                         lesson by lesson, and what it cannot
    evidence.py --help

The record is EVIDENCE ONLY. STATE.md is the only authority for a learner's
progress, and nothing in the teaching loop decides anything from this file
that STATE.md does not also say. references/state-lifecycle.md section 12 is
the format; references/runner-protocol.md section 16 says when the tutor
writes it and when it reads it.

The tutor appends events by writing lines. It never runs this script per
turn. `compact` runs at a lesson's completion, and also when the last line of
the record does not parse (a truncated write), because it drops that line.
`summary` runs when the tutor needs the record: the learner asks how they
did, or an assessment's remediation turns on whether earlier practice helped.

One JSON object per line. Every event has `seq`, `date`, `lesson` and `type`,
and the type decides the rest from a CLOSED set of fields (EVENT_FIELDS
below). No field holds free text: concept ids, validator names, lesson paths,
enumerated values and counts only. Learner code, answers and conversation
are never written here; the design spec's section 16 separates that content
layer from this signal layer.

A missing, empty, truncated or inconsistent record never stops a course.
validate_bundle.py check 33 reports a malformed one as a WARNING, and this
script reads what it can, says what it could not, and exits 0.

Exit codes:
    0  done (including "there is no record", which is a normal state)
    2  usage or I/O error

Stdlib only, Python 3.11. Reads STATE.md's frontmatter with the shared
restricted reader in yamlite.py. Writes nothing but EVENTS.jsonl, and only
from `compact`, and only when the file changes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from yamlite import YamlError, load_yaml

FILENAME = "EVENTS.jsonl"

# The retention cap, in lines. A raw event is 90 to 160 bytes, so 2000 lines
# is at most about 320 KB on disk. The largest course measured, rust-automaton-
# db, has 23 lessons; at the 30 to 60 events a lesson of about ten tasks
# produces, a whole course fits under the cap uncompacted, and compaction is
# for the learner who struggles long or retakes often. Nothing ever reads the
# whole file into a conversation: `summary` reads it and prints counts.
CAP = 2000

EXIT_OK = 0
EXIT_USAGE = 2

CHECK_RESULTS = ("pass", "fail")
HINT_RUNGS = (1, 2, 3, 4, 5)
ANSWER_OUTCOMES = ("demonstrated", "partial", "misconception", "not-enough-evidence")
ASSESSMENT_STATES = ("passed", "partial", "stopped", "skipped")

_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_LESSON_RE = re.compile(r"lessons(?:\.generated)?/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.md")
_GENERATED_RE = re.compile(r"lessons\.generated/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*\.md")
_CONCEPT_RE = re.compile(r"[a-z0-9-]+")
_VALIDATOR_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_NAME_MAX = 80
_PATH_MAX = 200


# -- field shapes ------------------------------------------------------------
#
# Each returns None when the value is acceptable, or a reason. They are the
# whole definition of what may be written: a value that passes them cannot
# carry a sentence, because none of them accepts a space.

Shape = Callable[[Any], "str | None"]


def _int(minimum: int, maximum: int | None = None) -> Shape:
    def shape(value: Any) -> str | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return "is not an integer"
        if value < minimum or (maximum is not None and value > maximum):
            upper = f" and at most {maximum}" if maximum is not None else ""
            return f"is {value}; it must be at least {minimum}{upper}"
        return None
    return shape


def _date(value: Any) -> str | None:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return "is not a calendar date YYYY-MM-DD (no clock time)"
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return f"{value!r} is not a real date"
    return None


def _matching(regex: re.Pattern, limit: int, what: str) -> Shape:
    def shape(value: Any) -> str | None:
        if not isinstance(value, str) or len(value) > limit:
            return f"is not {what}"
        if not regex.fullmatch(value) or "/../" in f"/{value}/" or "/./" in f"/{value}/":
            return f"is not {what}"
        return None
    return shape


_lesson = _matching(_LESSON_RE, _PATH_MAX, "a lesson path under lessons/ or lessons.generated/")
_generated = _matching(_GENERATED_RE, _PATH_MAX, "a lesson path under lessons.generated/")
_concept = _matching(_CONCEPT_RE, _NAME_MAX, "a concept id ([a-z0-9-]+)")
_validator = _matching(_VALIDATOR_RE, _NAME_MAX, "a validator name")


def _one_of(choices: tuple) -> Shape:
    def shape(value: Any) -> str | None:
        if isinstance(value, bool) or value not in choices:
            return f"is {value!r}, not one of {', '.join(str(c) for c in choices)}"
        return None
    return shape


def _true(value: Any) -> str | None:
    return None if value is True else "is written only as true, and only when it applies"


def _list_of(item: Shape, nonempty: bool) -> Shape:
    def shape(value: Any) -> str | None:
        if not isinstance(value, list):
            return "is not a list"
        if nonempty and not value:
            return "is an empty list"
        for entry in value:
            why = item(entry)
            if why is not None:
                return f"holds {entry!r}, which {why}"
        if len(set(map(json.dumps, value))) != len(value):
            return "names an entry twice"
        return None
    return shape


def _map_of(key: Shape, value_shape: Shape) -> Shape:
    def shape(value: Any) -> str | None:
        if not isinstance(value, dict):
            return "is not an object"
        for k, v in value.items():
            why = key(k)
            if why is not None:
                return f"has the key {k!r}, which {why}"
            why = value_shape(v)
            if why is not None:
                return f"has {k!r} whose value {why}"
        return None
    return shape


def _object(required: dict[str, Shape], optional: dict[str, Shape] | None = None) -> Shape:
    optional = optional or {}

    def shape(value: Any) -> str | None:
        if not isinstance(value, dict):
            return "is not an object"
        for name in value:
            if name not in required and name not in optional:
                return f"has the undeclared field {name!r}"
        for name, sub in required.items():
            if name not in value:
                return f"has no {name!r}"
            why = sub(value[name])
            if why is not None:
                return f"has {name!r} that {why}"
        for name, sub in optional.items():
            if name in value:
                why = sub(value[name])
                if why is not None:
                    return f"has {name!r} that {why}"
        return None
    return shape


def _rung_key(value: Any) -> str | None:
    return None if value in {str(r) for r in HINT_RUNGS} else "is not a rung 1 to 5"


def _outcome_key(value: Any) -> str | None:
    return None if value in ANSWER_OUTCOMES else f"is not one of {', '.join(ANSWER_OUTCOMES)}"


def _check_counts(value: Any) -> str | None:
    why = _object({"attempts": _int(0), "failures": _int(0)})(value)
    if why is None and value["failures"] > value["attempts"]:
        return "counts more failures than attempts"
    return why


_ATTEMPT = _object(
    {"state": _one_of(ASSESSMENT_STATES), "attempt": _int(1),
     "not_demonstrated": _list_of(_concept, nonempty=False)},
    {"requested": _true},
)


# -- the declared field set ---------------------------------------------------

COMMON_FIELDS: dict[str, Shape] = {
    "seq": _int(1),
    "date": _date,
    "lesson": _lesson,
    "type": lambda v: None,  # decided by EVENT_FIELDS
}

# type -> (required fields, optional fields), beyond the four common ones.
EVENT_FIELDS: dict[str, tuple[dict[str, Shape], dict[str, Shape]]] = {
    "lesson_started": ({}, {}),
    "lesson_completed": ({}, {}),
    "check": ({"validator": _validator, "result": _one_of(CHECK_RESULTS)}, {}),
    "hint": ({"rung": _one_of(HINT_RUNGS)}, {}),
    "answer": (
        {"concept": _concept, "outcome": _one_of(ANSWER_OUTCOMES)},
        {"requested": _true},
    ),
    "assessment": (
        {"state": _one_of(ASSESSMENT_STATES), "attempt": _int(1),
         "not_demonstrated": _list_of(_concept, nonempty=False)},
        {"requested": _true},
    ),
    "practice_offered": ({"concepts": _list_of(_concept, nonempty=True)}, {}),
    "practice_accepted": (
        {"concepts": _list_of(_concept, nonempty=True), "practice_lesson": _generated},
        {},
    ),
    # Written only by `compact`: the events of one completed lesson, as counts.
    "summary": (
        {
            "first_date": _date,
            "events": _int(1),
            "started": _int(0),
            "completed": _int(1),
            "checks": _map_of(_validator, _check_counts),
            "hints": _map_of(_rung_key, _int(0)),
            "answers": _map_of(_concept, _map_of(_outcome_key, _int(0))),
            "attempts": _list_of(_ATTEMPT, nonempty=False),
            "practice_offered": _int(0),
            "practice_lessons": _list_of(_generated, nonempty=False),
        },
        {},
    ),
}

EVENT_TYPES = tuple(EVENT_FIELDS)


def event_problem(event: Any) -> str | None:
    """Why `event` is not a well-formed event, or None if it is."""
    if not isinstance(event, dict):
        return "is not a JSON object"
    etype = event.get("type")
    if etype not in EVENT_FIELDS:
        return f"has type {etype!r}, which is not one of {', '.join(EVENT_TYPES)}"
    required, optional = EVENT_FIELDS[etype]
    shape = _object({**COMMON_FIELDS, **required}, optional)
    why = shape(event)
    if why is not None:
        return why
    if etype == "summary" and event["first_date"] > event["date"]:
        return "has a first_date later than its date"
    return None


# -- reading -----------------------------------------------------------------


@dataclass
class Record:
    """What a read of EVENTS.jsonl found. Reading never raises on content."""

    path: Path
    present: bool = False
    events: list[dict] = field(default_factory=list)
    # The line each event was read from, parallel to `events`, so that a
    # rewrite keeps an untouched event byte for byte.
    raw: list[str] = field(default_factory=list)
    # (line number, reason) for every line that is not a well-formed event,
    # and for every seq that does not follow the one before it.
    problems: list[tuple[int, str]] = field(default_factory=list)
    unreadable_lines: int = 0
    seq_ordered: bool = True
    truncated: bool = False
    lines: int = 0


def read_record(instance: Path) -> Record:
    path = instance / FILENAME
    record = Record(path=path)
    if not path.is_file():
        return record
    record.present = True
    try:
        raw = path.read_bytes()
    except OSError as exc:
        record.problems.append((0, f"the file could not be read: {exc}"))
        return record
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        record.problems.append((0, "the file is not UTF-8 text"))
        return record
    lines = text.split("\n")
    ends_cleanly = lines[-1] == ""
    if ends_cleanly:
        lines.pop()
    last_seq = 0
    for number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        record.lines += 1
        try:
            event = json.loads(line)
        except ValueError:
            event = None
            why = "is not JSON"
            if number == len(lines) and not ends_cleanly:
                record.truncated = True
                why = "is not JSON and has no line end: a truncated write"
        else:
            why = event_problem(event)
        if why is not None:
            record.unreadable_lines += 1
            record.problems.append((number, why))
            continue
        if event["seq"] <= last_seq:
            record.seq_ordered = False
            record.problems.append(
                (number, f"seq {event['seq']} does not follow seq {last_seq}")
            )
        last_seq = max(last_seq, event["seq"])
        record.events.append(event)
        record.raw.append(line)
    return record


# -- counting ----------------------------------------------------------------


def _empty_tally(lesson: str) -> dict:
    return {
        "lesson": lesson,
        "first_date": None,
        "date": None,
        "events": 0,
        "started": 0,
        "completed": 0,
        "checks": {},
        "hints": {},
        "answers": {},
        "attempts": [],
        "practice_offered": 0,
        "practice_lessons": [],
    }


def fold(tally: dict, event: dict) -> None:
    """Add one event, raw or summary, to a per-lesson tally in summary form."""
    first = event.get("first_date", event["date"])
    if tally["first_date"] is None or first < tally["first_date"]:
        tally["first_date"] = first
    if tally["date"] is None or event["date"] > tally["date"]:
        tally["date"] = event["date"]
    etype = event["type"]
    if etype == "summary":
        tally["events"] += event["events"]
        tally["started"] += event["started"]
        tally["completed"] += event["completed"]
        for name, counts in event["checks"].items():
            slot = tally["checks"].setdefault(name, {"attempts": 0, "failures": 0})
            slot["attempts"] += counts["attempts"]
            slot["failures"] += counts["failures"]
        for rung, n in event["hints"].items():
            tally["hints"][rung] = tally["hints"].get(rung, 0) + n
        for concept, outcomes in event["answers"].items():
            slot = tally["answers"].setdefault(concept, {})
            for outcome, n in outcomes.items():
                slot[outcome] = slot.get(outcome, 0) + n
        tally["attempts"].extend(dict(a) for a in event["attempts"])
        tally["practice_offered"] += event["practice_offered"]
        for path in event["practice_lessons"]:
            if path not in tally["practice_lessons"]:
                tally["practice_lessons"].append(path)
        return
    tally["events"] += 1
    if etype == "lesson_started":
        tally["started"] += 1
    elif etype == "lesson_completed":
        tally["completed"] += 1
    elif etype == "check":
        slot = tally["checks"].setdefault(event["validator"], {"attempts": 0, "failures": 0})
        slot["attempts"] += 1
        slot["failures"] += event["result"] == "fail"
    elif etype == "hint":
        rung = str(event["rung"])
        tally["hints"][rung] = tally["hints"].get(rung, 0) + 1
    elif etype == "answer":
        slot = tally["answers"].setdefault(event["concept"], {})
        slot[event["outcome"]] = slot.get(event["outcome"], 0) + 1
    elif etype == "assessment":
        attempt = {k: event[k] for k in ("state", "attempt", "not_demonstrated")}
        if event.get("requested"):
            attempt["requested"] = True
        tally["attempts"].append(attempt)
    elif etype == "practice_offered":
        tally["practice_offered"] += 1
    elif etype == "practice_accepted":
        if event["practice_lesson"] not in tally["practice_lessons"]:
            tally["practice_lessons"].append(event["practice_lesson"])


def tally(events: list[dict]) -> dict[str, dict]:
    """Per-lesson counts, in order of each lesson's first appearance.

    The same answer before and after compaction, for every lesson, is what
    compaction promises; tests/test_evidence.py asserts it.
    """
    out: dict[str, dict] = {}
    for event in events:
        fold(out.setdefault(event["lesson"], _empty_tally(event["lesson"])), event)
    return out


# -- STATE.md ----------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(?P<fm>.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def kept_lessons(instance: Path) -> tuple[set[str] | None, str]:
    """The lessons whose events compaction must keep, from STATE.md.

    `active_lesson`, and `resume_at` while a detour is under way: the lesson
    the detour interrupted is still in progress. None, with the reason, when
    STATE.md cannot say - and then nothing is compacted, because a lesson in
    progress cannot be told from a finished one.
    """
    try:
        text = (instance / "STATE.md").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, "STATE.md could not be read"
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return None, "STATE.md has no frontmatter"
    try:
        fm = load_yaml(match.group("fm"), "STATE.md")
    except YamlError as exc:
        return None, f"STATE.md's frontmatter does not parse: {exc}"
    if not isinstance(fm, dict) or not isinstance(fm.get("active_lesson"), str):
        return None, "STATE.md names no active_lesson"
    kept = {fm["active_lesson"]}
    if isinstance(fm.get("resume_at"), str):
        kept.add(fm["resume_at"])
    return kept, ""


# -- compaction --------------------------------------------------------------


@dataclass
class Compaction:
    present: bool = False
    lines_before: int = 0
    lines_after: int = 0
    dropped: list[tuple[int, str]] = field(default_factory=list)
    renumbered: bool = False
    compacted: list[str] = field(default_factory=list)
    skipped_reason: str = ""
    over_cap: bool = False
    written: bool = False


def _summary_event(tally_: dict, seq: int) -> dict:
    return {
        "seq": seq,
        "date": tally_["date"],
        "lesson": tally_["lesson"],
        "type": "summary",
        "first_date": tally_["first_date"],
        "events": tally_["events"],
        "started": tally_["started"],
        "completed": tally_["completed"],
        "checks": tally_["checks"],
        "hints": tally_["hints"],
        "answers": tally_["answers"],
        "attempts": tally_["attempts"],
        "practice_offered": tally_["practice_offered"],
        "practice_lessons": tally_["practice_lessons"],
    }


def dumps(event: dict) -> str:
    """One event as one line, ASCII, with no spaces to spare."""
    return json.dumps(event, separators=(",", ":"), ensure_ascii=True)


def compact(instance: Path, cap: int = CAP) -> Compaction:
    """Repair the record, and compact it when it is over `cap` lines.

    Repair is unconditional: a line that is not a well-formed event - a
    truncated last write among them - is dropped, and a record whose seq does
    not increase is renumbered from 1 in file order. Both are reported.

    Compaction replaces every event of each COMPLETED lesson by one summary
    event, placed where that lesson's last event was and carrying its seq and
    date, so the file stays in seq order without renumbering. A lesson is
    completed when it has a lesson_completed event (or a summary) and is
    neither STATE.md's active_lesson nor its resume_at. Every other event is
    kept as written. A summary already in the file is merged, so a lesson
    re-entered after compaction - an assessment's retake - stays one line.
    """
    result = Compaction()
    record = read_record(instance)
    if not record.present:
        return result
    result.present = True
    result.lines_before = record.lines
    if any(number == 0 for number, _ in record.problems):
        result.skipped_reason = record.problems[0][1] + "; the file was left as it is"
        result.lines_after = record.lines
        return result
    result.dropped = [(n, why) for n, why in record.problems if not why.startswith("seq ")]
    events = [dict(e) for e in record.events]
    # The text each output line is written as: the event's original line,
    # unless the event changed (renumbered) or is a new summary (None).
    lines: list[str | None] = list(record.raw)
    if not record.seq_ordered:
        for number, event in enumerate(events, start=1):
            event["seq"] = number
        lines = [None] * len(events)
        result.renumbered = True

    if len(events) > cap:
        kept, reason = kept_lessons(instance)
        if kept is None:
            result.skipped_reason = f"{reason}, so no lesson can be told finished"
        else:
            per_lesson = tally(events)
            done = [
                lesson for lesson, t in per_lesson.items()
                if t["completed"] > 0 and lesson not in kept
                and not _only_summary(events, lesson)
            ]
            if done:
                last_index = {e["lesson"]: i for i, e in enumerate(events)}
                out: list[dict] = []
                out_lines: list[str | None] = []
                for index, event in enumerate(events):
                    lesson = event["lesson"]
                    if lesson not in done:
                        out.append(event)
                        out_lines.append(lines[index])
                    elif index == last_index[lesson]:
                        out.append(_summary_event(per_lesson[lesson], event["seq"]))
                        out_lines.append(None)
                events, lines = out, out_lines
                result.compacted = done
    result.over_cap = len(events) > cap
    result.lines_after = len(events)

    if result.dropped or result.renumbered or result.compacted or not _ends_cleanly(record.path):
        body = "".join(
            (line if line is not None else dumps(event)) + "\n"
            for event, line in zip(events, lines)
        )
        tmp = record.path.with_name(record.path.name + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, record.path)
        result.written = True
    return result


def _only_summary(events: list[dict], lesson: str) -> bool:
    """True when the lesson is already exactly one summary line."""
    mine = [e for e in events if e["lesson"] == lesson]
    return len(mine) == 1 and mine[0]["type"] == "summary"


def _ends_cleanly(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return True
    return data == b"" or data.endswith(b"\n")


# -- reporting ---------------------------------------------------------------


def unknowns(record: Record) -> list[str]:
    """What the record cannot answer, in words the tutor can repeat."""
    if not record.present:
        return [
            f"there is no {FILENAME}: how many attempts a check needed, which "
            f"checks failed, which hints were given and how earlier answers "
            f"went are not known. STATE.md still holds the learner's progress."
        ]
    out = []
    if record.unreadable_lines:
        out.append(
            f"{record.unreadable_lines} line(s) could not be read and are not "
            f"counted, so every count below is a lower bound."
        )
    if not record.seq_ordered:
        out.append("seq does not increase through the file, so the order of "
                   "events is known only as far as the file order is right.")
    if record.present and not record.events and not record.unreadable_lines:
        out.append("the record holds no events yet.")
    return out


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def render_summary(record: Record, stream=sys.stdout) -> None:
    w = stream.write
    w(f"record:  {record.path}\n")
    for line in unknowns(record):
        w(f"unknown: {line}\n")
    for lesson, t in tally(record.events).items():
        span = t["first_date"] if t["first_date"] == t["date"] else f"{t['first_date']} to {t['date']}"
        state = "completed" if t["completed"] else "not completed"
        w(f"\n{lesson}  ({span}; started {t['started']}x, {state})\n")
        for name, c in t["checks"].items():
            w(f"  check {name}: {_plural(c['attempts'], 'attempt')}, {c['failures']} failed\n")
        if t["hints"]:
            rungs = ", ".join(f"rung {r} x{n}" for r, n in sorted(t["hints"].items()))
            w(f"  hints: {rungs}\n")
        for concept, outcomes in t["answers"].items():
            parts = ", ".join(f"{o} {outcomes[o]}" for o in ANSWER_OUTCOMES if o in outcomes)
            w(f"  answers {concept}: {parts}\n")
        for a in t["attempts"]:
            missing = ", ".join(a["not_demonstrated"]) or "none"
            asked = " (asked for by the learner)" if a.get("requested") else ""
            w(f"  assessment attempt {a['attempt']}: {a['state']}; not demonstrated: {missing}{asked}\n")
        if t["practice_offered"] or t["practice_lessons"]:
            taken = ", ".join(t["practice_lessons"]) or "none"
            w(f"  practice: offered {t['practice_offered']}x; accepted: {taken}\n")


def render_compaction(result: Compaction, path: Path, cap: int, stream=sys.stdout) -> None:
    w = stream.write
    if not result.present:
        w(f"no {FILENAME} at {path.parent}: nothing to compact. That is a normal state.\n")
        return
    for number, why in result.dropped:
        w(f"dropped line {number}: it {why}\n")
    if result.renumbered:
        w("renumbered: seq did not increase through the file; events are now numbered "
          "1 upwards in file order. Read the last line again before appending.\n")
    for lesson in result.compacted:
        w(f"compacted: {lesson} is now one summary line\n")
    if result.skipped_reason:
        w(f"not compacted: {result.skipped_reason}\n")
    w(f"lines:   {result.lines_before} -> {result.lines_after} (cap {cap})\n")
    if result.over_cap:
        w("over cap: the events left belong to lessons still in progress, and are kept.\n")
    w("written\n" if result.written else "unchanged\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence.py",
        description="Repair, compact or summarise a Belay instance's learning "
        "record (tutorial/EVENTS.jsonl). Evidence only: STATE.md is the "
        "authority for progress.",
    )
    parser.add_argument("command", choices=("compact", "summary"))
    parser.add_argument("instance", help="the instance (the tutorial/ directory)")
    args = parser.parse_args(argv)
    instance = Path(args.instance)
    if not instance.is_dir():
        print(f"error: {instance} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    try:
        if args.command == "compact":
            result = compact(instance)
            render_compaction(result, instance / FILENAME, CAP)
        else:
            render_summary(read_record(instance))
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
