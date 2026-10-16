#!/usr/bin/env python3
"""Test suite for skills/belay/scripts/plan_update.py.

Run it with:  python3 tests/test_plan_update.py

No pytest. Every case builds a fresh instance/bundle pair in a temporary
directory from the rust-cli-basics fixture (or the generated-instance one),
changes one thing, and asserts the CLASS each file gets and the EXIT CODE.
Message wording is not asserted: it is for the learner and may improve.

Two properties are the point of the script, and each has a case that could
fail rather than one that can only pass:

  * a file the learner has worked in is never classified `replace`. The
    completed, active and DESIGN.md cases each prove the classifier sees the
    difference at all - the same edit in an unstarted lesson IS `replace`;
  * the script writes nothing. Both trees are digested, names, sizes, mtimes
    and bytes, before and after a run that produces a plan and a run that
    refuses.
"""

from __future__ import annotations

import hashlib
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
SCRIPT = SCRIPTS / "plan_update.py"
FIXTURES = HERE / "fixtures"
BUNDLE_FIXTURE = FIXTURES / "rust-cli-basics"
GENERATED_FIXTURE = FIXTURES / "generated-instance"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import plan_update as pu  # noqa: E402

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


def edit(path: Path, old: str, new: str) -> None:
    """Replace `old` with `new`, asserting `old` was there - a no-op proves nothing."""
    text = path.read_text()
    assert old in text, f"{path.name}: expected to find {old!r}"
    path.write_text(text.replace(old, new, 1))


def append(path: Path, extra: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(extra)


L00 = "lessons/00-hello-args.md"
L01 = "lessons/01-subcommands/LESSON.md"
L01_MATERIAL = "lessons/01-subcommands/usage.txt"
L02 = "lessons/02-errors-and-tests.md"
OPT = "lessons/what-is-a-character.md"


def make_pair(
    tmp: Path,
    active: str = L01,
    status: str = "in-progress",
    stamp_version: str | None = "1.0",
) -> tuple[Path, Path]:
    """A bundle copy and an instance materialized from it, as section 3 does."""
    bundle = tmp / "bundle"
    shutil.copytree(BUNDLE_FIXTURE, bundle)
    inst = tmp / "workspace" / "tutorial"
    inst.mkdir(parents=True)
    for name in ("tutorial.yaml", "COURSE.md", "DESIGN.md"):
        shutil.copy2(bundle / name, inst / name)
    shutil.copytree(bundle / "lessons", inst / "lessons")
    state = (bundle / "STATE.template.md").read_text()
    state = state.replace("status: not-started", f"status: {status}")
    state = state.replace("updated: null", "updated: 2026-10-14")
    state = state.replace(f"active_lesson: {L00}", f"active_lesson: {active}")
    (inst / "STATE.md").write_text(state)
    stamp = "\ninstance:\n  materialized_from: local:../bundle\n"
    if stamp_version is not None:
        stamp += f'  materialized_version: "{stamp_version}"\n'
    stamp += "  materialized_at: 2026-10-14\n  runner_version: 1\n"
    append(inst / "tutorial.yaml", stamp)
    return inst, bundle


def set_version(root: Path, value: str | None) -> None:
    """Set or remove the top-level version line of root/tutorial.yaml."""
    text = (root / "tutorial.yaml").read_text()
    lines = [ln for ln in text.splitlines(keepends=True) if not ln.startswith("version:")]
    if value is not None:
        index = next(i for i, ln in enumerate(lines) if ln.startswith("id:"))
        lines.insert(index + 1, f'version: "{value}"\n')
    (root / "tutorial.yaml").write_text("".join(lines))


def run_cli(inst: Path, bundle: Path) -> int:
    proc = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), str(inst), str(bundle)],
        capture_output=True,
        text=True,
    )
    return proc.returncode


def digest(root: Path) -> str:
    h = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        st = path.lstat()
        h.update(f"{path.relative_to(root)}|{st.st_mode}|{st.st_mtime_ns}".encode())
        if path.is_file():
            h.update(path.read_bytes())
    return h.hexdigest()


