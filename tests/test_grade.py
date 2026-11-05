#!/usr/bin/env python3
"""Test suite for skills/belay/scripts/grade.py - the scheme, the store, collect and run.

Run it with:  python3 tests/test_grade.py

No pytest. Every case points XDG_DATA_HOME at a temporary directory, so the
real home is never touched, and asserts VALUES: paths, exit codes, what is left
on disk. Each refusal has a control showing the same call succeeds without the
fault.

Nothing here needs docker. BELAY_CONTAINER_RUNTIME points at a stub that records
its arguments and environment and runs the command directly. The fake cohort is
a local bare repository; the repository URL rules refuse a local path, so a test
gitconfig rewrites an https URL to it with url.<base>.insteadOf, and grade.py has
no test-only way in.
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
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
        "https://github.com:443/acme/team-7.git",
        "ssh://github.com/acme/team-7",
        "ssh://git@github.com:022/acme/team-7",
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
        "https://github.com:8443/acme/team-7.git",   # another port is another server
        "ssh://git@github.com:2222/acme/team-7.git",
        "ssh://github.com:443/acme/team-7.git",      # 443 is the default of https only
        "https://github.com:22/acme/team-7.git",     # 22 is the default of ssh only
        "alice@github.com:acme/team-7",              # another ssh account
        "ssh://bob@github.com/acme/team-7",
    ]
    all_names = {name} | {gr.cohort_name(u) for u in other}
    record(len(all_names) == len(other) + 1, "different URLs, even slug-alike ones, never collide",
           str(sorted(all_names)))
    plain = gr.cohort_name("git@github.com:acme/team-7.git")
    for url in ("https://user:p@ss@github.com/acme/team-7.git",
                "https://user:tok3n@github.com/acme/team-7.git",
                "https://tok3n@github.com/acme/team-7.git",
                "ssh://git:tok3n@github.com/acme/team-7"):
        n = gr.cohort_name(url)
        record("tok3n" not in n and n == plain and "ss" not in n.split("-team")[0],
               f"credentials in {url!r} never reach the cohort name, and the cohort is unchanged", n)
    # An ssh user is an account, not a credential; its password is one.
    for url, bare_user in (("user:tok3n@github.com:acme/team-7.git", "user@github.com:acme/team-7.git"),
                           ("ssh://u:tok3n@github.com/acme/team-7", "ssh://u@github.com/acme/team-7")):
        n = gr.cohort_name(url)
        record("tok3n" not in n and "tok3n" not in gr.normalise_url(url) and n == gr.cohort_name(bare_user),
               f"the password in {url!r} changes nothing: the cohort is that of the user alone", n)
    record(gr.cohort_name("host.com:8080/o/r") != gr.cohort_name("ssh://host.com:8080/o/r"),
           "scp host.com:8080/o/r (a directory) stays distinct from ssh://host.com:8080/o/r (a port)")
    record(gr.cohort_name("ssh://host.com:8080/o/r") != gr.cohort_name("https://host.com/o/r"),
           "a non-default port is kept: it can be another server")
    record(gr.cohort_name("ssh://host.com:22/o/r") == gr.cohort_name("https://host.com:443/o/r")
           == gr.cohort_name("https://host.com/o/r"), "a default port equals none")
    record(gr.cohort_name("alice@h:cohort") != gr.cohort_name("bob@h:cohort"),
           "two ssh accounts on a host are two cohorts: an scp path is relative to the account's home")
    hostile = ["https://h/../../etc/x", "git@h:../../x", "https://h/a b/c;d", "https://h/-x/y"]
    for url in hostile:
        n = gr.cohort_name(url)
        record(("/" not in n and "\\" not in n and ".." not in n and not n.startswith("-")
                and n not in ("", ".")), f"cohort name for {url!r} is one safe component", n)
    dotted = gr.cohort_name("https://h/a..b/c")
    record(gr.valid_cohort_arg(dotted), "forget accepts the name of a path holding '..'", dotted)
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
            for bad in ("../x", "a/b", "..", "", gr.CACHE_NAME):
                record(refused(gr.store_dir, "https://h/o/r", bad) is not None,
                       f"module id {bad!r} is refused")
        saved = {k: os.environ.get(k) for k in ("XDG_DATA_HOME", "HOME")}
        try:
            os.environ.pop("XDG_DATA_HOME", None)
            home = Path(tmp) / "home"
            os.environ["HOME"] = str(home)
            record(gr.data_home() == home / ".local" / "share",
                   "without XDG_DATA_HOME the base is ~/.local/share", str(gr.data_home()))
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


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
        record("symlink" in out and "left alone" in out,
               "forget on a symlinked cohort says it is a symlink and was left alone", out)


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



# --------------------------------------------------------------------------
# collect and run: the fake cohort and the stub runtime
# --------------------------------------------------------------------------

COHORT_URL = "https://cohort.invalid/acme/team-1.git"
TOKEN_URL = "https://user:s3cr3t-t0ken@cohort.invalid/acme/team-1.git"
ALICE_URL = "alice@cohort.invalid:acme/team-1"
IMAGE = "python:3.12-slim"
SECRET = "sk-grading-VALUE-123456"
UNDECLARED = "sk-trainer-PERSONAL-987"
MOUNT = "/workspace"

MODULE_YAML = """\
id: m1
version: 1.2.0
validators:
  scorer-tests: { kind: command, command: [sh, run-tests.sh] }
  lint: { kind: command, command: [sh, lint.sh] }
  has-readme: { kind: file-exists, path: README.md }
  has-test: { kind: file-contains, path: src/main.py, pattern: "^def test_[a-z]+" }
grading:
  image: python:3.12-slim
  env: [GRADE_KEY, GRADE_MISSING]
  timeout_minutes: 15
  validators:
    scorer-tests: { points: 30, gate: true }
    lint: { points: 10 }
    has-readme: { points: 10 }
    has-test: { points: 10 }
  rubric:
    - id: design
      points: 20
      standard: The choice is justified.
"""

PARTICIPANTS = {
    "alice": {  # passes everything
        "README.md": "alice\n",
        "run-tests.sh": 'echo "tests ok key=$GRADE_KEY"\nexit 0\n',
        "lint.sh": "exit 0\n",
        "src/main.py": "def test_x():\n    pass\n",
    },
    "bob": {  # fails the gate validator
        "README.md": "bob\n",
        "run-tests.sh": 'echo "2 failed"\nexit 1\n',
        "lint.sh": "exit 0\n",
        "src/main.py": "def test_y():\n    pass\n",
    },
    "carol": {  # passes the gate, fails the rest but the readme
        "README.md": "carol\n",
        "run-tests.sh": "exit 0\n",
        "lint.sh": 'echo "lint: bad"\nexit 3\n',
        "src/main.py": "print('no tests')\n",
    },
}

# As pushed -> as listed. Git allows every one of these in a ref name. U+0085, U+2028 and
# U+2029 are line ends to str.splitlines; U+009B is a terminal's control sequence introducer;
# "\\udcff" is the raw byte 0xFF, which is not UTF-8.
HOSTILE_BRANCHES = {
    "-x/m1": "-x/m1",
    "$(touch${IFS}pwned)/m1": "$(touch${IFS}pwned)/m1",
    "a;touch${IFS}pwned/m1": "a;touch${IFS}pwned/m1",
    "deep/er/m1": "deep/er/m1",
    "a\u0085b/m1": "a\\x85b/m1",
    "a\u2028b/m1": "a\\u2028b/m1",
    "a\u2029b/m1": "a\\u2029b/m1",
    "a\u009bb/m1": "a\\x9bb/m1",
    "caf\udcff/m1": "caf\\xff/m1",
    "caf\u00e9/m1": "caf\\xe9/m1",
}
HOSTILE_OTHER = {"x\u2028y": "x\\u2028y"}

STUB = """#!{python}
import json, os, shutil, signal, subprocess, sys
RECORD = {record!r}
INFO_FAILS = {info_fails!r}
KILL_FAILS = {kill_fails!r}
DIGEST_FAILS = {digest_fails!r}
args = sys.argv[1:]
entry = dict(argv=args, env=dict(os.environ))
cmd = args[0] if args else ""
parsed = None
if cmd == "run":
    i = 1
    parsed = dict(rm=False, name=None, network=None, mounts=[], workdir=None, env=[])
    while args[i].startswith("-"):
        flag = args[i]
        if flag == "--rm":
            parsed["rm"] = True; i += 1; continue
        value = args[i + 1]
        if flag == "--name": parsed["name"] = value
        elif flag == "--pids-limit": parsed["pids"] = value
        elif flag == "--memory": parsed["memory"] = value
        elif flag == "--security-opt": parsed["security"] = value
        elif flag == "--network": parsed["network"] = value
        elif flag == "-v": parsed["mounts"].append(value)
        elif flag == "-w": parsed["workdir"] = value
        elif flag == "-e": parsed["env"].append(value)
        else: parsed.setdefault("unknown", []).append(flag)
        i += 2
    parsed["image"] = args[i]
    parsed["command"] = args[i + 1:]
    src = parsed["mounts"][0].split(":")[0]
    git = os.path.join(src, ".git")
    snapshot = RECORD + ".git-snapshot"
    if os.path.isdir(git) and not os.path.exists(snapshot):
        shutil.copytree(git, snapshot)
    entry["checkout"] = dict(
        src=src,
        tree=sorted(os.path.relpath(os.path.join(d, f), src) for d, _, fs in os.walk(src)
                    for f in fs if not os.path.relpath(d, src).split(os.sep)[0] == ".git"),
        files=sorted(n for n in os.listdir(src) if n != ".git"),
        git_config=open(os.path.join(git, "config")).read() if os.path.isdir(git) else None,
        hooks_dir=os.path.exists(os.path.join(git, "hooks")),
        heads=sorted(os.path.relpath(os.path.join(d, f), os.path.join(git, "refs", "heads"))
                     for d, _, fs in os.walk(os.path.join(git, "refs", "heads")) for f in fs),
    )
entry["parsed"] = parsed
with open(RECORD, "a") as handle:
    handle.write(json.dumps(entry) + "\\n")
if cmd == "info":
    sys.exit(1 if INFO_FAILS else 0)
if cmd == "pull":
    sys.exit(0)
if cmd == "image":
    if DIGEST_FAILS:
        sys.exit(1)
    print("sha256:stubdigest")
    sys.exit(0)
if cmd == "kill":
    if KILL_FAILS:
        print("kill refused", file=sys.stderr)
        sys.exit(1)
    os.kill(int(open(RECORD + "." + args[1]).read()), signal.SIGKILL)
    sys.exit(0)
if cmd == "run":
    with open(RECORD + "." + parsed["name"], "w") as handle:
        handle.write(str(os.getpid()))
    os.chdir(src)
    env = dict(PATH=os.environ.get("PATH", ""))
    for name in parsed["env"]:
        if name in os.environ:
            env[name] = os.environ[name]
    command = [a.replace("{mount}", src) for a in parsed["command"]]
    os.execvpe(command[0], command, env)
