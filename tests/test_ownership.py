#!/usr/bin/env python3
"""Test suite for ownership resolution and the Claude Code ownership guard.

Run it with:  python3 tests/test_ownership.py

No pytest. Two halves, one per file under test:

  * skills/belay/scripts/ownership.py - the glob dialect and resolve().
    Every dialect rule has an example that matches and one that does not;
    every precedence rule has a case that fires and a control that stays
    quiet.
  * skills/belay/scripts/ownership_guard.py - the PreToolUse hook. It is
    run as Claude Code runs it: a subprocess fed the hook payload as JSON on
    stdin. Each case asserts the decision it prints, or that it prints
    nothing. The positive controls - a deny and an ask - are what make the
    silent cases mean anything.

PyYAML may or may not be installed; nothing here uses it.
"""

from __future__ import annotations

import json
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
GUARD = SCRIPTS / "ownership_guard.py"
HOOKS_JSON = REPO / "hooks" / "hooks.json"
FIXTURE = HERE / "fixtures" / "rust-cli-basics"

sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))
import ownership as own  # noqa: E402
import validate_bundle as vb  # noqa: E402

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


def manifest(policy: str = own.STRICT, **extra) -> dict:
    data = {
        "ownership_policy": policy,
        "tutor_owned": ["tutorial/STATE.md", "tutorial/DESIGN.md"],
        "learner_owned": ["src/**", "tests/**", "Cargo.toml"],
    }
    data.update(extra)
    return data


# --------------------------------------------------------------------------
# The glob dialect
# --------------------------------------------------------------------------


def test_dialect() -> None:
    print("glob dialect")
    cases = [
        # (rule, pattern, path that matches, path that does not)
        ("anchored at the workspace root", "Cargo.toml", "Cargo.toml", "x/Cargo.toml"),
        ("'*' stays inside one segment", "src/*.rs", "src/main.rs", "src/cli/args.rs"),
        ("'?' is one character, never '/'", "src/?.rs", "src/a.rs", "src/ab.rs"),
        ("'?' does not cross '/'", "a?b", "axb", "a/b"),
        ("'**' crosses segments", "src/**", "src/cli/args.rs", "srcx/main.rs"),
        ("'**' matches zero segments", "**/*.go", "main.go", "main.rs"),
        ("'**' matches many segments", "**/*.go", "cmd/x/main.go", "cmd/x/main.gox"),
        ("'**' in the middle", "src/**/mod.rs", "src/mod.rs", "src/a/lib.rs"),
        ("no glob character: exact path", "README.md", "README.md", "README.md.bak"),
        ("dotfiles are ordinary names", "src/**", "src/.env", ".env"),
        ("'*' matches a leading dot", "*.toml", ".rustfmt.toml", "a/.rustfmt.toml"),
        ("case-sensitive", "src/**", "src/main.rs", "Src/main.rs"),
        ("'[' is a literal", "a[1].txt", "a[1].txt", "a1.txt"),
    ]
    for rule, pattern, yes, no in cases:
        record(own.glob_matches(pattern, yes), f"{rule}: {pattern!r} matches {yes!r}")
        record(not own.glob_matches(pattern, no),
               f"{rule}: {pattern!r} does not match {no!r}")

    for bad in ("", "/src/**", "src/", "src//x", "./src/**", "src/../x", "src/**.rs",
                "a**/b", 7):
        try:
            own.compile_glob(bad)
            record(False, f"{bad!r} is rejected", "it parsed")
        except own.GlobError:
            record(True, f"{bad!r} is rejected")


