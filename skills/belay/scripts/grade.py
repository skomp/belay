#!/usr/bin/env python3
"""Cohort grading: the scheme reader, the local grade store, collect and run.

Usage:
    grade.py collect <repo> <module-id>
        fetch the cohort repository into the local cache and list the branches
    grade.py run --bundle <dir> <repo> <module-id> [--only <participant>]...
        run the bundle's validators on each collected branch, in a container
    grade.py forget <cohort>     delete one cohort's stored grades and cache
    grade.py --help

Later subcommands (propose, confirm) are added to SUBCOMMANDS below; each is a
function taking the parsed arguments and returning an exit code. The design is
docs/superpowers/specs/2026-11-03-cohort-grading-design.md; section 2.1 is the
`grading` key this reads, sections 3 and 4 are collect and run, section 5 is
the store.

`run` executes code nobody has reviewed. Its isolation is what the code cannot
reach, and the rules that keep it so are stated where they are enforced:
RUNTIME_ENV_KEYS (the runtime's environment), container_argv (the one command
that starts participant code), clean_git_env (the checkout's git), and
clean_output (what is stored of the output). There is no path that runs
participant code outside a container: no runtime stops the run.

The store is  <data home>/belay/grading/<cohort>/<module-id>/  where the data
home is $XDG_DATA_HOME, else ~/.local/share. The cohort name is DERIVED from
the repository URL (cohort_name) and is always one safe path component. The
store refuses to exist inside a Git work tree (refuse_work_tree), so grades
cannot be committed by accident, and `forget` accepts only a bare cohort name
so it cannot delete anything outside the store.

The store also holds, under <cohort>/, the cache of the repository (.repo.git)
and, under <module-id>/, the working file of step 2 (run.json), so `forget`
leaves no participant's work behind.

Exit codes:
    0  done
    1  refused: the bundle has no `grading` or cannot be graded, the store is in
       a work tree, the cohort name is not a bare name, the repository is not a
       Git URL, or there is no working container runtime. Also a finished run
       with a result that may not be a judgement of the code: a failed checkout,
       or a container that exited 125, 126 or 127.
    2  usage or I/O error, or a fetch that failed

Stdlib only, Python 3.11, and the shared restricted reader yamlite.py.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from catalogs import is_git_url, run_git
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from catalogs import is_git_url, run_git
    from yamlite import YamlError, load_yaml

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

MANIFEST = "tutorial.yaml"
STORE_SUBDIR = ("belay", "grading")
CACHE_NAME = ".repo.git"
RUN_FILE = "run.json"

# The one path the checkout is mounted at, and the container's working directory.
MOUNT = "/workspace"
# Stored output per validator, in characters.
OUTPUT_LIMIT = 16384
TRUNCATED_MARK = "\n[output truncated]"
# `grading.timeout_minutes` is optional in the format, but a branch always has a limit.
DEFAULT_TIMEOUT_MINUTES = 15
SECONDS_PER_MINUTE = 60
FETCH_TIMEOUT = 600
PROBE_TIMEOUT = 60
PULL_TIMEOUT = 1800
KILL_TIMEOUT = 30
CLEANUP_TIMEOUT = 120
# A file bigger than this is not read for `file-contains`.
FILE_CHECK_MAX_BYTES = 16 * 1024 * 1024
# The conventions docker and podman share: 125, the runtime itself failed; 126 and
# 127, the command could not be run. A command inside can exit with these as well.
RUNTIME_REFUSED_STATUS = 125
COMMAND_NOT_RUN_STATUSES = (126, 127)

# Limits on every container, so that one branch's code cannot take the trainer's
# machine down with a fork bomb or by eating its memory, or gain privileges through
# a setuid program. Rootless podman can refuse the first two without cgroup
# delegation; that shows as RUNTIME_REFUSED_STATUS.
PIDS_LIMIT = "512"
MEMORY_LIMIT = "4g"
SECURITY_OPT = "no-new-privileges"
CONTAINER_LIMITS = ("--pids-limit", PIDS_LIMIT, "--memory", MEMORY_LIMIT, "--security-opt", SECURITY_OPT)

GRADABLE_KINDS = ("command", "file-exists", "file-contains")

# What the runtime CLI needs of the trainer's environment, and nothing else:
# finding its helpers (PATH), its configuration and rootless storage (HOME and
# the XDG directories), the rootless socket (XDG_RUNTIME_DIR, DBUS session), and
# which daemon to talk to (the DOCKER_* and CONTAINER_* selectors). Git access
# (SSH_AUTH_SOCK, GIT_*, GH_TOKEN), proxies and everything personal stay out,
# which also stops podman copying proxy variables into the container.
RUNTIME_ENV_KEYS = (
    "PATH",
    "HOME",
    "XDG_RUNTIME_DIR",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "DBUS_SESSION_BUS_ADDRESS",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "CONTAINER_HOST",
    "CONTAINER_CONNECTION",
    "CONTAINERS_CONF",
)


class GradeError(Exception):
    """A refusal the caller prints; `code` is the exit status."""

    def __init__(self, message: str, code: int = EXIT_REFUSED) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------
# The scheme (spec section 2.1)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidatorShare:
    name: str
    points: int
    gate: bool
    declared: dict  # the bundle's own validator declaration (kind, command, ...)


@dataclass(frozen=True)
class Criterion:
    id: str
    points: int
    standard: str
    paths: tuple[str, ...] | None  # None: the whole branch


@dataclass(frozen=True)
class Scheme:
    module: str
    bundle_version: Any
    image: str | None
    network: bool
    env: tuple[str, ...]
    timeout_minutes: int | None
    validators: tuple[ValidatorShare, ...]
    rubric: tuple[Criterion, ...]

    @property
    def max_total(self) -> int:
        return sum(v.points for v in self.validators) + sum(c.points for c in self.rubric)


def load_scheme(bundle: Path) -> Scheme:
    """Read `grading` from a module bundle's tutorial.yaml.

    Shape errors are the validator's business (checks 47-50); this reads what
    is there and refuses with a message only when it cannot continue.
    """
    manifest_path = Path(bundle) / MANIFEST
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GradeError(f"cannot read {manifest_path}: {exc}", EXIT_USAGE) from exc
    try:
        manifest = load_yaml(text, str(manifest_path))
    except YamlError as exc:
        raise GradeError(f"{manifest_path} does not parse: {exc}", EXIT_USAGE) from exc
    if not isinstance(manifest, dict):
        raise GradeError(f"{manifest_path} is not a mapping", EXIT_USAGE)
    if "grading" not in manifest:
        raise GradeError(
            f"{manifest_path} has no `grading` key: this module is not set up for "
            "cohort grading (spec section 2.1)."
        )
    grading = manifest["grading"]
    if not isinstance(grading, dict):
        raise GradeError(f"`grading` in {manifest_path} is not a mapping")
    module = manifest.get("id")
    if not isinstance(module, str) or not module:
        raise GradeError(f"{manifest_path} has no `id`")
    declared = manifest.get("validators")
    declared = declared if isinstance(declared, dict) else {}

    shares = []
    gv = grading.get("validators")
    for name, spec in (gv.items() if isinstance(gv, dict) else ()):
        spec = spec if isinstance(spec, dict) else {}
        decl = declared.get(name)
        shares.append(
            ValidatorShare(
                name=str(name),
                points=spec.get("points") if isinstance(spec.get("points"), int) else 0,
                gate=spec.get("gate") is True,
                declared=decl if isinstance(decl, dict) else {},
            )
        )
    criteria = []
    rub = grading.get("rubric")
    for item in (rub if isinstance(rub, list) else ()):
        if not isinstance(item, dict):
            continue
        paths = item.get("paths")
        criteria.append(
            Criterion(
                id=str(item.get("id", "")),
                points=item.get("points") if isinstance(item.get("points"), int) else 0,
                standard=str(item.get("standard", "")),
                paths=tuple(str(p) for p in paths) if isinstance(paths, list) else None,
            )
        )
    env = grading.get("env")
    timeout = grading.get("timeout_minutes")
    image = grading.get("image")
    return Scheme(
        module=module,
        bundle_version=manifest.get("version"),
        image=image if isinstance(image, str) else None,
        network=grading.get("network") is True,
        env=tuple(str(e) for e in env) if isinstance(env, list) else (),
        timeout_minutes=timeout if isinstance(timeout, int) else None,
        validators=tuple(shares),
        rubric=tuple(criteria),
    )


# --------------------------------------------------------------------------
# The store (spec section 5)
# --------------------------------------------------------------------------

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


_DEFAULT_PORTS = {"https": "443", "ssh": "22"}


def normalise_url(repo_url: str) -> str:
    """[user@]host[:port]/path: one string per repository, however it was typed.

    https://Host/o/r.git, ssh://git@host/o/r and git@host:o/r all give host/o/r.
    Two forms that can reach different repositories stay different, because the
    cache and the grades are keyed on this: a port other than the scheme's default
    can be another server, and an scp path is relative to the ssh user's home.
    `git` is the shared ssh user of a forge, and equals none.

    A credential never reaches it. All of an https userinfo is one (the part up to
    the last '@' of the authority), and so is an ssh password. So one repository
    with or without a credential is one cohort.
    """
    url = repo_url.strip()
    scheme, has_scheme, rest = url.partition("://")
    scheme = scheme.lower() if has_scheme else ""
    if not has_scheme:
        rest = url
    # The authority ends at the first '/'; in scp form that is after host:dir,
    # which holds no '@' of its own, so the last '@' before it is the userinfo's.
    head, slash, tail = rest.partition("/")
    userinfo, _, address = head.rpartition("@")
    user = "" if scheme in ("https", "http") else userinfo.partition(":")[0]
    if user == "git":
        user = ""
    port = ""
    if not has_scheme and ":" in address and not address.startswith((".", "/")):
        # scp form host:path. A leading numeric part is a directory, not a port.
        host, _, first = address.partition(":")
        path = f"{first}{slash}{tail}"
    else:
        host, _, port = address.partition(":") if has_scheme else (address, "", "")
        path = tail
        port = str(int(port)) if port.isdigit() else port
        if port == _DEFAULT_PORTS.get(scheme):
            port = ""
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    who = f"{user}@" if user else ""
    where = f":{port}" if port else ""
    return f"{who}{host.lower()}{where}/{path}".strip("/")


def cohort_name(repo_url: str) -> str:
    """A single safe path component derived from the URL.

    A readable slug of the last two path parts, then a short hash of the whole
    normalised URL, so two URLs that slug alike ("a/b-c" and "a-b/c") differ.
    """
    norm = normalise_url(repo_url)
    if not norm:
        raise GradeError("the repository URL is empty", EXIT_USAGE)
    tail = "-".join(norm.split("/")[-2:])
    # No "..": `forget` refuses a name holding one, and it must accept every name collect prints.
    slug = re.sub(r"\.{2,}", ".", _SAFE.sub("-", tail)).strip("-.") or "cohort"
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:60]}-{digest}"


def data_home() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg and os.path.isabs(xdg):
        return Path(xdg)
    return Path.home() / ".local" / "share"


def grading_root() -> Path:
    return data_home().joinpath(*STORE_SUBDIR)


def refuse_work_tree(path: Path) -> None:
    """Raise GradeError when `path`, or where it would be, is in a Git work tree.

    Walks up from the nearest existing ancestor (symlinks resolved) looking
    for a `.git` entry, which is a directory in a clone and a file in a
    worktree or submodule.
    """
    probe = Path(os.path.abspath(path))
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    probe = probe.resolve()
    for candidate in (probe, *probe.parents):
        if (candidate / ".git").exists():
            raise GradeError(
                f"refusing to use {path}: it is inside the Git work tree {candidate}. "
                "Grades must never be committable; point XDG_DATA_HOME elsewhere."
            )


def store_dir(repo_url: str, module: str) -> Path:
    """<data home>/belay/grading/<cohort>/<module>/ ; refuses a work tree.

    The directory is not created here; writers create it on first write.
    """
    if not module or module in (".", "..", CACHE_NAME) or re.search(r"[/\\\0]", module):
        raise GradeError(f"{module!r} is not a usable module id", EXIT_USAGE)
    path = grading_root() / cohort_name(repo_url) / module
    refuse_work_tree(path)
    return path


def valid_cohort_arg(name: str) -> bool:
    return bool(name) and name not in (".", "..") and ".." not in name \
        and not re.search(r"[/\\\0]", name) and not name.startswith("-")


def forget(cohort: str) -> str:
    """Delete one cohort's grades; return what was done, in words."""
    if not valid_cohort_arg(cohort):
        raise GradeError(
            f"{cohort!r} is not a cohort name: it must be a bare name with no path "
            "separator and no '..'. Cohort names come from the store listing."
        )
    root = grading_root()
    refuse_work_tree(root)
    target = root / cohort
    if target.is_symlink():
        return f"{target} is a symlink, not a cohort directory; left alone, nothing deleted"
    if not target.is_dir():
        return f"no grades stored for cohort {cohort}; nothing deleted"
    if target.resolve().parent != root.resolve():  # belt and braces
        raise GradeError(f"{target} is not directly inside the store; not deleting")
    shutil.rmtree(target)
    return f"deleted the grades and the repository cache of cohort {cohort}"


