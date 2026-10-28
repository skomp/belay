#!/usr/bin/env python3
"""Plan, show and apply the update of a materialized instance from its bundle.

Usage:
    plan_update.py <instance>                    plan the update
    plan_update.py <instance> --diff <file>      show one file's difference
    plan_update.py <instance> --apply [--take <file>]... [--take-replace]
                                                 apply what the learner accepted
    plan_update.py <instance> --check-version    is the instance behind?
    plan_update.py --help

The bundle is the source the instance stamp's `materialized_from` names, read
inside this process. With --from-catalogs it is the instance's own tutorial id
resolved through the learner's catalogues instead, exactly as
`catalogs.py resolve` resolves it, from disk and without fetching. The tutor
never passes a bundle path (belay#76): under
permissions.blockReadsOutsideWorkingDirectories a path outside the workspace
on the command line makes the host ask the learner. An optional second
argument still names a bundle directory directly, for an author comparing a
bundle inside the workspace, and for this script's tests.

The learner asks for an update; the plan says what that update would do,
file by file. The plan, --diff and --check-version WRITE NOTHING: no file in
either directory, or anywhere else, is created, modified or removed by those
runs. The tutor shows the plan and each difference, the learner decides, and
--apply then copies exactly what the learner accepted, deletes the files the
bundle no longer has, and rewrites the stamp. --apply writes only inside the
instance, and nothing outside it. The tutor then re-validates the instance and
places supplies. references/state-lifecycle.md section 3.2 is the procedure;
this is the part of it that a session classifying files by eye would get
wrong.

What it compares is exactly what materialization copies (state-lifecycle.md
section 3 step 2): tutorial.yaml (without the instance stamp), COURSE.md,
DESIGN.md and every file under lessons/. STATE.md, the learning record
EVENTS.jsonl, lessons.generated/ and everything outside the instance are never
classified, because the update never touches them.

There is no common ancestor. The instance does not keep a copy of the bundle
as it was when the course began, so when a file differs this script cannot
tell whether the author changed it, the tutor changed it, or both did. It
does not pretend to: a difference in DESIGN.md, or in a lesson the learner has
already worked in, is reported as a difference for the learner to decide.

Whether a lesson has been started is read from what STATE.md and the
instance manifest already record, by the rule in state-lifecycle.md section
3.2 and in lesson_status() below. Where those records cannot decide, the
answer is "the learner decides", never "replace".

Exit codes (the shape validate_bundle.py uses):
    plan                0 nothing to do - same version, every file the same
                        1 a plan exists - show it to the learner
    --diff              0 the file is the same on both sides; 1 it differs
    --apply             0 applied, or nothing to apply
    --check-version     0 not behind; 1 behind
    every mode          2 usage or I/O error - correct the invocation; never
                          the learner's problem
                        3 refused - the update cannot be applied as things
                          stand, or the source cannot be resolved or read,
                          and the report says why. Nothing was written.

Stdlib only, Python 3.11, the same restricted YAML reader as the validator.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

try:
    import validate_bundle as vb
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import validate_bundle as vb
import catalogs  # noqa: E402 - the stamp, the source and the locator

# The classes. Each bundle-owned file gets exactly one.
UNCHANGED = "unchanged"
REPLACE = "replace"  # the instance copy is replaced with the bundle's
DECIDE_COMPLETED = "decide-completed"  # a completed lesson's file differs
DECIDE_ACTIVE = "decide-active"  # the active lesson's file differs
DECIDE_UNRECORDED = "decide-unrecorded"  # STATE.md cannot say if it started
DECIDE_DESIGN = "decide-design"  # DESIGN.md differs
ADDED = "added"  # only in the bundle
REMOVED = "removed"  # only in the instance

DECIDE = (DECIDE_COMPLETED, DECIDE_ACTIVE, DECIDE_UNRECORDED, DECIDE_DESIGN)
CLASSES = (UNCHANGED, REPLACE, *DECIDE, ADDED, REMOVED)

# Lesson states, from lesson_status().
COMPLETED = "completed"
ACTIVE = "active"
NOT_STARTED = "not-started"
UNRECORDED = "unrecorded"

EXIT_NOTHING = 0
EXIT_PLAN = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3


class UsageError(Exception):
    """The arguments do not name an instance and a bundle."""


@dataclass
class Plan:
    instance: Path
    bundle: Path
    old_version: str = vb.VERSION_ABSENT
    new_version: str = vb.VERSION_ABSENT
    bump: str = "none"  # none | MINOR | MAJOR | older
    structural: list[str] = field(default_factory=list)
    classes: dict[str, str] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)
    refusals: list[tuple[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)

    @property
    def review(self) -> str:
        """`per-file` or `one-change-set`.

        MAJOR always reviews file by file. So does a MINOR bump whose lessons
        list changes in a way the MAJOR row of the bump table names: the
        author's number is a claim, and a removed or reordered lesson is the
        evidence that outranks it.
        """
        if self.bump == "MAJOR" or self.structural:
            return "per-file"
        return "one-change-set"

    def has_changes(self) -> bool:
        return self.old_version != self.new_version or any(
            cls != UNCHANGED for cls in self.classes.values()
        )

    def exit_code(self) -> int:
        if self.refusals:
            return EXIT_REFUSED
        if self.has_changes():
            return EXIT_PLAN
        return EXIT_NOTHING


# -- reading ---------------------------------------------------------------


def _read_manifest(root: Path) -> dict | str:
    """The parsed manifest, or the reason there is none."""
    raw = vb.read_text(root / "tutorial.yaml")
    if raw is None:
        return "it could not be read as UTF-8 text"
    try:
        parsed = vb.load_yaml(raw, "tutorial.yaml")
    except vb.YamlError as exc:
        return f"it does not parse: {exc}"
    if not isinstance(parsed, dict):
        return "it is not a mapping"
    return parsed


def _frontmatter(path: Path) -> dict | None:
    text = vb.read_text(path)
    if text is None:
        return None
    fm, _ = vb.split_frontmatter(text)
    if fm is None:
        return None
    try:
        parsed = vb.load_yaml(fm, path.name)
    except vb.YamlError:
        return None
    return parsed if isinstance(parsed, dict) else None


def bundle_owned_files(root: Path) -> list[str]:
    """The files materialization copies, relative to `root`, sorted.

    tutorial.yaml, COURSE.md, DESIGN.md, and every file under lessons/.
    Names starting with "." are skipped, as the validator skips them.
    """
    found: list[str] = []
    for name in ("tutorial.yaml", "COURSE.md", "DESIGN.md"):
        if (root / name).is_file():
            found.append(name)
    lessons = root / "lessons"
    if lessons.is_dir():
        for path in sorted(lessons.rglob("*")):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            if path.is_file():
                found.append(rel.as_posix())
    return sorted(found)


def owning_lesson(rel: str) -> str | None:
    """The lesson path a file under lessons/ belongs to, or None.

    lessons/x.md is its own lesson. Anything inside lessons/<dir>/ belongs to
    lessons/<dir>/LESSON.md. A non-.md file directly in lessons/ belongs to
    no lesson.
    """
    parts = rel.split("/")
    if len(parts) < 2 or parts[0] != "lessons":
        return None
    if len(parts) == 2:
        return rel if rel.endswith(".md") else None
    return f"lessons/{parts[1]}/LESSON.md"


def _str_list(value: Any) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _optional_keys(manifest: dict) -> set[str]:
    value = manifest.get("optional_lessons")
    return {str(k) for k in value} if isinstance(value, dict) else set()


def lesson_status(lesson: str, manifest: dict, state: dict) -> str:
    """Whether the learner has started `lesson`, from the records alone.

    The rule, as state-lifecycle.md section 3.2 states it:

    1. `status: not-started`: no lesson has started.
    2. `status: complete`: every entry in `lessons` is completed.
    3. Otherwise the ANCHOR is `active_lesson` when it is an entry in
       `lessons`, else `resume_at` (a detour is active, sections 8.3 and
       9.3). An entry before the anchor is completed, the anchor is active,
       an entry after it is not started. `lessons` is the order (section 5
       step 3).
    4. `active_lesson` itself is active, whatever kind of path it is.
    5. Anything else - an optional lesson that is not active, a file in no
       list - is unrecorded: STATE.md's frontmatter does not say.
    """
    lessons = _str_list(manifest.get("lessons"))
    status = state.get("status")
    active = state.get("active_lesson")
    resume = state.get("resume_at")
    if status == "not-started":
        return NOT_STARTED
    if status == "complete" and lesson in lessons:
        return COMPLETED
    if lesson == active:
        return ACTIVE
    anchor = active if active in lessons else resume if resume in lessons else None
    if lesson in lessons and anchor is not None:
        here, there = lessons.index(lesson), lessons.index(anchor)
        if here < there:
            return COMPLETED
        if here == there:
            return ACTIVE
        return NOT_STARTED
    return UNRECORDED


def _version(value: Any, where: str, plan: Plan) -> tuple[int, int] | None:
    parsed = vb.parse_version(value)
    if isinstance(parsed, str):
        plan.refusals.append((where, f"the version is malformed: {parsed}"))
        return None
    return parsed


def _structural_changes(old: dict, new: dict) -> list[str]:
    """Changes to the lessons list that the bump table calls MAJOR."""
    found: list[str] = []
    old_list, new_list = _str_list(old.get("lessons")), _str_list(new.get("lessons"))
    for entry in old_list:
        if entry not in new_list:
            found.append(f"{entry} is no longer in `lessons`")
    common_old = [e for e in old_list if e in new_list]
    common_new = [e for e in new_list if e in old_list]
    if common_old != common_new:
        found.append("the order of `lessons` changed")
    for key in sorted(_optional_keys(old) - _optional_keys(new)):
        found.append(f"{key} is no longer in `optional_lessons`")
    return found


def _generated_lessons(instance: Path) -> list[str]:
    gen = instance / vb.GENERATED_DIR
    if not gen.is_dir():
        return []
    out: list[str] = []
    for child in sorted(gen.iterdir()):
        if child.name.startswith("."):
            continue
        if child.is_file() and child.name.endswith(".md"):
            out.append(f"{vb.GENERATED_DIR}/{child.name}")
        elif child.is_dir() and (child / "LESSON.md").is_file():
            out.append(f"{vb.GENERATED_DIR}/{child.name}/LESSON.md")
    return out


# -- planning --------------------------------------------------------------


def make_plan(instance: Path, bundle: Path) -> Plan:
    """Classify every bundle-owned file. Reads both trees, writes nothing."""
    if not instance.is_dir():
        raise UsageError(f"{instance} is not a directory")
    if not bundle.is_dir():
        raise UsageError(f"{bundle} is not a directory")
    if not (instance / "STATE.md").is_file():
        raise UsageError(
            f"{instance} has no STATE.md, so it is not an instance. The first "
            f"argument is the instance (the tutorial/ directory)."
        )
    if (bundle / "STATE.md").is_file() or not (bundle / "tutorial.yaml").is_file():
        raise UsageError(
            f"{bundle} is not a bundle: a bundle has tutorial.yaml and no "
            f"STATE.md. The second argument is the bundle."
        )

    plan = Plan(instance=instance, bundle=bundle)
    old = _read_manifest(instance)
    new = _read_manifest(bundle)
    for label, parsed in (("instance", old), ("bundle", new)):
        if isinstance(parsed, str):
            plan.refusals.append((f"{label} tutorial.yaml", parsed))
    if isinstance(old, str) or isinstance(new, str):
        return plan
    if "instance" in new:
        raise UsageError(
            f"{bundle}: tutorial.yaml carries an instance stamp, so it is an "
            f"instance, not a bundle"
        )
    state = _frontmatter(instance / "STATE.md")
    if state is None:
        plan.refusals.append(
            ("STATE.md", "its frontmatter does not parse, so nothing can say "
             "which lessons the learner has started")
        )
        state = {}

    # -- versions
    stamp = old.get("instance") if isinstance(old.get("instance"), dict) else {}
    if "materialized_version" in stamp:
        old_raw, old_where = stamp["materialized_version"], "instance.materialized_version"
    elif "version" in old:
        old_raw, old_where = old["version"], "instance tutorial.yaml version"
    else:
        old_raw, old_where = vb.VERSION_ABSENT, "instance (absent)"
    new_raw = new.get("version", vb.VERSION_ABSENT)
    old_v = _version(old_raw, old_where, plan)
    new_v = _version(new_raw, "bundle tutorial.yaml version", plan)
    if old_v is not None:
        plan.old_version = f"{old_v[0]}.{old_v[1]}"
    if new_v is not None:
        plan.new_version = f"{new_v[0]}.{new_v[1]}"
    if old_v is not None and new_v is not None:
        if new_v < old_v:
            plan.bump = "older"
            plan.refusals.append(
                ("tutorial.yaml",
                 f'the bundle\'s version "{plan.new_version}" is older than '
                 f'the instance\'s "{plan.old_version}". Applying it would '
                 f"roll the course back; check that this is the right source")
            )
        elif new_v[0] != old_v[0]:
            plan.bump = "MAJOR"
        elif new_v[1] != old_v[1]:
            plan.bump = "MINOR"
    plan.structural = _structural_changes(old, new)

    # -- identity
    if old.get("id") != new.get("id"):
        plan.refusals.append(
            ("tutorial.yaml",
             f"the bundle is course {new.get('id')!r} and the instance is "
             f"course {old.get('id')!r}")
        )

    # -- where the learner stands must survive the update
    new_lessons = _str_list(new.get("lessons"))
    new_optional = _optional_keys(new)
    old_lessons = _str_list(old.get("lessons"))
    active = state.get("active_lesson")
    resume = state.get("resume_at")
    gen_prefix = vb.GENERATED_DIR + "/"
    if isinstance(active, str) and not active.startswith(gen_prefix):
        if active not in old_lessons and active not in _optional_keys(old):
            plan.refusals.append(
                (active,
                 "active_lesson names a path in neither `lessons` nor "
                 "`optional_lessons` of the instance. STATE.md is "
                 "inconsistent (state-lifecycle.md section 7); repair it first")
            )
        elif not (bundle / active).is_file() or (
            active not in new_lessons and active not in new_optional
        ):
            plan.refusals.append(
                (active,
                 "active_lesson names this lesson file and the new bundle does "
                 "not have it, so the learner's place would point nowhere")
            )
    elif not isinstance(active, str):
        plan.refusals.append(("STATE.md", "active_lesson is missing"))
    if isinstance(resume, str) and (
        not (bundle / resume).is_file() or resume not in new_lessons
    ):
        plan.refusals.append(
            (resume,
             "resume_at names this lesson file and the new bundle's `lessons` "
             "does not have it, so the active detour could not return")
        )
    for gen in _generated_lessons(instance):
        after = (_frontmatter(instance / gen) or {}).get("after")
        if isinstance(after, str) and after in old_lessons and after not in new_lessons:
            plan.refusals.append(
                (gen,
                 f"this generated lesson's after: names {after}, which the new "
                 f"bundle's `lessons` does not have")
            )

    # -- the files
    inst_files = set(bundle_owned_files(instance))
    bund_files = set(bundle_owned_files(bundle))
    for rel in sorted(inst_files | bund_files):
        lesson = owning_lesson(rel)
        status = lesson_status(lesson, old, state) if lesson else None
        if status:
            plan.details[rel] = f"lesson {status}"
        if rel not in bund_files:
            plan.classes[rel] = REMOVED
            continue
        if rel not in inst_files:
            plan.classes[rel] = ADDED
            continue
        if rel == "tutorial.yaml":
            same = {k: v for k, v in old.items() if k != "instance"} == new
        else:
            same = (instance / rel).read_bytes() == (bundle / rel).read_bytes()
        if same:
            plan.classes[rel] = UNCHANGED
        elif rel == "DESIGN.md":
            plan.classes[rel] = DECIDE_DESIGN
        elif lesson is None and rel.startswith("lessons/"):
            plan.classes[rel] = DECIDE_UNRECORDED
            plan.details[rel] = "belongs to no lesson"
        elif status is None or status == NOT_STARTED:
            plan.classes[rel] = REPLACE
        elif status == COMPLETED:
            plan.classes[rel] = DECIDE_COMPLETED
        elif status == ACTIVE:
            plan.classes[rel] = DECIDE_ACTIVE
        else:
            plan.classes[rel] = DECIDE_UNRECORDED

    # -- an Optional lessons entry naming a lesson the bundle no longer offers
    body = vb.read_text(instance / "STATE.md") or ""
    _, body = vb.split_frontmatter(body)
    for line in vb.section_lines(body, "Optional lessons") or []:
        for path in re.findall(r"`(lessons/[^`]+)`", line):
            if path not in new_optional and path in _optional_keys(old):
                plan.notes.append(
                    f"STATE.md's Optional lessons section records {path}, which "
                    f"the new bundle no longer offers. Remove that entry when "
                    f"applying, and say so."
                )

    # -- an Assessments row naming a lesson that would no longer be an
    # assessment (belay#33). Check 32 requires a path row to name a lesson
    # that declares `assesses`, and a scope that reads as a path to name a
    # lesson the instance has, so either row would fail validation after
    # the update. The row is the learner's record; the plan only says so.
    new_listed = set(new_lessons) | new_optional
    lines = vb.section_lines(body, vb.ASSESSMENT_SECTION) or []
    for _, row in vb.parse_assessment_records(lines):
        if row is None:
            continue
        path = row["path"]
        if row["scope"]:
            if ("/" in path or path.endswith(".md")) and path not in new_listed:
                plan.notes.append(
                    f"STATE.md's Assessments section records a quiz scoped to "
                    f"{path}, which the new bundle no longer has. Rewrite that "
                    f"scope in words when applying, and say so."
                )
            continue
        fm = _frontmatter(bundle / path) if path in new_listed else None
        if fm is None or vb.ASSESSES_KEY not in fm:
            plan.notes.append(
                f"STATE.md's Assessments section records {path}, which is no "
                f"longer an assessment in the new bundle. Remove that row when "
                f"applying, and say so."
            )

    plan.kept = (
        ["STATE.md"]
        + (["EVENTS.jsonl"] if (instance / "EVENTS.jsonl").is_file() else [])
        + ([vb.GENERATED_DIR + "/"] if (instance / vb.GENERATED_DIR).is_dir() else [])
    )
    return plan


# -- reporting -------------------------------------------------------------


def render(plan: Plan, stream=sys.stdout) -> None:
    code = plan.exit_code()
    outcome = {EXIT_NOTHING: "nothing to do", EXIT_PLAN: "plan",
               EXIT_REFUSED: "refused"}[code]
    w = stream.write
    w(f"instance:  {plan.instance}\n")
    w(f"bundle:    {plan.bundle}\n")
    bump = "" if plan.bump == "none" else f"  ({plan.bump})"
    w(f'version:   "{plan.old_version}" -> "{plan.new_version}"{bump}\n')
    if code == EXIT_PLAN:
        w(f"review:    {plan.review}\n")
        for reason in plan.structural:
            w(f"           {reason}\n")
        if plan.bump == "MINOR" and plan.structural:
            w("           (a MINOR bump with a MAJOR change: review file by file)\n")
        if plan.old_version == plan.new_version:
            w("           (the version did not move, yet files differ)\n")
    w(f"outcome:   {outcome}\n")

    if plan.refusals:
        w("\nrefused:\n")
        for where, why in plan.refusals:
            w(f"  {where}: {why}\n")

    w("\nfiles:\n")
    width = max(len(c) for c in CLASSES)
    for rel, cls in plan.classes.items():
        detail = plan.details.get(rel)
        tail = f"  ({detail})" if detail else ""
        w(f"  {cls:<{width}}  {rel}{tail}\n")

    counts = {c: sum(1 for v in plan.classes.values() if v == c) for c in CLASSES}
    w("\nsummary:   " + ", ".join(f"{n} {c}" for c, n in counts.items() if n) + "\n")
    w(f"kept:      {', '.join(plan.kept)}, and everything outside the instance\n")
    if code == EXIT_PLAN:
        w(f'stamp:     materialized_version "{plan.old_version}" -> '
          f'"{plan.new_version}", materialized_at -> today\n')
    for note in plan.notes:
        w(f"note:      {note}\n")


# -- the source -----------------------------------------------------------


class Refused(Exception):
    """The source cannot be resolved or read. Nothing was written."""


@dataclass
class Source:
    bundle: Path
    locator: str
    how: str  # "the instance stamp" | "the catalogues" | "the command line"


def resolve_source(args) -> Source:
    """Where the bundle is, without the tutor ever naming it (belay#76)."""
    instance = Path(args.instance)
    if args.bundle is not None:
        bundle = Path(args.bundle)
        return Source(bundle, catalogs.locator_for(bundle), "the command line")
    if not (instance / "tutorial.yaml").is_file():
        raise UsageError(
            f"{instance} has no tutorial.yaml, so it is not an instance. The "
            f"argument is the instance (the tutorial/ directory)."
        )
    try:
        if args.from_catalogs:
            manifest = catalogs.read_manifest(
                instance / "tutorial.yaml", "the instance manifest"
            )
            lookup = argparse.Namespace(
                id=str(manifest.get("id")),
                config=args.config,
                cache_dir=args.cache_dir,
                timeout=catalogs.DEFAULT_TIMEOUT,
            )
            entry = catalogs.find_entry(lookup)
            bundle = Path(entry.resolved_path)
            source = Source(bundle, catalogs.locator_for(bundle), "the catalogues")
        else:
            bundle, locator = catalogs.source_from_stamp(instance)
            source = Source(bundle, locator, "the instance stamp")
        catalogs.usable_source(source.bundle, source.locator)
    except catalogs.Refusal as exc:
        raise Refused(str(exc)) from exc
    except catalogs.ConfigError as exc:
        raise UsageError(str(exc)) from exc
    return source


# -- one file's difference ------------------------------------------------


def strip_stamp(text: str) -> str:
    """tutorial.yaml without its top-level `instance:` block.

    The block is a top-level key: its own line, then every blank or indented
    line after it, up to the next line that starts in column one.
    """
    out: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if re.match(r"instance:\s*(#.*)?$", line.rstrip("\r\n")):
            skipping = True
            continue
        if skipping and (not line.strip() or line[0] in " \t"):
            continue
        skipping = False
        out.append(line)
    return "".join(out).rstrip("\n") + "\n"


def _text_of(path: Path, rel: str) -> str | None:
    """The file as text for a diff, or None when it is not UTF-8 text."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    if rel == "tutorial.yaml":
        text = strip_stamp(text)
    return text


def show_diff(plan: Plan, rel: str, stream=sys.stdout) -> int:
    """A unified diff of one bundle-owned file: the instance, then the bundle."""
    if rel not in plan.classes:
        raise UsageError(
            f"{rel} is not a file the update compares. The plan lists every "
            f"one, by its path inside the instance."
        )
    cls = plan.classes[rel]
    w = stream.write
    w(f"file:      {rel}  ({cls})\n")
    w(f"yours:     {plan.instance / rel}\n")
    w(f'bundle:    version "{plan.new_version}"\n\n')
    if cls == UNCHANGED:
        w("The two copies are the same.\n")
        return 0
    old = _text_of(plan.instance / rel, rel) if cls != ADDED else ""
    new = _text_of(plan.bundle / rel, rel) if cls != REMOVED else ""
    if old is None or new is None:
        sizes = [
            (plan.instance / rel).stat().st_size if cls != ADDED else 0,
            (plan.bundle / rel).stat().st_size if cls != REMOVED else 0,
        ]
        w(f"It is not text. Yours is {sizes[0]} bytes, the bundle's is "
          f"{sizes[1]} bytes, and they differ.\n")
        return 1
    if rel == "tutorial.yaml" and cls != ADDED:
        new = new.rstrip("\n") + "\n"
    lines = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"tutorial/{rel} (yours)" if cls != ADDED else "/dev/null",
        tofile=f"{rel} (bundle {plan.new_version})" if cls != REMOVED else "/dev/null",
    )
    for line in lines:
        w(line if line.endswith("\n") else line + "\n\\ No newline at end of file\n")
    return 1


# -- applying what the learner accepted -----------------------------------


# The validation keys an update removes (state-lifecycle.md section 3.2,
# apply step 2). Section 3.1 writes them again when the instance is checked.
VALIDATION_KEYS = ("validated", "validation", "validation_warnings", "validation_unchecked")


def _stamp_value(key: str, value: Any) -> str:
    if key == "materialized_version":
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_stamp_value("", item) for item in value) + "]"
    return catalogs.yaml_scalar(str(value))


def new_stamp(old: dict, locator: str, version: str, today: str) -> dict:
    """The stamp after an update. Section 3.2 apply step 2, as a function."""
    stamp: dict[str, Any] = {}
    for key, value in old.items():
        if key not in VALIDATION_KEYS:
            stamp[key] = value
    stamp["materialized_from"] = locator
    stamp["materialized_version"] = version
    stamp["materialized_at"] = today
    stamp.setdefault("runner_version", catalogs.RUNNER_VERSION)
    unchecked = old.get("validation_unchecked")
    setup = [
        item for item in (unchecked if isinstance(unchecked, list) else [])
        if isinstance(item, str) and item.startswith("setup:")
    ]
    if setup and old.get("validation") == "not-certified":
        # An update re-runs no setup check, so a failed one stays recorded.
        stamp["validation"] = "not-certified"
        stamp["validation_unchecked"] = setup
    return stamp


def render_stamp(stamp: dict) -> str:
    return "instance:\n" + "".join(
        f"  {key}: {_stamp_value(key, value)}\n" for key, value in stamp.items()
    )


@dataclass
class Applied:
    taken: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)
    stamp: str = ""


def check_takes(plan: Plan, take: list[str]) -> None:
    allowed = (REPLACE, *DECIDE)
    for rel in take:
        cls = plan.classes.get(rel)
        if rel == "tutorial.yaml" or cls in (ADDED, REMOVED):
            raise UsageError(
                f"--take {rel}: tutorial.yaml, the added files and the removed "
                f"files are always applied together, so they are never named"
            )
        if cls not in allowed:
            raise UsageError(
                f"--take {rel}: the plan classes it {cls or 'not at all'}; "
                f"only a {', '.join(allowed)} file is taken by choice"
            )


def apply_plan(
    plan: Plan, take: list[str], take_replace: bool, source: Source, today: str
) -> Applied:
    """Copy what was accepted, delete what the bundle dropped, then restamp.

    tutorial.yaml is written LAST. An apply interrupted before it leaves the
    old stamp and the old manifest, so the next plan shows what is left
    rather than an instance that claims a version it does not hold.
    """
    chosen = set(take)
    if take_replace:
        chosen |= {rel for rel, cls in plan.classes.items() if cls == REPLACE}
    done = Applied()
    for rel, cls in plan.classes.items():
        if rel == "tutorial.yaml" or cls == UNCHANGED:
            continue
        if cls == REMOVED:
            continue
        if cls == ADDED or rel in chosen:
            target = plan.instance / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(plan.bundle / rel, target)
            done.taken.append(rel)
        else:
            done.kept.append((rel, cls))
    lessons_dir = plan.instance / vb.LESSONS_DIR
    for rel, cls in plan.classes.items():
        if cls != REMOVED:
            continue
        target = plan.instance / rel
        target.unlink()
        done.deleted.append(rel)
        parent = target.parent
        while parent != lessons_dir and lessons_dir in parent.parents:
            try:
                parent.rmdir()  # only when empty
            except OSError:
                break
            parent = parent.parent

    old = _read_manifest(plan.instance)
    old_stamp = old.get("instance") if isinstance(old, dict) else None
    old_stamp = old_stamp if isinstance(old_stamp, dict) else {}
    new_manifest = _read_manifest(plan.bundle)
    version = catalogs.bundle_version(new_manifest if isinstance(new_manifest, dict) else {})
    # From the stamp, source.locator is the stamp's own string, so a relative
    # `local:` path stays relative. Any other source is recorded as it was
    # resolved, which is "update materialized_from when the source changed".
    stamp = new_stamp(old_stamp, source.locator, version, today)
    done.stamp = render_stamp(stamp)
    text = (plan.bundle / "tutorial.yaml").read_text(encoding="utf-8")
    text = text.rstrip("\n") + "\n\n" + done.stamp
    (plan.instance / "tutorial.yaml").write_text(text, encoding="utf-8")
    done.taken.insert(0, "tutorial.yaml")
    return done


def render_applied(plan: Plan, done: Applied, stream=sys.stdout) -> None:
    w = stream.write
    w(f"instance:  {plan.instance}\n")
    w(f'version:   "{plan.old_version}" -> "{plan.new_version}"\n')
    w("outcome:   applied\n\nfiles:\n")
    for rel in done.taken:
        w(f"  taken    {rel}\n")
    for rel in done.deleted:
        w(f"  deleted  {rel}\n")
    for rel, cls in done.kept:
        w(f"  kept     {rel}  ({cls}; the learner's copy stays)\n")
    w("\nstamp, rewritten at the end of tutorial/tutorial.yaml:\n")
    for line in done.stamp.splitlines():
        w(f"  {line}\n")
    w("\nnext:      belay-validate --instance tutorial (section 3.1), then "
      "belay-catalogs place-supplies,\n           then STATE.md "
      "(state-lifecycle.md section 3.2, apply steps 3 to 5)\n")
    for note in plan.notes:
        w(f"note:      {note}\n")


# -- is the instance behind? ----------------------------------------------


def check_version(instance: Path, source: Source, stream=sys.stdout) -> int:
    """runner-protocol.md section 1, **A resume may say the course has moved on**.

    Reads the source manifest's `version` and nothing else. Exit 3 means
    "cannot tell", and the tutor says nothing about it.
    """
    old = _read_manifest(instance)
    new = _read_manifest(source.bundle)
    if isinstance(old, str) or isinstance(new, str):
        raise Refused("a manifest could not be read: "
                      + (old if isinstance(old, str) else new))
    stamp = old.get("instance") if isinstance(old.get("instance"), dict) else {}
    have = stamp.get("materialized_version", old.get("version", vb.VERSION_ABSENT))
    want = new.get("version", vb.VERSION_ABSENT)
    have_v, want_v = vb.parse_version(have), vb.parse_version(want)
    for label, parsed in (("the instance's", have_v), ("the source's", want_v)):
        if isinstance(parsed, str):
            raise Refused(f"{label} version is malformed: {parsed}")
    behind = want_v > have_v
    stream.write(
        f'instance:  "{have_v[0]}.{have_v[1]}"\n'
        f'source:    "{want_v[0]}.{want_v[1]}"  ({source.how})\n'
        f"outcome:   {'behind' if behind else 'not behind'}\n"
    )
    return EXIT_PLAN if behind else EXIT_NOTHING


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_update.py",
        description="Plan the update of a Belay instance from its bundle, show "
        "one file's difference, or apply what the learner accepted. Only "
        "--apply writes, and only inside the instance.",
    )
    parser.add_argument("instance", help="the instance (the tutorial/ directory)")
    parser.add_argument(
        "bundle",
        nargs="?",
        help="a bundle directory to compare with. The tutor omits it: the "
        "source is the one the instance stamp names",
    )
    parser.add_argument(
        "--from-catalogs",
        action="store_true",
        help="take the bundle the catalogues offer for this course's id "
        "instead of the one the stamp names; fetches nothing",
    )
    parser.add_argument("--config", default=catalogs.DEFAULT_CONFIG)
    parser.add_argument("--cache-dir", default=catalogs.DEFAULT_CACHE_DIR)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--diff", metavar="FILE", help="show one file's difference")
    mode.add_argument("--apply", action="store_true", help="apply the update")
    mode.add_argument(
        "--check-version",
        action="store_true",
        help="say whether the source's version is later than the instance's",
    )
    parser.add_argument(
        "--take",
        action="append",
        default=[],
        metavar="FILE",
        help="with --apply: a replace or decide-* file the learner accepted",
    )
    parser.add_argument(
        "--take-replace",
        action="store_true",
        help="with --apply: take every replace file (a one-change-set review)",
    )
    args = parser.parse_args(argv)
    if (args.take or args.take_replace) and not args.apply:
        print("error: --take and --take-replace go with --apply", file=sys.stderr)
        return EXIT_USAGE
    if args.bundle is not None and args.from_catalogs:
        print("error: name a bundle, or --from-catalogs, not both", file=sys.stderr)
        return EXIT_USAGE
    instance = Path(args.instance)
    try:
        source = resolve_source(args)
        if args.check_version:
            return check_version(instance, source)
        plan = make_plan(instance, source.bundle)
        if args.diff is not None:
            return show_diff(plan, args.diff)
        if args.apply:
            if plan.exit_code() == EXIT_REFUSED:
                render(plan)
                sys.stdout.write("\nNothing was applied.\n")
                return EXIT_REFUSED
            if plan.exit_code() == EXIT_NOTHING:
                render(plan)
                return EXIT_NOTHING
            check_takes(plan, args.take)
            done = apply_plan(
                plan, args.take, args.take_replace, source, catalogs.today_stamp()
            )
            render_applied(plan, done)
            return EXIT_NOTHING
    except Refused as exc:
        print(f"refused:   {exc}")
        print("Nothing was written.")
        return EXIT_REFUSED
    except (UsageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    render(plan)
    if source.how != "the command line":
        sys.stdout.write(f"source:    {source.locator}  ({source.how})\n")
    return plan.exit_code()


if __name__ == "__main__":
    sys.exit(main())
