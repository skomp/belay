#!/usr/bin/env python3
"""Test suite for the plugin's bin/ wrappers - belay-catalogs and the rest.

Run it with:  python3 tests/test_bin_wrappers.py

No pytest. Each wrapper is started the way a host starts it - by a bare name
found on PATH, from a working directory outside this repository - and also by
its path and through a symlink. Every case asserts that the wrapped script
really ran, by the script's own --help text, and that its exit status, stdout
and stderr arrive unchanged. Each assertion has a control showing that it can
fail: a copy of a wrapper with no plugin tree behind it.

Why the wrappers exist is belay#78: under
permissions.blockReadsOutsideWorkingDirectories, `python3 <plugin cache>/...`
asks the learner every time, and a bare command whose arguments stay inside
the workspace does not.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
BIN = REPO / "bin"
SKILL = REPO / "skills" / "belay"
SCRIPTS = SKILL / "scripts"

# wrapper -> (script, a phrase from that script's own --help description)
WRAPPERS = {
    "belay-catalogs": ("catalogs.py", "Fetch, cache and merge"),
    "belay-validate": ("validate_bundle.py", "Structurally validate a Belay"),
    "belay-plan-update": ("plan_update.py", "Plan, without applying"),
    "belay-evidence": ("evidence.py", "Repair, compact or summarise"),
}

# Scripts that are libraries, not commands, and so have no wrapper.
LIBRARIES = {"yamlite.py"}

sys.dont_write_bytecode = True

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


def run(argv: list[str], cwd: Path, path_prefix: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=60)


def ran_script(proc: subprocess.CompletedProcess, script: str, phrase: str) -> bool:
    """The output is the named script's own --help, not merely exit status 0."""
    return (
        proc.returncode == 0
        and proc.stdout.startswith(f"usage: {script}")
        and phrase in proc.stdout
    )


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------


def test_every_script_has_a_wrapper() -> None:
    scripts = {p.name for p in SCRIPTS.glob("*.py")} - LIBRARIES
    wrapped = {script for script, _ in WRAPPERS.values()}
    record(scripts == wrapped, "every runner script has exactly one wrapper",
           f"scripts {sorted(scripts)}, wrapped {sorted(wrapped)}")
    present = {p.name for p in BIN.iterdir()} if BIN.is_dir() else set()
    record(present == set(WRAPPERS), "bin/ holds the four wrappers and nothing else",
           f"found {sorted(present)}")


def test_wrappers_are_executable_posix_sh() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-s", "--", "bin"], cwd=REPO, capture_output=True, text=True
    )
    modes = {}
    for line in tracked.stdout.splitlines():
        meta, _, path = line.partition("\t")
        modes[Path(path).name] = meta.split()[0]
    for name in WRAPPERS:
        path = BIN / name
        record(os.access(path, os.X_OK), f"{name} is executable on disk")
        if tracked.returncode == 0 and name in modes:
            record(modes[name] == "100755", f"{name} is mode 100755 in git", modes[name])
        else:
            print(f"  note  {name} is not in the git index yet; mode checked on disk only")
        text = path.read_text(encoding="utf-8")
        record(text.startswith("#!/bin/sh\n"), f"{name} starts with #!/bin/sh")
        record(text.isascii(), f"{name} is ASCII")
        check = subprocess.run(["sh", "-n", str(path)], capture_output=True, text=True)
        record(check.returncode == 0, f"{name} parses under sh -n", check.stderr.strip())


def test_by_path_from_another_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        for name, (script, phrase) in WRAPPERS.items():
            proc = run([str(BIN / name), "--help"], cwd=Path(tmp))
            record(ran_script(proc, script, phrase), f"{name} by absolute path runs {script}",
                   f"rc={proc.returncode} stdout={proc.stdout[:80]!r} stderr={proc.stderr[:200]!r}")