# --------------------------------------------------------------------------
# Collect (spec section 3, step 1)
# --------------------------------------------------------------------------

# Review Focus 1. A participant name becomes a path component and a ref, so it
# is one component of a narrow alphabet: not an option, not `.` or `..`.
_PARTICIPANT = re.compile(r"(?!-)(?!\.+\Z)[A-Za-z0-9._-]+")


@dataclass(frozen=True)
class BranchRef:
    participant: str
    branch: str
    commit: str
    committed_at: str


@dataclass
class Listing:
    participants: list[BranchRef] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)


def classify_branch(branch: str, module: str) -> tuple[str, str | None]:
    """("participant", name), ("refused", None) or ("other", None).

    Refused is a branch that is for this module and whose participant part is
    unusable; other is a branch that is not for this module at all.
    """
    suffix = f"/{module}"
    if not branch.endswith(suffix):
        return "other", None
    who = branch[: -len(suffix)]
    return ("participant", who) if _PARTICIPANT.fullmatch(who) else ("refused", None)


def checked_url(repo: str) -> str:
    """The URL rule of `catalogs.start_from_problems`, which is `is_git_url`."""
    # `?` and `#` are refused on top of that rule: a token in a query or fragment
    # is not in the authority, so it would reach a directory name and the output.
    if not is_git_url(repo) or "?" in repo or "#" in repo:
        raise GradeError(
            "the repository is not a Git URL; use https://..., ssh://... or "
            "user@host:path, whose host (and any user) begins with a letter or digit, "
            "and which holds no whitespace and none of ` $ ; | & < > ( ) ' \" \\ ? #"
        )
    return repo