def test_normalisation() -> None:
    print("normalisation")
    record(own.normalise("src/./a/../main.rs") == "src/main.rs", "'.' and '..' fold")
    record(own.normalise("../x") is None, "'..' above the root is outside")
    record(own.normalise("src/../../x") is None, "a climb out through src/ is outside")
    record(own.normalise("/etc/passwd") is None, "absolute with no workspace is outside")
    record(own.normalise("/w/src/a.rs", "/w") == "src/a.rs", "absolute inside the workspace")
    record(own.normalise("/w2/a.rs", "/w") is None, "a sibling directory is outside")
    record(own.normalise(".") is None, "the root itself is not a file path")

    res = own.resolve("../outside.rs", own.MODIFY, manifest())
    record(res.owner == own.OUTSIDE and res.path is None, "'..' path resolves to outside",
           repr(res))
    res = own.resolve("src/../../src/main.rs", own.MODIFY, manifest())
    record(res.owner == own.OUTSIDE, "a '..' escape is never matched by 'src/**'",
           repr(res))
    res = own.resolve("tests/../src/main.rs", own.MODIFY, manifest())
    record(res.owner == own.LEARNER and res.path == "src/main.rs",
           "a '..' that stays inside resolves to the real path", repr(res))


# --------------------------------------------------------------------------
# resolve()
# --------------------------------------------------------------------------


def test_policies() -> None:
    print("each ownership_policy")
    expected = {
        own.STRICT: own.REFUSE,
        own.ON_REQUEST: own.NEEDS_LEARNER_REQUEST,
        own.UNRESTRICTED: own.ALLOW,
    }
    for policy, verdict in expected.items():
        for op in own.OPERATIONS:
            res = own.resolve("src/main.rs", op, manifest(policy))
            record(res.owner == own.LEARNER and res.verdict == verdict,
                   f"{policy}: {op} a learner_owned path -> {verdict}", repr(res))
        res = own.resolve("tutorial/STATE.md", own.MODIFY, manifest(policy))
        record(res.owner == own.TUTOR and res.verdict == own.ALLOW,
               f"{policy}: control - a tutor_owned path is allowed", repr(res))
    try:
        own.resolve("src/main.rs", own.MODIFY, manifest("whatever"))
        record(False, "an unknown policy raises ManifestError", "it resolved")
    except own.ManifestError:
        record(True, "an unknown policy raises ManifestError")


def test_unlisted_is_learner() -> None:
    print("unlisted paths")
    res = own.resolve("notes/plan.txt", own.CREATE, manifest())
    record(res.owner == own.LEARNER and res.verdict == own.REFUSE
           and "unlisted" in res.rule, "an unlisted path is the learner's", repr(res))
    res = own.resolve("notes/plan.txt", own.CREATE,
                      manifest(tutor_owned=["tutorial/STATE.md", "notes/**"]))
    record(res.owner == own.TUTOR, "control: once tutor_owned lists it, it is not",
           repr(res))


def test_supplies() -> None:
    print("supplies targets")
    targets = own.SuppliesTargets({"Cargo.toml", "assets/a.png"}, [])
    for policy in (own.STRICT, own.ON_REQUEST, own.UNRESTRICTED):
        m = manifest(policy)
        res = own.resolve("Cargo.toml", own.CREATE, m, True, targets)
        record(res.owner == own.SUPPLIES_TARGET and res.verdict == own.ALLOW,
               f"{policy}: create a supplies target -> allow", repr(res))
        res = own.resolve("Cargo.toml", own.MODIFY, m, True, targets)
        record(res.owner == own.SUPPLIES_TARGET and res.verdict == own.REFUSE,
               f"{policy}: modify a supplies target -> refuse", repr(res))
        res = own.resolve("assets/b.png", own.CREATE, m, True, targets)
        record(res.owner == own.LEARNER,
               f"{policy}: control - an undeclared path beside one is not a target",
               repr(res))
    res = own.resolve("Cargo.toml", own.MODIFY, manifest(), True, None)
    record(res.owner == own.LEARNER, "control: with no supplies, Cargo.toml is learner_owned",
           repr(res))