sys.exit(2)
"""


def git_fixture(*args: str, cwd: Path) -> str:
    env = {"PATH": os.environ["PATH"], "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1",
           "GIT_CONFIG_GLOBAL": os.devnull}
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid",
                           "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, env=env, capture_output=True, text=True, check=True)
    return done.stdout.strip()


_orphans = iter(range(10 ** 6))


def commit_branch(work: Path, branch: str, files: dict[str, str | tuple]) -> str:
    """One orphan commit holding exactly `files`; a tuple value is a symlink target."""
    git_fixture("checkout", "-q", "--orphan", f"w{next(_orphans)}", cwd=work)
    git_fixture("rm", "-rfq", "--ignore-unmatch", ".", cwd=work)
    for rel, content in files.items():
        path = work / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, tuple):
            path.symlink_to(content[0])
        else:
            path.write_text(content)
    git_fixture("add", "-A", cwd=work)
    git_fixture("commit", "-q", "--allow-empty", "-m", branch, cwd=work)
    return git_fixture("rev-parse", "HEAD", cwd=work)


class Scene:
    """A temp world: a bare cohort, a stub runtime, a data home, a test git config."""

    def __init__(self, tmp: str, *, info_fails: bool = False, kill_fails: bool = False,
                 digest_fails: bool = False, module_yaml: str = MODULE_YAML) -> None:
        self.tmp = Path(tmp).resolve()
        self.data = self.tmp / "data"
        self.bare = self.tmp / "cohort.git"
        self.work = self.tmp / "work"
        self.cwd = self.tmp / "cwd"
        self.cwd.mkdir()
        self.work.mkdir()
        git_fixture("init", "-q", "--bare", str(self.bare), cwd=self.tmp)
        git_fixture("init", "-q", str(self.work), cwd=self.tmp)
        self.commits: dict[str, str] = {}
        for who, files in PARTICIPANTS.items():
            self.add_branch(f"{who}/m1", files)
        self.add_branch("main", {"README.md": "cohort\n"})
        self.add_branch("alice/m2", {"README.md": "another module\n"})
        config = self.tmp / "gitconfig"
        config.write_text(
            f'[url "file://{self.bare}"]\n\tinsteadOf = {COHORT_URL}\n\tinsteadOf = {TOKEN_URL}\n'
            f'\tinsteadOf = {ALICE_URL}\n')
        self.record = self.tmp / "stub-record.jsonl"
        self.stub = self.tmp / "stub-runtime"
        self.write_stub(self.stub, info_fails, kill_fails, digest_fails)
        self.bundle = self.tmp / "bundle"
        self.bundle.mkdir()
        (self.bundle / "tutorial.yaml").write_text(module_yaml)
        self.env = {
            "PATH": os.environ["PATH"],
            "HOME": str(self.tmp / "home"),
            "XDG_DATA_HOME": str(self.data),
            "XDG_RUNTIME_DIR": str(self.tmp / "run"),
            "GIT_CONFIG_GLOBAL": str(config),
            "GIT_CONFIG_NOSYSTEM": "1",
            "BELAY_CONTAINER_RUNTIME": str(self.stub),
            "GRADE_KEY": SECRET,
            "UNDECLARED_SECRET": UNDECLARED,
            "SSH_AUTH_SOCK": "/run/agent.sock",
            "GH_TOKEN": "gh-token-value",
            "GIT_ASKPASS": "/usr/bin/askpass",
            "TMPDIR": str(self.tmp),
        }

    def write_stub(self, path: Path, info_fails: bool = False, kill_fails: bool = False,
                   digest_fails: bool = False) -> None:
        path.write_text(STUB.replace("{python}", sys.executable)
                        .replace("{record!r}", repr(str(self.record)))
                        .replace("{info_fails!r}", repr(info_fails))
                        .replace("{kill_fails!r}", repr(kill_fails))
                        .replace("{digest_fails!r}", repr(digest_fails))
                        .replace("{mount}", MOUNT))
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def add_branch(self, branch: str, files: dict) -> None:
        self.commits[branch] = commit_branch(self.work, branch, files)
        git_fixture("push", "-q", str(self.bare), f"+HEAD:refs/heads/{branch}", cwd=self.work)

    def add_hostile_branches(self) -> None:
        sha = self.commits["alice/m1"]
        for branch in (*HOSTILE_BRANCHES, *HOSTILE_OTHER):
            git_fixture("--git-dir", str(self.bare), "update-ref", f"refs/heads/{branch}", sha,
                        cwd=self.tmp)

    def cli(self, *args: str, prelude: str = "", env: dict | None = None) -> tuple[int, str, str]:
        if prelude:
            argv = [sys.executable, "-B", "-c",
                    "import sys\nsys.path.insert(0, " + repr(str(SCRIPTS)) + ")\nimport grade\n"
                    + prelude + "\nsys.exit(grade.main(sys.argv[1:]))", *args]
        else:
            argv = [sys.executable, "-B", str(SCRIPT), *args]
        done = subprocess.run(argv, capture_output=True, text=True, cwd=self.cwd,
                              env=self.env if env is None else env)
        return done.returncode, done.stdout, done.stderr

    def run_all(self, *extra: str, url: str = COHORT_URL, prelude: str = "") -> tuple[int, str, str]:
        return self.cli("run", "--bundle", str(self.bundle), url, "m1", *extra, prelude=prelude)

    def records(self, command: str | None = None) -> list[dict]:
        if not self.record.exists():
            return []
        rows = [json.loads(line) for line in self.record.read_text().splitlines()]
        return [r for r in rows if command is None or r["argv"][:1] == [command]]

    def store(self) -> Path:
        with Env(self.data):
            return gr.store_dir(COHORT_URL, "m1")

    def results(self) -> dict:
        return json.loads((self.store() / "run.json").read_text())

    def leftovers(self) -> list[str]:
        return sorted(p.name for p in self.tmp.glob("belay-grade-*"))


LIMIT_PRELUDE = "grade.SECONDS_PER_MINUTE = 3"  # timeout_minutes: 1 is three seconds


def hang_yaml(validators: str, order: str) -> str:
    return f"""\
id: m1
validators:
{validators}
grading:
  image: python:3.12-slim
  timeout_minutes: 1
  validators:
{order}
  rubric: []