def cache_dir(repo: str) -> Path:
    path = grading_root() / cohort_name(repo) / CACHE_NAME
    refuse_work_tree(path)
    return path


def make_private(path: Path) -> None:
    """Create a store directory, and its cohort directory, for the trainer only."""
    path.mkdir(parents=True, exist_ok=True)
    root = grading_root()
    for directory in (path, *path.parents):
        if directory == root or root not in directory.parents:
            break
        directory.chmod(0o700)


def clean_git_env() -> dict[str, str]:
    """Git with none of the trainer's: no config, no hooks, no credentials.

    `collect` alone borrows the trainer's access (catalogs.git_env), to fetch.
    Everything after it reads the local cache, and participant content meets
    git only here. With no global or system config, a trainer's hooksPath,
    templateDir, credential helper or LFS smudge filter cannot act on it.
    """
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": "/nonexistent",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "LC_ALL": "C",
    }


def clean_git(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    """Bytes in and out: a ref name is whatever bytes a participant pushed."""
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=clean_git_env(),
        timeout=timeout,
        check=False,
    )


def scrub_credentials(text: str, repo: str) -> str:
    return re.sub(r"://[^/@\s]+@", "://", text.replace(repo, normalise_url(repo)))


def fetch_cache(repo: str, cache: Path) -> None:
    """Mirror the repository's branches into the bare cache.

    The URL goes on the command line and in no file: the cache has no remote
    and no FETCH_HEAD, so a credential in the URL is not stored anywhere.
    """
    make_private(cache)
    if not (cache / "HEAD").exists():
        local_git(["init", "--quiet", "--bare", "--template=", str(cache)], "create the cache")
    run = run_git(
        ["-c", "core.hooksPath=/dev/null", "--git-dir", str(cache), "fetch", "--quiet", "--prune",
         "--no-tags", "--no-write-fetch-head", "--", repo, "+refs/heads/*:refs/heads/*"],
        FETCH_TIMEOUT,
    )
    if not run.ok:
        raise GradeError(
            f"cannot fetch {normalise_url(repo)}: {scrub_credentials(run.stderr, repo).strip()}",
            EXIT_USAGE,
        )