def tmpcase(fn: Callable[[Path], None]) -> Callable[[], None]:
    def wrapper() -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fn(Path(tmp))
    wrapper.__name__ = fn.__name__
    return wrapper


def expect_classes(name: str, plan: pu.Plan, expected: dict[str, str]) -> None:
    for rel, cls in expected.items():
        got = plan.classes.get(rel)
        record(got == cls, f"{name}: {rel} is {cls}", f"got {got!r}")


def expect_exit(name: str, inst: Path, bundle: Path, plan: pu.Plan, code: int) -> None:
    record(plan.exit_code() == code, f"{name}: plan exit code {code}",
           f"got {plan.exit_code()}")
    got = run_cli(inst, bundle)
    record(got == code, f"{name}: CLI exits {code}", f"got {got}")


# --------------------------------------------------------------------------
# Cases
# --------------------------------------------------------------------------


@tmpcase
def test_identical_is_nothing_to_do(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    plan = pu.make_plan(inst, bundle)
    record(bool(plan.classes) and all(c == pu.UNCHANGED for c in plan.classes.values()),
           "identical: every file is unchanged", repr(plan.classes))
    record("STATE.md" not in plan.classes, "identical: STATE.md is never classified")
    expect_exit("identical", inst, bundle, plan, pu.EXIT_NOTHING)


@tmpcase
def test_minor_change_in_unstarted_lesson_is_replace(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    set_version(inst, "1.0")
    set_version(bundle, "1.1")
    append(bundle / L02, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("minor/unstarted", plan, {L02: pu.REPLACE, L00: pu.UNCHANGED,
                                             "tutorial.yaml": pu.REPLACE})
    record(plan.bump == "MINOR", "minor/unstarted: bump is MINOR", plan.bump)
    record(plan.review == "one-change-set", "minor/unstarted: one change set",
           plan.review)
    expect_exit("minor/unstarted", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_change_in_completed_lesson_is_decide(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, active=L01)
    append(bundle / L00, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("completed", plan, {L00: pu.DECIDE_COMPLETED})
    expect_exit("completed", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_change_in_active_lesson_is_decide(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, active=L01)
    append(bundle / L01, "\nA corrected sentence.\n")
    append(bundle / L01_MATERIAL, "one more line\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("active", plan, {L01: pu.DECIDE_ACTIVE,
                                    L01_MATERIAL: pu.DECIDE_ACTIVE})
    expect_exit("active", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_design_with_local_addition_is_decide(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    append(inst / "DESIGN.md", "\n## Learner decision {#learner-choice}\n\nKept it.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("design", plan, {"DESIGN.md": pu.DECIDE_DESIGN})
    record(plan.classes.get("DESIGN.md") != pu.REPLACE, "design: never replace")
    expect_exit("design", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_active_lesson_removed_upstream_is_refused(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, active=L01)
    shutil.rmtree(bundle / "lessons" / "01-subcommands")
    edit(bundle / "tutorial.yaml", f"  - {L01}\n", "")
    set_version(bundle, "2.0")
    plan = pu.make_plan(inst, bundle)
    named = [where for where, _ in plan.refusals]
    record(L01 in named, "removed active: refusal names the file", repr(named))
    expect_exit("removed active", inst, bundle, plan, pu.EXIT_REFUSED)


@tmpcase
def test_lesson_removed_upstream_not_active(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, active=L01)
    (bundle / L02).unlink()
    edit(bundle / "tutorial.yaml", f"  - {L02}\n", "")
    set_version(bundle, "1.1")
    plan = pu.make_plan(inst, bundle)
    expect_classes("removed", plan, {L02: pu.REMOVED})
    record(plan.review == "per-file",
           "removed: a MINOR bump that removes a lesson reviews per file",
           plan.review)
    expect_exit("removed", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_lesson_added_upstream(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    (bundle / "lessons" / "03-new.md").write_text("---\nid: 03-new\ntitle: New\n---\n")
    edit(bundle / "tutorial.yaml", f"  - {L02}\n", f"  - {L02}\n  - lessons/03-new.md\n")
    set_version(bundle, "1.1")
    plan = pu.make_plan(inst, bundle)
    expect_classes("added", plan, {"lessons/03-new.md": pu.ADDED})
    record(plan.review == "one-change-set", "added: appending a lesson is MINOR",
           plan.review)
    expect_exit("added", inst, bundle, plan, pu.EXIT_PLAN)


@tmpcase
def test_generated_lessons_are_untouched(tmp: Path) -> None:
    inst = tmp / "tutorial"
    shutil.copytree(GENERATED_FIXTURE, inst)
    bundle = tmp / "bundle"
    shutil.copytree(BUNDLE_FIXTURE, bundle)
    plan = pu.make_plan(inst, bundle)
    record(plan.exit_code() == pu.EXIT_NOTHING,
           "generated: an unchanged bundle is nothing to do", repr(plan.refusals))
    append(bundle / L02, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    touched = [rel for rel in plan.classes if rel.startswith("lessons.generated")]
    record(not touched, "generated: lessons.generated/ is never classified",
           repr(touched))
    record("lessons.generated/" in plan.kept, "generated: reported as kept",
           repr(plan.kept))
    # STATE.md sits on a detour with resume_at lesson 01: 00 completed,
    # 01 active, 02 not started.
    expect_classes("generated", plan, {L02: pu.REPLACE})
    append(bundle / L00, "\nA corrected sentence.\n")
    append(bundle / L01, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("generated/detour", plan,
                   {L00: pu.DECIDE_COMPLETED, L01: pu.DECIDE_ACTIVE})


@tmpcase
def test_generated_after_removed_is_refused(tmp: Path) -> None:
    inst = tmp / "tutorial"
    shutil.copytree(GENERATED_FIXTURE, inst)
    bundle = tmp / "bundle"
    shutil.copytree(BUNDLE_FIXTURE, bundle)
    # 03-reading-files-draft says after: lessons/02-errors-and-tests.md
    (bundle / L02).unlink()
    edit(bundle / "tutorial.yaml", f"  - {L02}\n", "")
    plan = pu.make_plan(inst, bundle)
    named = [where for where, _ in plan.refusals]
    record("lessons.generated/03-reading-files-draft/LESSON.md" in named,
           "generated after: removed target refuses, naming the lesson", repr(named))
    record(plan.exit_code() == pu.EXIT_REFUSED, "generated after: exit 3")


@tmpcase
def test_optional_lesson_change_is_decide(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    append(bundle / OPT, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("optional", plan, {OPT: pu.DECIDE_UNRECORDED})


@tmpcase
def test_status_not_started_and_complete(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, active=L00, status="not-started")
    append(bundle / L00, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("not-started", plan, {L00: pu.REPLACE})
    shutil.rmtree(tmp / "bundle")
    shutil.rmtree(tmp / "workspace")
    inst, bundle = make_pair(tmp, active=L02, status="complete")
    append(bundle / L02, "\nA corrected sentence.\n")
    append(bundle / L00, "\nA corrected sentence.\n")
    plan = pu.make_plan(inst, bundle)
    expect_classes("complete", plan, {L02: pu.DECIDE_COMPLETED,
                                      L00: pu.DECIDE_COMPLETED})


@tmpcase
def test_version_ordering(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, stamp_version="2.9")
    set_version(inst, "2.9")
    set_version(bundle, "2.10")
    plan = pu.make_plan(inst, bundle)
    record(plan.bump == "MINOR" and not plan.refusals,
           '"2.10" is later than "2.9"', f"{plan.bump} {plan.refusals}")
    record(plan.exit_code() == pu.EXIT_PLAN,
           "a version move alone is a plan (the stamp must move)")
    shutil.rmtree(tmp / "bundle")
    shutil.rmtree(tmp / "workspace")
    inst, bundle = make_pair(tmp, stamp_version="2.10")
    set_version(inst, "2.10")
    set_version(bundle, "2.9")
    plan = pu.make_plan(inst, bundle)
    record(plan.bump == "older" and plan.exit_code() == pu.EXIT_REFUSED,
           '"2.9" after "2.10" is an older bundle, refused', plan.bump)


@tmpcase
def test_absent_version_reads_as_1_0(tmp: Path) -> None:
    inst, bundle = make_pair(tmp, stamp_version=None)
    set_version(inst, None)
    set_version(bundle, None)
    plan = pu.make_plan(inst, bundle)
    record(plan.old_version == "1.0" and plan.new_version == "1.0",
           "absent on both sides reads as 1.0",
           f"{plan.old_version} {plan.new_version}")
    record(plan.exit_code() == pu.EXIT_NOTHING, "absent on both sides: nothing to do")
    set_version(bundle, "1.0")
    plan = pu.make_plan(inst, bundle)
    record(plan.bump == "none" and plan.old_version == plan.new_version,
           'absent against "1.0" is the same version', plan.bump)
    changed = {r: c for r, c in plan.classes.items() if c != pu.UNCHANGED}
    record(changed == {"tutorial.yaml": pu.REPLACE},
           "absent against \"1.0\": only the manifest's new line differs",
           repr(changed))
    set_version(bundle, "2.0")
    plan = pu.make_plan(inst, bundle)
    record(plan.bump == "MAJOR" and plan.review == "per-file",
           'absent against "2.0" is MAJOR, per-file', f"{plan.bump} {plan.review}")


@tmpcase
def test_usage_errors_exit_2(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    record(run_cli(bundle, inst) == pu.EXIT_USAGE, "swapped arguments exit 2")
    record(run_cli(inst, tmp / "missing") == pu.EXIT_USAGE, "missing bundle exits 2")


@tmpcase
def test_writes_nothing(tmp: Path) -> None:
    inst, bundle = make_pair(tmp)
    set_version(bundle, "2.0")
    append(bundle / L02, "\nchanged\n")
    append(inst / "DESIGN.md", "\nlocal\n")
    before = (digest(inst), digest(bundle))
    code = run_cli(inst, bundle)
    record(code == pu.EXIT_PLAN, "writes nothing: the run made a plan", str(code))
    record((digest(inst), digest(bundle)) == before,
           "writes nothing: both trees identical after a planning run")
    shutil.rmtree(bundle / "lessons" / "01-subcommands")
    edit(bundle / "tutorial.yaml", f"  - {L01}\n", "")
    before = (digest(inst), digest(bundle))
    code = run_cli(inst, bundle)
    record(code == pu.EXIT_REFUSED, "writes nothing: the run refused", str(code))
    record((digest(inst), digest(bundle)) == before,
           "writes nothing: both trees identical after a refused run")
    # The control: the digest must be able to see a write, or its silence
    # above proves nothing.
    before = digest(inst)
    (inst / "STATE.md").write_text((inst / "STATE.md").read_text())
    record(digest(inst) != before, "writes nothing: the digest sees a rewrite")


def main() -> int:
    print("plan_update.py test suite")
    print(f"  script: {SCRIPT}")
    for test in (
        test_identical_is_nothing_to_do,
        test_minor_change_in_unstarted_lesson_is_replace,
        test_change_in_completed_lesson_is_decide,
        test_change_in_active_lesson_is_decide,
        test_design_with_local_addition_is_decide,
        test_active_lesson_removed_upstream_is_refused,
        test_lesson_removed_upstream_not_active,
        test_lesson_added_upstream,
        test_generated_lessons_are_untouched,
        test_generated_after_removed_is_refused,
        test_optional_lesson_change_is_decide,
        test_status_not_started_and_complete,
        test_version_ordering,
        test_absent_version_reads_as_1_0,
        test_usage_errors_exit_2,
        test_writes_nothing,
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