def test_by_bare_name_on_path() -> None:
    """The way Claude Code starts it: a bare name, the plugin's bin/ on PATH."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        for name, (script, phrase) in WRAPPERS.items():
            proc = run([name, "--help"], cwd=workspace, path_prefix=BIN)
            record(ran_script(proc, script, phrase), f"{name} by bare name on PATH runs {script}",
                   f"rc={proc.returncode} stdout={proc.stdout[:80]!r} stderr={proc.stderr[:200]!r}")
            # Through a shell, too, which is what the Bash tool is.
            proc = run(["sh", "-c", f"{name} --help"], cwd=workspace, path_prefix=BIN)
            record(ran_script(proc, script, phrase), f"{name} looked up on PATH by sh runs {script}",
                   f"rc={proc.returncode} stderr={proc.stderr[:200]!r}")
        # A relative PATH entry makes $0 relative; it must still resolve.
        proc = run(["sh", "-c", "belay-evidence --help"], cwd=REPO, path_prefix=Path("bin"))
        record(ran_script(proc, *WRAPPERS["belay-evidence"]),
               "a relative PATH entry (bin) still finds the script",
               f"rc={proc.returncode} stderr={proc.stderr[:200]!r}")


def test_through_a_symlink() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        links = Path(tmp) / "links"
        links.mkdir()
        script, phrase = WRAPPERS["belay-catalogs"]
        (links / "absolute").symlink_to(BIN / "belay-catalogs")
        (links / "relative").symlink_to("absolute")  # a chain, the second link relative
        for link in ("absolute", "relative"):
            proc = run([str(links / link), "--help"], cwd=Path(tmp))
            record(ran_script(proc, script, phrase), f"a {link} symlink to belay-catalogs runs it",
                   f"rc={proc.returncode} stderr={proc.stderr[:200]!r}")
            proc = run([link, "--help"], cwd=Path(tmp), path_prefix=links)
            record(ran_script(proc, script, phrase),
                   f"a {link} symlink on PATH runs belay-catalogs",
                   f"rc={proc.returncode} stderr={proc.stderr[:200]!r}")


def test_status_and_streams_pass_through() -> None:
    """Identical to running the script directly, including a failure's status and stderr."""
    with tempfile.TemporaryDirectory() as tmp:
        cwd = Path(tmp)
        missing = str(cwd / "no-such-instance")
        cases = {
            "belay-catalogs": [],                       # argparse: command required -> 2
            "belay-validate": [missing],                # not a directory -> 2
            "belay-plan-update": [missing, missing],
            "belay-evidence": ["summary", missing],
        }
        for name, args in cases.items():
            script = WRAPPERS[name][0]
            direct = run([sys.executable, str(SCRIPTS / script), *args], cwd=cwd)
            wrapped = run([name, *args], cwd=cwd, path_prefix=BIN)
            record(direct.returncode != 0, f"{script} {' '.join(args).replace(missing, '<missing>') or '(no args)'} fails directly",
                   f"rc={direct.returncode}")
            record(
                (wrapped.returncode, wrapped.stdout, wrapped.stderr)
                == (direct.returncode, direct.stdout, direct.stderr),
                f"{name} passes the failing status ({direct.returncode}), stdout and stderr through",
                f"direct={direct.returncode} {direct.stderr[:120]!r} "
                f"wrapped={wrapped.returncode} {wrapped.stderr[:120]!r}",
            )
        # The stderr really came from the script, not from the shell.
        proc = run(["belay-catalogs"], cwd=cwd, path_prefix=BIN)
        record("catalogs.py: error:" in proc.stderr, "the error text is the script's own",
               proc.stderr[:200])


def test_controls_can_fail() -> None:
    """A wrapper with no plugin tree behind it fails, and every check above sees it."""
    with tempfile.TemporaryDirectory() as tmp:
        stray = Path(tmp) / "bin"
        stray.mkdir()
        shutil.copy2(BIN / "belay-validate", stray / "belay-validate")
        script, phrase = WRAPPERS["belay-validate"]
        proc = run(["belay-validate", "--help"], cwd=Path(tmp), path_prefix=stray)
        record(proc.returncode != 0, "control: a stray wrapper exits non-zero",
               f"rc={proc.returncode}")
        record(not ran_script(proc, script, phrase), "control: ran_script rejects its output")
        # And the content check is specific: one script's help is not another's.
        other = run([str(BIN / "belay-evidence"), "--help"], cwd=Path(tmp))
        record(other.returncode == 0 and not ran_script(other, script, phrase),
               "control: belay-evidence's help does not pass as validate_bundle.py's")


def test_runner_documents_name_the_wrappers() -> None:
    """The runner says `belay-<x>`, and names a script path only in the fallback."""
    pattern = re.compile(r"scripts/(catalogs|validate_bundle|plan_update|evidence)\.py")
    docs = [SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md"))]
    hits = []
    for doc in docs:
        for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and "python3 <skill dir>/scripts/" not in line:
                hits.append(f"{doc.name}:{number}")
    # The one deliberate exception: state-lifecycle.md names the file that holds the
    # learning record's definition, which is a file and not a command.
    allowed = {"state-lifecycle.md": "`scripts/evidence.py` holds this definition"}
    unexplained = []
    for hit in hits:
        name, number = hit.split(":")
        line = (SKILL / ("SKILL.md" if name == "SKILL.md" else f"references/{name}")).read_text(
            encoding="utf-8").splitlines()[int(number) - 1]
        if not (name in allowed and allowed[name] in line):
            unexplained.append(hit)
    record(not unexplained, "no runner document starts a script by its path outside the fallback",
           ", ".join(unexplained))
    # Prove the pattern can see a hit: the fallback line itself matches it.
    fallback = [d.name for d in docs if "python3 <skill dir>/scripts/" in d.read_text(encoding="utf-8")]
    record("runner-protocol.md" in fallback and "catalogue-format.md" in fallback,
           "the fallback is stated in runner-protocol.md and catalogue-format.md", str(fallback))
    for name in WRAPPERS:
        named = any(name in d.read_text(encoding="utf-8") for d in docs)
        record(named, f"the runner documents name {name}")


def main() -> int:
    print("bin/ wrapper test suite")
    print(f"  bin: {BIN}")
    for test in (
        test_every_script_has_a_wrapper,
        test_wrappers_are_executable_posix_sh,
        test_by_path_from_another_directory,
        test_by_bare_name_on_path,
        test_through_a_symlink,
        test_status_and_streams_pass_through,
        test_controls_can_fail,
        test_runner_documents_name_the_wrappers,
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