"""


def test_classify_branch() -> None:
    table = [
        ("alice/m1", "participant", "alice"),
        ("A.b_c-9/m1", "participant", "A.b_c-9"),
        ("a b/m1", "refused", None),
        ("../x/m1", "refused", None),
        ("-x/m1", "refused", None),
        ("../m1", "refused", None),
        ("./m1", "refused", None),
        ("/m1", "refused", None),
        ("a/b/m1", "refused", None),
        ("$(id)/m1", "refused", None),
        ("a;b/m1", "refused", None),
        ("a\n/m1", "refused", None),
        ("a\u00e9/m1", "refused", None),
        ("a\u2028b/m1", "refused", None),
        ("a\\xffb/m1", "refused", None),
        ("main", "other", None),
        ("alice/m2", "other", None),
        ("alice/m1x", "other", None),
        ("m1", "other", None),
    ]
    for branch, kind, who in table:
        got = gr.classify_branch(branch, "m1")
        record(got == (kind, who), f"branch {branch!r} is {kind}", str(got))


def test_collect() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.add_hostile_branches()
        code, out, err = scene.cli("collect", COHORT_URL, "m1")
        record(code == 0, "collect succeeds", f"{code} {err}")
        cohort = gr.cohort_name(COHORT_URL)
        record(f"cohort: {cohort}" in out, "collect prints the cohort name forget takes", out)
        lines = out.splitlines()
        for who in PARTICIPANTS:
            sha = scene.commits[f"{who}/m1"]
            row = [l for l in lines if l.split()[:2] == [who, f"{who}/m1"]]
            record(len(row) == 1 and sha[:12] in row[0] and "T" in row[0].split()[3],
                   f"collect lists {who} with branch, last commit and date", str(row))
        head_refused = lines.index(next(l for l in lines if l.startswith("refused")))
        head_other = lines.index(next(l for l in lines if l.startswith("no convention")))
        refused_rows = [l.strip() for l in lines[head_refused + 1:head_other] if l.strip()]
        other_rows = [l.strip() for l in lines[head_other + 1:] if l.strip()]
        record(sorted(refused_rows) == sorted(HOSTILE_BRANCHES.values()),
               "hostile participant names are listed apart as refused, escaped", str(refused_rows))
        record(sorted(other_rows) == sorted(["alice/m2", "main", *HOSTILE_OTHER.values()]),
               "branches outside the convention are listed apart, escaped", str(other_rows))
        record(out.isascii() and all(c.isprintable() or c == "\n" for c in out),
               "nothing but printable ASCII reaches the terminal", repr(out))
        participants_block = "\n".join(lines[:head_refused])
        record(not any(b in participants_block for b in HOSTILE_BRANCHES),
               "no hostile name is in the participants' block", participants_block)
        record(not (scene.cwd / "pwned").exists(), "a branch name is never run through a shell")

        cache = scene.data / "belay" / "grading" / cohort / ".repo.git"
        record(cache.is_dir() and not (cache / ".git").exists(),
               "the cache is a bare repository in the store", str(cache))
        record(not (cache / "hooks").exists(), "the cache has no hooks directory")
        # A second collect updates the cache: a moved and a deleted branch show.
        scene.add_branch("alice/m1", {"README.md": "moved\n"})
        git_fixture("--git-dir", str(scene.bare), "update-ref", "-d", "refs/heads/carol/m1", cwd=scene.tmp)
        code, out, err = scene.cli("collect", COHORT_URL, "m1")
        record(scene.commits["alice/m1"][:12] in out, "collect again shows a moved branch", out)
        record("carol" not in out, "collect again drops a deleted branch", out)
        code, out, err = scene.cli("forget", cohort)
        record(code == 0 and not (scene.data / "belay" / "grading" / cohort).exists(),
               "forget with the printed name removes the cohort, cache included", f"{code} {out}{err}")


def test_collect_keeps_credentials_out() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        code, out, err = scene.cli("collect", TOKEN_URL, "m1")
        record(code == 0, "collect accepts a URL holding a credential", f"{code} {err}")
        record("s3cr3t" not in out + err, "the credential is not printed", out + err)
        root = scene.data / "belay" / "grading"

        def holding() -> list[str]:
            return [str(p) for p in root.rglob("*") if p.is_file() and b"s3cr3t" in p.read_bytes()]

        record(holding() == [], "the credential is in no file of the cache", str(holding()))
        canary = root / "canary"
        canary.write_text("s3cr3t")
        record(holding() == [str(canary)], "control: that search does find a planted credential")
        canary.unlink()
        # A failing fetch's message does not carry it either.
        broken = dict(scene.env, GIT_CONFIG_GLOBAL=os.devnull)
        code, out, err = scene.cli("collect", "https://user:s3cr3t-t0ken@127.0.0.1:9/acme/x.git", "m1", env=broken)
        record(code != 0 and "s3cr3t" not in out + err,
               "a failed fetch says so with no credential in the message", f"{code} {out}{err}")


def test_collect_url_rules() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        for bad in (str(scene.bare), f"file://{scene.bare}", "http://h/o/r", "ext::sh -c id",
                    "https://h/o/r;id", "https://-oProxy/x",
                    "https://h/o/r?token=abc", "https://h/o/r#abc", "git@h:o/r?token=abc"):
            for command in (("collect", bad, "m1"),
                            ("run", "--bundle", str(scene.bundle), bad, "m1")):
                code, out, err = scene.cli(*command)
                record(code == gr.EXIT_REFUSED and "not a Git URL" in err,
                       f"{command[0]} refuses repository {bad!r}", f"{code} {err}")
        code, out, err = scene.cli("collect", "-upload-pack=x", "m1")
        record(code == gr.EXIT_USAGE, "an option as the repository is a usage error", f"{code} {err}")
        code, out, err = scene.cli("collect", "--", "-upload-pack=x", "m1")
        record(code == gr.EXIT_REFUSED and "not a Git URL" in err,
               "an option as the repository after -- is refused", f"{code} {err}")
        record(not scene.data.exists(), "a refused URL created nothing")
        record(scene.records() == [], "a refused URL ran nothing")
        code, out, err = scene.cli("collect", COHORT_URL, "../m1")
        record(code == gr.EXIT_USAGE and not scene.data.exists(), "a module id with a slash is refused",
               f"{code} {err}")
        with_tree = scene.tmp / "tree"
        with_tree.mkdir()
        git_fixture("init", "-q", str(with_tree), cwd=scene.tmp)
        env = dict(scene.env, XDG_DATA_HOME=str(with_tree / "data"))
        code, out, err = scene.cli("collect", COHORT_URL, "m1", env=env)
        record(code == gr.EXIT_REFUSED and "work tree" in err and not (with_tree / "data").exists(),
               "collect refuses a store inside a Git work tree", f"{code} {err}")


def test_run_results() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.add_hostile_branches()
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all()
        record(code == 0, "run succeeds", f"{code} {out} {err}")
        data = scene.results()
        record(sorted(data["branches"]) == ["alice", "bob", "carol"],
               "exactly the three conforming branches are graded", str(sorted(data["branches"])))
        expected = {
            "alice": dict(zip(("scorer-tests", "lint", "has-readme", "has-test"), (True, True, True, True))),
            "bob": dict(zip(("scorer-tests", "lint", "has-readme", "has-test"), (False, True, True, True))),
            "carol": dict(zip(("scorer-tests", "lint", "has-readme", "has-test"), (True, False, True, False))),
        }
        for who, want in expected.items():
            branch = data["branches"][who]
            got = {k: v["passed"] for k, v in branch["validators"].items()}
            record(got == want, f"{who}: each validator's result", str(got))
            record(list(branch["validators"]) == list(want),
                   f"{who}: results keep the declared order", str(list(branch["validators"])))
            record(branch["commit"] == scene.commits[f"{who}/m1"] and branch["branch"] == f"{who}/m1",
                   f"{who}: the graded commit is recorded", str(branch["commit"]))
            record(branch["validators"]["scorer-tests"]["gate"] is True
                   and branch["validators"]["lint"]["gate"] is False,
                   f"{who}: the gate flag follows the scheme")
        bob = data["branches"]["bob"]["validators"]["scorer-tests"]
        record("2 failed" in bob["output"] and "exit status 1" in bob["reason"],
               "a failed command keeps its output and says why", str(bob))
        carol_lint = data["branches"]["carol"]["validators"]["lint"]
        record("lint: bad" in carol_lint["output"] and "exit status 3" in carol_lint["reason"],
               "the exit status is reported", str(carol_lint))
        record(data["module"] == "m1" and data["bundle_version"] == "1.2.0"
               and data["cohort"] == gr.cohort_name(COHORT_URL),
               "the working file names the module, version and cohort", str(data)[:200])
        record(sorted(data["refused"]) == sorted(HOSTILE_BRANCHES.values()),
               "the working file lists refused branches, escaped", str(data["refused"]))
        record(HOSTILE_OTHER["x\u2028y"] in data["no_convention"],
               "the working file lists other branches, escaped", str(data["no_convention"]))
        for shown in HOSTILE_BRANCHES.values():
            record(shown in out, f"run lists {shown!r} as not graded", out)
        record(not (scene.cwd / "pwned").exists() and not any(
            b in " ".join(r["argv"]) for r in scene.records() for b in HOSTILE_BRANCHES),
            "no hostile branch name reached the runtime or a shell")
        record("alice (alice/m1" in out and "lint  FAIL: exit status 3" in out
               and "scorer-tests (gate)  FAIL: exit status 1" in out and "has-readme  pass" in out,
               "the summary reports each branch's results", out)
        record(scene.leftovers() == [], "every checkout is removed", str(scene.leftovers()))
        store = scene.store()
        record(stat.S_IMODE((store / "run.json").stat().st_mode) == 0o600,
               "the working file is private to the trainer")


def test_container_command() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all()
        runs = scene.records("run")
        record(len(runs) == 6, "only command validators reach the container: 2 per branch",
               str(len(runs)))
        names = set()
        for row in runs:
            p = row["parsed"]
            src = row["checkout"]["src"]
            names.add(p["name"])
            want = ["run", "--rm", "--name", p["name"],
                    "--pids-limit", "512", "--memory", "4g", "--security-opt", "no-new-privileges",
                    "--network", "none",
                    "-v", f"{src}:{MOUNT}", "-w", MOUNT, "-e", "GRADE_KEY",
                    IMAGE, "sh", p["command"][1]]
            record(row["argv"] == want, "the container command is exactly the declared shape",
                   str(row["argv"]))
            record(len(p["mounts"]) == 1 and src.startswith(str(scene.tmp)) and "unknown" not in p,
                   "exactly one mount, the checkout", str(p["mounts"]))
            env = row["env"]
            record(env.get("GRADE_KEY") == SECRET, "a declared variable's value reaches the runtime's env")
            allowed = set(gr.RUNTIME_ENV_KEYS) | {"GRADE_KEY", "LC_CTYPE"}  # Python's own locale coercion
            record(set(env) <= allowed, "the runtime's env holds only what it needs and what is declared",
                   str(sorted(set(env) - allowed)))
            record("UNDECLARED_SECRET" not in env and "GH_TOKEN" not in env and "SSH_AUTH_SOCK" not in env
                   and "GIT_ASKPASS" not in env and "GIT_CONFIG_GLOBAL" not in env,
                   "no undeclared variable and no git access reaches the runtime")
            record(env.get("XDG_RUNTIME_DIR") == scene.env["XDG_RUNTIME_DIR"]
                   and env.get("HOME") == scene.env["HOME"] and "PATH" in env,
                   "the runtime keeps PATH, HOME and XDG_RUNTIME_DIR")
            joined = " ".join(row["argv"])
            record(SECRET not in joined and UNDECLARED not in joined,
                   "no value is on any command line")
            co = row["checkout"]
            record(co["git_config"] is not None and "url" not in co["git_config"]
                   and "remote" not in co["git_config"] and "cohort" not in co["git_config"],
                   "the checkout's git config has no remote", str(co["git_config"]))
            record(co["hooks_dir"] is False, "the checkout has no hooks directory")
            record(len(co["heads"]) == 1 and co["heads"][0] in {f"{w}/m1" for w in PARTICIPANTS},
                   "the checkout holds only this participant's branch", str(co["heads"]))
            record("README.md" in co["files"] and "src" in co["files"], "the files are checked out",
                   str(co["files"]))
            record(not Path(src).exists(), "the mounted checkout is gone afterwards", src)
        record(len(names) == 6, "each container gets its own generated name", str(names))
        for row in scene.records():
            if row["argv"][0] != "run":
                record("GRADE_KEY" not in row["env"],
                       f"`{row['argv'][0]}` does not receive the declared variables")
        record(scene.records("info") != [], "the runtime is probed first")
        record([r["argv"] for r in scene.records("pull")] == [["pull", IMAGE]],
               "the image is pulled once, before any branch's clock starts",
               str(scene.records("pull")))
        (scene.bundle / "tutorial.yaml").write_text(
            MODULE_YAML.replace("  env: [GRADE_KEY, GRADE_MISSING]\n", "  network: true\n"))
        scene.record.unlink()
        scene.run_all("--only", "alice")
        runs = scene.records("run")
        record(runs and all("--network" not in r["argv"] for r in runs),
               "network: true passes no --network flag", str(runs[0]["argv"]))
        record(all(not r["parsed"]["env"] and "GRADE_KEY" not in r["env"] for r in runs),
               "with no declared env, none is passed")


def test_env_warning_and_masking() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all()
        record(code == 0 and "GRADE_MISSING" in err and "warning" in err,
               "a missing declared variable warns and the run continues", f"{code} {err}")
        record(any("GRADE_MISSING" in w for w in scene.results()["warnings"]),
               "the warning is in the working file")
        record(all("GRADE_MISSING" not in r["argv"] for r in scene.records("run")),
               "a missing variable is not passed")
        alice = scene.results()["branches"]["alice"]["validators"]["scorer-tests"]
        record("tests ok key=[masked:GRADE_KEY]" in alice["output"],
               "a declared value is masked in stored output", alice["output"])
        text = (scene.store() / "run.json").read_text()
        record(SECRET not in text and SECRET not in out and SECRET not in err,
               "the value is nowhere in the working file or the output")


def test_clean_output() -> None:
    limit = gr.OUTPUT_LIMIT
    secret = "ABCDEFGHIJKLMNOPQRST"
    secrets = {"KEY": secret}

    def no_part(text: str) -> bool:
        # no run of 5+ characters of the secret survives
        return not any(secret[i:i + 5] in text for i in range(len(secret) - 4))

    straddling = ("x" * (limit - 8) + secret + "y" * 100).encode()
    text = gr.clean_output(straddling, False, secrets)
    record(no_part(text), "a value straddling the size limit is masked, not cut in half", text[-60:])
    control = straddling.decode()[:limit]
    record(not no_part(control), "control: truncating first would have left part of the value")
    record(text.endswith(gr.TRUNCATED_MARK) and len(text) <= limit + len(gr.TRUNCATED_MARK),
           "output over the limit is truncated and says so", str(len(text)))
    record(gr.clean_output(b"short", False, secrets) == "short", "short output is unchanged")
    many = (secret * 1000 + secret[:9]).encode()
    text = gr.clean_output(many, True, secrets)
    record(no_part(text) and secret[:9] not in text,
           "a value cut by the capture cap itself does not survive, even after masks shrink the text",
           text[-60:])
    record(gr.TRUNCATED_MARK in text, "a capped capture says it was truncated")
    text = gr.clean_output(b"key=ABC and key=ABCDEF", False, {"A": "ABC", "B": "ABCDEF", "C": ""})
    record(text == "key=[masked:A] and key=[masked:B]",
           "the longer value is masked first, and an empty value masks nothing", text)
    text = gr.clean_output(b"x caf\xe9 y", False, {"KEY": "caf\udce9"})
    record(text == "x [masked:KEY] y", "a value that is not UTF-8 is masked too", repr(text))
    text = gr.clean_output(b"\xff\xfe binary " + secret.encode(), False, secrets)
    record(secret not in text and "[masked:KEY]" in text, "undecodable bytes do not stop masking", text)


def test_huge_output_end_to_end() -> None:
    yaml = hang_yaml(
        '  flood: { kind: command, command: [sh, -c, "head -c 3000000 /dev/zero | tr \\"\\\\000\\" x; echo ; exit 1"] }',
        "    flood: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        got = scene.results()["branches"]["alice"]["validators"]["flood"]
        record(code == 0 and got["passed"] is False and "exit status 1" in got["reason"],
               "a flood of output neither blocks the run nor loses the exit status", f"{code} {err} {got['reason']}")
        record(gr.TRUNCATED_MARK in got["output"]
               and len(got["output"]) <= gr.OUTPUT_LIMIT + len(gr.TRUNCATED_MARK),
               "stored output is cut to the fixed size", str(len(got["output"])))


def test_time_limit() -> None:
    yaml = hang_yaml(
        '  quick: { kind: command, command: [sh, -c, "echo fine"] }\n'
        '  hang: { kind: command, command: [sh, -c, "echo started; sleep 60"] }\n'
        '  after: { kind: command, command: [sh, -c, "echo after"] }\n'
        '  has-readme: { kind: file-exists, path: README.md }',
        "    quick: { points: 10 }\n    hang: { points: 10, gate: true }\n"
        "    after: { points: 10 }\n    has-readme: { points: 10 }")
    for kill_fails in (False, True):
        with tempfile.TemporaryDirectory() as tmp:
            scene = Scene(tmp, module_yaml=yaml, kill_fails=kill_fails)
            scene.cli("collect", COHORT_URL, "m1")
            began = time.monotonic()
            code, out, err = scene.run_all("--only", "alice", prelude=LIMIT_PRELUDE)
            took = time.monotonic() - began
            data = scene.results()["branches"]["alice"]
            got = data["validators"]
            tag = "kill refused: " if kill_fails else ""
            record(code == 0 and took < 40, tag + "a hanging validator does not hang the run",
                   f"{code} {took:.1f}s {err}")
            record(data["timed_out"] is True, tag + "the branch is marked as having hit its limit")
            record(got["quick"]["passed"] is True and got["has-readme"]["passed"] is True,
                   tag + "what finished before the limit keeps its result", str(got))
            record(got["hang"]["passed"] is False and "time limit" in got["hang"]["reason"]
                   and "started" in got["hang"]["output"] and got["hang"]["gate"] is True,
                   tag + "the hanging validator fails with the reason and its output so far", str(got["hang"]))
            record(got["after"]["passed"] is False and "time limit" in got["after"]["reason"]
                   and "not run" in got["after"]["reason"],
                   tag + "the remaining validator counts as failed, with the reason", str(got["after"]))
            runs = scene.records("run")
            record([r["parsed"]["command"][-1] for r in runs] == ["echo fine", "echo started; sleep 60"],
                   tag + "the remaining validator never starts a container", str(len(runs)))
            kills = scene.records("kill")
            hang = runs[1]["parsed"]["name"]
            record([k["argv"] for k in kills] == [["kill", hang]],
                   tag + "the time limit issues `<runtime> kill <the generated name>`", str(kills))
            record(runs[1]["parsed"]["rm"] is True, tag + "the container runs with --rm")
            record(scene.leftovers() == [], tag + "the checkout is removed after a timeout",
                   str(scene.leftovers()))
            warned = hang in err and any(hang in w for w in scene.results()["warnings"])
            record(warned is kill_fails, tag + "a failed kill warns naming the container; a good one does not",
                   err)


def test_interrupted_run_kills_the_container() -> None:
    yaml = hang_yaml('  hang: { kind: command, command: [sh, -c, "sleep 60"] }',
                     "    hang: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.cli("collect", COHORT_URL, "m1")
        proc = subprocess.Popen(
            [sys.executable, "-B", str(SCRIPT), "run", "--bundle", str(scene.bundle), COHORT_URL, "m1",
             "--only", "alice"], env=scene.env, cwd=scene.cwd,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        waited = 0.0
        while not scene.records("run") and waited < 30:
            time.sleep(0.1)
            waited += 0.1
        name = scene.records("run")[0]["parsed"]["name"]
        pidfile = Path(str(scene.record) + "." + name)
        while not pidfile.exists() and waited < 30:
            time.sleep(0.1)
            waited += 0.1
        proc.send_signal(signal.SIGTERM)
        code = proc.wait(timeout=30)
        record(code != 0, "a terminated run exits non-zero", str(code))
        record([k["argv"] for k in scene.records("kill")] == [["kill", name]],
               "terminating the run kills the container", str(scene.records("kill")))
        record(scene.leftovers() == [], "terminating the run removes the checkout", str(scene.leftovers()))


def test_hanging_regex() -> None:
    yaml = hang_yaml(
        '  evil: { kind: file-contains, path: slow.txt, pattern: "^(a+)+$" }\n'
        '  later: { kind: command, command: [sh, -c, "echo later"] }',
        "    evil: { points: 10 }\n    later: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.add_branch("erin/m1", {"slow.txt": "a" * 64 + "b\n"})
        scene.cli("collect", COHORT_URL, "m1")
        began = time.monotonic()
        code, out, err = scene.run_all("--only", "erin", prelude=LIMIT_PRELUDE)
        took = time.monotonic() - began
        got = scene.results()["branches"]["erin"]["validators"]
        record(code == 0 and took < 40, "a pathological regex does not hang the run", f"{code} {took:.1f}s {err}")
        record(got["evil"]["passed"] is False and "time limit" in got["evil"]["reason"],
               "the regex is stopped by the branch's time limit", str(got["evil"]))
        record(got["later"]["passed"] is False and "not run" in got["later"]["reason"],
               "the remaining validator counts as failed", str(got["later"]))
        record(scene.records("run") == [], "no container started after the limit")
        record(scene.leftovers() == [], "the checkout is removed", str(scene.leftovers()))


def test_file_checks() -> None:
    yaml = hang_yaml(
        '  plain: { kind: file-contains, path: notes.md, pattern: "#\\\\[test\\\\]" }\n'
        '  word: { kind: file-contains, path: notes.md, pattern: "^second line$" }\n'
        '  no-match: { kind: file-contains, path: notes.md, pattern: "absent" }\n'
        '  missing: { kind: file-contains, path: nope.md, pattern: "x" }\n'
        '  a-dir: { kind: file-exists, path: sub }\n'
        '  inner-link: { kind: file-contains, path: inner, pattern: "second" }\n'
        '  out-link: { kind: file-contains, path: out, pattern: "." }\n'
        '  out-exists: { kind: file-exists, path: out }\n'
        '  via-dir: { kind: file-exists, path: etc/passwd }\n'
        '  dotdot: { kind: file-exists, path: ../../../../etc/passwd }\n'
        '  absolute: { kind: file-exists, path: /etc/passwd }\n'
        '  planted: { kind: file-exists, path: planted.txt }\n'
        '  plant: { kind: command, command: [sh, -c, "echo y > planted.txt; rm notes.md"] }\n'
        '  after-plant: { kind: file-exists, path: notes.md }',
        "\n".join(f"    {n}: {{ points: 10 }}" for n in (
            "plant", "plain", "word", "no-match", "missing", "a-dir", "inner-link", "out-link",
            "out-exists", "via-dir", "dotdot", "absolute", "planted", "after-plant")))
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.add_branch("erin/m1", {
            "notes.md": "first #[test]\nsecond line\n",
            "sub/x": "x\n",
            "inner": ("notes.md",),
            "out": ("/etc/passwd",),
            "etc": ("/etc",),
        })
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "erin")
        got = scene.results()["branches"]["erin"]["validators"]
        want = {"plant": True, "plain": True, "word": True, "no-match": False, "missing": False,
                "a-dir": True, "inner-link": True, "out-link": False, "out-exists": False,
                "via-dir": False, "dotdot": False, "absolute": False,
                "planted": False, "after-plant": True}
        for name, passed in want.items():
            record(got[name]["passed"] is passed, f"file check {name}: {'pass' if passed else 'fail'}",
                   str(got[name]))
        for name in ("out-link", "out-exists", "via-dir", "dotdot", "absolute"):
            record("outside the checkout" in got[name]["reason"], f"{name} says it left the checkout",
                   str(got[name]["reason"]))
        record(all("/etc" not in r["argv"] for r in scene.records("run")),
               "file checks run in no container")
        record(len(scene.records("run")) == 1, "only the command validator started a container")


def test_no_runtime() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        env = dict(scene.env, BELAY_CONTAINER_RUNTIME=str(scene.tmp / "no-such-runtime"))
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", env=env)
        record(code == gr.EXIT_REFUSED and "no-such-runtime" in err,
               "a named runtime that does not exist stops the run", f"{code} {err}")
        empty = scene.tmp / "emptybin"
        empty.mkdir()
        env = {k: v for k, v in scene.env.items() if k != "BELAY_CONTAINER_RUNTIME"}
        env["PATH"] = str(empty)
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", env=env)
        record(code == gr.EXIT_REFUSED and "docker" in err and "podman" in err,
               "no docker and no podman stops the run", f"{code} {err}")
        record(scene.records() == [] and scene.leftovers() == [] and not (scene.store() / "run.json").exists(),
               "with no runtime nothing ran, nothing was checked out, nothing was written")
        record("alice" not in out, "with no runtime no participant is reported", out)
        # selection order
        both = scene.tmp / "both"
        both.mkdir()
        for name in ("docker", "podman"):
            scene.write_stub(both / name)
        only = scene.tmp / "only"
        only.mkdir()
        scene.write_stub(only / "podman")
        saved = {k: os.environ.get(k) for k in ("PATH", "BELAY_CONTAINER_RUNTIME")}
        try:
            os.environ.pop("BELAY_CONTAINER_RUNTIME", None)
            os.environ["PATH"] = str(both)
            record(gr.find_runtime() == str(both / "docker"), "docker is preferred", gr.find_runtime())
            os.environ["PATH"] = str(only)
            record(gr.find_runtime() == str(only / "podman"), "else podman", gr.find_runtime())
            os.environ["PATH"] = str(both)
            os.environ["BELAY_CONTAINER_RUNTIME"] = str(only / "podman")
            record(gr.find_runtime() == str(only / "podman"), "the variable wins")
            os.environ["BELAY_CONTAINER_RUNTIME"] = str(empty / "gone")
            record(refused(gr.find_runtime) is not None,
                   "a named runtime that is missing never falls back to docker")
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, info_fails=True)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all()
        record(code == gr.EXIT_REFUSED and "does not answer" in err, "a runtime that does not answer stops the run",
               f"{code} {err}")
        record(scene.records("run") == [] and not (scene.store() / "run.json").exists(),
               "no participant is failed because the runtime is down")


def test_run_refusals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        code, out, err = scene.run_all()
        record(code == gr.EXIT_REFUSED and "collect" in err and scene.records("run") == []
               and "cohort.invalid" not in err,
               "run before collect is refused, naming collect and no form it would refuse",
               f"{code} {err}")
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice", "--only", "nobody")
        record(code == gr.EXIT_REFUSED and "nobody" in err and scene.records("run") == [],
               "--only with an unknown participant runs nothing", f"{code} {err}")
        code, out, err = scene.run_all("--only", "alice", "bob")
        record(code == gr.EXIT_USAGE and scene.records("run") == [],
               "--only takes one value each", f"{code} {err}")
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m2")
        record(code == gr.EXIT_REFUSED and "m1" in err and "m2" in err,
               "a module id that is not the bundle's is refused", f"{code} {err}")
        for label, bad, needle in (
            ("a manual validator", MODULE_YAML.replace("kind: file-exists, path: README.md", "kind: manual"), "has-readme"),
            ("a shell-string command", MODULE_YAML.replace("command: [sh, lint.sh]", 'command: "sh lint.sh"'), "lint"),
            ("an undeclared validator", MODULE_YAML.replace("  lint: { kind: command, command: [sh, lint.sh] }\n", ""), "lint"),
            ("a bad regex", MODULE_YAML.replace("^def test_[a-z]+", "(unclosed"), "has-test"),
            ("no image", MODULE_YAML.replace("  image: python:3.12-slim\n", ""), "image"),
            ("an option as image", MODULE_YAML.replace("image: python:3.12-slim", "image: --privileged"), "image"),
            ("a variable with a value", MODULE_YAML.replace("GRADE_MISSING", '"A=b"'), "A=b"),
        ):
            (scene.bundle / "tutorial.yaml").write_text(bad)
            code, out, err = scene.run_all()
            record(code == gr.EXIT_REFUSED and needle in err and scene.records("run") == [],
                   f"{label} is refused before anything runs", f"{code} {err}")
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML)
        colon = scene.tmp / "a:b"
        colon.mkdir()
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1",
                                   env=dict(scene.env, TMPDIR=str(colon)))
        record(code == gr.EXIT_REFUSED and "':'" in err and scene.records("run") == [],
               "a temporary directory that cannot be mounted is refused", f"{code} {err}")
        (scene.bundle / "tutorial.yaml").write_text("id: m1\nversion: 1\n")
        code, out, err = scene.run_all()
        record(code == gr.EXIT_REFUSED and "`grading`" in err, "a bundle with no grading is refused",
               f"{code} {err}")
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace("  timeout_minutes: 15\n", ""))
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and scene.results()["timeout_minutes"] == gr.DEFAULT_TIMEOUT_MINUTES,
               "control: no timeout_minutes still has a limit, the default", f"{code} {err}")


def test_run_again_and_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all()
        before = scene.results()["branches"]["alice"]["commit"]
        # A push after collect is not picked up by run: the trainer confirmed the list.
        scene.add_branch("bob/m1", PARTICIPANTS["alice"])
        code, out, err = scene.run_all("--only", "bob")
        data = scene.results()
        record(code == 0 and sorted(data["branches"]) == ["alice", "bob", "carol"],
               "--only keeps the other participants' results", str(sorted(data["branches"])))
        record(data["branches"]["alice"]["commit"] == before, "their results are untouched")
        record(data["branches"]["bob"]["validators"]["scorer-tests"]["passed"] is False,
               "run grades what collect fetched, not a later push")
        record(len(scene.records("run")) == 8, "--only ran one branch more", str(len(scene.records("run"))))
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "bob")
        record(scene.results()["branches"]["bob"]["validators"]["scorer-tests"]["passed"] is True,
               "after collect again, run sees the new commit")
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace("points: 30", "points: 40"))
        code, out, err = scene.run_all("--only", "carol")
        data = scene.results()
        record(sorted(data["branches"]) == ["carol"] and "scheme" in err,
               "a changed scheme discards results made under the old one, and says so",
               f"{sorted(data['branches'])} {err}")


def test_exit_125_is_not_a_silent_fail() -> None:
    for status, words in ((125, ("runtime refused", "rootless podman", "--pids-limit")),
                          (126, ("could not be run",)), (127, ("could not be run",))):
        yaml = hang_yaml(f'  boom: {{ kind: command, command: [sh, -c, "exit {status}"] }}',
                         "    boom: { points: 10 }")
        with tempfile.TemporaryDirectory() as tmp:
            scene = Scene(tmp, module_yaml=yaml)
            scene.cli("collect", COHORT_URL, "m1")
            code, out, err = scene.run_all("--only", "alice")
            got = scene.results()["branches"]["alice"]["validators"]["boom"]
            record(code == gr.EXIT_REFUSED and str(status) in err and got["passed"] is False
                   and all(w in got["reason"] for w in words),
                   f"exit {status} says plainly what it may mean, and the exit code says so",
                   f"{code} {err} {got}")
    yaml = hang_yaml('  boom: { kind: command, command: [sh, -c, "exit 124"] }', "    boom: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0, "control: exit 124 is an ordinary failure", f"{code} {err}")


def test_checkout_removal() -> None:
    yaml = hang_yaml('  lock: { kind: command, command: [sh, -c, "mkdir locked; echo x > locked/f; chmod 000 locked"] }',
                     "    lock: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and scene.leftovers() == [], "a directory the code locked is still removed",
               f"{scene.leftovers()} {err}")
        # Files a rootful container left owned by root: the trainer cannot delete
        # them, so the same image removes them, then the trainer removes the rest.
        prelude = (
            "real = grade.force_remove\ncalls = []\n"
            "def fake(p):\n    calls.append(p)\n    return real(p) if len(calls) > 1 else False\n"
            "grade.force_remove = fake")
        scene.record.unlink()
        code, out, err = scene.run_all("--only", "alice", prelude=prelude)
        runs = scene.records("run")
        record(len(runs) == 2 and runs[1]["parsed"]["command"] == ["find", MOUNT, "-mindepth", "1", "-delete"]
               and runs[1]["parsed"]["network"] == "none" and runs[1]["parsed"]["image"] == "python:3.12-slim",
               "a checkout the trainer cannot delete is emptied by the same image, with no network",
               str([r["parsed"]["command"] for r in runs]))
        record(all("GRADE_KEY" not in r["env"] for r in runs[1:]), "that cleanup gets no declared variable")
        record(scene.leftovers() == [], "and the checkout is gone", str(scene.leftovers()))
        prelude = "grade.force_remove = lambda p: False"
        code, out, err = scene.run_all("--only", "alice", prelude=prelude)
        left = scene.leftovers()
        record(left and left[0] in err and "could not remove" in err,
               "a checkout that cannot be removed is reported, naming it", f"{left} {err}")
        for name in left:
            shutil.rmtree(scene.tmp / name, ignore_errors=True)
    # A failed checkout is removed too, and counts against no one silently.
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all(
            "--only", "alice",
            prelude="def boom(*a):\n    raise grade.CheckoutFailed('cannot')\ngrade.make_checkout = boom")
        got = scene.results()["branches"]["alice"]["validators"]
        record(all(v["passed"] is False and "checkout failed" in v["reason"] for v in got.values()),
               "a failed checkout fails each validator with the reason", str(got))
        record(scene.records("run") == [] and scene.leftovers() == [],
               "a failed checkout starts no container and leaves nothing", str(scene.leftovers()))
        record(code == gr.EXIT_REFUSED, "a failed checkout shows in the exit code", str(code))


def test_trainer_git_config_does_not_reach_the_checkout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.add_branch("erin/m1", {".gitattributes": "README.md filter=canary\n", "README.md": "erin\n"})
        scene.cli("collect", COHORT_URL, "m1")
        hooks = scene.tmp / "trainer-hooks"
        hooks.mkdir()
        canary = scene.tmp / "hook-fired"
        hook = hooks / "post-checkout"
        hook.write_text(f"#!/bin/sh\ntouch {canary}\n")
        hook.chmod(0o755)
        config = scene.tmp / "trainer-gitconfig"
        smudged = scene.tmp / "filter-fired"
        config.write_text(f"[core]\n\thooksPath = {hooks}\n[init]\n\ttemplateDir = {hooks}\n"
                          f"[filter \"canary\"]\n\tsmudge = \"touch {smudged}; cat\"\n"
                          f"[url \"{scene.bare}\"]\n\tinsteadOf = x\n")
        env = dict(scene.env, GIT_CONFIG_GLOBAL=str(config))
        control = scene.tmp / "control"
        subprocess.run(["git", "clone", "-q", str(scene.bare), str(control), "-b", "alice/m1"],
                       env=env, capture_output=True, check=True)
        record(canary.exists(), "control: that config does fire a checkout hook in plain git")
        canary.unlink()
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "alice", env=env)
        record(code == 0 and not canary.exists(), "the trainer's git hooks do not run on participant code",
               f"{code} {err}")
        control = scene.tmp / "control-filter"
        subprocess.run(["git", "clone", "-q", str(scene.bare), str(control), "-b", "erin/m1"],
                       env=env, capture_output=True, check=True)
        record(smudged.exists(), "control: that config does run a smudge filter a branch asks for")
        smudged.unlink()
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "erin", env=env)
        record(code == 0 and not smudged.exists(),
               "a filter in the trainer's git config does not run on participant content", f"{code} {err}")
        co = scene.records("run")[0]["checkout"]
        record(str(hooks) not in co["git_config"], "the trainer's git config is not in the checkout")


def test_cache_is_not_reused_for_another_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        other_port = "https://cohort.invalid:8443/acme/team-1.git"
        for url, why in ((other_port, "another port"), ("ssh://carl@cohort.invalid/acme/team-1", "another account")):
            code, out, err = scene.run_all(url=url)
            record(code == gr.EXIT_REFUSED and "collect" in err and scene.records("run") == [],
                   f"run under {why} does not grade the commits of the collected URL", f"{code} {err}")
        code, out, err = scene.run_all("--only", "alice", url="https://cohort.invalid:443/acme/team-1.git")
        record(code == 0 and scene.records("run") != [], "control: the default port is the same cohort",
               f"{code} {err}")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        code, out, err = scene.cli("collect", ALICE_URL, "m1")
        record(code == 0, "collect over an account's scp URL", f"{code} {err}")
        code, out, err = scene.run_all(url="bob@cohort.invalid:acme/team-1")
        record(code == gr.EXIT_REFUSED and "collect" in err and scene.records("run") == [],
               "another ssh account does not reuse the cache", f"{code} {err}")
        code, out, err = scene.run_all("--only", "alice", url=ALICE_URL)
        record(code == 0 and scene.records("run") != [], "control: the same account does", f"{code} {err}")


def test_run_with_a_token_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", TOKEN_URL, "m1")
        code, out, err = scene.run_all(url=TOKEN_URL)
        record(code == 0 and sorted(scene.results()["branches"]) == ["alice", "bob", "carol"],
               "run works with a URL holding a credential, in the same cohort", f"{code} {err}")
        root = scene.data / "belay" / "grading"
        holding = [str(p) for p in root.rglob("*") if p.is_file() and b"s3cr3t" in p.read_bytes()]
        record(holding == [] and "s3cr3t" not in out + err,
               "the credential is in no stored file and no output", str(holding))
        record(all("s3cr3t" not in json.dumps(r) for r in scene.records()),
               "the credential reaches the runtime neither as an argument nor in its environment")


def test_mounted_git_discloses_nothing() -> None:
    login = pwd.getpwuid(os.getuid()).pw_name
    host = socket.gethostname()
    # A name under 5 characters can occur by chance in compressed bytes.
    names = [n for n in (login, host) if len(n) >= 5]

    def found_in(tree: Path, needles: list[str]) -> set[str]:
        hits = set()
        for path in tree.rglob("*"):
            if path.is_file():
                data = path.read_bytes()
                hits |= {n for n in needles if n.encode() in data}
        return hits

    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all("--only", "alice")
        snapshot = Path(str(scene.record) + ".git-snapshot")
        cache = str(scene.data / "belay" / "grading" / gr.cohort_name(COHORT_URL) / gr.CACHE_NAME)
        needles = [cache, str(scene.tmp), *names]
        record(snapshot.is_dir() and any(snapshot.rglob("*")), "the stub kept what was mounted")
        hits = found_in(snapshot, needles)
        record(hits == set(), "the mounted .git holds no cache path, login or hostname", str(hits))
        record(not (snapshot / "FETCH_HEAD").exists() and not (snapshot / "logs").exists(),
               "the mounted .git has no FETCH_HEAD and no reflog")
        # Control: the same steps with git's defaults do disclose them, so the scan can see them.
        control = scene.tmp / "control"
        env = gr.clean_git_env()
        for step in (["init", "-q", "--template=", str(control)],
                     ["-C", str(control), "fetch", "-q", "--no-tags", "--", cache,
                      "+refs/heads/alice/m1:refs/heads/alice/m1"],
                     ["-C", str(control), "checkout", "-q", "--detach", scene.commits["alice/m1"]]):
            subprocess.run(["git", *step], env=env, capture_output=True, check=True)
        hits = found_in(control / ".git", [cache, *names])
        record(hits == {cache, *names}, "control: git's defaults write them, and the scan finds them", str(hits))


def test_docker_proxies_warning() -> None:
    proxy = "http://u:proxy-p4ss@proxy.corp:3128"
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and "proxies" not in err, "control: no docker config, no warning", err)
        conf = Path(scene.env["HOME"]) / ".docker" / "config.json"
        conf.parent.mkdir(parents=True)
        conf.write_text("{ not json")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and "proxies" not in err, "an unreadable docker config changes nothing", f"{code} {err}")
        conf.write_text(json.dumps({"auths": {}}))
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and "proxies" not in err, "control: a config with no proxies is silent", err)
        conf.write_text(json.dumps({"proxies": {"default": {"httpProxy": proxy}}}))
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and "proxies" in err and "warning" in err, "a proxies key warns", f"{code} {err}")
        text = (scene.store() / "run.json").read_text()
        record("proxies" in text and "proxy-p4ss" not in text + out + err and "proxy.corp" not in text + out + err,
               "the warning is in the working file, and the value is nowhere", err)
        moved = scene.tmp / "dockercfg"
        moved.mkdir()
        env = dict(scene.env, DOCKER_CONFIG=str(moved))
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "alice", env=env)
        record(code == 0 and "proxies" not in err, "DOCKER_CONFIG replaces ~/.docker", err)
        (moved / "config.json").write_text(json.dumps({"proxies": {"default": {"httpProxy": proxy}}}))
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "alice", env=env)
        record(code == 0 and "proxies" in err and "proxy-p4ss" not in err, "$DOCKER_CONFIG/config.json is read", err)


def test_run_json_records() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all()
        branch = scene.results()["branches"]["alice"]
        record(branch["runtime"] == str(scene.stub) and branch["image_digest"] == "sha256:stubdigest",
               "each branch records the runtime and the image's digest", str(branch)[:200])
        # A full re-run starts empty: a deleted branch does not stay.
        git_fixture("--git-dir", str(scene.bare), "update-ref", "-d", "refs/heads/carol/m1", cwd=scene.tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record("carol" in scene.results()["branches"], "control: --only keeps what it did not run")
        code, out, err = scene.run_all()
        record(code == 0 and sorted(scene.results()["branches"]) == ["alice", "bob"],
               "a full re-run drops a deleted branch", str(sorted(scene.results()["branches"])))
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, digest_fails=True)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0 and scene.results()["branches"]["alice"]["image_digest"] == "unknown",
               "a digest the runtime does not give is recorded as unknown", f"{code} {err}")


def test_real_checkout_failure() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        cache = scene.data / "belay" / "grading" / gr.cohort_name(COHORT_URL) / gr.CACHE_NAME
        blob = git_fixture("--git-dir", str(cache), "rev-parse", "refs/heads/alice/m1:README.md", cwd=scene.tmp)
        loose = cache / "objects" / blob[:2] / blob[2:]
        record(loose.exists(), "the fixture can reach the blob it breaks", str(loose))
        loose.unlink()
        code, out, err = scene.run_all()
        data = scene.results()["branches"]
        record(code == gr.EXIT_REFUSED and all(
            v["passed"] is False and "checkout failed" in v["reason"] for v in data["alice"]["validators"].values()),
            "a real git failure fails that branch's validators with the reason", f"{code} {data['alice']}")
        record(data["bob"]["validators"]["lint"]["passed"] is True
               and data["carol"]["validators"]["scorer-tests"]["passed"] is True,
               "the other participants are still graded")
        srcs = {r["checkout"]["src"] for r in scene.records("run")}
        record(len(scene.records("run")) == 4 and len(srcs) == 2, "the broken branch starts no container", str(srcs))
        record(scene.leftovers() == [], "it leaves nothing behind", str(scene.leftovers()))


def test_gitmodules_are_not_followed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        work = scene.work
        target = scene.commits["alice/m1"]
        git_fixture("checkout", "-q", "--orphan", "with-module", cwd=work)
        git_fixture("rm", "-rfq", "--ignore-unmatch", ".", cwd=work)
        (work / ".gitmodules").write_text(f'[submodule "sub"]\n\tpath = sub\n\turl = {scene.bare}\n')
        (work / "README.md").write_text("erin\n")
        (work / "run-tests.sh").write_text("exit 0\n")
        (work / "lint.sh").write_text("exit 0\n")
        git_fixture("add", "-A", cwd=work)
        git_fixture("update-index", "--add", "--cacheinfo", f"160000,{target},sub", cwd=work)
        git_fixture("commit", "-q", "-m", "module", cwd=work)
        git_fixture("push", "-q", str(scene.bare), "HEAD:refs/heads/erin/m1", cwd=work)
        control = scene.tmp / "control"
        git_fixture("-c", "protocol.file.allow=always", "clone", "-q", "--recurse-submodules",
                    "-b", "erin/m1", str(scene.bare), str(control), cwd=scene.tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "erin")
        co = scene.records("run")[0]["checkout"]
        record((control / "sub" / "README.md").exists(), "control: a recursive clone would fetch it")
        record(code == 0 and not any(p.startswith("sub/") for p in co["tree"]) and ".gitmodules" in co["tree"],
               "a .gitmodules is not followed: the submodule's files are not in the checkout", f"{code} {co['tree']}")
        record(not (Path(str(scene.record) + ".git-snapshot") / "modules").exists(),
               "no submodule repository is fetched")


def test_local_git_timeout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        prelude = "grade.PROBE_TIMEOUT = 0.000001"
        code, out, err = scene.cli("collect", COHORT_URL, "m1", prelude=prelude)
        # collect reaches list_branches after a real fetch
        record(code == gr.EXIT_USAGE and "Traceback" not in err and "did not finish" in err,
               "a local git that times out in collect is reported, no traceback", f"{code} {err}")
        code, out, err = scene.run_all(prelude=prelude)
        record(code == gr.EXIT_USAGE and "Traceback" not in err and "did not finish" in err,
               "a local git that times out in run is reported, no traceback", f"{code} {err}")
        record(scene.records("run") == [], "and nothing ran")


def test_only_takes_positionals_after_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.cli("run", "--only", "alice", "--only", "bob", "--bundle", str(scene.bundle),
                                   COHORT_URL, "m1")
        record(code == 0 and sorted(scene.results()["branches"]) == ["alice", "bob"],
               "--only before the positionals does not swallow them; it repeats", f"{code} {err}")


def test_password_holding_a_slash() -> None:
    urls = ("https://user:pa/ss-SECRET@cohort.invalid/team-1", "ssh://user:pa/ss-SECRET@cohort.invalid/team-1")
    for url in urls:
        with tempfile.TemporaryDirectory() as tmp:
            scene = Scene(tmp)
            for command in (("collect", url, "m1"), ("run", "--bundle", str(scene.bundle), url, "m1")):
                code, out, err = scene.cli(*command)
                record(code == gr.EXIT_REFUSED and "SECRET" not in out + err and "'@'" in err,
                       f"{command[0]} refuses an '@' after the first '/' of {url[:8]}..., printing no value",
                       f"{code} {out}{err}")
            record(not scene.data.exists(), "no directory exists for it")
            record(scene.records() == [], "and nothing ran")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        code, out, err = scene.cli("collect", "https://host.invalid/o/a@b", "m1")
        record(code == gr.EXIT_REFUSED and "'@'" in err and not scene.data.exists(),
               "an '@' in a path is refused as well, to keep the rule simple", f"{code} {err}")
        code, out, err = scene.cli("collect", TOKEN_URL, "m1")
        record(code == 0, "control: an '@' in the authority is accepted", f"{code} {err}")


def test_port_rule() -> None:
    long_port = "1" * 5000
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        for url, label in ((f"https://h.invalid:{long_port}/o/r", "5000 digits"),
                           ("https://h.invalid:123456/o/r", "6 digits"),
                           ("ssh://u@h.invalid:\u00b2/o/r", "a superscript digit"),
                           ("https://h.invalid:abc/o/r", "letters")):
            for command in (("collect", url, "m1"), ("run", "--bundle", str(scene.bundle), url, "m1")):
                code, out, err = scene.cli(*command)
                record(code == gr.EXIT_REFUSED and "port" in err and "Traceback" not in err,
                       f"{command[0]} refuses a port of {label}", f"{code} {err[:200]}")
        record(not scene.data.exists(), "a refused port created nothing")
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), "https://h.invalid:65535/o/r", "m1")
        record(code == gr.EXIT_REFUSED and "port" not in err and "collect" in err,
               "control: five digits pass the URL rule", f"{code} {err}")
    for url in (f"https://h:{long_port}/o/r", "https://h:\u00b2/o/r"):
        record(bool(gr.cohort_name(url)), f"cohort_name does not raise on {url[:14]}...")
    record(gr.cohort_name("https://h:08443/o/r") == gr.cohort_name("https://h:8443/o/r")
           and gr.cohort_name("https://h:0443/o/r") == gr.cohort_name("https://h/o/r"),
           "leading zeros do not make another port")
    record(gr.cohort_name("alice@h:srv/x") == gr.cohort_name("alice@h:/srv/x") == gr.cohort_name("ssh://alice@h/srv/x"),
           "as the docstring says: the same user's relative and absolute paths share a cohort")


def test_ascii_stdout() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.add_hostile_branches()
        env = dict(scene.env, PYTHONIOENCODING="ascii")
        code, out, err = scene.cli("collect", COHORT_URL, "m1", env=env)
        record(code == 0 and "caf\\xe9/m1" in out and "Traceback" not in err,
               "collect survives an ASCII stream, with the name escaped", f"{code} {err[-200:]}")
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", env=env)
        record(code == 0 and "caf\\xe9/m1" in out and "Traceback" not in err,
               "run survives an ASCII stream, with the name escaped", f"{code} {err[-200:]}")
        (scene.bundle / "tutorial.yaml").write_text(
            MODULE_YAML.replace("lint", "l\u00efnt").replace("sh, l\u00efnt.sh", "sh, lint.sh"), encoding="utf-8")
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "alice", env=env)
        record(code == 0 and "l\\xefnt" in out and "Traceback" not in err,
               "a bundle's non-ASCII validator name does not crash an ASCII stream either", f"{code} {out[-200:]} {err[-200:]}")


def test_only_keeps_other_branches_provenance() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all()
        second = scene.tmp / "second-runtime"
        scene.write_stub(second, digest_fails=True)
        env = dict(scene.env, BELAY_CONTAINER_RUNTIME=str(second))
        code, out, err = scene.cli("run", "--bundle", str(scene.bundle), COHORT_URL, "m1", "--only", "bob", env=env)
        branches = scene.results()["branches"]
        record(code == 0 and branches["bob"]["runtime"] == str(second) and branches["bob"]["image_digest"] == "unknown",
               "the branch --only ran records this run's runtime and digest", f"{code} {branches['bob']}")
        for who in ("alice", "carol"):
            record(branches[who]["runtime"] == str(scene.stub)
                   and branches[who]["image_digest"] == "sha256:stubdigest",
                   f"{who} keeps the runtime and digest of the run that graded it", str(branches[who])[:160])


# --------------------------------------------------------------------------
# propose and confirm
# --------------------------------------------------------------------------

GATE_CRITERION_YAML = MODULE_YAML.replace(
    "      points: 20\n      standard: The choice is justified.\n",
    "      points: 20\n      standard: The choice is justified.\n      gate: true\n")
NO_GATE_YAML = MODULE_YAML.replace("{ points: 30, gate: true }", "{ points: 30 }")


def ratings(alice: int = 15, bob: int = 10, carol: int = 0) -> dict:
    return {"participants": {
        who: {"design": {"points": pts, "evidence": f"{who}: src/main.py:1 quoted"}}
        for who, pts in (("alice", alice), ("bob", bob), ("carol", carol))}}


def graded(scene: Scene, judged: dict | None = None) -> Path:
    """collect, run and write the judgement file; returns the judgement path."""
    scene.cli("collect", COHORT_URL, "m1")
    code, out, err = scene.run_all()
    assert code == 0, (out, err)
    path = scene.tmp / "judgement.json"
    path.write_text(json.dumps(judged if judged is not None else ratings()))
    return path


def propose(scene: Scene, judgement: Path) -> tuple[int, str, str]:
    return scene.cli("propose", "--bundle", str(scene.bundle), "--judgement", str(judgement),
                     COHORT_URL, "m1")


def confirm(scene: Scene, *extra: str, by: str | None = "Trainer T") -> tuple[int, str, str]:
    by_args = ["--by", by] if by is not None else []
    return scene.cli("confirm", "--bundle", str(scene.bundle), *by_args, *extra, COHORT_URL, "m1")


def load(scene: Scene, name: str) -> dict:
    return json.loads((scene.store() / name).read_text())


def test_propose_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        code, out, err = propose(scene, path)
        record(code == 0, "propose succeeds", f"{code} {out} {err}")
        prop = load(scene, "proposal.json")
        totals = {w: p["total"] for w, p in prop["participants"].items()}
        record(totals == {"alice": 75, "bob": 40, "carol": 40}, "totals of the three branches", str(totals))
        record({w: (p["validator_points"], p["rubric_points"]) for w, p in prop["participants"].items()}
               == {"alice": (60, 15), "bob": (30, 10), "carol": (40, 0)}, "validator and rubric points")
        record({w: p["gate"] for w, p in prop["participants"].items()}
               == {"alice": True, "bob": False, "carol": True}, "gate results")
        record(prop["max_total"] == 80 and prop["participants"]["bob"]["max_total"] == 80, "max_total")
        record(prop["ranking"] == [
            {"rank": 1, "total": 75, "participants": ["alice"], "tied": False},
            {"rank": 2, "total": 40, "participants": ["bob", "carol"], "tied": True}],
            "the ranking shows bob and carol as a tie", str(prop["ranking"]))
        record("TIE" in out and "rank 2= bob, carol (40)" in out, "the tie is printed as a tie", out)
        record(prop["participants"]["alice"]["commit"] == scene.commits["alice/m1"]
               and prop["grading_hash"], "the proposal records each commit and the grading hash")
        record(prop["participants"]["bob"]["validators"]["scorer-tests"]
               == {"passed": False, "points": 0, "gate": True, "reason": "exit status 1", "fault": False},
               "a failed validator earns 0 and keeps its reason")
        record(stat.S_IMODE((scene.store() / "proposal.json").stat().st_mode) == 0o600,
               "proposal.json is private")
        # Totals are never taken from the judgement: a key carrying one is refused.
        for extra in ({"totals": {"alice": 999}}, {"ranking": ["bob"]}):
            bad = {**ratings(), **extra}
            path.write_text(json.dumps(bad))
            before = (scene.store() / "proposal.json").read_text()
            code, out, err = propose(scene, path)
            record(code == 1 and "unknown top-level key" in err
                   and (scene.store() / "proposal.json").read_text() == before,
                   f"a judgement carrying {list(extra)[0]!r} is refused and changes nothing", err)
        path.write_text(json.dumps(ratings()))
        record(propose(scene, path)[0] == 0, "control: the clean judgement is accepted again")


def test_propose_refusals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)

        def refused_with(data: str | dict, needle: str, name: str) -> None:
            path.write_text(data if isinstance(data, str) else json.dumps(data))
            code, out, err = propose(scene, path)
            record(code != 0 and needle in err and not (scene.store() / "proposal.json").exists(),
                   f"propose refuses {name}", f"{code} {err}")

        missing_person = ratings()
        del missing_person["participants"]["carol"]
        refused_with(missing_person, "carol is in run.json and missing", "a missing participant")
        missing_crit = ratings()
        missing_crit["participants"]["bob"] = {}
        refused_with(missing_crit, "bob: criterion design is missing", "a missing criterion")
        for pts, name in ((21, "points above max"), (-1, "negative points"), (True, "boolean points"),
                          (1.5, "fractional points"), ("5", "string points")):
            bad = ratings()
            bad["participants"]["bob"]["design"]["points"] = pts
            refused_with(bad, "must be an integer from 0 to 20", name)
        for ev in ("", "   ", None):
            bad = ratings()
            bad["participants"]["bob"]["design"]["evidence"] = ev
            refused_with(bad, "has no evidence", f"evidence {ev!r}")
        extra_person = ratings()
        extra_person["participants"]["dave"] = extra_person["participants"]["bob"]
        refused_with(extra_person, "dave is in the judgement and is not in run.json", "a participant absent from run.json")
        extra_crit = ratings()
        extra_crit["participants"]["bob"]["bonus"] = {"points": 1, "evidence": "x"}
        refused_with(extra_crit, "bonus is not a criterion", "an unknown criterion")
        extra_key = ratings()
        extra_key["participants"]["bob"]["design"]["total"] = 5
        refused_with(extra_key, "unknown key 'total'", "a total inside a rating")
        refused_with('{"participants": {"alice": {}, "alice": {}}}', "not valid JSON", "a duplicate key")
        refused_with("[1]", "must be a JSON object", "a judgement that is a list")
        refused_with("{nope", "not valid JSON", "text that is not JSON")
        path.write_text(json.dumps(ratings()))
        code, out, err = scene.cli("propose", "--bundle", str(scene.bundle), "--judgement",
                                   str(scene.tmp / "absent.json"), COHORT_URL, "m1")
        record(code == 2 and "cannot read" in err, "a missing judgement file is a usage error", err)
        record(propose(scene, path)[0] == 0, "control: the valid judgement is accepted")
        # The scheme moved since the run: the validator results are not for it.
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace("points: 10", "points: 11", 1))
        code, out, err = propose(scene, path)
        record(code == 1 and "changed since the last run" in err, "propose refuses results of another scheme", err)
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        path = scene.tmp / "j.json"
        path.write_text(json.dumps(ratings()))
        code, out, err = propose(scene, path)
        record(code == 1 and "run `belay-grade run` first" in err, "propose before run is refused", err)


def test_confirm_values() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene, {**ratings(), "draft": {"why_best": "alice tests the failure path",
                                                      "gaps": {"bob": "gate not met"}}})
        record(propose(scene, path)[0] == 0, "propose with a draft")
        record(load(scene, "proposal.json")["draft"]["gaps"] == {"bob": "gate not met"}, "the draft is stored")
        code, out, err = confirm(scene, "--change", "bob:design=18:Better than it reads: it handles retries: see lines 4-9",
                                 by="Rob")
        record(code == 0, "confirm succeeds", f"{code} {out} {err}")
        final = load(scene, "final.json")
        record(sorted(final) == ["bundle_version", "confirmed_at", "confirmed_by", "module", "not_graded",
                                 "participants"] and final["not_graded"] == {}
               and final["module"] == "m1" and final["bundle_version"] == "1.2.0"
               and final["confirmed_by"] == "Rob" and final["confirmed_at"].endswith("Z"),
               "final.json top level has exactly the contract's keys", str(sorted(final)))
        bob = final["participants"]["bob"]
        record(sorted(bob) == ["commit", "criteria", "gate", "max_total", "total", "validators"],
               "a participant has exactly commit, validators, criteria, gate, total, max_total", str(sorted(bob)))
        record(all(final["participants"][w]["commit"] == scene.commits[f"{w}/m1"]
                   == load(scene, "proposal.json")["participants"][w]["commit"]
                   for w in ("alice", "bob", "carol")),
               "final.json records each participant's graded commit, as proposal.json does")
        record(bob["criteria"]["design"] == {
            "points": 18, "proposed_points": 10, "max": 20, "evidence": "bob: src/main.py:1 quoted",
            "changed_by_trainer": True,
            "reason": "Better than it reads: it handles retries: see lines 4-9"},
            "a change keeps its reason, colons included", str(bob["criteria"]))
        record(bob["validators"]["lint"] == {"passed": True, "points": 10}, "validators are {passed, points}")
        record((bob["total"], bob["gate"], bob["max_total"]) == (48, False, 80), "bob's total moves, the gate does not")
        alice = final["participants"]["alice"]["criteria"]["design"]
        record(alice["changed_by_trainer"] is False and alice["reason"] is None and alice["points"] == 15,
               "an unchanged criterion is not marked changed", str(alice))
        record({w: p["total"] for w, p in final["participants"].items()} == {"alice": 75, "bob": 48, "carol": 40},
               "confirmed totals")
        record(not any("winner" in k for k in final), "final.json stores no winner")
        record("changed bob:design 10 -> 18" in out and "previous confirmation" not in out,
               "confirm reports each change", out)
        record(not list(scene.store().glob("final.*.json")), "the first confirmation has nothing to keep")
        first = (scene.store() / "final.json").read_text()
        # Re-grade: a second confirmation keeps the first beside it.
        code, out, err = confirm(scene, by="Rob again")
        kept = sorted(p.name for p in scene.store().glob("final.*.json"))
        day = final["confirmed_at"][:10]
        record(code == 0 and kept == [f"final.{day}.json"]
               and (scene.store() / kept[0]).read_text() == first,
               "a re-confirmation keeps the old file, with its date", f"{kept} {err}")
        record(load(scene, "final.json")["confirmed_by"] == "Rob again"
               and load(scene, "final.json")["participants"]["bob"]["total"] == 40,
               "final.json is the new confirmation")
        code, out, err = confirm(scene, "--change", "carol:design=2:fine", by="Rob third")
        kept2 = sorted(p.name for p in scene.store().glob("final.*.json"))
        record(code == 0 and kept2 == [f"final.{day}-2.json", f"final.{day}.json"]
               and json.loads((scene.store() / f"final.{day}-2.json").read_text())["confirmed_by"] == "Rob again"
               and json.loads((scene.store() / f"final.{day}.json").read_text())["confirmed_by"] == "Rob",
               "two confirmations in one day do not overwrite each other", str(kept2))
        record(load(scene, "final.json")["participants"]["carol"]["total"] == 42
               and "changed carol:design 0 -> 2: fine" in out,
               "the third confirmation is computed from its own change", out)
        leftovers = [p.name for p in scene.store().iterdir() if p.name.startswith(".")]
        record(leftovers == [], "no temp file is left in the store", str(leftovers))
        # A re-grade writes a new proposal, and the next confirmation is made from it.
        path.write_text(json.dumps(ratings(alice=0, bob=0, carol=0)))
        record(propose(scene, path)[0] == 0, "propose again (re-grade)")
        pr = load(scene, "proposal.json")
        code, out, err = confirm(scene, "--change", "bob:design=20:full marks")
        top = load(scene, "final.json")
        record(code == 0 and sorted(pr["participants"]) == ["alice", "bob", "carol"]
               and top["participants"]["alice"]["total"] == 60 and top["participants"]["bob"]["total"] == 50,
               "confirm after a re-proposal uses the new proposal")


def test_confirm_top_tie() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene, ratings(alice=0, bob=0, carol=0))
        propose(scene, path)
        # alice 60 + 0, carol 40 + 0: a change lifts carol to 60, a real tie at the top.
        code, out, err = confirm(scene, "--change", "carol:design=20:full marks on review")
        final = load(scene, "final.json")
        record(code == 0 and final["participants"]["alice"]["total"] == 60
               and final["participants"]["carol"]["total"] == 60, "alice and carol tie at 60", str(err))
        record("the top place is a tie" in out and "rank 1= alice, carol (60)" in out,
               "a tie at the top is shown and not broken", out)
        record("winner" not in json.dumps(final), "the tie is not resolved in final.json")


def test_confirm_refusals() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        code, out, err = confirm(scene)
        record(code == 1 and "no proposal" in err, "confirm without a proposal is refused", err)
        propose(scene, path)

        def refused_with(needle: str, name: str, *extra: str, by: str | None = "T") -> None:
            code, out, err = confirm(scene, *extra, by=by)
            record(code != 0 and needle in err and not (scene.store() / "final.json").exists(),
                   f"confirm refuses {name}", f"{code} {err}")

        code, out, err = confirm(scene, by=None)
        record(code == 2 and "--by" in err and not (scene.store() / "final.json").exists(),
               "confirm without --by is refused", err)
        refused_with("--by", "an empty --by", by="  ")
        refused_with("has no reason", "a change with no reason", "--change", "bob:design=12:")
        refused_with("has no reason", "a change with a blank reason", "--change", "bob:design=12:   ")
        refused_with("is not <participant>", "a change with no reason separator", "--change", "bob:design=12")
        refused_with("is not <participant>", "a change with no points", "--change", "bob:design:why")
        refused_with("is not <participant>", "points that are not a number", "--change", "bob:design=x:why")
        refused_with("not in the proposal", "an unknown participant", "--change", "dave:design=1:why")
        refused_with("no points for", "an unknown criterion", "--change", "bob:style=1:why")
        refused_with("must be from 0 to 20", "points above max", "--change", "bob:design=21:why")
        refused_with("must be from 0 to 20", "negative points", "--change", "bob:design=-1:why")
        refused_with("twice", "the same change twice", "--change", "bob:design=11:a", "--change", "bob:design=12:b")
        refused_with("is not a change", "a change to the same points", "--change", "bob:design=10:why")
        code, out, err = confirm(scene, "--change", "bob:design=12:why")
        record(code == 0, "control: the same call with a valid change succeeds", err)
        (scene.store() / "final.json").unlink()
        for f in scene.store().glob("final.*.json"):
            f.unlink()

        # Staleness: confirm reads the local cache and does not fetch.
        git_fixture("--git-dir", str(scene.bare), "update-ref", "refs/heads/bob/m1",
                    scene.commits["alice/m1"], cwd=scene.tmp)
        code, out, err = confirm(scene)
        record(code == 0, "the remote moved and the cache did not: confirm does not fetch", err)
        (scene.store() / "final.json").unlink()
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = confirm(scene)
        record(code == 1 and "stale" in err and f"bob's branch moved: {scene.commits['bob/m1'][:12]} -> "
               f"{scene.commits['alice/m1'][:12]}" in err and "carol" not in err,
               "after collect, a moved branch makes the proposal stale and says which", err)
        record(not (scene.store() / "final.json").exists(), "a stale proposal writes nothing")
        # Back in place: control.
        git_fixture("--git-dir", str(scene.bare), "update-ref", "refs/heads/bob/m1",
                    scene.commits["bob/m1"], cwd=scene.tmp)
        scene.cli("collect", COHORT_URL, "m1")
        record(confirm(scene)[0] == 0, "control: the branch back where it was, confirm succeeds")
        (scene.store() / "final.json").unlink()
        git_fixture("--git-dir", str(scene.bare), "update-ref", "-d", "refs/heads/carol/m1", cwd=scene.tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = confirm(scene)
        record(code == 1 and "carol's branch is no longer in the cache" in err, "a removed branch is stale", err)
        git_fixture("--git-dir", str(scene.bare), "update-ref", "refs/heads/carol/m1",
                    scene.commits["carol/m1"], cwd=scene.tmp)
        scene.add_branch("dave/m1", {"README.md": "dave\n"})
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = confirm(scene)
        record(code == 1 and "dave has a branch the proposal does not cover" in err, "a new branch is reported", err)
        git_fixture("--git-dir", str(scene.bare), "update-ref", "-d", "refs/heads/dave/m1", cwd=scene.tmp)
        scene.cli("collect", COHORT_URL, "m1")
        record(confirm(scene)[0] == 0, "control: without the new branch, confirm succeeds")
        (scene.store() / "final.json").unlink()
        # The bundle's grading block changed since the proposal.
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace("standard: The choice is justified.",
                                                                       "standard: The choice is justified well."))
        code, out, err = confirm(scene)
        record(code == 1 and "`grading` block differs" in err, "a changed grading block makes the proposal stale", err)
        record(not (scene.store() / "final.json").exists(), "and writes nothing")


def test_gate_criterion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=GATE_CRITERION_YAML)
        path = graded(scene, ratings(alice=20, bob=20, carol=19))
        code, out, err = propose(scene, path)
        prop = load(scene, "proposal.json")
        record(code == 0 and {w: p["gate"] for w, p in prop["participants"].items()}
               == {"alice": True, "bob": False, "carol": False},
               "a gate criterion short of full points fails the gate even when the validators pass",
               f"{ {w: p['gate'] for w, p in prop['participants'].items()} } {err}")
        code, out, err = confirm(scene, "--change", "carol:design=20:the 19 was a misreading")
        final = load(scene, "final.json")["participants"]
        record(code == 0 and final["carol"]["gate"] is True,
               "the trainer's change to a gate criterion flips the gate to passed", f"{final['carol']['gate']} {err}")
        record(final["bob"]["gate"] is False, "a failed gate validator still fails it after full rubric points")
        code, out, err = confirm(scene, "--change", "alice:design=19:too generous")
        final = load(scene, "final.json")["participants"]
        record(code == 0 and final["alice"]["gate"] is False,
               "a change that lowers a gate criterion flips the gate to not passed", err)
        scheme = gr.load_scheme(scene.bundle)
        record([c.gate for c in scheme.rubric] == [True], "load_scheme reads gate on a criterion")


def test_reconfirm_names_the_changes_it_does_not_repeat() -> None:
    header = "does not repeat them"
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=GATE_CRITERION_YAML)
        path = graded(scene, ratings(alice=20, bob=10, carol=19))
        record(propose(scene, path)[0] == 0, "reconfirm: propose")
        code, out, err = confirm(scene, "--change", "carol:design=20:the 19 was a misreading",
                                 "--change", "bob:design=12:handles: retries")
        record(code == 0 and header not in out, "a first confirmation has nothing to name", f"{code} {out} {err}")
        record(load(scene, "final.json")["participants"]["carol"]["gate"] is True, "carol's gate passes on the change")

        code, out, err = confirm(scene, "--change", "bob:design=12:handles: retries")
        carol = load(scene, "final.json")["participants"]["carol"]
        record(code == 0 and "carol:design was 20, now 19: the 19 was a misreading" in out and header in out,
               "a change not repeated is named: participant, criterion, points and reason", out)
        record("bob:design was" not in out, "a repeated change is not named", out)
        record(carol["criteria"]["design"]["points"] == 19 and carol["criteria"]["design"]["changed_by_trainer"] is False
               and carol["gate"] is False, "the change is not carried over, and the gate goes back", str(carol))

        code, out, err = confirm(scene, "--change", "bob:design=13:one more")
        record(code == 0 and "bob:design was 12, now 13: handles: retries" in out,
               "a change to other points does not repeat the earlier one", out)
        code, out, err = confirm(scene, "--change", "bob:design=13:the same points, reworded")
        record(code == 0 and header not in out, "the same points with another reason repeat the change", out)

        # The proposal now gives the changed points, so --change would refuse them.
        path.write_text(json.dumps(ratings(alice=20, bob=13, carol=19)))
        record(propose(scene, path)[0] == 0, "reconfirm: propose again")
        code, out, err = confirm(scene)
        record(code == 0 and "bob:design was 13, now 13: the same points, reworded" in out,
               "points the proposal now gives stand, and losing the reason is named", out)

        final = scene.store() / "final.json"
        for damaged in ("{ not json", '"a string"', '{"participants": {"bob": {"criteria": {"design": 3}}}}'):
            final.write_text(damaged)
            code, out, err = confirm(scene)
            record(code == 0 and "Traceback" not in err and load(scene, "final.json")["confirmed_by"] == "Trainer T",
                   f"a damaged previous final.json does not stop a confirmation: {damaged}", f"{code} {err}")
            record(("could not be read" in out) == (damaged == "{ not json"),
                   f"only an unreadable one is reported as unreadable: {damaged}", out)
        data = load(scene, "final.json")
        data["participants"]["hostile\u2028name"] = {"criteria": {"gone": {
            "changed_by_trainer": True, "points": 1, "reason": "x\u2028y"}}}
        final.write_text(json.dumps(data))
        code, out, err = confirm(scene)
        record(code == 0 and "hostile\\u2028name:gone was 1, not in this confirmation: x\\u2028y" in out,
               "a change to what is no longer there is named, and escaped", out)


def test_change_addresses_what_check_49_allows() -> None:
    record(gr.parse_change("anna-2:q-1=3:why: this") == ("anna-2", "q-1", 3, "why: this"),
           "--change takes a participant and a criterion id of [a-z0-9-]+")
    record(refused(gr.parse_change, "anna:q:1=3:why") is not None, "--change cannot parse an id holding ':'")


def test_output_arrives_while_the_run_goes_on() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        conf = Path(scene.env["HOME"]) / ".docker" / "config.json"
        conf.parent.mkdir(parents=True)
        conf.write_text(json.dumps({"proxies": {"default": {"httpProxy": "http://proxy.corp:3128"}}}))
        stub = scene.stub.read_text()
        pull = 'if cmd == "pull":\n    sys.exit(0)'
        assert pull in stub, "the stub's pull has moved"
        scene.stub.write_text(stub.replace(pull, 'if cmd == "pull":\n    print("no such image", file=sys.stderr)\n    sys.exit(1)'))
        # A file, as a background run's output is: fully buffered unless told otherwise.
        # The spy copies what the file holds as each branch starts.
        output, seen = scene.tmp / "output.txt", scene.tmp / "seen.jsonl"
        prelude = (
            "import json\nreal = grade.run_branch\n"
            "def spy(plan, ref, warnings):\n"
            f"    text = open({str(output)!r}).read()\n"
            f"    open({str(seen)!r}, 'a').write(json.dumps([ref.participant, text]) + '\\n')\n"
            "    return real(plan, ref, warnings)\n"
            "grade.run_branch = spy\n")
        argv = [sys.executable, "-B", "-c",
                "import sys\nsys.path.insert(0, " + repr(str(SCRIPTS)) + ")\nimport grade\n"
                + prelude + "\nsys.exit(grade.main(sys.argv[1:]))",
                "run", "--bundle", str(scene.bundle), COHORT_URL, "m1"]
        with output.open("w") as sink:
            done = subprocess.run(argv, stdout=sink, stderr=subprocess.STDOUT, cwd=scene.cwd, env=scene.env)
        rows = [json.loads(line) for line in seen.read_text().splitlines()]
        record(done.returncode == 0 and [r[0] for r in rows] == ["alice", "bob", "carol"],
               "the spy saw each branch start", str(done.returncode))
        first = rows[0][1]
        for needle, name in (("warning: GRADE_MISSING is declared", "a missing variable"),
                             ("warning: could not pull", "a failed pull"),
                             ("warning: " + str(conf), "docker's proxies")):
            record(needle in first, f"{name} warns before the first branch starts", first)
        record("alice (" not in first and "results: " in first and "cohort: " in first,
               "control: no branch's output yet, and the results path is already there", first)
        record("alice (" in rows[1][1] and "scorer-tests" in rows[1][1],
               "the first branch's lines are readable while the next branch runs", rows[1][1])
        text = output.read_text()
        record(text.count("warning: GRADE_MISSING") == 1, "each warning is printed once", text)
        record(text.rstrip().splitlines()[-1].startswith("results: "), "the results path closes the output too", text)
        record(any("could not pull" in w for w in scene.results()["warnings"]), "the warnings stay in run.json")


def test_no_gate_is_null() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=NO_GATE_YAML)
        path = graded(scene)
        code, out, err = propose(scene, path)
        prop = load(scene, "proposal.json")
        record(code == 0 and all(p["gate"] is None for p in prop["participants"].values()),
               "a module with no gate records null, not passed", err)
        record("gate n/a" in out and "gate passed" not in out, "and prints it as n/a", out)
        code, out, err = confirm(scene)
        raw = (scene.store() / "final.json").read_text()
        final = json.loads(raw)["participants"]
        record(code == 0 and all(p["gate"] is None for p in final.values()) and '"gate": null' in raw,
               "final.json has gate null for every participant", err)
        record(final["bob"]["total"] == 40 and final["alice"]["total"] == 75, "the totals do not depend on the gate")


def test_writes_refuse_a_work_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "work"
        repo.mkdir()
        git_fixture("init", "-q", cwd=repo)
        target = repo / "store" / "module"
        msg = refused(gr.write_json_private, target / "proposal.json", {"x": 1})
        record(msg is not None and "work tree" in msg and not (repo / "store").exists(),
               "a write into a Git work tree is refused and creates nothing", str(msg))
        outside = Path(tmp) / "out"
        gr.write_json_private(outside / "ok.json", {"x": 1})
        record(json.loads((outside / "ok.json").read_text()) == {"x": 1}, "control: a write outside succeeds")
        with tempfile.TemporaryDirectory() as tmp2:
            scene = Scene(tmp2)
            path = graded(scene)
            scene.env["XDG_DATA_HOME"] = str(repo)
            code, out, err = propose(scene, path)
            record(code == 1 and "work tree" in err, "propose with the store in a work tree is refused", err)


# --------------------------------------------------------------------------
# propose and confirm: runtime faults, --exclude, and the fix-round extras
# --------------------------------------------------------------------------


def fault_scene(tmp: str, status: int) -> Scene:
    """Bob's gate validator exits `status`; alice and carol are as in PARTICIPANTS."""
    scene = Scene(tmp)
    scene.add_branch("bob/m1", {**PARTICIPANTS["bob"], "run-tests.sh": f"exit {status}\n"})
    return scene