def escape_name(name: str) -> str:
    """A branch name a participant chose, with anything unprintable made visible.

    It is shown to the trainer's terminal and stored, so it can carry no control
    sequence and no line end. Backslash cannot be in a ref name, so this is unambiguous.
    """
    return "".join(c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in name)


def local_git(args: list[str], what: str) -> subprocess.CompletedProcess:
    """clean_git on the local cache, where a failure is a message and not a traceback."""
    try:
        done = clean_git(args, PROBE_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise GradeError(f"cannot {what}: git did not finish within {PROBE_TIMEOUT} seconds", EXIT_USAGE) from exc
    if done.returncode != 0:
        raise GradeError(f"cannot {what}: {done.stderr.decode('utf-8', 'replace').strip()}", EXIT_USAGE)
    return done


def list_branches(cache: Path, module: str) -> Listing:
    done = local_git(
        ["--git-dir", str(cache), "for-each-ref",
         "--format=%(refname:lstrip=2)%09%(objectname)%09%(committerdate:iso-strict)", "refs/heads"],
        "read the cache",
    )
    listing = Listing()
    # Lines end at "\n" alone: str.splitlines also splits on U+0085, U+2028 and
    # U+2029, which git allows in a ref name, and neither "\n" nor a tab can be in
    # one. Bytes that are not UTF-8 become \xNN, whose backslash fails the
    # participant pattern, so such a name is listed and not used.
    for line in done.stdout.decode("utf-8", "backslashreplace").split("\n"):
        if not line:
            continue
        branch, commit, date = line.split("\t")
        kind, who = classify_branch(branch, module)
        if kind == "participant":
            listing.participants.append(BranchRef(who, branch, commit, date))
        elif kind == "refused":
            listing.refused.append(escape_name(branch))
        else:
            listing.other.append(escape_name(branch))
    return listing


def render_not_graded(listing: Listing) -> None:
    print(f"refused, a participant name that cannot be used; never graded ({len(listing.refused)}):")
    for branch in listing.refused:
        print(f"  {branch}")
    print(f"no convention, not <participant>/<module>; never graded ({len(listing.other)}):")
    for branch in listing.other:
        print(f"  {branch}")


def cmd_collect(args: argparse.Namespace) -> int:
    repo = checked_url(args.repo)
    store_dir(repo, args.module)  # refuses a bad module id and a store in a work tree
    cache = cache_dir(repo)
    fetch_cache(repo, cache)
    listing = list_branches(cache, args.module)
    print(f"cohort: {cohort_name(repo)}")
    print(f"repository: {normalise_url(repo)}")
    print(f"module: {args.module}")
    print(f"participants ({len(listing.participants)}):")
    for ref in listing.participants:
        print(f"  {ref.participant}  {ref.branch}  {ref.commit[:12]}  {ref.committed_at}")
    render_not_graded(listing)
    return EXIT_OK


# --------------------------------------------------------------------------
# Run: the runtime and the container (spec section 4)
# --------------------------------------------------------------------------


def find_runtime() -> str:
    """BELAY_CONTAINER_RUNTIME if set, else docker, else podman, else a refusal.

    A runtime named by the variable and missing is a refusal too. It does not
    fall through to docker: the trainer asked for that one.
    """
    named = os.environ.get("BELAY_CONTAINER_RUNTIME")
    if named:
        found = shutil.which(named)
        if not found:
            raise GradeError(
                f"BELAY_CONTAINER_RUNTIME is {named}, and that cannot be run. Nothing ran: "
                "participant code runs only in a container."
            )
        return found
    for candidate in ("docker", "podman"):
        found = shutil.which(candidate)
        if found:
            return found
    raise GradeError(
        "no container runtime found: neither docker nor podman is installed, and "
        "BELAY_CONTAINER_RUNTIME is not set. Nothing ran: participant code runs only in a container."
    )


@dataclass(frozen=True)
class RunPlan:
    runtime: str
    scheme: Scheme
    cache: Path
    limit_seconds: float
    runtime_env: dict[str, str]  # for info, pull, kill and cleanup
    run_env: dict[str, str]  # runtime_env plus the declared variables
    declared: tuple[str, ...]  # the declared variables that are set
    masks: dict[str, str]  # name -> value, of the declared variables that are set


def container_argv(
    runtime: str, name: str, image: str, checkout: Path, command: list[str],
    env_names: tuple[str, ...], network: bool,
) -> list[str]:
    """The one command that starts participant code. An argument list, no shell.

    One mount, the checkout. CONTAINER_LIMITS. Variables by name only: `-e NAME` takes the value
    from the runtime's own environment, so no value is on a command line. --rm
    and a generated --name make the container killable and leave nothing behind.
    """
    argv = [runtime, "run", "--rm", "--name", name, *CONTAINER_LIMITS]
    if not network:
        argv += ["--network", "none"]
    argv += ["-v", f"{checkout}:{MOUNT}", "-w", MOUNT]
    for variable in env_names:
        argv += ["-e", variable]
    return [*argv, image, *command]


class _Capture(threading.Thread):
    """Drains the output, keeping only the first `cap` bytes.

    It reads to the end, so a flood cannot block the validator into a false
    timeout, and it keeps a bounded amount, so a flood cannot fill the trainer's
    memory or disk.
    """

    def __init__(self, stream, cap: int) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.cap = cap
        self.kept = bytearray()
        self.cut = False

    def run(self) -> None:
        while True:
            try:
                chunk = self.stream.read(65536)
            except (OSError, ValueError):
                return
            if not chunk:
                return
            room = self.cap - len(self.kept)
            self.kept += chunk[:room]
            if len(chunk) > room:
                self.cut = True


@dataclass
class Outcome:
    status: int | None = None
    raw: bytes = b""
    cut: bool = False
    timed_out: bool = False
    kill_ok: bool = True
    name: str = ""
    error: str | None = None


def stop_container(plan: RunPlan, proc: subprocess.Popen, name: str) -> bool:
    """Kill the container by name, then its client. True when the kill was accepted.

    Killing `docker run` alone can leave the container running under the daemon,
    with the participant's code and any declared key, so the name comes first.
    """
    try:
        ok = subprocess.run(
            [plan.runtime, "kill", name], env=plan.runtime_env, stdin=subprocess.DEVNULL,
            capture_output=True, timeout=KILL_TIMEOUT, check=False,
        ).returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        ok = False
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    proc.wait()
    return ok


def run_container(
    plan: RunPlan, checkout: Path, command: list[str], limit: float,
    env: dict[str, str], env_names: tuple[str, ...], network: bool,
) -> Outcome:
    name = f"belay-grade-{secrets.token_hex(8)}"
    argv = container_argv(plan.runtime, name, plan.scheme.image or "", checkout, command, env_names, network)
    try:
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, start_new_session=True,
        )
    except OSError as exc:
        return Outcome(error=f"the container runtime could not be started: {exc}")
    longest = max((len(v.encode("utf-8", "surrogateescape")) for v in plan.masks.values()), default=0)
    capture = _Capture(proc.stdout, OUTPUT_LIMIT * 4 + longest + 1)
    capture.start()
    outcome = Outcome(name=name)
    try:
        outcome.status = proc.wait(timeout=limit)
    except subprocess.TimeoutExpired:
        outcome.timed_out = True
        outcome.kill_ok = stop_container(plan, proc, name)
    except BaseException:  # an interrupt or SIGTERM must not leave the container running
        stop_container(plan, proc, name)
        raise
    capture.join(timeout=5)
    outcome.raw = bytes(capture.kept)
    outcome.cut = capture.cut
    return outcome