def test_runner_settled() -> None:
    print("runner-settled paths")
    m = manifest(own.UNRESTRICTED, tutor_owned=["tutorial/STATE.md", "tutorial/lessons/**"])
    res = own.resolve("tutorial/lessons/00-hello-args.md", own.MODIFY, m)
    record(res.owner == own.READ_ONLY and res.verdict == own.REFUSE,
           "tutorial/lessons/** is read-only even when tutor_owned lists it", repr(res))
    res = own.resolve("tutorial/lessons/01-x/usage.txt", own.CREATE, m)
    record(res.owner == own.READ_ONLY, "... and for lesson material, and for a create",
           repr(res))
    m = manifest(learner_owned=["src/**", "tutorial/lessons.generated/**"])
    res = own.resolve("tutorial/lessons.generated/x.md", own.CREATE, m)
    record(res.owner == own.TUTOR and res.verdict == own.ALLOW,
           "lessons.generated/** is tutor-owned even when learner_owned lists it",
           repr(res))
    res = own.resolve("tutorial/EVENTS.jsonl", own.MODIFY, manifest(tutor_owned=["x"]))
    record(res.owner == own.TUTOR, "EVENTS.jsonl is tutor-owned unlisted", repr(res))
    res = own.resolve("tutorial/tutorial.yaml", own.MODIFY, manifest(tutor_owned=["x"]))
    record(res.owner == own.TUTOR and "instance" in res.rule,
           "the instance stamp's file is the instance, not the learner's", repr(res))
    res = own.resolve("tutorial/lessons/x.md", own.MODIFY, manifest(), False)
    record(res.owner == own.LEARNER,
           "control: with no instance the runner-settled rules do not apply", repr(res))
    res = own.resolve("tutorial-notes/lessons/x.md", own.MODIFY, manifest())
    record(res.owner == own.LEARNER, "control: a lookalike directory is not the instance",
           repr(res))


def test_check_10_reports_a_glob_that_does_not_parse() -> None:
    print("validator check 10")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "b"
        shutil.copytree(FIXTURE, bundle)
        report = vb.validate(bundle, "bundle")
        quiet = not [f for f in report.findings if f.check == 10]
        record(quiet, "control: the fixture's globs raise no check-10 finding")
        path = bundle / "tutorial.yaml"
        path.write_text(path.read_text().replace(
            "learner_owned:  [src/**, tests/**, Cargo.toml]",
            "learner_owned:  [src/**, /tests/**, Cargo.toml]"))
        report = vb.validate(bundle, "bundle")
        hits = [f for f in report.findings if f.check == 10 and "/tests/**" in f.message]
        record(len(hits) == 1, "an absolute glob is a check-10 finding",
               repr([f.message for f in report.findings]))


# --------------------------------------------------------------------------
# The hook
# --------------------------------------------------------------------------


def make_workspace(tmp: Path, policy: str = own.STRICT, stamp: bool = True) -> Path:
    """A materialized rust-cli-basics instance, with supplies of every kind."""
    ws = tmp / "workspace"
    bundle = tmp / "bundle"
    shutil.copytree(FIXTURE, bundle)
    (bundle / "supplies" / "shaders").mkdir(parents=True)
    (bundle / "supplies" / "shaders" / "base.glsl").write_text("void main() {}\n")
    (bundle / "supplies" / "Cargo.toml").write_text("[package]\n")
    text = (bundle / "tutorial.yaml").read_text()
    text = text.replace("ownership_policy: tutor-must-not-edit-learner-owned",
                        f"ownership_policy: {policy}")
    text += ("\nsupplies:\n"
             "  - from: supplies/Cargo.toml\n    to: Cargo.toml\n    describe: manifest\n"
             "  - from: supplies/shaders/\n    to: src/shaders\n    describe: shaders\n")
    (bundle / "tutorial.yaml").write_text(text)
    lesson = bundle / "lessons" / "01-subcommands" / "LESSON.md"
    body = lesson.read_text()
    body = body.replace("---\n", "---\nsupplies:\n"
                        "  - from: lessons/01-subcommands/usage.txt\n"
                        "    to: usage.txt\n    describe: usage\n", 1)
    lesson.write_text(body)

    inst = ws / "tutorial"
    inst.mkdir(parents=True)
    for name in ("tutorial.yaml", "COURSE.md", "DESIGN.md"):
        shutil.copy(bundle / name, inst / name)
    shutil.copytree(bundle / "lessons", inst / "lessons")
    shutil.copy(bundle / "STATE.template.md", inst / "STATE.md")
    if stamp:
        with (inst / "tutorial.yaml").open("a") as handle:
            handle.write("\ninstance:\n  materialized_from: local:../bundle\n"
                         "  materialized_at: 2026-10-16\n  runner_version: 1\n")
    (ws / "src").mkdir()
    (ws / "src" / "main.rs").write_text("fn main() {}\n")
    (ws / "Cargo.toml").write_text("[package]\n")
    return ws