def judge_without(scene: Scene, *people: str) -> Path:
    path = scene.tmp / "judgement.json"
    path.write_text(json.dumps({"participants": {
        w: {"design": {"points": p, "evidence": f"{w}: quoted"}}
        for w, p in (("alice", 15), ("carol", 5)) if w not in people}}))
    return path


def check_ungradable(scene: Scene, who: str, word: str, label: str) -> None:
    path = judge_without(scene, who)
    code, out, err = propose(scene, path)
    prop = load(scene, "proposal.json")
    bob = prop["participants"][who]
    record(code == 0, f"{label}: propose succeeds without a judgement of {who}", f"{code} {err}")
    record(bob["ungradable"] is True and word in bob["reason"] and bob["total"] is None
           and bob["gate"] is None and bob["validator_points"] is None,
           f"{label}: {who} is ungradable with the reason, no total and gate null", str(bob)[:300])
    record(any(v["fault"] and v["reason"] for v in bob["validators"].values()),
           f"{label}: the validator keeps its reason and fault flag", str(bob["validators"]))
    ranked = [n for g in prop["ranking"] for n in g["participants"]]
    record(who not in ranked and len(ranked) == 2, f"{label}: {who} has no rank", str(prop["ranking"]))
    record(f"{who}: NOT GRADABLE" in out and "runtime fault" in out and word in out,
           f"{label}: the propose summary says it is a fault, not the participant's result", out)
    code, out, err = confirm(scene)
    record(code == 1 and who in err and word in err and "--exclude" in err
           and not (scene.store() / "final.json").exists(),
           f"{label}: confirm refuses and names the participant", f"{code} {err}")
    for bad, needle in (("dave", "not in the proposal"), ("alice", "who is gradable")):
        code, out, err = confirm(scene, "--exclude", bad)
        record(code == 1 and needle in err, f"{label}: --exclude {bad} is refused", err)
    code, out, err = confirm(scene, "--exclude", who, "--change", f"{who}:design=1:x")
    record(code == 1 and "not graded" in err, f"{label}: a change to {who} is refused", err)
    code, out, err = confirm(scene, "--exclude", who)
    final = load(scene, "final.json")
    record(code == 0 and sorted(final["participants"]) == sorted({"alice", "bob", "carol"} - {who})
           and word in final["not_graded"][who]["reason"] and list(final["not_graded"]) == [who],
           f"{label}: --exclude leaves {who} out of final.json and lists it as not graded", f"{code} {err}")
    record(final["not_graded"][who]["commit"] == scene.commits[f"{who}/m1"] == bob["commit"],
           f"{label}: not_graded records the commit of an ungradable participant, as the proposal does",
           str(final["not_graded"]))
    record(f"{who}: NOT GRADABLE" in out, f"{label}: the confirm summary says it too", out)