def mask(text: str, masks: dict[str, str]) -> str:
    # Longest first: a value that holds another value is masked whole.
    for variable, value in sorted(masks.items(), key=lambda kv: -len(kv[1])):
        if value:
            text = text.replace(value, f"[masked:{variable}]")
    return text


def clean_output(raw: bytes, cut: bool, masks: dict[str, str]) -> str:
    """What is stored of a validator's output: masked, THEN truncated (Review Focus 2).

    Masking first means the limit cannot cut a value in half and leave the first
    half unmasked. `cut` says the capture itself stopped partway, which can have
    happened inside a value, so whatever follows the last whole value is dropped.
    Masks can shrink the text, so that tail could otherwise land inside the limit.
    The text is matched with surrogateescape, the way os.environ holds a value that
    is not UTF-8, and only then made valid for storing.
    """
    text = mask(raw.decode("utf-8", "surrogateescape"), masks)
    text = text.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    longest = max((len(v.encode("utf-8", "surrogateescape")) for v in masks.values()), default=0)
    if cut and longest:
        text = text[:-longest]
    truncated = cut or len(text) > OUTPUT_LIMIT
    return text[:OUTPUT_LIMIT] + TRUNCATED_MARK if truncated else text


# --------------------------------------------------------------------------
# Run: the checkout and the file checks
# --------------------------------------------------------------------------


class CheckoutFailed(Exception):
    pass


def make_checkout(cache: Path, ref: BranchRef, target: Path, deadline: float) -> None:
    """A fresh repository holding this branch alone, from the local cache.

    This `.git` is mounted, so it holds nothing of the trainer's. Not a clone: it
    has no remote, so no URL or credential is in its config. No FETCH_HEAD and no
    reflog: those would hold the cache's path, and the trainer's login and hostname.
    No template, so no hooks directory. It fetches one ref, so another participant's
    work is not in what is mounted. The branch reaches git only as an argument, and
    only after it passed the participant pattern.
    """
    quiet_logs = ["-C", str(target), "-c", "core.logAllRefUpdates=false"]
    steps = (
        ["init", "--quiet", "--template=", str(target)],
        [*quiet_logs, "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--", str(cache),
         f"+refs/heads/{ref.branch}:refs/heads/{ref.branch}"],
        [*quiet_logs, "checkout", "--quiet", "--force", "--detach", ref.commit],
    )
    for step in steps:
        done = clean_git(step, max(deadline - time.monotonic(), 0.001))
        if done.returncode != 0:
            raise CheckoutFailed(done.stderr.decode("utf-8", "replace").strip() or "git said nothing")


def safe_path(root: Path, relative: str) -> str | None:
    """The real path of `relative`, or None when it leaves `root`.

    Resolving every symlink is the containment: a link out of the checkout, a
    link to a directory outside, `..` and an absolute path all end up outside.
    """
    real_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(real_root, relative))
    return target if os.path.commonpath([real_root, target]) == real_root else None


# Python's `re` cannot be interrupted from a thread, so the match is a process
# of its own that the time limit can kill. `-I` keeps the checkout off its path.
_MATCH_SCRIPT = (
    "import re, sys\n"
    "text = open(sys.argv[1], 'rb').read().decode('utf-8', 'replace')\n"
    "sys.exit(0 if re.search(sys.argv[2], text, re.MULTILINE) else 1)\n"
)


