#!/usr/bin/env python3
"""Which instance files git sees: the version-control policy (belay#35).

Usage:
    instance_git.py apply <workspace>     the learner chose "local": keep their
                                          progress out of git in this checkout
    instance_git.py track <workspace>     the learner chose "remote": record that
                                          their progress is committed and pushed
    instance_git.py status <workspace>    say what is in force; "undecided" means the
                                          tutor has not asked the learner yet
    instance_git.py --help

The policy, references/state-lifecycle.md section 3.3:

  * course material, always ordinary committed content: tutorial/tutorial.yaml,
    COURSE.md, DESIGN.md, lessons/ and lessons.generated/. Nothing here
    touches them, so they appear in `git status` as untracked files like any
    other new file.
  * progress, the learner's choice, asked once: tutorial/STATE.md and
    tutorial/EVENTS.jsonl. "remote" commits them with the learner's work and
    pushes them. "local" keeps them on this machine.

A course repository belongs to one learner. The local rule goes in the
checkout's own exclude file, never in .gitignore: it is a preference about one
machine, and .gitignore reaches every clone. The file is found with `git rev-parse --git-path info/exclude`,
which is right in a linked worktree and in a submodule, where `.git` is not a
directory. In a linked worktree that file is the main repository's, so the
rule covers every worktree of that repository.

The exclude file is also where the learner's choice is recorded, because it
is per checkout like the choice itself. `apply` appends a marked block;
`track` removes exactly that block and appends one marker line saying the
learner chose "remote", so `track` records a choice even when no block was
ever applied. `status` reports "undecided" only when neither is there, and that
is the one case in which the tutor asks. A later `apply` is the learner
changing their mind: it removes the marker line and appends the block.

Every edit is append-only, or removes exactly lines this script wrote. Lines
written by anyone else are never rewritten or reordered. When the file's last
line has no line end, a line end is added before belay's first line and that
line says so, so the removal can restore the file byte for byte.

Nothing here writes to git history: no add, no commit, no rm. A file git
already tracks is not hidden by an exclude rule; the script says so and
leaves it, because untracking is the learner's call.

A workspace that is not inside a git work tree, or a machine with no git,
gets one plain sentence on stdout and exit 0.

Exit codes:
    0  done, including "not a git repository" and "nothing to change"
    1  belay's block in the exclude file was edited by hand; nothing changed
    2  usage or I/O error

Stdlib only. Runs git with an argument list and never through a shell.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXIT_OK = 0
EXIT_EDITED = 1
EXIT_USAGE = 2

INSTANCE_DIR = "tutorial"
LOCAL_FILES = ("STATE.md", "EVENTS.jsonl")
COMMITTED = ("tutorial.yaml", "COURSE.md", "DESIGN.md", "lessons/", "lessons.generated/")

ISSUE = "belay#35"
JOINED = " (belay added a line end before this line)"

# Environment variables that would point git at some other repository than
# the one holding the workspace. The workspace decides, so they are dropped.
_GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                      "GIT_OBJECT_DIRECTORY", "GIT_NAMESPACE")


class NotGit(Exception):
    """The workspace is not in a git work tree, or git is not installed."""


class EditedByHand(Exception):
    """belay's block is present but not as belay wrote it."""


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def _git(workspace: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}
    try:
        return subprocess.run(["git", "-C", str(workspace), *args], env=env,
                              capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise NotGit("git is not installed on this machine") from exc


@dataclass
class Repo:
    workspace: Path
    prefix: str          # the workspace's path from the work tree's top, "" or "a/b/"
    exclude: Path        # the checkout's info/exclude

    @property
    def instance_rel(self) -> str:
        """The instance directory as git names it from the top, "tutorial/"."""
        return f"{self.prefix}{INSTANCE_DIR}/"

    def local_paths(self) -> list[str]:
        """Workspace-relative paths of the personal-progress files."""
        return [f"{INSTANCE_DIR}/{name}" for name in LOCAL_FILES]


def find_repo(workspace: Path) -> Repo:
    inside = _git(workspace, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise NotGit(f"{workspace} is not inside a git repository")
    prefix = _git(workspace, "rev-parse", "--show-prefix")
    path = _git(workspace, "rev-parse", "--git-path", "info/exclude")
    if prefix.returncode != 0 or path.returncode != 0:
        raise OSError((prefix.stderr or path.stderr).strip() or "git rev-parse failed")
    exclude = Path(path.stdout.rstrip("\n"))
    if not exclude.is_absolute():
        exclude = workspace / exclude
    return Repo(workspace, prefix.stdout.rstrip("\n"), exclude)


def is_tracked(repo: Repo, rel: str) -> bool:
    result = _git(repo.workspace, "ls-files", "--", rel)
    return result.returncode == 0 and result.stdout.strip() != ""


def is_ignored(repo: Repo, rel: str) -> bool:
    return _git(repo.workspace, "check-ignore", "-q", "--", rel).returncode == 0


# --------------------------------------------------------------------------
# The exclude file
# --------------------------------------------------------------------------


def _escape(path: str) -> str:
    """A path as a literal gitignore pattern."""
    out = "".join("\\" + c if c in "*?[\\" else c for c in path)
    if out.endswith(" "):
        out = out[:-1] + "\\ "
    return out


def begin_line(repo: Repo) -> str:
    return f"# belay: personal course progress in {repo.instance_rel}, kept out of git ({ISSUE})"


def end_line(repo: Repo) -> str:
    return f"# belay: end of personal course progress in {repo.instance_rel}"


def tracked_line(repo: Repo) -> str:
    return (f"# belay: course progress in {repo.instance_rel} is tracked, "
            f"by the learner's choice ({ISSUE})")


def block_lines(repo: Repo) -> list[str]:
    patterns = ["/" + _escape(repo.instance_rel + name) for name in LOCAL_FILES]
    return [begin_line(repo), *patterns, end_line(repo)]


@dataclass
class Found:
    start: int           # index of the first line
    stop: int            # one past the last line
    joined: bool         # the first line carries JOINED


def _strip(line: bytes) -> str:
    return line.rstrip(b"\r\n").decode("utf-8", errors="surrogateescape")


def find_block(lines: list[bytes], repo: Repo) -> Found | None:
    want = block_lines(repo)
    for i, line in enumerate(lines):
        text = _strip(line)
        if text not in (want[0], want[0] + JOINED):
            continue
        body = [_strip(x) for x in lines[i + 1:i + len(want)]]
        if body != want[1:]:
            raise EditedByHand(
                f"belay's block for {repo.instance_rel} in {repo.exclude} is not "
                f"as belay wrote it, so belay will not remove or rewrite it")
        return Found(i, i + len(want), text.endswith(JOINED))
    return None


def find_marker(lines: list[bytes], repo: Repo) -> Found | None:
    want = tracked_line(repo)
    for i, line in enumerate(lines):
        text = _strip(line)
        if text in (want, want + JOINED):
            return Found(i, i + 1, text.endswith(JOINED))
    return None


def remove(lines: list[bytes], found: Found) -> list[bytes]:
    """The lines without belay's chunk. When belay had added a line end before
    it and the chunk was the end of the file, that line end goes too."""
    kept = lines[:found.start] + lines[found.stop:]
    if found.joined and found.stop == len(lines) and kept:
        last = kept[-1]
        if last.endswith(b"\n"):
            kept[-1] = last[:-1]
    return kept


def append(data: bytes, chunk: list[str]) -> bytes:
    """`data` unchanged, then the chunk. Never touches a byte of `data`."""
    if data and not data.endswith(b"\n"):
        chunk = [chunk[0] + JOINED, *chunk[1:]]
        data += b"\n"
    return data + "".join(line + "\n" for line in chunk).encode(
        "utf-8", errors="surrogateescape")


def read_exclude(repo: Repo) -> bytes:
    try:
        return repo.exclude.read_bytes()
    except FileNotFoundError:
        return b""


def write_exclude(repo: Repo, data: bytes) -> None:
    repo.exclude.parent.mkdir(parents=True, exist_ok=True)
    tmp = repo.exclude.with_name(repo.exclude.name + ".belay-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, repo.exclude)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _already_tracked(repo: Repo) -> list[str]:
    return [p for p in repo.local_paths() if is_tracked(repo, p)]


def _say_tracked(paths: list[str]) -> None:
    for p in paths:
        print(f"note: {p} is already committed, and an exclude rule does not hide a "
              f"file git already tracks. Untracking it is your choice: "
              f"git rm --cached {p}")


def cmd_apply(repo: Repo) -> int:
    data = read_exclude(repo)
    lines = data.splitlines(keepends=True)
    block = find_block(lines, repo)
    marker = find_marker(lines, repo)
    names = " and ".join(repo.local_paths())
    committed = _already_tracked(repo)

    if block is not None:
        if marker is not None:
            data = b"".join(remove(lines, marker))
            write_exclude(repo, data)
        print(f"unchanged: {names} are already kept out of git in this checkout "
              f"({repo.exclude}).")
        return EXIT_OK

    if marker is not None:
        data = b"".join(remove(lines, marker))
    write_exclude(repo, append(data, block_lines(repo)))
    print(f"applied: {names} stay out of git in this checkout ({repo.exclude}); "
          f"the rest of {INSTANCE_DIR}/ is course material to commit. "
          f"To commit your progress too: instance_git.py track.")
    _say_tracked(committed)
    return EXIT_OK


def cmd_track(repo: Repo) -> int:
    data = read_exclude(repo)
    lines = data.splitlines(keepends=True)
    block = find_block(lines, repo)
    marker = find_marker(lines, repo)
    names = " and ".join(repo.local_paths())
    if block is None and marker is not None:
        print(f"unchanged: {names} are already tracked by your choice.")
        return EXIT_OK
    if block is not None:
        lines = remove(lines, block)
    if marker is None:
        data = append(b"".join(lines), [tracked_line(repo)])
    else:
        data = b"".join(lines)
    write_exclude(repo, data)
    ignored = [p for p in repo.local_paths() if is_ignored(repo, p)]
    print(f"tracked: {names} are the learner's to commit and push, and the choice is "
          f"recorded. To keep them local instead: instance_git.py apply.")
    for p in ignored:
        print(f"note: {p} is still ignored by another rule: "
              f"git check-ignore -v {p} names it.")
    return EXIT_OK


def cmd_status(repo: Repo) -> int:
    lines = read_exclude(repo).splitlines(keepends=True)
    block = find_block(lines, repo)
    marker = find_marker(lines, repo)
    if block is not None:
        choice = "local (belay's block is in the exclude file)"
    elif marker is not None:
        choice = "remote (the learner chose to commit and push their progress)"
    else:
        choice = "undecided (no belay block and no recorded choice)"
    print(f"exclude file: {repo.exclude}")
    print(f"progress:     {choice}")
    for rel in repo.local_paths():
        if is_tracked(repo, rel):
            state = "committed"
        elif is_ignored(repo, rel):
            state = "ignored"
        elif (repo.workspace / rel).exists():
            state = "shows in git status"
        else:
            state = "absent"
        print(f"  {rel}: {state}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="instance_git.py",
        description="Record how a Belay learner's progress (tutorial/STATE.md, "
        "tutorial/EVENTS.jsonl) is kept: local, out of git in this checkout, or "
        "remote, committed and pushed by the learner. Writes only the checkout's "
        "info/exclude; never stages, commits or pushes.",
    )
    parser.add_argument("command", choices=("apply", "track", "status"))
    parser.add_argument("workspace", help="the workspace root, the directory holding tutorial/")
    args = parser.parse_args(argv)
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"error: {workspace} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    try:
        repo = find_repo(workspace)
    except NotGit as exc:
        print(f"{str(exc)[0].upper()}{str(exc)[1:]}, so belay sets no version-control "
              f"rule: every instance file stays on disk and nothing is ignored.")
        return EXIT_OK
    try:
        if args.command == "apply":
            return cmd_apply(repo)
        if args.command == "track":
            return cmd_track(repo)
        return cmd_status(repo)
    except EditedByHand as exc:
        print(f"error: {exc}. Nothing changed.", file=sys.stderr)
        return EXIT_EDITED
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