def test_runtime_faults_are_not_scores() -> None:
    for status in (125, 126, 127):
        with tempfile.TemporaryDirectory() as tmp:
            scene = fault_scene(tmp, status)
            scene.cli("collect", COHORT_URL, "m1")
            code, out, err = scene.run_all()
            record(code == gr.EXIT_REFUSED and scene.results()["branches"]["bob"]["fault"]
                   and scene.results()["branches"]["alice"]["fault"] is None,
                   f"exit {status}: run.json marks bob's fault and nobody else's", err)
            check_ungradable(scene, "bob", f"exit status {status}", f"exit {status}")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        cache = scene.data / "belay" / "grading" / gr.cohort_name(COHORT_URL) / gr.CACHE_NAME
        blob = git_fixture("--git-dir", str(cache), "rev-parse", "refs/heads/alice/m1:README.md", cwd=scene.tmp)
        (cache / "objects" / blob[:2] / blob[2:]).unlink()
        scene.run_all()
        path = scene.tmp / "judgement.json"
        path.write_text(json.dumps({"participants": {
            w: {"design": {"points": p, "evidence": f"{w}: quoted"}} for w, p in (("bob", 10), ("carol", 5))}}))
        code, out, err = propose(scene, path)
        prop = load(scene, "proposal.json")
        record(code == 0 and prop["participants"]["alice"]["ungradable"] is True
               and "checkout failed" in prop["participants"]["alice"]["reason"]
               and prop["participants"]["alice"]["total"] is None
               and prop["participants"]["bob"]["ungradable"] is False,
               "a checkout failure makes that participant ungradable and no other", str(prop["participants"]["alice"])[:300])
        code, out, err = confirm(scene)
        record(code == 1 and "alice" in err and "checkout failed" in err, "confirm refuses on a checkout failure", err)
        # A judgement that does cover the ungradable participant is checked and then unused.
        path.write_text(json.dumps({"participants": {
            w: {"design": {"points": p, "evidence": f"{w}: quoted"}}
            for w, p in (("alice", 15), ("bob", 10), ("carol", 5))}}))
        record(propose(scene, path)[0] == 0 and load(scene, "proposal.json")["participants"]["alice"]["total"] is None,
               "a judgement covering an ungradable participant is accepted and not used")
        bad = json.loads(path.read_text())
        bad["participants"]["alice"]["design"]["points"] = 99
        path.write_text(json.dumps(bad))
        record(propose(scene, path)[0] == 1, "and is still checked")
        code, out, err = confirm(scene, "--exclude", "alice", "--exclude", "alice")
        record(code == 0 and load(scene, "final.json")["not_graded"].keys() == {"alice"},
               "a repeated --exclude is harmless", err)
    # A timeout is the participant's own result: gradable, with the reason shown.
    yaml = hang_yaml(
        '  quick: { kind: command, command: [sh, -c, "echo fine"] }\n'
        '  hang: { kind: command, command: [sh, -c, "echo started; sleep 60"] }\n'
        '  has-readme: { kind: file-exists, path: README.md }',
        "    quick: { points: 10 }\n    hang: { points: 10, gate: true }\n    has-readme: { points: 10 }")
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp, module_yaml=yaml)
        scene.cli("collect", COHORT_URL, "m1")
        scene.run_all(prelude=LIMIT_PRELUDE)
        path = scene.tmp / "judgement.json"
        path.write_text(json.dumps({"participants": {w: {} for w in ("alice", "bob", "carol")}}))
        code, out, err = propose(scene, path)
        alice = load(scene, "proposal.json")["participants"]["alice"]
        record(code == 0 and alice["ungradable"] is False and alice["timed_out"] is True
               and alice["total"] == 20 and alice["gate"] is False
               and "time limit" in alice["validators"]["hang"]["reason"],
               "a timeout stays gradable, keeps its reason and scores what finished", str(alice)[:300])
        record("timed out" in out and "time limit" in out and "NOT GRADABLE" not in out,
               "the summary shows the timeout", out)
        code, out, err = confirm(scene)
        record(code == 0 and load(scene, "final.json")["participants"]["alice"]["total"] == 20
               and load(scene, "final.json")["not_graded"] == {}, "confirm needs no --exclude for a timeout", err)