def check_file(share: ValidatorShare, checkout: Path, limit: float) -> tuple[bool, str | None]:
    """A `file-exists` or `file-contains` check; raises TimeoutExpired past the limit.

    The format's `pattern` is what the runner-protocol hands to the Grep tool: a
    regular expression searched for line by line. The nearest stdlib reading is
    `re.search` with MULTILINE, where ^ and $ are line ends and . stops at one.
    """
    relative = share.declared["path"]
    target = safe_path(checkout, relative)
    if target is None:
        return False, f"{relative} is outside the checkout"
    if not os.path.exists(target):
        return False, f"{relative} does not exist"
    if share.declared.get("kind") == "file-exists":
        return True, None
    if not os.path.isfile(target):
        return False, f"{relative} is not a file"
    if os.path.getsize(target) > FILE_CHECK_MAX_BYTES:
        return False, f"{relative} is larger than {FILE_CHECK_MAX_BYTES} bytes and was not read"
    done = subprocess.run(
        [sys.executable, "-I", "-c", _MATCH_SCRIPT, target, share.declared["pattern"]],
        stdin=subprocess.DEVNULL, capture_output=True, env={}, timeout=limit, check=False,
    )
    if done.returncode == 0:
        return True, None
    if done.returncode == 1 and not done.stderr:
        return False, f"{relative} does not match the pattern"
    return False, f"{relative} could not be checked"


def force_remove(path: Path) -> bool:
    """Remove a tree, also where the code took its own permissions away.

    rmtree and the walk do not follow symlinks, so a link the code planted
    cannot lead this outside the tree.
    """
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    for root, dirs, _files in os.walk(path):
        for name in dirs:
            child = os.path.join(root, name)
            if not os.path.islink(child):
                try:
                    os.chmod(child, 0o700)
                except OSError:
                    pass
    shutil.rmtree(path, ignore_errors=True)
    return not os.path.lexists(path)


def remove_checkout(plan: RunPlan, parent: Path, checkout: Path, warnings: list[str]) -> None:
    """A rootful container leaves files the trainer cannot delete, so on failure
    the same image empties the mount, with no network and no declared variable."""
    if force_remove(parent):
        return
    if plan.scheme.image and checkout.is_dir():
        run_container(plan, checkout, ["find", MOUNT, "-mindepth", "1", "-delete"], CLEANUP_TIMEOUT,
                      plan.runtime_env, (), False)
    if not force_remove(parent):
        warnings.append(f"could not remove the checkout {parent}; it holds participant code, remove it by hand")


# --------------------------------------------------------------------------
# Run: one branch, then the command
# --------------------------------------------------------------------------


def verdict(share: ValidatorShare, passed: bool, output: str = "", reason: str | None = None) -> dict:
    return {
        "kind": share.declared.get("kind"),
        "passed": passed,
        "gate": share.gate,
        "output": output,
        "reason": reason,
    }


def not_a_judgement(status: int) -> str:
    if status == RUNTIME_REFUSED_STATUS:
        return (f"exit status {status}: the container runtime refused the command. This may be a limit "
                f"on rootless podman (--pids-limit, --memory need cgroup delegation) or an image it "
                "could not start, so this may not be a judgement of the code. The command itself can "
                "also exit with this status.")
    return (f"exit status {status}: the command could not be run in the image, or it exited with this "
            "status itself, so this may not be a judgement of the code.")


