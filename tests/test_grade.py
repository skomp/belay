#!/usr/bin/env python3
"""Test suite for skills/belay/scripts/grade.py - the scheme and the grade store.

Run it with:  python3 tests/test_grade.py

No pytest. Every case points XDG_DATA_HOME at a temporary directory, so the
real home is never touched, and asserts VALUES: paths, exit codes, what is left
on disk. Each refusal has a control showing the same call succeeds without the
fault.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "skills" / "belay" / "scripts"
SCRIPT = SCRIPTS / "grade.py"
FIXTURE = HERE / "fixtures" / "rust-cli-basics"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import grade as gr  # noqa: E402

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


class Env:
    """XDG_DATA_HOME pointed at a temp directory for the length of a block."""

    def __init__(self, data_home: Path) -> None:
        self.data_home = data_home

    def __enter__(self) -> "Env":
        self.old = os.environ.get("XDG_DATA_HOME")
        os.environ["XDG_DATA_HOME"] = str(self.data_home)
        return self

    def __exit__(self, *exc) -> None:
        if self.old is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = self.old


def run_cli(data_home: Path, *args: str) -> tuple[int, str, str]:
    env = dict(os.environ, XDG_DATA_HOME=str(data_home))
    proc = subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                          capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def refused(func, *args) -> str | None:
    try:
        func(*args)
    except gr.GradeError as exc:
        return str(exc)
    return None


GRADING = """
grading:
  image: python:3.12-slim
  network: true
  env: [ANTHROPIC_API_KEY]
  timeout_minutes: 15
  validators:
    cargo-test: { points: 30, gate: true }
    has-test: { points: 20 }
  rubric:
    - id: failure-handling
      points: 15
      standard: Every call has a timeout.
      paths: [src/**]
    - id: design
      points: 10
      standard: The choice is justified.
"""


def make_bundle(tmp: Path, grading: str | None) -> Path:
    bundle = tmp / "bundle"
    shutil.copytree(FIXTURE, bundle)
    if grading:
        with (bundle / "tutorial.yaml").open("a", encoding="utf-8") as handle:
            handle.write(grading)
    return bundle


# --------------------------------------------------------------------------


def test_cohort_from_url_forms() -> None:
    same = [
        "https://github.com/acme/team-7.git",
        "https://github.com/acme/team-7",
        "https://github.com/acme/team-7/",
        "https://user:tok@GitHub.com/acme/team-7.git",
        "ssh://git@github.com/acme/team-7.git",
        "ssh://git@github.com:22/acme/team-7.git",
        "git@github.com:acme/team-7.git",
        "git@github.com:acme/team-7",
    ]
    names = {gr.cohort_name(u) for u in same}
    record(len(names) == 1, "https, ssh and scp forms of one repository are one cohort",
           str(sorted(names)))
    name = names.pop()
    record(name.startswith("acme-team-7-") and len(name) == len("acme-team-7-") + 10,
           "the cohort name is a readable slug plus a ten-character hash", name)
    other = [
        "https://github.com/acme/team-8.git",
        "https://github.com/acme-team/7.git",   # slugs alike, must not collide
        "https://gitlab.com/acme/team-7.git",   # another host
        "https://github.com/Acme/team-7.git",   # paths are case sensitive
    ]
    all_names = {name} | {gr.cohort_name(u) for u in other}
    record(len(all_names) == 5, "different URLs, even slug-alike ones, never collide",
           str(sorted(all_names)))
    hostile = ["https://h/../../etc/x", "git@h:../../x", "https://h/a b/c;d", "https://h/-x/y"]
    for url in hostile:
        n = gr.cohort_name(url)
        record(("/" not in n and "\\" not in n and ".." not in n and not n.startswith("-")
                and n not in ("", ".")), f"cohort name for {url!r} is one safe component", n)
    record(refused(gr.cohort_name, "") is not None, "an empty URL is refused")


def test_store_dir_follows_xdg() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        with Env(Path(tmp) / "data"):
            path = gr.store_dir("https://github.com/acme/team-7.git", "m1")
            expected = (Path(tmp) / "data" / "belay" / "grading"
                        / gr.cohort_name("https://github.com/acme/team-7.git") / "m1")
            record(path == expected, "store_dir is <XDG_DATA_HOME>/belay/grading/<cohort>/<module>",
                   str(path))
            record(not (Path(tmp) / "data").exists(), "store_dir creates nothing")
            for bad in ("../x", "a/b", "..", ""):
                record(refused(gr.store_dir, "https://h/o/r", bad) is not None,
                       f"module id {bad!r} is refused")
        old = os.environ.pop("XDG_DATA_HOME", None)
        try:
            home = Path(tmp) / "home"
            os.environ["HOME"] = str(home)
            record(gr.data_home() == home / ".local" / "share",
                   "without XDG_DATA_HOME the base is ~/.local/share", str(gr.data_home()))
        finally:
            if old is not None:
                os.environ["XDG_DATA_HOME"] = old


def test_work_tree_refusal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        repo = tmp / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        with Env(repo / "data"):
            msg = refused(gr.store_dir, "https://h/o/r", "m1")
            record(msg is not None and "Git work tree" in msg and str(repo) in msg,
                   "XDG_DATA_HOME inside a work tree is refused, naming the tree", str(msg))
        (repo / "sub" / "deep").mkdir(parents=True)
        record(refused(gr.refuse_work_tree, repo / "sub" / "deep" / "not" / "yet") is not None,
               "a path that does not exist yet is judged by its nearest existing parent")
        # a linked worktree has a .git FILE, not a directory
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", str(tmp / "wt")],
                       check=True)
        record(refused(gr.refuse_work_tree, tmp / "wt" / "d") is not None,
               "a linked worktree (a .git file) is refused too")
        link = tmp / "link"
        link.symlink_to(repo)
        record(refused(gr.refuse_work_tree, link / "d") is not None,
               "a symlink into a work tree is refused")
        # control
        outside = tmp / "plain" / "data"
        outside.parent.mkdir()
        with Env(outside):
            record(refused(gr.store_dir, "https://h/o/r", "m1") is None,
                   "control: a directory outside any work tree is accepted")
        code, out, err = run_cli(repo / "data", "forget", "anything")
        record(code == gr.EXIT_REFUSED and "work tree" in err,
               "forget refuses too, with exit 1", f"{code} {err}")


def test_forget() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        root = data / "belay" / "grading"
        keep = root / "keep-me-1234567890" / "m1"
        gone = root / "gone-1234567890" / "m1"
        for d in (keep, gone):
            d.mkdir(parents=True)
            (d / "final.json").write_text("{}")
        outside = Path(tmp) / "outside"
        outside.mkdir()
        (outside / "precious").write_text("x")
        code, out, err = run_cli(data, "forget", "gone-1234567890")
        record(code == 0 and "deleted" in out, "forget deletes the named cohort", f"{code} {out}{err}")
        record(not (root / "gone-1234567890").exists(), "the named cohort is gone")
        record((keep / "final.json").exists(), "another cohort is untouched")
        code, out, err = run_cli(data, "forget", "gone-1234567890")
        record(code == 0 and "no grades stored" in out and "nothing deleted" in out,
               "forgetting a cohort that is not there says so", f"{code} {out}")
        for bad in ("../outside", "a/b", "..", ".", "keep-me-1234567890/m1", "/etc",
                    "x..y", "..\\outside", "-rf"):
            code, out, err = run_cli(data, "forget", bad)
            record(code in (gr.EXIT_REFUSED, gr.EXIT_USAGE) and "deleted" not in out,
                   f"forget refuses {bad!r}", f"{code} {out}{err}")
        record((outside / "precious").exists() and (keep / "final.json").exists(),
               "after every refusal nothing outside or beside was deleted")
        # a symlinked cohort entry is not followed
        (root / "evil").symlink_to(outside)
        code, out, err = run_cli(data, "forget", "evil")
        record((outside / "precious").exists(), "forget never follows a symlink out of the store",
               f"{code} {out}{err}")


def test_scheme() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = make_bundle(Path(tmp), GRADING)
        s = gr.load_scheme(bundle)
        record(s.module == "rust-cli-basics" and s.image == "python:3.12-slim"
               and s.network is True and s.env == ("ANTHROPIC_API_KEY",)
               and s.timeout_minutes == 15, "scalar keys are read", str(s))
        record([(v.name, v.points, v.gate) for v in s.validators]
               == [("cargo-test", 30, True), ("has-test", 20, False)],
               "validator shares are read with points and gate", str(s.validators))
        record(s.validators[0].declared.get("kind") == "command",
               "a share carries the bundle's own validator declaration")
        record([(c.id, c.points, c.paths) for c in s.rubric]
               == [("failure-handling", 15, ("src/**",)), ("design", 10, None)],
               "rubric criteria are read; paths default to None", str(s.rubric))
        record(s.max_total == 75, "max_total adds validators and rubric", str(s.max_total))
        plain = gr.load_scheme(make_bundle(Path(tmp) / "b2", "grading:\n  validators: {}\n"))
        record(plain.network is False and plain.env == () and plain.image is None,
               "defaults: network false, no env, no image")
        msg = refused(gr.load_scheme, make_bundle(Path(tmp) / "b3", None))
        record(msg is not None and "`grading`" in msg, "a bundle with no grading is refused, naming the key",
               str(msg))
        msg = refused(gr.load_scheme, Path(tmp) / "nowhere")
        record(msg is not None, "a directory with no tutorial.yaml is refused")


def test_cli() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, out, err = run_cli(Path(tmp), "--help")
        record(code == 0 and "Grade a cohort" in out and "forget" in out, "--help works", out[:80])
        code, out, err = run_cli(Path(tmp), "forget")
        record(code == 2, "forget with no argument is a usage error", str(code))
        code, out, err = run_cli(Path(tmp), "bogus")
        record(code == 2, "an unknown subcommand is a usage error", str(code))
        record(not (Path(tmp) / "belay").exists(), "no command wrote anything into the store")


def main() -> int:
    for test in (test_cohort_from_url_forms, test_store_dir_follows_xdg, test_work_tree_refusal,
                 test_forget, test_scheme, test_cli):
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