def test_proposed_points_and_validator_changes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        propose(scene, path)
        code, out, err = confirm(scene, "--change", "bob:lint=0:no")
        record(code == 1 and "validators are deterministic" in err and "cannot change them" in err
               and "design" in err, "a change on a validator says validators cannot be changed", err)
        code, out, err = confirm(scene, "--change", "bob:design=18:why")
        crit = load(scene, "final.json")["participants"]["bob"]["criteria"]["design"]
        record(code == 0 and crit["points"] == 18 and crit["proposed_points"] == 10,
               "a changed criterion keeps the AI's proposed points", str(crit))
        other = load(scene, "final.json")["participants"]["alice"]["criteria"]["design"]
        record(other["points"] == 15 and other["proposed_points"] == 15,
               "an unchanged criterion's proposed_points equals its points", str(other))
        # A re-proposal overwrites proposal.json; final.json keeps the audit.
        path.write_text(json.dumps(ratings(bob=2)))
        propose(scene, path)
        record(load(scene, "final.json")["participants"]["bob"]["criteria"]["design"]["proposed_points"] == 10,
               "final.json still holds the first proposed value after a re-proposal")


def test_damaged_proposal_and_recursion() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        propose(scene, path)
        good = (scene.store() / "proposal.json").read_text()
        damaged = {
            "a participant with no body": lambda d: d["participants"].__setitem__("alice", {}),
            "no participants key": lambda d: d.pop("participants"),
            "a criterion with no points": lambda d: d["participants"]["bob"]["criteria"]["design"].pop("points"),
            "a validator with no passed": lambda d: d["participants"]["bob"]["validators"]["lint"].pop("passed"),
            "a missing max_total": lambda d: d.pop("max_total"),
        }
        for name, damage in damaged.items():
            data = json.loads(good)
            damage(data)
            (scene.store() / "proposal.json").write_text(json.dumps(data))
            code, out, err = confirm(scene)
            record(code == 1 and "proposal.json is damaged" in err and "Traceback" not in err
                   and "propose` again" in err, f"confirm says a damaged proposal ({name}) is damaged", f"{code} {err}")
        (scene.store() / "proposal.json").write_text("[1, 2]")
        record("is damaged" in confirm(scene)[2], "a proposal that is a list is damaged")
        (scene.store() / "proposal.json").write_text(good)
        record(confirm(scene)[0] == 0, "control: the intact proposal confirms")
        deep = scene.tmp / "deep.json"
        deep.write_text("[" * 200000)
        code, out, err = propose(scene, deep)
        record(code == 2 and "not valid JSON" in err and "Traceback" not in err,
               "a deeply nested judgement is a message and not a traceback", f"{code} {err[:200]}")