def run_branch(plan: RunPlan, ref: BranchRef, warnings: list[str]) -> tuple[dict, bool]:
    """Every validator's result for one branch, and whether a result is suspect.

    One clock for the branch. The file checks run first, on what the participant
    committed, before their code can change it; results keep the declared order.
    """
    started = now_iso()
    deadline = time.monotonic() + plan.limit_seconds
    minutes = plan.limit_seconds / SECONDS_PER_MINUTE
    ran_out = f"the branch's time limit of {minutes:g} minutes ran out"
    found: dict[str, dict] = {}
    timed_out = False
    suspect = False
    stop_reason: str | None = None
    parent = Path(tempfile.mkdtemp(prefix="belay-grade-"))
    checkout = parent / "checkout"
    try:
        try:
            make_checkout(plan.cache, ref, checkout, deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_reason = f"not run: {ran_out} during the checkout"
        except CheckoutFailed as exc:
            suspect = True
            stop_reason = f"checkout failed: {exc}"
            warnings.append(f"{ref.participant}: {stop_reason}")
        ordered = sorted(plan.scheme.validators, key=lambda v: v.declared.get("kind") == "command")
        for share in ordered:
            left = deadline - time.monotonic()
            if stop_reason is None and left <= 0:
                timed_out = True
                stop_reason = f"not run: {ran_out}"
            if stop_reason is not None:
                found[share.name] = verdict(share, False, reason=stop_reason)
                continue
            if share.declared.get("kind") != "command":
                try:
                    passed, reason = check_file(share, checkout, left)
                    found[share.name] = verdict(share, passed, reason=reason)
                except subprocess.TimeoutExpired:
                    timed_out = True
                    found[share.name] = verdict(share, False, reason=f"stopped: {ran_out}")
                    stop_reason = f"not run: {ran_out}"
                continue
            outcome = run_container(plan, checkout, share.declared["command"], left, plan.run_env,
                                    plan.declared, plan.scheme.network)
            output = clean_output(outcome.raw, outcome.cut, plan.masks)
            if outcome.timed_out:
                timed_out = True
                found[share.name] = verdict(share, False, output, f"stopped: {ran_out}")
                stop_reason = f"not run: {ran_out}"
                if not outcome.kill_ok:
                    warnings.append(
                        f"{ref.participant}: the kill of container {outcome.name} was not accepted; "
                        "check that it is not still running"
                    )
            elif outcome.status is None:
                suspect = True
                found[share.name] = verdict(share, False, output, outcome.error)
            elif outcome.status == 0:
                found[share.name] = verdict(share, True, output)
            elif outcome.status == RUNTIME_REFUSED_STATUS or outcome.status in COMMAND_NOT_RUN_STATUSES:
                suspect = True
                reason = not_a_judgement(outcome.status)
                found[share.name] = verdict(share, False, output, reason)
                warnings.append(f"{ref.participant}: {share.name}: {reason}")
            else:
                found[share.name] = verdict(share, False, output, f"exit status {outcome.status}")
    finally:
        remove_checkout(plan, parent, checkout, warnings)
    record = {
        "branch": ref.branch,
        "commit": ref.commit,
        "committed_at": ref.committed_at,
        "started_at": started,
        "finished_at": now_iso(),
        "timed_out": timed_out,
        "validators": {v.name: found[v.name] for v in plan.scheme.validators},
    }
    return record, suspect


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def scheme_problems(scheme: Scheme) -> list[str]:
    """What stops a run before anything runs. A defect here is the bundle's, and
    every participant would lose the points for it, so it is not recorded as a fail."""
    problems = []
    if not scheme.validators:
        problems.append("grading.validators names no validator")
    for share in scheme.validators:
        kind = share.declared.get("kind")
        if not share.declared:
            problems.append(f"{share.name} is in grading.validators and is not a declared validator")
        elif kind not in GRADABLE_KINDS:
            problems.append(f"{share.name} is of kind {kind}, which cannot earn points")
        elif kind == "command":
            command = share.declared.get("command")
            if not (isinstance(command, list) and command
                    and all(isinstance(a, str) and a for a in command)):
                problems.append(f"{share.name}: `command` is not a list of arguments")
        else:
            if not (isinstance(share.declared.get("path"), str) and share.declared["path"]):
                problems.append(f"{share.name}: `path` is not a non-empty string")
            if kind == "file-contains":
                pattern = share.declared.get("pattern")
                try:
                    re.compile(pattern)
                except (re.error, TypeError) as exc:
                    problems.append(f"{share.name}: `pattern` is not a regular expression: {exc}")
    if any(v.declared.get("kind") == "command" for v in scheme.validators) and (
        not scheme.image or scheme.image.startswith("-")
    ):
        problems.append("grading.image is not a usable image name")
    for variable in scheme.env:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", variable):
            problems.append(f"grading.env holds {variable}, which is not a variable name")
    return problems


def scheme_digest(scheme: Scheme) -> str:
    text = json.dumps(dataclasses.asdict(scheme), sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json_private(path: Path, data: dict) -> None:
    """Atomic, and readable by the trainer alone: mkstemp makes the file 0600."""
    make_private(path.parent)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=False)
            stream.write("\n")
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


def earlier_results(path: Path, digest: str, warnings: list[str]) -> dict:
    """Results a re-run with --only must keep: only those made under this scheme."""
    try:
        earlier = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        warnings.append(f"{path} could not be read; earlier results are not kept")
        return {}
    if earlier.get("scheme_digest") != digest:
        warnings.append("the module's grading scheme changed since the last run; earlier results are discarded")
        return {}
    branches = earlier.get("branches")
    return branches if isinstance(branches, dict) else {}


def select_branches(listing: Listing, only: list[str] | None) -> list[BranchRef]:
    if not listing.participants:
        raise GradeError("no branch matches this module in the cache; run collect and check the module id")
    if not only:
        return listing.participants
    known = {ref.participant for ref in listing.participants}
    unknown = [who for who in only if who not in known]
    if unknown:
        raise GradeError(f"--only names {', '.join(unknown)}, not among the collected: {', '.join(sorted(known))}")
    return [ref for ref in listing.participants if ref.participant in only]


def probe_runtime(runtime: str, env: dict[str, str]) -> None:
    """A runtime with its daemon down would fail every participant. It stops the run."""
    try:
        done = subprocess.run([runtime, "info"], env=env, stdin=subprocess.DEVNULL, capture_output=True,
                              timeout=PROBE_TIMEOUT, check=False)
        detail = done.stderr.decode("utf-8", "replace").strip()
        ok = done.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as exc:
        ok, detail = False, str(exc)
    if not ok:
        raise GradeError(f"the container runtime {runtime} does not answer: {detail}. Nothing ran.")


def pull_image(plan: RunPlan, warnings: list[str]) -> None:
    """Pull before any clock starts, or the first branch pays for the download
    in its time limit. A failure is not final: the image may exist only locally."""
    try:
        done = subprocess.run([plan.runtime, "pull", plan.scheme.image or ""], env=plan.runtime_env,
                              stdin=subprocess.DEVNULL, capture_output=True, timeout=PULL_TIMEOUT, check=False)
        if done.returncode == 0:
            return
        detail = done.stderr.decode("utf-8", "replace").strip()
    except (subprocess.TimeoutExpired, OSError) as exc:
        detail = str(exc)
    warnings.append(f"could not pull {plan.scheme.image}: {detail}")


def docker_proxy_warning() -> str | None:
    """The docker client adds its config's `proxies` to every container, undeclared.

    Only whether the key is set is read; a proxy URL can hold a password, so its
    value is never printed or stored. An unreadable config is docker's business.
    """
    directory = os.environ.get("DOCKER_CONFIG")
    base = Path(directory) if directory else Path(os.environ.get("HOME", "/nonexistent")) / ".docker"
    path = base / "config.json"
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (isinstance(config, dict) and config.get("proxies")):
        return None
    return (f"{path} sets `proxies`: docker adds a proxy address, and any password in it, to every "
            "container, though grading.env does not declare it. Remove it for grading if that matters.")


def image_digest(plan: RunPlan) -> str:
    """The image the results came from, or "unknown". A tag can move between runs."""
    try:
        done = subprocess.run(
            [plan.runtime, "image", "inspect", "--format", "{{.Id}}", plan.scheme.image or ""],
            env=plan.runtime_env, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=PROBE_TIMEOUT, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "unknown"
    digest = done.stdout.decode("utf-8", "replace").strip()
    return digest if done.returncode == 0 and digest else "unknown"


def build_plan(repo: str, scheme: Scheme, runtime: str, warnings: list[str]) -> RunPlan:
    runtime_env = {k: os.environ[k] for k in RUNTIME_ENV_KEYS if k in os.environ}
    declared = []
    for variable in scheme.env:
        if variable in os.environ:
            declared.append(variable)
        else:
            warnings.append(f"{variable} is declared in grading.env and is not set; continuing without it")
    values = {v: os.environ[v] for v in declared}
    minutes = scheme.timeout_minutes or DEFAULT_TIMEOUT_MINUTES
    return RunPlan(
        runtime=runtime,
        scheme=scheme,
        cache=cache_dir(repo),
        limit_seconds=minutes * SECONDS_PER_MINUTE,
        runtime_env=runtime_env,
        run_env={**runtime_env, **values},
        declared=tuple(declared),
        masks={k: v for k, v in values.items() if v},
    )


def _terminate(signum: int, _frame: Any) -> None:
    # Becomes SystemExit, so run_container kills the container and run_branch
    # removes the checkout. SIGKILL cannot be handled, so it leaves both behind.
    raise SystemExit(128 + signum)


def cmd_run(args: argparse.Namespace) -> int:
    repo = checked_url(args.repo)
    store = store_dir(repo, args.module)
    scheme = load_scheme(Path(args.bundle))
    if scheme.module != args.module:
        raise GradeError(f"the bundle is module {scheme.module}, and the run asked for {args.module}")
    problems = scheme_problems(scheme)
    if problems:
        raise GradeError(
            "the bundle cannot be graded, and nothing ran (belay-validate reports these):\n  "
            + "\n  ".join(problems)
        )
    runtime = find_runtime()
    if ":" in tempfile.gettempdir():
        raise GradeError(f"the temporary directory {tempfile.gettempdir()} holds ':', so it cannot be mounted")
    warnings: list[str] = []
    plan = build_plan(repo, scheme, runtime, warnings)
    if not (plan.cache / "HEAD").exists():
        raise GradeError("nothing is collected for this repository; run collect with the same URL first")
    listing = list_branches(plan.cache, args.module)
    selected = select_branches(listing, args.only)
    probe_runtime(runtime, plan.runtime_env)
    digest_of_image = "unknown"
    if any(v.declared.get("kind") == "command" for v in scheme.validators):
        pull_image(plan, warnings)
        digest_of_image = image_digest(plan)
        proxy_warning = docker_proxy_warning()
        if proxy_warning:
            warnings.append(proxy_warning)

    path = store / RUN_FILE
    digest = scheme_digest(scheme)
    data = {
        "module": scheme.module,
        "bundle_version": scheme.bundle_version,
        "cohort": cohort_name(repo),
        "repository": normalise_url(repo),
        "image": scheme.image,
        "network": scheme.network,
        "env": list(scheme.env),
        "timeout_minutes": scheme.timeout_minutes or DEFAULT_TIMEOUT_MINUTES,
        "scheme_digest": digest,
        "refused": listing.refused,
        "no_convention": listing.other,
        "warnings": warnings,
        # A full run starts empty, so a deleted branch does not stay.
        "branches": earlier_results(path, digest, warnings) if args.only else {},
    }
    print(f"cohort: {data['cohort']}")
    any_suspect = False
    signals = {s: signal.signal(s, _terminate) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for ref in selected:
            record, suspect = run_branch(plan, ref, warnings)
            any_suspect = any_suspect or suspect
            record["runtime"] = runtime
            record["image_digest"] = digest_of_image
            data["branches"][ref.participant] = record
            write_json_private(path, data)  # after each branch: a stopped run keeps the rest
            print(f"{ref.participant} ({ref.branch}, {ref.commit[:12]}):")
            for name, result in record["validators"].items():
                gate = " (gate)" if result["gate"] else ""
                word = "pass" if result["passed"] else f"FAIL: {result['reason']}"
                print(f"  {name}{gate}  {word}")
    finally:
        for number, handler in signals.items():
            signal.signal(number, handler)
    write_json_private(path, data)
    render_not_graded(listing)
    print(f"results: {path}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if any_suspect:
        print("error: a result above may not be a judgement of the code; look at it before grading",
              file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def cmd_forget(args: argparse.Namespace) -> int:
    print(forget(args.cohort))
    return EXIT_OK


def _add_collect_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("repo", help="the cohort repository's URL")
    parser.add_argument("module", metavar="module-id", help="the module's id")


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle", required=True, help="the module's bundle directory")
    _add_collect_args(parser)
    parser.add_argument("--only", action="append", metavar="participant",
                        help="grade only this participant, repeat for more; others' results are kept")


# name -> (function, help, argument-adder). Add propose/confirm here.
SUBCOMMANDS: dict[str, tuple[Callable[[argparse.Namespace], int], str,
                             Callable[[argparse.ArgumentParser], None]]] = {
    "collect": (
        cmd_collect,
        "fetch the cohort repository into the local cache and list the module's branches",
        _add_collect_args,
    ),
    "run": (
        cmd_run,
        "run the module's validators on each collected branch, in a container",
        _add_run_args,
    ),
    "forget": (
        cmd_forget,
        "delete one cohort's stored grades and repository cache",
        lambda p: p.add_argument("cohort", help="the cohort name (a bare name)"),
    ),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grade.py",
        description="Grade a cohort's module work: read the scheme, keep the local "
        "grade store. Grades are stored outside any Git work tree.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (func, text, add_args) in SUBCOMMANDS.items():
        p = sub.add_parser(name, help=text, description=text)
        add_args(p)
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except GradeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return exc.code
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
