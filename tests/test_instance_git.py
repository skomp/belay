#!/usr/bin/env python3
"""Test suite for the instance version-control policy (belay#35).

Run it with:  python3 tests/test_instance_git.py

No pytest. Every case runs skills/belay/scripts/instance_git.py as the tutor
runs it, a subprocess, against a real git repository made with `git init` in
a temporary directory. Nothing outside those directories is touched: git runs
with the system and global configuration switched off, so the developer's
own configuration can neither help nor break a case.

The positive control comes first: without `apply`, tutorial/STATE.md shows
in `git status`. Every later "does not show" means something only because of
it.

PyYAML may or may not be installed; nothing here uses it.
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
SKILL = REPO / "skills" / "belay"
SCRIPT = SKILL / "scripts" / "instance_git.py"

sys.dont_write_bytecode = True

_passed = 0
_failures: list[str] = []

ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
ENV.update({
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
})

LOCAL = ("tutorial/STATE.md", "tutorial/EVENTS.jsonl")
COMMITTED = ("tutorial/tutorial.yaml", "tutorial/COURSE.md", "tutorial/DESIGN.md",
             "tutorial/lessons/00-start.md", "tutorial/lessons.generated/side.md")

# What a learner's exclude file might already hold: git's own template text,
# a rule of their own, a blank line, a CRLF line and a negation.
EXISTING = (b"# git ls-files --others --exclude-from=.git/info/exclude\n"
            b"# Lines that start with '#' are comments.\n"
            b"*.swp\n"
            b"\n"
            b"scratch/\r\n"
            b"!keep.swp\n")


def record(ok: bool, name: str, detail: str = "") -> None:
    global _passed
    if ok:
        _passed += 1
        print(f"  ok    {name}")
    else:
        _failures.append(f"{name}: {detail}" if detail else name)
        print(f"  FAIL  {name}{': ' + detail if detail else ''}")


def git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], env=ENV,
                          capture_output=True, text=True, check=False)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=ENV,
                          capture_output=True, text=True, check=False)


def new_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    result = git(root, "init", "-q", "-b", "main")
    assert result.returncode == 0, result.stderr
    return root


def materialize(workspace: Path) -> None:
    """The files of a materialized instance, enough for git to see."""
    for rel in (*COMMITTED, *LOCAL):
        path = workspace / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{rel}\n")


def exclude_of(cwd: Path) -> Path:
    out = git(cwd, "rev-parse", "--git-path", "info/exclude").stdout.strip()
    path = Path(out)
    return path if path.is_absolute() else cwd / path


def porcelain(cwd: Path) -> set[str]:
    out = git(cwd, "status", "--porcelain", "-uall").stdout
    return {line[3:] for line in out.splitlines()}


def nothing_staged(cwd: Path) -> bool:
    return git(cwd, "diff", "--cached", "--name-only").stdout == ""


# --------------------------------------------------------------------------


def test_positive_control(tmp: Path) -> None:
    print("positive control: without apply")
    ws = new_repo(tmp / "control")
    materialize(ws)
    seen = porcelain(ws)
    record(all(p in seen for p in LOCAL),
           "without apply, STATE.md and EVENTS.jsonl show in git status", repr(seen))
    record(all(p in seen for p in COMMITTED), "without apply, the course material shows")


def test_apply_appends(tmp: Path) -> None:
    print("apply appends, once")
    ws = new_repo(tmp / "append")
    materialize(ws)
    exclude = exclude_of(ws)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes(EXISTING)

    result = run("apply", str(ws))
    record(result.returncode == 0, "apply exits 0", result.stderr)
    record(result.stdout.startswith("applied:"), "apply says what it did", result.stdout)
    record("track" in result.stdout, "apply says how to opt in", result.stdout)
    after = exclude.read_bytes()
    record(after.startswith(EXISTING), "existing exclude content is byte-identical")
    record(b"# belay: personal course progress in tutorial/" in after[len(EXISTING):],
           "the block is marked as belay's")
    record(b"/tutorial/STATE.md\n" in after and b"/tutorial/EVENTS.jsonl\n" in after,
           "both personal files are excluded, anchored")
    record(b"/tutorial/\n" not in after and b"tutorial\n" not in after,
           "tutorial/ as a whole is not excluded")
    seen = porcelain(ws)
    record(not any(p in seen for p in LOCAL),
           "after apply, STATE.md and EVENTS.jsonl do not show", repr(seen))
    record(all(p in seen for p in COMMITTED),
           "after apply, every committed category still shows as untracked", repr(seen))
    record(not (ws / ".gitignore").exists(), "no .gitignore is written")
    record(nothing_staged(ws), "nothing is staged")
    record(git(ws, "rev-parse", "--verify", "-q", "HEAD").returncode != 0,
           "nothing is committed")

    again = run("apply", str(ws))
    record(again.returncode == 0 and again.stdout.startswith("unchanged:"),
           "a second apply says unchanged", again.stdout)
    record(exclude.read_bytes() == after, "a second apply adds no duplicate")
    status = run("status", str(ws))
    record("progress:     local" in status.stdout and exclude.read_bytes() == after,
           "after apply, status says local and changes nothing", status.stdout)


def test_track_removes_only_belay(tmp: Path) -> None:
    print("track removes only belay's lines")
    ws = new_repo(tmp / "track")
    materialize(ws)
    exclude = exclude_of(ws)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes(EXISTING)
    run("apply", str(ws))
    # The learner adds a rule of their own after belay's block.
    later = b"build/\n"
    with exclude.open("ab") as fh:
        fh.write(later)

    result = run("track", str(ws))
    record(result.returncode == 0 and result.stdout.startswith("tracked:"),
           "track exits 0 and says so", result.stdout + result.stderr)
    after = exclude.read_bytes()
    record(b"personal course progress" not in after, "belay's block is gone")
    record(after.startswith(EXISTING + later),
           "every other line is intact, in order, byte for byte", repr(after))
    record(after[len(EXISTING + later):].startswith(b"# belay: course progress in "
                                                   b"tutorial/ is tracked"),
           "the choice is recorded after them, as one marker line", repr(after))
    seen = porcelain(ws)
    record(all(p in seen for p in LOCAL), "after track, STATE.md shows again", repr(seen))
    record(nothing_staged(ws), "track stages nothing")

    status = run("status", str(ws))
    record(status.returncode == 0 and exclude.read_bytes() == after
           and "progress:     remote" in status.stdout,
           "status reads the recorded choice as remote and changes nothing", status.stdout)

    again = run("track", str(ws))
    record(exclude.read_bytes() == after and again.stdout.startswith("unchanged:"),
           "a second track changes nothing", again.stdout)

    back = run("apply", str(ws))
    final = exclude.read_bytes()
    record(back.stdout.startswith("applied:"), "a plain apply opts out again", back.stdout)
    record(final.startswith(EXISTING + later) and b"is tracked" not in final,
           "opting out removes the marker and nothing else", repr(final))
    record(not any(p in porcelain(ws) for p in LOCAL), "and progress is local again")


def test_track_restores_unterminated(tmp: Path) -> None:
    print("a file with no final line end")
    ws = new_repo(tmp / "noeol")
    materialize(ws)
    exclude = exclude_of(ws)
    exclude.parent.mkdir(parents=True, exist_ok=True)
    original = b"*.swp\nscratch/"
    exclude.write_bytes(original)
    joined = b" (belay added a line end before this line)"
    block = (b"# belay: personal course progress in tutorial/, kept out of git (belay#35)"
             + joined + b"\n/tutorial/STATE.md\n/tutorial/EVENTS.jsonl\n"
             b"# belay: end of personal course progress in tutorial/\n")
    marker = (b"# belay: course progress in tutorial/ is tracked, by the learner's "
              b"choice (belay#35)" + joined + b"\n")
    run("apply", str(ws))
    record(exclude.read_bytes() == original + b"\n" + block,
           "apply adds one line end, says so, and keeps every original byte",
           repr(exclude.read_bytes()))
    record(not any(p in porcelain(ws) for p in LOCAL), "and the rules take effect")
    run("track", str(ws))
    record(exclude.read_bytes() == original + b"\n" + marker,
           "track removes the block and the line end it added, then appends the marker",
           repr(exclude.read_bytes()))
    run("apply", str(ws))
    record(exclude.read_bytes() == original + b"\n" + block,
           "opting out again gives the same bytes as the first apply",
           repr(exclude.read_bytes()))


def test_track_without_apply_and_missing_file(tmp: Path) -> None:
    print("no exclude file yet")
    ws = new_repo(tmp / "missing")
    materialize(ws)
    exclude = exclude_of(ws)
    if exclude.exists():
        exclude.unlink()
    if exclude.parent.exists():
        exclude.parent.rmdir()
    result = run("apply", str(ws))
    record(result.returncode == 0 and exclude.is_file(),
           "apply creates the exclude file when git's template left none", result.stderr)
    record(exclude.read_bytes().startswith(b"# belay: personal course progress"),
           "and it holds only belay's block")


def test_not_git(tmp: Path) -> None:
    print("a workspace that is not a git repository")
    ws = tmp / "plain"
    materialize(ws)
    before = sorted(p.relative_to(ws) for p in ws.rglob("*"))
    for command in (["apply"], ["track"], ["status"]):
        result = run(*command, str(ws))
        record(result.returncode == 0, f"{' '.join(command)}: exit 0", result.stderr)
        lines = result.stdout.strip().splitlines()
        record(len(lines) == 1 and "not inside a git repository" in lines[0],
               f"{' '.join(command)}: one plain sentence", result.stdout)
        record(result.stderr == "", f"{' '.join(command)}: nothing on stderr", result.stderr)
    after = sorted(p.relative_to(ws) for p in ws.rglob("*"))
    record(before == after, "no file is created", repr(set(after) - set(before)))


def test_worktree(tmp: Path) -> None:
    print("a linked worktree")
    main = new_repo(tmp / "main")
    (main / "README").write_text("x\n")
    git(main, "add", "README")
    record(git(main, "commit", "-q", "-m", "init").returncode == 0, "setup: a first commit")
    wt = tmp / "linked"
    record(git(main, "worktree", "add", "-q", str(wt)).returncode == 0, "setup: worktree add")
    record((wt / ".git").is_file(), "setup: the worktree's .git is a file, not a directory")
    materialize(wt)
    record(all(p in porcelain(wt) for p in LOCAL), "control: STATE.md shows in the worktree")
    result = run("apply", str(wt))
    record(result.returncode == 0, "apply in a worktree exits 0", result.stderr)
    resolved = exclude_of(wt).resolve()
    record(resolved == (main / ".git" / "info" / "exclude").resolve(),
           "git resolves the worktree's exclude to the common directory", str(resolved))
    record(b"/tutorial/STATE.md" in resolved.read_bytes(), "the block lands there")
    record(not any(p in porcelain(wt) for p in LOCAL),
           "after apply, the worktree hides STATE.md and EVENTS.jsonl", repr(porcelain(wt)))
    record(all(p in porcelain(wt) for p in COMMITTED), "and shows the course material")
    record(nothing_staged(wt), "nothing is staged in the worktree")


def test_subdirectory_workspace(tmp: Path) -> None:
    print("a workspace below the top of the repository")
    top = new_repo(tmp / "mono")
    ws = top / "courses" / "rust"
    materialize(ws)
    materialize(top)          # a second, unrelated instance at the top
    result = run("apply", str(ws))
    record(result.returncode == 0, "apply exits 0", result.stderr)
    data = exclude_of(top).read_bytes()
    record(b"/courses/rust/tutorial/STATE.md\n" in data,
           "patterns are anchored at the top of the work tree", repr(data))
    seen = porcelain(top)
    record("courses/rust/tutorial/STATE.md" not in seen, "the workspace's STATE.md is hidden")
    record("tutorial/STATE.md" in seen,
           "control: the top-level instance's STATE.md is not", repr(seen))
    record(run("apply", str(top)).returncode == 0, "the second instance gets its own block")
    data = exclude_of(top).read_bytes()
    record(data.count(b"# belay: personal course progress") == 2, "two blocks, one each")
    run("track", str(ws))
    data = exclude_of(top).read_bytes()
    record(b"/tutorial/STATE.md\n" in data and b"/courses/rust/tutorial/STATE.md" not in data,
           "track removes only that workspace's block", repr(data))


def test_already_committed(tmp: Path) -> None:
    print("progress that is already committed")
    ws = new_repo(tmp / "committed")
    materialize(ws)
    git(ws, "add", "tutorial/STATE.md")
    git(ws, "commit", "-q", "-m", "learner commits progress")
    status = run("status", str(ws))
    record("progress:     undecided" in status.stdout
           and "tutorial/STATE.md: committed" in status.stdout,
           "a committed STATE.md is not a recorded choice: status says undecided",
           status.stdout)
    explicit = run("apply", str(ws))
    record("note: tutorial/STATE.md is already committed" in explicit.stdout,
           "an explicit apply says an exclude cannot hide a tracked file", explicit.stdout)
    record(git(ws, "ls-files", "tutorial/STATE.md").stdout.strip() == "tutorial/STATE.md",
           "and does not untrack it")
    record(nothing_staged(ws), "nothing is staged")


def test_track_records_choice_without_block(tmp: Path) -> None:
    print("remote is recorded though no block was ever applied")
    ws = new_repo(tmp / "remote")
    materialize(ws)
    exclude = exclude_of(ws)
    if exclude.exists():
        exclude.unlink()
    before = run("status", str(ws)).stdout
    record("progress:     undecided" in before, "a fresh instance is undecided", before)
    result = run("track", str(ws))
    record(result.returncode == 0 and result.stdout.startswith("tracked:"),
           "track on an undecided instance succeeds", result.stdout + result.stderr)
    data = exclude.read_bytes()
    record(b"is tracked" in data and b"personal course" not in data,
           "it appends the marker and no block", repr(data))
    after = run("status", str(ws)).stdout
    record("progress:     remote" in after,
           "status then reports the choice, so the tutor does not ask again", after)
    seen = porcelain(ws)
    record(all(p in seen for p in LOCAL), "STATE.md and EVENTS.jsonl show in git status", repr(seen))
    record(nothing_staged(ws), "nothing is staged")
    run("apply", str(ws))
    switched = run("status", str(ws)).stdout
    record("progress:     local" in switched and b"is tracked" not in exclude.read_bytes(),
           "a later apply switches to local and removes the marker", switched)


def test_edited_block(tmp: Path) -> None:
    print("a block edited by hand")
    ws = new_repo(tmp / "edited")
    materialize(ws)
    run("apply", str(ws))
    exclude = exclude_of(ws)
    edited = exclude.read_bytes().replace(b"/tutorial/EVENTS.jsonl\n", b"/tutorial/x\n")
    exclude.write_bytes(edited)
    for command in ("track", "apply", "status"):
        result = run(command, str(ws))
        record(result.returncode == 1 and "not as belay wrote it" in result.stderr,
               f"{command} refuses with exit 1", result.stdout + result.stderr)
    record(exclude.read_bytes() == edited, "the file is left exactly as it was")


def test_status(tmp: Path) -> None:
    print("status")
    ws = new_repo(tmp / "status")
    materialize(ws)
    out = run("status", str(ws)).stdout
    record("undecided" in out and "tutorial/STATE.md: shows in git status" in out,
           "before apply: undecided, and STATE.md shows", out)
    run("apply", str(ws))
    out = run("status", str(ws)).stdout
    record("progress:     local" in out and "tutorial/STATE.md: ignored" in out,
           "after apply: local, and STATE.md ignored", out)
    run("track", str(ws))
    out = run("status", str(ws)).stdout
    record("progress:     remote" in out, "after track: remote", out)


def test_documents() -> None:
    print("documents")
    words = len((SKILL / "SKILL.md").read_text(encoding="utf-8").split())
    record(words <= 3000, "SKILL.md stays at or under 3,000 words", str(words))
    lifecycle = (SKILL / "references" / "state-lifecycle.md").read_text(encoding="utf-8")
    protocol = (SKILL / "references" / "runner-protocol.md").read_text(encoding="utf-8")
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    record("scripts/instance_git.py apply" in lifecycle and "scripts/instance_git.py track" in lifecycle,
           "state-lifecycle.md maps both answers to a command")
    record("instance_git.py status" in protocol and "--if-undecided" not in protocol + lifecycle,
           "runner-protocol.md tells a resume to read status, and the flag is gone")
    record("info/exclude" in readme and "remote" in readme and "local" in readme,
           "README.md names the two choices and the mechanism")
    record("belay#35's question" not in lifecycle,
           "the provisional answer in section 12 is gone")
    source = SCRIPT.read_text(encoding="utf-8")
    record(all(ord(c) < 128 for c in source), "the script is ASCII")
    for forbidden in ('"add"', '"commit"', '"rm"', "shell=True", ".gitignore\""):
        record(forbidden not in source, f"the script never uses {forbidden}")


def main() -> int:
    print("instance version-control test suite")
    tmp_root = Path(tempfile.mkdtemp(prefix="belay-instance-git-"))
    try:
        for test in (
            test_positive_control,
            test_apply_appends,
            test_track_removes_only_belay,
            test_track_restores_unterminated,
            test_track_without_apply_and_missing_file,
            test_not_git,
            test_worktree,
            test_subdirectory_workspace,
            test_already_committed,
            test_track_records_choice_without_block,
            test_edited_block,
            test_status,
        ):
            try:
                test(tmp_root)
            except Exception:  # pragma: no cover
                record(False, test.__name__, "raised:\n" + traceback.format_exc())
        try:
            test_documents()
        except Exception:  # pragma: no cover
            record(False, "test_documents", "raised:\n" + traceback.format_exc())
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

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