def run_hook(payload, cwd: Path | None = None, env_extra: dict | None = None,
             raw: str | None = None) -> tuple[int, str, str]:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True, text=True, env=env,
        cwd=str(cwd) if cwd else None, timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


def payload(ws: Path, tool: str, rel: str, **tool_input) -> dict:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    data = {key: str(ws / rel)}
    data.update(tool_input)
    return {
        "session_id": "test", "cwd": str(ws), "permission_mode": "default",
        "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": data,
        "tool_use_id": "toolu_test",
    }


def decision(stdout: str) -> tuple[str | None, str]:
    if not stdout.strip():
        return None, ""
    out = json.loads(stdout)["hookSpecificOutput"]
    if out.get("hookEventName") != "PreToolUse":
        return "bad-event", ""
    return out.get("permissionDecision"), out.get("permissionDecisionReason", "")


def expect(ws: Path, name: str, want: str | None, tool: str, rel: str,
           must_cite: str = "", **tool_input) -> None:
    code, out, err = run_hook(payload(ws, tool, rel, **tool_input))
    got, reason = decision(out)
    ok = code == 0 and got == want and must_cite in reason
    record(ok, name, f"exit={code} decision={got} reason={reason!r} stderr={err[-300:]!r}")


def test_hook_strict() -> None:
    print("hook: tutor-must-not-edit-learner-owned")
    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp))
        expect(ws, "positive control: Edit of a learner-owned file is denied", "deny",
               "Edit", "src/main.rs", "src/**", old_string="a", new_string="b")
        expect(ws, "Write creating an unlisted file is denied", "deny",
               "Write", "notes.txt", "unlisted", content="x")
        expect(ws, "MultiEdit is guarded", "deny", "MultiEdit", "src/main.rs", edits=[])
        expect(ws, "NotebookEdit is guarded", "deny", "NotebookEdit", "src/a.ipynb",
               new_source="x")
        expect(ws, "a supplies target that exists is denied, citing section 10", "deny",
               "Edit", "Cargo.toml", "section 10", old_string="a", new_string="b")
        (ws / "Cargo.toml").unlink()
        expect(ws, "creating a missing supplies target is allowed", None,
               "Write", "Cargo.toml", content="[package]\n")
        expect(ws, "a directory entry's file, listed from the bundle, may be created",
               None, "Write", "src/shaders/base.glsl", content="void main() {}\n")
        expect(ws, "control: an undeclared file beside it is denied", "deny",
               "Write", "src/shaders/mine.glsl", content="mine\n")
        expect(ws, "a lesson-scope target may be created", None,
               "Write", "usage.txt", content="whatever\n")
        (ws / "usage.txt").write_text("placed\n")
        expect(ws, "... and once placed, it is never modified", "deny",
               "Write", "usage.txt", content="changed\n")
        expect(ws, "tutorial/lessons/** asks, citing the rule", "ask",
               "Edit", "tutorial/lessons/00-hello-args.md", "read-only",
               old_string="a", new_string="b")
        expect(ws, "tutor_owned STATE.md: no decision", None,
               "Edit", "tutorial/STATE.md", old_string="a", new_string="b")
        expect(ws, "lessons.generated: no decision", None,
               "Write", "tutorial/lessons.generated/x.md", content="x")
        expect(ws, "the instance stamp: no decision", None,
               "Edit", "tutorial/tutorial.yaml", old_string="a", new_string="b")
        expect(ws, "a path outside the workspace: no decision", None,
               "Write", "../elsewhere.txt", content="x")
        expect(ws, "Read is not guarded", None, "Read", "src/main.rs")
        bundled = (FIXTURE / "lessons" / "01-subcommands" / "usage.txt").read_text()
        expect(ws, "creating a byte-copy of a file the instance ships: no decision "
               "(section 10.1 is the tutor's judgement)", None,
               "Write", "docs/usage.txt", content=bundled)
        expect(ws, "control: the same create with other content is denied", "deny",
               "Write", "docs/usage.txt", content=bundled + "x")
        expect(ws, "control: a modify of a learner file holding a bundle file's "
               "content is still denied", "deny",
               "Write", "src/main.rs", content=bundled)

        # The session's directory is below the workspace: CLAUDE_PROJECT_DIR.
        p = payload(ws, "Edit", "src/main.rs", old_string="a", new_string="b")
        p["cwd"] = str(ws / "src")
        _, out, _ = run_hook(p)
        record(decision(out)[0] is None, "control: cwd below the workspace, no project "
               "dir - no instance seen, silent")
        _, out, _ = run_hook(p, env_extra={"CLAUDE_PROJECT_DIR": str(ws)})
        record(decision(out)[0] == "deny", "with CLAUDE_PROJECT_DIR the instance is found")


