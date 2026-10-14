#!/usr/bin/env python3
"""Plan the update of a materialized instance from a newer copy of its bundle.

Usage:
    plan_update.py <instance-dir> <bundle-dir>
    plan_update.py --help

The learner asks for an update; this script says what that update would do,
file by file, and does nothing else. It reads the instance and the bundle and
WRITES NOTHING: no file in either directory, or anywhere else, is created,
modified or removed by a run. The tutor shows the plan, the learner decides,
the tutor copies, and the tutor then re-validates the instance.
references/state-lifecycle.md section 3.2 is the procedure; this is the part
of it that a session classifying files by eye would get wrong.

What it compares is exactly what materialization copies (state-lifecycle.md
section 3 step 2): tutorial.yaml (without the instance stamp), COURSE.md,
DESIGN.md and every file under lessons/. STATE.md, lessons.generated/ and
everything outside the instance are never classified, because the update
never touches them.

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
    0  nothing to do - same version, every file the same
    1  a plan exists - show it to the learner
    2  usage or I/O error - correct the invocation; never the learner's problem
    3  refused - the update cannot be applied as things stand, and the
       report says why. Nothing should be copied.

Stdlib only, Python 3.11, the same restricted YAML reader as the validator.
"""

from __future__ import annotations

import argparse
import re
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

    plan.kept = ["STATE.md"] + (
        [vb.GENERATED_DIR + "/"] if (instance / vb.GENERATED_DIR).is_dir() else []
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_update.py",
        description="Plan, without applying, the update of a Belay instance "
        "from its bundle. Writes nothing.",
    )
    parser.add_argument("instance", help="the instance (the tutorial/ directory)")
    parser.add_argument("bundle", help="the bundle directory to update from")
    args = parser.parse_args(argv)
    try:
        plan = make_plan(Path(args.instance), Path(args.bundle))
    except (UsageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    render(plan)
    return plan.exit_code()


if __name__ == "__main__":
    sys.exit(main())