def test_rubric_edit_needs_no_rerun() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        propose(scene, path)
        first = load(scene, "proposal.json")["grading_hash"]
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace(
            "standard: The choice is justified.", "standard: The choice is justified well."))
        code, out, err = confirm(scene)
        record(code == 1 and "`grading` block differs" in err,
               "a rubric edit makes the old proposal stale", err)
        code, out, err = propose(scene, path)
        record(code == 0 and load(scene, "proposal.json")["grading_hash"] != first,
               "a rubric-only edit needs no container re-run: propose works from run.json", err)
        record(confirm(scene)[0] == 0, "and the new proposal confirms")
        # Control: a validator edit does demand a re-run.
        (scene.bundle / "tutorial.yaml").write_text(MODULE_YAML.replace("lint.sh", "lint2.sh"))
        code, out, err = propose(scene, path)
        record(code == 1 and "changed since the last run" in err, "control: a validator edit still demands a run", err)


def test_archive_without_hard_links() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        propose(scene, path)
        prelude = "import os\ndef _no(*a, **k): raise OSError(1, 'hard links are not allowed')\ngrade.os.link = _no"
        scene.cli("confirm", "--bundle", str(scene.bundle), "--by", "one", COHORT_URL, "m1", prelude=prelude)
        first = (scene.store() / "final.json").read_text()
        code, out, err = scene.cli("confirm", "--bundle", str(scene.bundle), "--by", "two", COHORT_URL, "m1",
                                   prelude=prelude)
        kept = sorted(p.name for p in scene.store().glob("final.*.json"))
        record(code == 0 and len(kept) == 1 and (scene.store() / kept[0]).read_text() == first
               and load(scene, "final.json")["confirmed_by"] == "two",
               "without hard links the previous final.json is copied beside the new one", f"{kept} {err}")
        record([p.name for p in scene.store().iterdir() if p.name.startswith(".")] == [],
               "and no temp file is left")