def test_hook_other_policies() -> None:
    print("hook: on-request and unrestricted")
    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp), own.ON_REQUEST)
        expect(ws, "on-request: a learner-owned edit asks", "ask",
               "Edit", "src/main.rs", "on-request", old_string="a", new_string="b")
        expect(ws, "on-request: a supplies target that exists is still denied", "deny",
               "Edit", "Cargo.toml", old_string="a", new_string="b")
    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp), own.UNRESTRICTED)
        expect(ws, "unrestricted: a learner-owned edit gets no decision", None,
               "Edit", "src/main.rs", old_string="a", new_string="b")
        expect(ws, "unrestricted: a supplies target that exists is still denied", "deny",
               "Edit", "Cargo.toml", old_string="a", new_string="b")
        expect(ws, "unrestricted: tutorial/lessons/** still asks", "ask",
               "Edit", "tutorial/lessons/00-hello-args.md", old_string="a",
               new_string="b")


def test_hook_silent_and_fail_open() -> None:
    print("hook: silent outside a course, fail open")
    with tempfile.TemporaryDirectory() as tmp:
        plain = Path(tmp) / "plain"
        (plain / "src").mkdir(parents=True)
        code, out, err = run_hook(payload(plain, "Edit", "src/main.rs"))
        record(code == 0 and out == "" and err == "", "no tutorial/ at all: exit 0, silent",
               f"{code} {out!r} {err!r}")

    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp), stamp=False)
        code, out, _ = run_hook(payload(ws, "Edit", "src/main.rs"))
        record(code == 0 and out == "", "a bundle with no instance stamp: silent")

    with tempfile.TemporaryDirectory() as tmp:
        ws = make_workspace(Path(tmp))
        manifest_path = ws / "tutorial" / "tutorial.yaml"
        good = manifest_path.read_text()
        manifest_path.write_text(good + "  broken: [unclosed\n")
        code, out, err = run_hook(payload(ws, "Edit", "src/main.rs"))
        record(code == 0 and out == "" and err == "", "a manifest that does not parse: "
               "exit 0, no decision", f"{code} {out!r} {err[-200:]!r}")
        manifest_path.write_text(good.replace("ownership_policy: tutor-must-not-edit-"
                                              "learner-owned", "ownership_policy: maybe"))
        code, out, _ = run_hook(payload(ws, "Edit", "src/main.rs"))
        record(code == 0 and out == "", "an unknown policy: exit 0, no decision")
        manifest_path.write_text(good.replace("learner_owned:  [src/**",
                                              "learner_owned:  [/src/**"))
        code, out, _ = run_hook(payload(ws, "Edit", "src/main.rs"))
        record(code == 0 and out == "", "a glob that does not parse: exit 0, no decision")
        manifest_path.write_text(good)
        code, out, _ = run_hook(payload(ws, "Edit", "src/main.rs"))
        record(decision(out)[0] == "deny", "control: the same workspace repaired denies")

        for label, raw in (("empty stdin", ""), ("not JSON", "{nope"),
                           ("a JSON list", "[]"), ("no tool_input", json.dumps(
                               {"tool_name": "Edit", "cwd": str(ws)})),
                           ("tool_input not a mapping", json.dumps(
                               {"tool_name": "Edit", "cwd": str(ws), "tool_input": 3})),
                           ("cwd not a string", json.dumps(
                               {"tool_name": "Edit", "cwd": 5, "tool_input":
                                {"file_path": str(ws / "src/main.rs")}}))):
            code, out, err = run_hook(None, raw=raw)
            record(code == 0 and out == "" and err == "",
                   f"unexpected payload ({label}): exit 0, silent",
                   f"{code} {out!r} {err[-200:]!r}")


def test_hook_registration() -> None:
    print("hook registration")
    data = json.loads(HOOKS_JSON.read_text())
    entries = data["hooks"]["PreToolUse"]
    record(len(entries) == 1 and entries[0]["matcher"] ==
           "Write|Edit|MultiEdit|NotebookEdit", "hooks/hooks.json matches the four tools")
    command = entries[0]["hooks"][0]["command"]
    record("${CLAUDE_PLUGIN_ROOT}" in command and
           "skills/belay/scripts/ownership_guard.py" in command,
           "the command runs the guard from the plugin root")
    codex = json.loads((REPO / ".codex-plugin" / "plugin.json").read_text())
    record(codex.get("hooks") == {}, "the Codex manifest still declares no hooks")

    # Missing python: the shell form must still exit 0 with nothing on stdout.
    shell_command = command.replace("python3", "belay-no-such-python")
    proc = subprocess.run(["sh", "-c", shell_command], input="{}", capture_output=True,
                          text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)})
    record(proc.returncode == 0 and proc.stdout == "",
           "with no interpreter the hook command exits 0, silent",
           f"{proc.returncode} {proc.stdout!r}")
    proc = subprocess.run(["sh", "-c", command], input="{}", capture_output=True,
                          text=True, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)})
    record(proc.returncode == 0 and proc.stdout == "",
           "control: the real command runs and exits 0 on an empty payload")


def test_runner_needs_no_adapter() -> None:
    print("the runner with no adapter")
    with tempfile.TemporaryDirectory() as tmp:
        skill = Path(tmp) / "belay"
        shutil.copytree(REPO / "skills" / "belay", skill)
        (skill / "scripts" / "ownership_guard.py").unlink()
        ws = make_workspace(Path(tmp))
        (ws / "tutorial" / "STATE.template.md").unlink(missing_ok=True)
        proc = subprocess.run(
            [sys.executable, str(skill / "scripts" / "validate_bundle.py"),
             "--instance", str(ws / "tutorial")],
            capture_output=True, text=True)
        record("Traceback" not in proc.stderr and proc.returncode in (0, 1),
               "validate_bundle.py runs with the hook script removed",
               proc.stderr[-300:])
    for name in ("validate_bundle.py", "plan_update.py", "evidence.py", "catalogs.py"):
        text = (SCRIPTS / name).read_text()
        record("ownership_guard" not in text, f"{name} does not depend on the hook")
    for doc in ("SKILL.md", "references/runner-protocol.md",
                "references/state-lifecycle.md"):
        text = (REPO / "skills" / "belay" / doc).read_text()
        record("ownership_guard.py" not in text,
               f"{doc} never tells the tutor to run the hook")


def main() -> int:
    print("ownership test suite")
    for test in (
        test_dialect,
        test_normalisation,
        test_policies,
        test_unlisted_is_learner,
        test_supplies,
        test_runner_settled,
        test_check_10_reports_a_glob_that_does_not_parse,
        test_hook_strict,
        test_hook_other_policies,
        test_hook_silent_and_fail_open,
        test_hook_registration,
        test_runner_needs_no_adapter,
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