def test_exclude_a_branch_the_proposal_does_not_cover() -> None:
    """The list `collect` shows can be narrowed through to `confirm`, and only on purpose."""
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        scene.cli("collect", COHORT_URL, "m1")
        code, out, err = scene.run_all("--only", "alice")
        record(code == 0, "a run of one participant succeeds", err)
        path = scene.tmp / "judgement.json"
        path.write_text(json.dumps({"participants": {
            "alice": {"design": {"points": 15, "evidence": "alice: quoted"}}}}))
        code, out, err = propose(scene, path)
        record(code == 0, "the proposal covers only alice", err)
        final = scene.store() / "final.json"

        code, out, err = confirm(scene)
        record(code == 1 and "bob has a branch" in err and "carol has a branch" in err
               and "--exclude" in err and not final.exists(),
               "with no --exclude confirm refuses, and says how to leave a branch out", f"{code} {err}")
        code, out, err = confirm(scene, "--exclude", "bob")
        record(code == 1 and "carol has a branch" in err and "bob has a branch" not in err
               and not final.exists(), "--exclude of one still refuses for the other", f"{code} {err}")
        code, out, err = confirm(scene, "--exclude", "bob", "--exclude", "carol", "--exclude", "dave")
        record(code == 1 and "dave" in err and "no branch" in err and not final.exists(),
               "--exclude of a name with no branch is refused", f"{code} {err}")
        code, out, err = confirm(scene, "--exclude", "bob", "--exclude", "carol", "--exclude", "alice")
        record(code == 1 and "who is gradable" in err and not final.exists(),
               "--exclude of a gradable participant the proposal covers stays refused", f"{code} {err}")
        code, out, err = confirm(scene, "--exclude", "bob", "--exclude", "carol", "--change", "bob:design=1:x")
        record(code == 1 and "not in the proposal" in err and not final.exists(),
               "an excluded participant takes no change", f"{code} {err}")

        code, out, err = confirm(scene, "--exclude", "bob", "--exclude", "carol")
        data = json.loads(final.read_text()) if final.exists() else {}
        record(code == 0 and sorted(data.get("participants", [])) == ["alice"]
               and sorted(data.get("not_graded", [])) == ["bob", "carol"],
               "excluded participants are in not_graded and not in participants", f"{code} {err}")
        record("excluded by the trainer" in data.get("not_graded", {}).get("bob", {}).get("reason", ""),
               "the reason says the trainer excluded them", str(data.get("not_graded")))
        record(data.get("not_graded", {}).get("bob", {}).get("commit") == scene.commits["bob/m1"],
               "not_graded records the commit of a branch the proposal does not cover",
               str(data.get("not_graded")))
        record("bob" in out and "excluded by the trainer" in out, "the summary says so too", out)

    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        path = graded(scene)
        propose(scene, path)
        code, out, err = confirm(scene, "--exclude", "bob")
        record(code == 1 and "who is gradable" in err, "after a full run bob stays in the proposal", err)
        (scene.store() / "run.json").unlink()
        code, out, err = scene.run_all("--only", "alice")
        path.write_text(json.dumps({"participants": {
            "alice": {"design": {"points": 15, "evidence": "alice: quoted"}}}}))
        propose(scene, path)
        code, out, err = confirm(scene, "--exclude", "bob", "--exclude", "carol")
        record(code == 0 and sorted(load(scene, "final.json")["not_graded"]) == ["bob", "carol"],
               "deleting run.json and running --only is the way out after a run", f"{code} {err}")


def test_by_takes_printable_unicode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = Scene(tmp)
        propose(scene, graded(scene))
        for bad, label in (("Ann\nBob", "a line break"), ("Ann\x1b[31m", "a control character"),
                           ("Ann\u2028Bob", "a Unicode line separator")):
            code, out, err = confirm(scene, by=bad)
            record(code == 1 and "--by" in err and not (scene.store() / "final.json").exists(),
                   f"--by refuses {label}", f"{code} {err}")
        code, out, err = confirm(scene, by="J\u00fcrgen M\u00fcller")
        record(code == 0 and load(scene, "final.json")["confirmed_by"] == "J\u00fcrgen M\u00fcller",
               "--by accepts printable Unicode, and stores it as given", f"{code} {err}")


def main() -> int:
    for test in (test_cohort_from_url_forms, test_store_dir_follows_xdg, test_work_tree_refusal,
                 test_forget, test_scheme, test_cli, test_classify_branch, test_collect,
                 test_collect_keeps_credentials_out, test_collect_url_rules, test_run_results,
                 test_container_command, test_env_warning_and_masking, test_clean_output,
                 test_huge_output_end_to_end, test_time_limit, test_interrupted_run_kills_the_container,
                 test_hanging_regex, test_file_checks, test_no_runtime, test_run_refusals,
                 test_run_again_and_only, test_exit_125_is_not_a_silent_fail, test_checkout_removal,
                 test_trainer_git_config_does_not_reach_the_checkout,
                 test_cache_is_not_reused_for_another_url, test_run_with_a_token_url,
                 test_mounted_git_discloses_nothing, test_docker_proxies_warning, test_run_json_records,
                 test_real_checkout_failure, test_gitmodules_are_not_followed, test_local_git_timeout,
                 test_only_takes_positionals_after_it, test_password_holding_a_slash, test_port_rule,
                 test_ascii_stdout, test_only_keeps_other_branches_provenance,
                 test_propose_values, test_propose_refusals, test_confirm_values,
                 test_confirm_top_tie, test_confirm_refusals, test_gate_criterion,
                 test_reconfirm_names_the_changes_it_does_not_repeat,
                 test_change_addresses_what_check_49_allows,
                 test_output_arrives_while_the_run_goes_on,
                 test_no_gate_is_null, test_writes_refuse_a_work_tree,
                 test_runtime_faults_are_not_scores, test_proposed_points_and_validator_changes,
                 test_damaged_proposal_and_recursion, test_rubric_edit_needs_no_rerun,
                 test_archive_without_hard_links,
                 test_exclude_a_branch_the_proposal_does_not_cover, test_by_takes_printable_unicode):
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
