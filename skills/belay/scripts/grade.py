#!/usr/bin/env python3
"""Cohort grading: the scheme reader, the local grade store, collect and run.

Usage:
    grade.py collect <repo> <module-id>
        fetch the cohort repository into the local cache and list the branches
    grade.py run --bundle <dir> <repo> <module-id> [--only <participant>]...
        run the bundle's validators on each collected branch, in a container
    grade.py propose --bundle <dir> --judgement <file> <repo> <module-id>
        merge the validator results with the tutor's judgement: proposal.json
    grade.py confirm --bundle <dir> --by <name> [--change <p>:<criterion>=<points>:<reason>]...
                     [--exclude <p>]... <repo> <module-id>
        write final.json; the previous one is kept beside it as final.<date>.json
    grade.py makeup run|propose|confirm <repo> <bundle-id> <participant> --bundle <dir>
                     --catalog <file> [--judgement <file>] [--by <name> [--change <criterion>=<points>:<reason>]...]
        a further attempt, on <participant>/<bundle-id>-makeup, into <bundle-id>/makeup/<participant>/;
        final-project-and-certificate spec, section 3.1
    grade.py forget <cohort>     delete one cohort's stored grades and cache
    grade.py --help

Each subcommand is a function in SUBCOMMANDS below, taking the parsed arguments
and returning an exit code. The design is
docs/superpowers/specs/2026-11-03-cohort-grading-design.md; section 2.1 is the
`grading` key this reads, sections 3 and 4 are collect and run, section 5 is
the store.

propose and confirm compute every total, gate and rank themselves. The gate is
passed when every gate validator passed and every gate criterion has its full
points, from the CONFIRMED points; a module with no gate records null. Ties are
shown as ties, never broken. confirm refuses a stale proposal, comparing the
bundle's `grading` hash and each branch's commit in the LOCAL cache (no fetch).

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
and, under <module-id>/, the working files (run.json, proposal.json), so `forget`
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
    gate: bool = False  # must earn its full points for the gate to be passed


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
    grading_hash: str = ""  # of the manifest's `grading` block, without `retries`
    retries: int = 0  # further attempts after the first; not part of the hash

    @property
    def max_total(self) -> int:
        return sum(v.points for v in self.validators) + sum(c.points for c in self.rubric)


def grading_hash(grading: dict) -> str:
    """What a proposal is compared on: the `grading` block without `retries`.

    Raising `retries` during a programme must not stale a proposal, while any
    change to what is graded still does.
    """
    kept = {k: v for k, v in grading.items() if k != "retries"}
    return hashlib.sha256(json.dumps(kept, sort_keys=True, default=str).encode("utf-8")).hexdigest()


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
                gate=item.get("gate") is True,
            )
        )
    env = grading.get("env")
    timeout = grading.get("timeout_minutes")
    image = grading.get("image")
    retries = grading.get("retries")
    return Scheme(
        module=module,
        bundle_version=manifest.get("version"),
        image=image if isinstance(image, str) else None,
        network=grading.get("network") is True,
        env=tuple(str(e) for e in env) if isinstance(env, list) else (),
        timeout_minutes=timeout if isinstance(timeout, int) else None,
        validators=tuple(shares),
        rubric=tuple(criteria),
        grading_hash=grading_hash(grading),
        retries=retries if isinstance(retries, int) and not isinstance(retries, bool) and retries >= 0 else 0,
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
    can be another server, and two ssh users are two accounts. `git` is the shared
    ssh user of a forge, and equals none.

    Paths are compared as written, with no leading '/'. So alice@h:srv/x (relative
    to alice's home), alice@h:/srv/x and ssh://alice@h/srv/x share a cohort, though
    the first can be another directory. One trainer collecting a cohort under two of
    these forms is the case that would mix them.

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
        # ASCII digits only, and no int(): it refuses a very long number, and
        # str.isdigit accepts characters that int() refuses.
        if re.fullmatch(r"[0-9]+", port):
            port = port.lstrip("0") or "0"
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
    if module == "certificate":
        raise GradeError("`certificate` is not usable as a module id: the certificate's "
                         "output directory <cohort>/certificate/ would collide with it", EXIT_USAGE)
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
    makeup: list[BranchRef] = field(default_factory=list)


def classify_branch(branch: str, module: str) -> tuple[str, str | None]:
    """("participant", name), ("makeup", name), ("refused", None) or ("other", None).

    A makeup branch is <participant>/<module>-makeup, a further attempt at the module.

    Refused is a branch that is for this module and whose participant part is
    unusable; other is a branch that is not for this module at all.
    """
    for suffix, kind in ((f"/{module}", "participant"), (f"/{module}-makeup", "makeup")):
        if branch.endswith(suffix):
            who = branch[: -len(suffix)]
            return (kind, who) if _PARTICIPANT.fullmatch(who) else ("refused", None)
    return "other", None


def checked_url(repo: str) -> str:
    """The URL rule of `catalogs.start_from_problems`, which is `is_git_url`, and more.

    No refusal here prints the URL, because what it refuses can hold a credential.
    """
    # `?` and `#` are refused on top of that rule: a token in a query or fragment
    # is not in the authority, so it would reach a directory name and the output.
    if not is_git_url(repo) or "?" in repo or "#" in repo:
        raise GradeError(
            "the repository is not a Git URL; use https://..., ssh://... or "
            "user@host:path, whose host (and any user) begins with a letter or digit, "
            "and which holds no whitespace and none of ` $ ; | & < > ( ) ' \" \\ ? #"
        )
    scheme, has_scheme, rest = repo.partition("://")
    if has_scheme:
        authority, _, path = rest.partition("/")
        # A raw password can hold a '/', and then the authority ends inside it and
        # the rest of the password reads as a path, which reaches names and output.
        # Telling that from a real '@' in a path is not possible, so both are refused.
        if "@" in path:
            raise GradeError(
                "the repository URL has an '@' after its first '/'. That can be a password "
                "holding a '/', so it is refused and not shown; percent-encode the '/' or the '@'."
            )
        if not re.fullmatch(r"[0-9]{0,5}", authority.rpartition("@")[2].partition(":")[2]):
            raise GradeError("the repository URL's port is not a number of up to five digits.")
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
    """A branch name a participant chose, as printable ASCII.

    It is shown to the trainer's terminal and stored, so it can carry no control
    sequence and no line end, and it must not crash a stream that is not UTF-8.
    Backslash cannot be in a ref name, so this is unambiguous.
    """
    return "".join(c if c.isascii() and c.isprintable() else c.encode("unicode_escape").decode("ascii")
                   for c in name)


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
        elif kind == "makeup":
            listing.makeup.append(BranchRef(who, branch, commit, date))
        elif kind == "refused":
            listing.refused.append(escape_name(branch))
        else:
            listing.other.append(escape_name(branch))
    return listing


def render_not_graded(listing: Listing) -> None:
    print(f"refused, a participant name that cannot be used; never graded ({len(listing.refused)}):")
    for branch in listing.refused:
        print(f"  {branch}")
    print(f"further attempts ({len(listing.makeup)}):")
    for ref in listing.makeup:
        print(f"  {ref.participant}  {escape_name(ref.branch)}  {ref.commit[:12]}  {ref.committed_at}")
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


def verdict(share: ValidatorShare, passed: bool, output: str = "", reason: str | None = None,
            fault: bool = False) -> dict:
    """`fault` marks a result that is the runtime's or the checkout's, not the participant's."""
    return {
        "kind": share.declared.get("kind"),
        "passed": passed,
        "gate": share.gate,
        "output": output,
        "reason": reason,
        "fault": fault,
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
    checkout_failed = False
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
            checkout_failed = True
            stop_reason = f"checkout failed: {exc}"
            warnings.append(f"{ref.participant}: {stop_reason}")
        ordered = sorted(plan.scheme.validators, key=lambda v: v.declared.get("kind") == "command")
        for share in ordered:
            left = deadline - time.monotonic()
            if stop_reason is None and left <= 0:
                timed_out = True
                stop_reason = f"not run: {ran_out}"
            if stop_reason is not None:
                found[share.name] = verdict(share, False, reason=stop_reason, fault=checkout_failed)
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
                found[share.name] = verdict(share, False, output, outcome.error, fault=True)
            elif outcome.status == 0:
                found[share.name] = verdict(share, True, output)
            elif outcome.status == RUNTIME_REFUSED_STATUS or outcome.status in COMMAND_NOT_RUN_STATUSES:
                suspect = True
                reason = not_a_judgement(outcome.status)
                found[share.name] = verdict(share, False, output, reason, fault=True)
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
        # Why this branch's result may not be a judgement of the code, or None.
        "fault": next((r["reason"] or "a runtime fault" for r in found.values() if r["fault"]), None),
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
    """What a RUN depends on: the image, the container settings and the validators.

    The rubric, the module's version and the grading hash are left out, so editing
    a rubric criterion forces no container re-run. confirm still refuses such an
    edit, through the grading hash in the proposal.
    """
    text = json.dumps(
        dict(image=scheme.image, network=scheme.network, env=scheme.env,
             timeout_minutes=scheme.timeout_minutes,
             validators=[dataclasses.asdict(v) for v in scheme.validators]),
        sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json_private(path: Path, data: dict) -> None:
    """Atomic, and readable by the trainer alone: mkstemp makes the file 0600.

    Every write of the store comes through here, so the work-tree refusal is here too.
    """
    refuse_work_tree(path.parent)
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
    shown = 0

    def announce() -> None:
        # Printed as they arise: a warning that matters, a missing key above all, is
        # no use after a run of several hours. Each is printed once.
        nonlocal shown
        for warning in warnings[shown:]:
            print(f"warning: {warning}", file=sys.stderr, flush=True)
        shown = len(warnings)

    plan = build_plan(repo, scheme, runtime, warnings)
    if not (plan.cache / "HEAD").exists():
        raise GradeError("nothing is collected for this repository; run collect with the same URL first")
    listing = list_branches(plan.cache, args.module)
    selected = select_branches(listing, args.only)
    probe_runtime(runtime, plan.runtime_env)
    announce()
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
    print(f"results: {path}")
    announce()
    any_suspect = False
    signals = {s: signal.signal(s, _terminate) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        for ref in selected:
            record, suspect = run_branch(plan, ref, warnings)
            any_suspect = any_suspect or suspect
            record["runtime"] = runtime
            record["image_digest"] = digest_of_image
            data["branches"][ref.participant] = record
            # After each branch, so a stopped run keeps what it finished. A stopped full
            # run has already dropped the earlier results of branches it did not reach.
            write_json_private(path, data)
            print(f"{ref.participant} ({ref.branch}, {ref.commit[:12]}):")
            for name, result in record["validators"].items():
                gate = " (gate)" if result["gate"] else ""
                word = "pass" if result["passed"] else f"FAIL: {result['reason']}"
                print(f"  {name}{gate}  {word}")
            announce()
    finally:
        for number, handler in signals.items():
            signal.signal(number, handler)
    write_json_private(path, data)
    render_not_graded(listing)
    print(f"results: {path}")
    if any_suspect:
        print("error: a result above may not be a judgement of the code; look at it before grading",
              file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


# --------------------------------------------------------------------------
# Propose and confirm (spec section 3, steps 3 to 5, and section 5)
# --------------------------------------------------------------------------
#
# The judgement file is what the tutor writes (JSON, read strictly):
#
#   {"participants": {"<participant>": {"<criterion id>": {"points": 12, "evidence": "..."}}},
#    "draft": {"why_best": "...", "gaps": {"<participant>": "..."}}}        <- draft optional
#
# Totals, gate results and the ranking are computed here from the validator
# results in run.json and these points. A judgement that carries any key not
# listed above (a "total", a "ranking") is REFUSED, not ignored, so a number the
# tutor typed can never be mistaken for a computed one.

PROPOSAL_FILE = "proposal.json"
FINAL_FILE = "final.json"
JUDGEMENT_MAX_BYTES = 4 * 1024 * 1024
EVIDENCE_MAX_CHARS = 20000
MAX_REPORTED_PROBLEMS = 25


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"the key {key!r} appears twice")
        out[key] = value
    return out


def read_json_file(path: Path, what: str, limit: int) -> Any:
    try:
        raw = path.read_bytes() if path.stat().st_size <= limit else None
    except OSError as exc:
        raise GradeError(f"cannot read {what} {path}: {exc}", EXIT_USAGE) from exc
    if raw is None:
        raise GradeError(f"{what} {path} is larger than {limit} bytes", EXIT_USAGE)
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (ValueError, UnicodeDecodeError, RecursionError) as exc:
        raise GradeError(f"{what} {path} is not valid JSON: {exc}", EXIT_USAGE) from exc


def _is_points(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_judgement(path: Path, scheme: Scheme, known: list[str],
                   ungradable: frozenset[str] = frozenset()) -> tuple[dict, dict | None]:
    """The rated points and the draft, or a refusal naming every defect found.

    `known` are the participants in run.json. An `ungradable` one (a runtime fault)
    need not be in the judgement; if it is, it is checked like any other and unused.
    """
    data = read_json_file(path, "the judgement", JUDGEMENT_MAX_BYTES)
    problems: list[str] = []

    def bad(text: str) -> None:
        problems.append(text)

    if not isinstance(data, dict):
        raise GradeError(f"the judgement {path} must be a JSON object with `participants`")
    for key in data:
        if key not in ("participants", "draft"):
            bad(f"unknown top-level key {key!r}: totals and the ranking are computed here and "
                "are never taken from the judgement (keys: participants, draft)")
    people = data.get("participants")
    ratings: dict[str, dict[str, dict]] = {}
    if not isinstance(people, dict):
        bad("`participants` must be an object of participant to criteria")
        people = {}
    for who in people:
        if who not in known:
            bad(f"{escape_name(str(who))} is in the judgement and is not in run.json, which holds "
                f"{', '.join(known) or 'nobody'}; run `belay-grade run` for that branch first "
                "(or remove it from the judgement)")
    ids = [c.id for c in scheme.rubric]
    for who in known:
        entry = people.get(who)
        if entry is None:
            if who not in ungradable:
                bad(f"{who} is in run.json and missing from the judgement")
            continue
        if not isinstance(entry, dict):
            bad(f"{who}: must be an object of criterion id to {{points, evidence}}")
            continue
        for cid in entry:
            if cid not in ids:
                bad(f"{who}: {escape_name(str(cid))} is not a criterion of this module "
                    f"(criteria: {', '.join(ids) or 'none'})")
        rated: dict[str, dict] = {}
        for crit in scheme.rubric:
            item = entry.get(crit.id)
            if item is None:
                bad(f"{who}: criterion {crit.id} is missing")
                continue
            if not isinstance(item, dict):
                bad(f"{who}: {crit.id} must be an object with `points` and `evidence`")
                continue
            for key in item:
                if key not in ("points", "evidence"):
                    bad(f"{who}: {crit.id} has the unknown key {escape_name(str(key))!r}; "
                        "the keys are points and evidence")
            pts, evidence = item.get("points"), item.get("evidence")
            if not _is_points(pts) or not 0 <= pts <= crit.points:
                bad(f"{who}: {crit.id} points is {pts!r}; it must be an integer from 0 to {crit.points}")
                continue
            if not isinstance(evidence, str) or not evidence.strip():
                bad(f"{who}: {crit.id} has no evidence; quote code, specification text or "
                    "validator output with file and line")
                continue
            if len(evidence) > EVIDENCE_MAX_CHARS:
                bad(f"{who}: {crit.id} evidence is longer than {EVIDENCE_MAX_CHARS} characters")
                continue
            rated[crit.id] = {"points": pts, "evidence": evidence}
        ratings[who] = rated
    draft = data.get("draft")
    if draft is not None:
        if not isinstance(draft, dict):
            bad("`draft` must be an object with why_best and gaps")
        else:
            for key in draft:
                if key not in ("why_best", "gaps"):
                    bad(f"draft has the unknown key {escape_name(str(key))!r} (keys: why_best, gaps)")
            if not isinstance(draft.get("why_best"), str):
                bad("draft.why_best must be a string")
            gaps = draft.get("gaps", {})
            if not isinstance(gaps, dict) or not all(
                    isinstance(v, str) and k in known for k, v in gaps.items()):
                bad("draft.gaps must map a graded participant to a string")
    if problems:
        shown = problems[:MAX_REPORTED_PROBLEMS]
        more = len(problems) - len(shown)
        raise GradeError(
            f"the judgement {path} is refused, and no proposal was written:\n  "
            + "\n  ".join(shown) + (f"\n  ... and {more} more" if more else ""))
    return ratings, draft


def rank(totals: dict[str, int]) -> list[dict]:
    """Groups of equal totals, best first. A tie is one group; nothing breaks it.

    `rank` is the place of the group's first member (1, 2, 2, 4 style).
    """
    out, ahead = [], 0
    for total in sorted(set(totals.values()), reverse=True):
        who = sorted(p for p, t in totals.items() if t == total)
        out.append({"rank": ahead + 1, "total": total, "participants": who, "tied": len(who) > 1})
        ahead += len(who)
    return out


def gate_result(validators: dict, criteria: dict) -> bool | None:
    """None when the module has no gate at all (not applicable, never 'passed')."""
    gate_v = [v for v in validators.values() if v["gate"]]
    gate_c = [c for c in criteria.values() if c["gate"]]
    if not gate_v and not gate_c:
        return None
    return all(v["passed"] for v in gate_v) and all(c["points"] == c["max"] for c in gate_c)


def short(text: Any) -> str:
    """A reason for the terminal: printable ASCII, one line, bounded."""
    return escape_name(str(text))[:300]


def _summary_lines(participants: dict, ranking: list[dict], max_total: int) -> list[str]:
    lines = []
    for who, p in participants.items():
        if p.get("ungradable"):
            lines.append(f"{who}: NOT GRADABLE, no total and no rank. A runtime fault, not the "
                         f"participant's result: {short(p['reason'])}")
            continue
        gate = {True: "passed", False: "NOT passed", None: "n/a"}[p["gate"]]
        late = f"  (timed out: {short(next((v['reason'] for v in p['validators'].values() if v.get('reason') and 'time limit' in v['reason']), ''))})" \
            if p.get("timed_out") else ""
        lines.append(f"{who}: validators {p['validator_points']}, rubric {p['rubric_points']}, "
                     f"total {p['total']}/{max_total}, gate {gate}{late}")
    for group in ranking:
        names = ", ".join(group["participants"])
        mark = f"{group['rank']}= " if group["tied"] else f"{group['rank']}. "
        lines.append(f"rank {mark}{names} ({group['total']})" + ("  TIE" if group["tied"] else ""))
    return lines


def proposed_validators(rec: dict, scheme: Scheme) -> dict:
    """One branch's validator results from run.json, with the points they earn."""
    validators = {}
    for share in scheme.validators:
        got = rec["validators"][share.name]
        passed = got.get("passed") is True
        validators[share.name] = {"passed": passed, "points": share.points if passed else 0,
                                  "gate": share.gate, "reason": got.get("reason"),
                                  "fault": got.get("fault") is True}
    return validators


def proposed_criteria(rated: dict, scheme: Scheme) -> dict:
    return {crit.id: {**rated[crit.id], "max": crit.points, "gate": crit.gate} for crit in scheme.rubric}


def cmd_propose(args: argparse.Namespace) -> int:
    repo = checked_url(args.repo)
    store = store_dir(repo, args.module)
    scheme = load_scheme(Path(args.bundle))
    if scheme.module != args.module:
        raise GradeError(f"the bundle is module {scheme.module}, and the proposal asked for {args.module}")
    run = read_json_file(store / RUN_FILE, "the run results", JUDGEMENT_MAX_BYTES * 8) \
        if (store / RUN_FILE).exists() else None
    if not isinstance(run, dict) or not isinstance(run.get("branches"), dict) or not run["branches"]:
        raise GradeError("there are no run results for this module; run `belay-grade run` first")
    if run.get("module") != scheme.module:
        raise GradeError(f"run.json is for module {run.get('module')!r}, not {scheme.module}")
    if run.get("scheme_digest") != scheme_digest(scheme):
        raise GradeError("the module's grading scheme changed since the last run, so the validator "
                         "results are not for this scheme; run `belay-grade run` again")
    branches = run["branches"]
    known = list(branches)
    for who in known:
        got = branches[who].get("validators") if isinstance(branches[who], dict) else None
        if not isinstance(got, dict) or any(v.name not in got for v in scheme.validators):
            raise GradeError(f"run.json holds no complete validator results for {who}; run again")
    faults = {who: branches[who]["fault"] for who in known
              if isinstance(branches[who].get("fault"), str)}
    ratings, draft = read_judgement(Path(args.judgement), scheme, known, frozenset(faults))

    warnings: list[str] = []
    cache = cache_dir(repo)
    if (cache / "HEAD").exists():
        live = {r.participant for r in list_branches(cache, args.module).participants}
        for who in known:
            if who not in live:
                warnings.append(f"{who} is in run.json and its branch is no longer in the cache "
                                "(removed since a merged --only run?); it is graded from run.json")

    participants: dict[str, dict] = {}
    for who in known:
        rec = branches[who]
        validators = proposed_validators(rec, scheme)
        if who in faults:
            # A runtime fault is not the participant's result: no total, no rank, no gate.
            participants[who] = {
                "branch": rec.get("branch"), "commit": rec.get("commit"),
                "ungradable": True, "reason": faults[who], "timed_out": rec.get("timed_out") is True,
                "validators": validators, "criteria": {}, "validator_points": None,
                "rubric_points": None, "gate": None, "total": None, "max_total": scheme.max_total,
            }
            continue
        criteria = proposed_criteria(ratings[who], scheme)
        vpts = sum(v["points"] for v in validators.values())
        rpts = sum(c["points"] for c in criteria.values())
        participants[who] = {
            "branch": rec.get("branch"), "commit": rec.get("commit"),
            "ungradable": False, "reason": None, "timed_out": rec.get("timed_out") is True,
            "validators": validators, "criteria": criteria,
            "validator_points": vpts, "rubric_points": rpts,
            "gate": gate_result(validators, criteria),
            "total": vpts + rpts, "max_total": scheme.max_total,
        }
    ranking = rank({w: p["total"] for w, p in participants.items() if not p["ungradable"]})
    proposal = {
        "module": scheme.module,
        "bundle_version": scheme.bundle_version,
        "grading_hash": scheme.grading_hash,
        "cohort": cohort_name(repo),
        "repository": normalise_url(repo),
        "proposed_at": now_iso(),
        "max_total": scheme.max_total,
        "participants": participants,
        "ranking": ranking,
        "draft": draft,
        "warnings": warnings,
    }
    path = store / PROPOSAL_FILE
    write_json_private(path, proposal)
    print(f"cohort: {proposal['cohort']}")
    for line in _summary_lines(participants, ranking, scheme.max_total):
        print(line)
    if any(g["tied"] for g in ranking):
        print("a tie is shown as a tie; nothing here breaks it. The trainer picks.")
    print(f"proposal: {path}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return EXIT_OK


def parse_change(text: str) -> tuple[str, str, int, str]:
    """<participant>:<criterion>=<points>:<reason>; the reason may hold ':'."""
    # The criterion id ends at the LAST '=' before the first ':' that follows it.
    who, sep, rest = text.partition(":")
    head, sep2, reason = rest.partition(":")
    cid, eq, pts = head.rpartition("=")
    if not (sep and sep2 and eq and who and cid and re.fullmatch(r"-?[0-9]+", pts)):
        raise GradeError(
            f"--change {escape_name(text)!r} is not <participant>:<criterion>=<points>:<reason>")
    if not reason.strip():
        raise GradeError(f"--change for {escape_name(who)}:{escape_name(cid)} has no reason; "
                         "a change needs one")
    return who, cid, int(pts), reason.strip()


def changes_since(proposal: dict, scheme: Scheme, cache: Path, module: str,
                  excluded: list[str]) -> list[str]:
    """What moved since the proposal. Reads the local cache only; it never fetches.

    A branch the proposal does not cover counts, so nobody is dropped by accident,
    unless the trainer leaves it out by name with --exclude.
    """
    stale = []
    if proposal.get("grading_hash") != scheme.grading_hash:
        stale.append("the bundle's `grading` block differs from the one the proposal was made under")
    if not (cache / "HEAD").exists():
        stale.append("the local cache of the repository is gone, so the branches cannot be compared")
        return stale
    live = {r.participant: r.commit for r in list_branches(cache, module).participants}
    for who, p in proposal["participants"].items():
        if who not in live:
            stale.append(f"{who}'s branch is no longer in the cache")
        elif live[who] != p.get("commit"):
            stale.append(f"{who}'s branch moved: {str(p.get('commit'))[:12]} -> {live[who][:12]}")
    for who in sorted(set(live) - set(proposal["participants"]) - set(excluded)):
        stale.append(f"{who} has a branch the proposal does not cover; "
                     "to leave it out on purpose, pass --exclude with that name")
    return stale


def archive_previous(store: Path) -> Path | None:
    """Keep the existing final.json beside the new one as final.<date>.json.

    The date is the day it was confirmed. A hard link makes the archive atomic and
    cannot overwrite: on a name already taken, the next suffix is used.
    """
    current = store / FINAL_FILE
    if not current.exists():
        return None
    day = now_iso()[:10]
    try:
        stamp = json.loads(current.read_text(encoding="utf-8")).get("confirmed_at")
        if isinstance(stamp, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T.*", stamp):
            day = stamp[:10]
    except (OSError, ValueError, AttributeError):
        pass
    for n in range(1, 10000):
        target = store / (f"final.{day}.json" if n == 1 else f"final.{day}-{n}.json")
        try:
            os.link(current, target)
        except FileExistsError:
            continue
        except OSError:
            # No hard links here (a file system without them): copy, then rename.
            if target.exists():
                continue
            handle, name = tempfile.mkstemp(dir=store, prefix=f".{target.name}.")
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(current.read_bytes())
                os.replace(name, target)
            except BaseException:
                if os.path.exists(name):
                    os.unlink(name)
                raise
        return target
    raise GradeError("cannot find a free name for the previous final.json")


def unrepeated_changes(store: Path, final_people: dict) -> list[str]:
    """The trainer's changes in the current final.json that the new one does not repeat.

    Every confirmation starts from proposal.json and nothing is carried over, so this
    is how a trainer learns that a change, and perhaps a gate, went with the old file.
    Call it before final.json is replaced. The old file is only read here, and a
    damaged one does not stop a confirmation.
    """
    try:
        previous = json.loads((store / FINAL_FILE).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, RecursionError):
        return ["the previous final.json could not be read, so its changes cannot be listed"]
    people = previous.get("participants") if isinstance(previous, dict) else None
    lines = []
    for who, entry in (people.items() if isinstance(people, dict) else ()):
        criteria = entry.get("criteria") if isinstance(entry, dict) else None
        for cid, old in (criteria.items() if isinstance(criteria, dict) else ()):
            if not (isinstance(old, dict) and old.get("changed_by_trainer") is True):
                continue
            now = final_people.get(who, {}).get("criteria", {}).get(cid)
            if now is not None and now["changed_by_trainer"] and now["points"] == old.get("points"):
                continue
            state = "not in this confirmation" if now is None else f"now {now['points']}"
            lines.append(f"{short(who)}:{short(cid)} was {short(old.get('points'))}, {state}: "
                         f"{short(old.get('reason'))}")
    return lines


def check_proposal(proposal: Any) -> None:
    """A proposal.json that parses but is not one is a message, not a KeyError."""
    def damaged(why: str) -> GradeError:
        return GradeError(f"proposal.json is damaged ({why}); run `belay-grade propose` again")

    if not isinstance(proposal, dict):
        raise damaged("it is not an object")
    for key in ("module", "bundle_version", "grading_hash", "max_total", "participants"):
        if key not in proposal:
            raise damaged(f"no `{key}`")
    people = proposal["participants"]
    if not isinstance(people, dict) or not people:
        raise damaged("`participants` is empty or not an object")
    for who, p in people.items():
        if not isinstance(p, dict) or not isinstance(p.get("validators"), dict) \
                or not isinstance(p.get("commit"), str) or "ungradable" not in p:
            raise damaged(f"the entry of {escape_name(str(who))} is incomplete")
        if p["ungradable"]:
            if not isinstance(p.get("reason"), str):
                raise damaged(f"{escape_name(str(who))} is ungradable with no reason")
            continue
        if not isinstance(p.get("criteria"), dict) or "max_total" not in p:
            raise damaged(f"the entry of {escape_name(str(who))} is incomplete")
        for name, v in p["validators"].items():
            if not (isinstance(v, dict) and {"passed", "points", "gate"} <= set(v)):
                raise damaged(f"{escape_name(str(who))}: validator {escape_name(str(name))} is incomplete")
        for cid, c in p["criteria"].items():
            if not (isinstance(c, dict) and {"points", "max", "evidence", "gate"} <= set(c)
                    and _is_points(c["points"]) and _is_points(c["max"])):
                raise damaged(f"{escape_name(str(who))}: criterion {escape_name(str(cid))} is incomplete")


def check_change(who: str, cid: str, pts: int, entry: dict, applied: dict) -> None:
    """One --change against one proposed entry; `applied` holds the (who, cid) already taken."""
    if cid in entry["validators"]:
        raise GradeError(f"--change names {escape_name(cid)}, which is a validator: validators are "
                         "deterministic and the trainer cannot change them. A criterion of the "
                         f"rubric can be changed ({', '.join(entry['criteria']) or 'none'}).")
    crit = entry["criteria"].get(cid)
    if crit is None:
        raise GradeError(f"--change names criterion {escape_name(cid)}, which {who} has no "
                         f"points for ({', '.join(entry['criteria']) or 'none'})")
    if not 0 <= pts <= crit["max"]:
        raise GradeError(f"--change {who}:{cid} gives {pts}; it must be from 0 to {crit['max']}")
    if (who, cid) in applied:
        raise GradeError(f"--change names {who}:{cid} twice")
    if pts == crit["points"]:
        raise GradeError(f"--change {who}:{cid}={pts} is not a change: the proposal has {pts}")


def confirmed_entry(p: dict, changes: dict[str, tuple[int, str]]) -> tuple[dict, dict, bool | None, int]:
    """validators, criteria, gate and total of one proposed entry with the trainer's changes."""
    validators = {n: {"passed": v["passed"], "points": v["points"]} for n, v in p["validators"].items()}
    criteria, gating = {}, {}
    for cid, c in p["criteria"].items():
        pts, reason = changes.get(cid, (c["points"], None))
        criteria[cid] = {"points": pts, "proposed_points": c["points"], "max": c["max"],
                         "evidence": c["evidence"],
                         "changed_by_trainer": reason is not None, "reason": reason}
        gating[cid] = {"points": pts, "max": c["max"], "gate": c["gate"]}
    # The gate is computed from the CONFIRMED points, so a change can flip it.
    gate = gate_result({n: {"passed": v["passed"], "gate": p["validators"][n]["gate"]}
                        for n, v in validators.items()}, gating)
    total = sum(v["points"] for v in validators.values()) + sum(c["points"] for c in criteria.values())
    return validators, criteria, gate, total


def cmd_confirm(args: argparse.Namespace) -> int:
    repo = checked_url(args.repo)
    store = store_dir(repo, args.module)
    by = args.by.strip()
    if not by or len(by) > 200 or not by.isprintable():
        raise GradeError("--by must name who confirms: one line of printable text")
    scheme = load_scheme(Path(args.bundle))
    if scheme.module != args.module:
        raise GradeError(f"the bundle is module {scheme.module}, and the confirmation asked for {args.module}")
    if not (store / PROPOSAL_FILE).exists():
        raise GradeError("there is no proposal for this module; run `belay-grade propose` first")
    proposal = read_json_file(store / PROPOSAL_FILE, "the proposal", JUDGEMENT_MAX_BYTES * 8)
    check_proposal(proposal)
    excluded = list(dict.fromkeys(args.exclude or []))
    stale = changes_since(proposal, scheme, cache_dir(repo), args.module, excluded)
    if stale:
        raise GradeError(
            "the proposal is stale, and nothing was confirmed (confirm reads the local cache and "
            "does not fetch; run collect to update it, then run and propose again):\n  "
            + "\n  ".join(stale))

    people = proposal["participants"]
    live = {r.participant: r.commit for r in list_branches(cache_dir(repo), args.module).participants}
    for who in excluded:
        if who not in people:
            if who not in live:
                raise GradeError(f"--exclude names {escape_name(who)}, who is not in the proposal "
                                 f"({', '.join(people)}) and has no branch of this module in the cache")
            continue
        if not people[who]["ungradable"]:
            raise GradeError(f"--exclude names {who}, who is gradable; only a participant with a "
                             "runtime fault, or a branch the proposal does not cover, can be excluded")
    open_faults = [w for w, p in people.items() if p["ungradable"] and w not in excluded]
    if open_faults:
        raise GradeError(
            "nothing was confirmed: these participants could not be graded because of a runtime "
            "fault, which is not their result. Repair the fault and run again, or pass "
            "--exclude <participant> to leave one out of final.json:\n  "
            + "\n  ".join(f"{w}: {short(people[w]['reason'])}" for w in open_faults))
    applied: dict[tuple[str, str], tuple[int, str]] = {}
    for text in args.change or []:
        who, cid, pts, reason = parse_change(text)
        if who not in people:
            raise GradeError(f"--change names {escape_name(who)}, who is not in the proposal "
                             f"({', '.join(people)})")
        if people[who]["ungradable"]:
            raise GradeError(f"--change names {who}, who is not graded (a runtime fault)")
        check_change(who, cid, pts, people[who], applied)
        applied[(who, cid)] = (pts, reason)

    final_people: dict[str, dict] = {}
    for who, p in people.items():
        if p["ungradable"]:
            continue
        validators, criteria, gate, total = confirmed_entry(
            p, {cid: change for (w, cid), change in applied.items() if w == who})
        final_people[who] = {"commit": p["commit"], "validators": validators, "criteria": criteria, "gate": gate,
                             "total": total, "max_total": p["max_total"]}
    final = {
        "module": proposal["module"],
        "bundle_version": proposal["bundle_version"],
        "grading_hash": proposal["grading_hash"],
        "confirmed_by": by,
        "confirmed_at": now_iso(),
        "participants": final_people,
        "not_graded": {w: {"reason": people[w]["reason"], "commit": people[w]["commit"]} if w in people else
                       {"reason": "excluded by the trainer; the proposal does not cover this branch",
                        "commit": live.get(w)}
                       for w in excluded},
    }
    refuse_work_tree(store)
    unrepeated = unrepeated_changes(store, final_people)
    kept = archive_previous(store)
    path = store / FINAL_FILE
    write_json_private(path, final)
    ranking = rank({w: p["total"] for w, p in final_people.items()})
    print(f"confirmed by {by}; {len(applied)} change(s)")
    for (who, cid), (pts, reason) in applied.items():
        print(f"  changed {who}:{cid} {people[who]['criteria'][cid]['points']} -> {pts}: {escape_name(reason)}")
    shown = {w: {**p, "validator_points": sum(v["points"] for v in p["validators"].values()),
                 "rubric_points": sum(c["points"] for c in p["criteria"].values()),
                 "timed_out": people[w].get("timed_out"),
                 "validators": people[w]["validators"]}
             for w, p in final_people.items()}
    for w in excluded:
        if w in people:
            shown[w] = people[w]
    for line in _summary_lines(shown, ranking, proposal["max_total"]):
        print(line)
    for w in excluded:
        if w not in people:
            print(f"{w}: excluded by the trainer, not graded")
    if ranking and ranking[0]["tied"]:
        print("the top place is a tie: choosing the start branch is the trainer's; final.json stores no winner.")
    if unrepeated:
        print("the previous confirmation changed these, and this one does not repeat them; nothing "
              "is carried over, so to keep one, confirm again with its --change:")
        for line in unrepeated:
            print(f"  {line}")
    if kept:
        print(f"previous confirmation kept: {kept}")
    print(f"final: {path}")
    return EXIT_OK


# --------------------------------------------------------------------------
# Further attempts (final-project-and-certificate spec, section 3.1)
# --------------------------------------------------------------------------
#
# A further attempt is graded on its own branch, <participant>/<bundle>-makeup, into
# <store>/<cohort>/<bundle>/makeup/<participant>/, by the same steps as the cohort:
# run, propose, confirm. It never touches the bundle's own final.json, and it is
# never ranked. An attempt is a COMMIT: the count is the number of different commits
# with a confirmed result, so a trainer correcting a confirmed attempt uses none.
#
# Every refusal is raised before anything is written.

MAKEUP_DIR = "makeup"


def _certificate_module():
    """certificate.py, imported here and not at load time, so there is no import cycle.

    certificate.py takes GradeError from `grade`. Run as a script this module is
    __main__, and importing `grade` again would make a second GradeError class that
    main() does not catch, so this module is registered under its own name first.
    """
    sys.modules.setdefault("grade", sys.modules[__name__])
    import certificate
    return certificate


def attempts_used(store: Path) -> set[str]:
    """The distinct commits confirmed in a makeup directory: final.json and every final.*.json.

    A file that cannot be read is a refusal, not a miscount, because a miscount could
    give an attempt the course did not allow.
    """
    used: set[str] = set()
    for path in [store / FINAL_FILE, *sorted(store.glob("final.*.json"))]:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError) as exc:
            raise GradeError(f"{path} cannot be read, so the attempts used cannot be counted: {exc}") from exc
        commit = data.get("commit") if isinstance(data, dict) else None
        if isinstance(commit, str):
            used.add(commit)
    return used


@dataclass(frozen=True)
class Makeup:
    repo: str
    bundle: str
    participant: str
    kind: str  # "module" or "final_project"
    share: int
    scheme: Scheme  # the bundle's whole scheme
    graded: Scheme  # what a further attempt is graded on
    store: Path  # <bundle store>/makeup/<participant>
    module_final: dict
    latest: dict | None  # the latest confirmed further attempt, or None
    used: frozenset[str]


def gate_scheme(scheme: Scheme) -> Scheme:
    """A module's further attempt: the gate validators and gate criteria, nothing else."""
    return dataclasses.replace(scheme, validators=tuple(v for v in scheme.validators if v.gate),
                               rubric=tuple(c for c in scheme.rubric if c.gate))


def makeup_context(args: argparse.Namespace) -> Makeup:
    """Everything every makeup step checks first, read and refused before any write."""
    repo = checked_url(args.repo)
    bundle_store = store_dir(repo, args.bundle_id)
    who = args.participant
    if not _PARTICIPANT.fullmatch(who):
        raise GradeError(f"{escape_name(who)!r} is not a usable participant name: the part of a branch "
                         "name before the slash, of letters, digits, '.', '_' and '-'")
    cert_module = _certificate_module()
    cert = cert_module.load_certificate(Path(args.catalog))
    kind = cert_module.kind_of(cert, args.bundle_id)
    scheme = load_scheme(Path(args.bundle))
    if scheme.module != args.bundle_id:
        raise GradeError(f"the bundle is {scheme.module}, and the further attempt asked for {args.bundle_id}")
    problems = scheme_problems(scheme)
    if problems:
        raise GradeError("the bundle cannot be graded (belay-validate reports these):\n  " + "\n  ".join(problems))
    if not (bundle_store / FINAL_FILE).is_file():
        raise GradeError(f"{args.bundle_id} has no confirmed final.json in this cohort's store: a further "
                         "attempt follows the cohort's grading, so confirm that first")
    module_final = read_json_file(bundle_store / FINAL_FILE, "the confirmed grades", JUDGEMENT_MAX_BYTES * 8)
    if not isinstance(module_final, dict) or not isinstance(module_final.get("participants"), dict):
        raise GradeError(f"{bundle_store / FINAL_FILE} is damaged: it has no `participants`")
    if not isinstance(module_final.get("grading_hash"), str):
        raise GradeError(f"{bundle_store / FINAL_FILE} records no grading_hash: it was confirmed by an older "
                         "Belay, so the grading block the cohort met is unknown. The bundle must be "
                         "confirmed again with this Belay (`belay-grade confirm`) before a further attempt")
    if module_final["grading_hash"] != scheme.grading_hash:
        raise GradeError(f"the bundle's grading block differs from the one the cohort met in "
                         f"{args.bundle_id}'s final.json; a further attempt is graded on the same task, so "
                         "use the bundle the cohort was graded with")
    store = bundle_store / MAKEUP_DIR / who
    refuse_work_tree(store)
    latest = read_json_file(store / FINAL_FILE, "the latest further attempt", JUDGEMENT_MAX_BYTES * 8) \
        if (store / FINAL_FILE).is_file() else None
    if latest is not None and not isinstance(latest, dict):
        raise GradeError(f"{store / FINAL_FILE} is damaged: it is not an object")
    return Makeup(
        repo=repo, bundle=args.bundle_id, participant=who, kind=kind, share=cert.share, scheme=scheme,
        graded=gate_scheme(scheme) if kind == "module" else scheme, store=store,
        module_final=module_final, latest=latest, used=frozenset(attempts_used(store)),
    )


def open_requirement(ctx: Makeup) -> str | None:
    """Why the participant's requirement is open, in the latest confirmed attempt; None when met.

    A module is open on a gate of false, an entry in not_graded, or no branch at the
    checkpoint. A final project is open only for someone under `participants`, on a
    gate of false or too few points.
    """
    if ctx.latest is not None:
        entry, where = ctx.latest, "in the latest confirmed further attempt"
    else:
        people = ctx.module_final["participants"]
        not_graded = ctx.module_final.get("not_graded")
        if ctx.kind == "module":
            if isinstance(not_graded, dict) and ctx.participant in not_graded:
                return f"{ctx.participant} is in not_graded of {ctx.bundle}'s final.json"
            if ctx.participant not in people:
                return f"{ctx.participant} had no branch of {ctx.bundle} at the checkpoint"
        elif ctx.participant not in people:
            return None
        entry, where = people[ctx.participant], f"in {ctx.bundle}'s final.json"
    if not isinstance(entry, dict):
        raise GradeError(f"the entry of {ctx.participant} {where} is damaged")
    if entry.get("gate") is False:
        return f"the gate is not met yet {where}"
    if ctx.kind == "final_project":
        total, max_total = entry.get("total"), entry.get("max_total")
        if _is_points(total) and _is_points(max_total) and total * 100 < ctx.share * max_total:
            return f"{total} of {max_total} points {where}, under the share of {ctx.share}%"
    return None


def admit_attempt(ctx: Makeup, commit: str) -> str:
    """Refuse a commit that is not a permitted attempt; return what it is, in words."""
    if ctx.latest is not None and ctx.latest.get("commit") == commit:
        return "a correction of the latest confirmed attempt, which uses no further attempt"
    reason = open_requirement(ctx)
    if reason is None:
        where = f"in {ctx.bundle}" if ctx.kind == "module" else f"in the final project {ctx.bundle}"
        raise GradeError(f"{ctx.participant} has nothing open {where}: the requirement is met, or "
                         "(for a final project) they did not take part in it, so a further attempt "
                         "would replace nothing")
    if commit in ctx.used:
        return f"open ({reason}); this commit was confirmed before, so it uses no further attempt"
    if ctx.scheme.retries == 0:
        raise GradeError(f"{ctx.bundle} allows no further attempt: its grading.retries is absent or 0 "
                         f"({reason})")
    if len(ctx.used) >= ctx.scheme.retries:
        raise GradeError(f"{ctx.participant}'s further attempts at {ctx.bundle} are used up: "
                         f"{len(ctx.used)} of {ctx.scheme.retries} (grading.retries) confirmed")
    return f"open ({reason}); attempt {len(ctx.used) + 1} of {ctx.scheme.retries}"


def makeup_branch(ctx: Makeup) -> BranchRef:
    """The participant's makeup branch in the local cache; it never fetches."""
    cache = cache_dir(ctx.repo)
    if not (cache / "HEAD").exists():
        raise GradeError("nothing is collected for this repository; run collect with the same URL first")
    for ref in list_branches(cache, ctx.bundle).makeup:
        if ref.participant == ctx.participant:
            return ref
    raise GradeError(f"there is no branch {ctx.participant}/{ctx.bundle}-makeup in the cache; the "
                     "further attempt goes on that branch. Run collect after it is pushed")


def cmd_makeup_run(args: argparse.Namespace) -> int:
    ctx = makeup_context(args)
    ref = makeup_branch(ctx)
    what = admit_attempt(ctx, ref.commit)
    graded = ctx.graded
    warnings: list[str] = []
    record: dict
    suspect = False
    if graded.validators:
        runtime = find_runtime()
        if ":" in tempfile.gettempdir():
            raise GradeError(f"the temporary directory {tempfile.gettempdir()} holds ':', so it cannot be mounted")
        plan = build_plan(ctx.repo, graded, runtime, warnings)
        probe_runtime(runtime, plan.runtime_env)
        digest_of_image = "unknown"
        if any(v.declared.get("kind") == "command" for v in graded.validators):
            pull_image(plan, warnings)
            digest_of_image = image_digest(plan)
            proxy_warning = docker_proxy_warning()
            if proxy_warning:
                warnings.append(proxy_warning)
        signals = {s: signal.signal(s, _terminate) for s in (signal.SIGTERM, signal.SIGHUP)}
        try:
            record, suspect = run_branch(plan, ref, warnings)
        finally:
            for number, handler in signals.items():
                signal.signal(number, handler)
        record["runtime"] = runtime
        record["image_digest"] = digest_of_image
    else:
        # A module with no gate validator: nothing runs, the trainer confirms the work.
        stamp = now_iso()
        record = {"branch": ref.branch, "commit": ref.commit, "committed_at": ref.committed_at,
                  "started_at": stamp, "finished_at": stamp, "timed_out": False, "fault": None,
                  "validators": {}}
    data = {
        "bundle": ctx.bundle,
        "kind": ctx.kind,
        "participant": ctx.participant,
        "bundle_version": ctx.scheme.bundle_version,
        "cohort": cohort_name(ctx.repo),
        "repository": normalise_url(ctx.repo),
        "grading_hash": ctx.scheme.grading_hash,
        "scheme_digest": scheme_digest(graded),
        "warnings": warnings,
        "branch": record,
    }
    path = ctx.store / RUN_FILE
    write_json_private(path, data)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(f"{ctx.participant} ({ref.branch}, {ref.commit[:12]}): {what}")
    if not record["validators"]:
        print("  no gate validator: nothing ran; the trainer confirms that the work exists")
    for name, result in record["validators"].items():
        word = "pass" if result["passed"] else f"FAIL: {short(result['reason'])}"
        print(f"  {name}{' (gate)' if result['gate'] else ''}  {word}")
    print(f"results: {path}")
    if suspect:
        print("error: a result above may not be a judgement of the code; it records no result and uses "
              "no attempt. Repair the fault and run again", file=sys.stderr)
        return EXIT_REFUSED
    return EXIT_OK


def cmd_makeup_propose(args: argparse.Namespace) -> int:
    ctx = makeup_context(args)
    path = ctx.store / RUN_FILE
    if not path.is_file():
        raise GradeError(f"there are no run results for {ctx.participant}'s further attempt; run "
                         "`belay-grade makeup run` first")
    run = read_json_file(path, "the run results", JUDGEMENT_MAX_BYTES * 8)
    rec = run.get("branch") if isinstance(run, dict) else None
    if not isinstance(rec, dict) or not isinstance(rec.get("validators"), dict) \
            or not isinstance(rec.get("commit"), str):
        raise GradeError(f"{path} is damaged; run `belay-grade makeup run` again")
    if run.get("bundle") != ctx.bundle or run.get("participant") != ctx.participant:
        raise GradeError(f"{path} is not for {ctx.participant}'s further attempt at {ctx.bundle}")
    if run.get("scheme_digest") != scheme_digest(ctx.graded):
        raise GradeError("the grading scheme changed since the run, so the validator results are not "
                         "for it; run `belay-grade makeup run` again")
    if any(v.name not in rec["validators"] for v in ctx.graded.validators):
        raise GradeError(f"{path} holds no complete validator results; run `belay-grade makeup run` again")
    if isinstance(rec.get("fault"), str):
        raise GradeError(f"the further attempt could not be graded, and no proposal was written: "
                         f"{short(rec['fault'])}. A runtime fault is not the participant's result and "
                         "uses no attempt; repair it and run again")
    admit_attempt(ctx, rec["commit"])
    ratings, draft = read_judgement(Path(args.judgement), ctx.graded, [ctx.participant])
    if draft is not None:
        raise GradeError("the judgement has a `draft`, and a further attempt has no comparison and no "
                         "shared review; remove it. No proposal was written")
    validators = proposed_validators(rec, ctx.graded)
    criteria = proposed_criteria(ratings[ctx.participant], ctx.graded)
    vpts = sum(v["points"] for v in validators.values())
    rpts = sum(c["points"] for c in criteria.values())
    proposal = {
        "bundle": ctx.bundle,
        "kind": ctx.kind,
        "participant": ctx.participant,
        "branch": rec.get("branch"),
        "commit": rec["commit"],
        "bundle_version": ctx.scheme.bundle_version,
        "grading_hash": ctx.scheme.grading_hash,
        "cohort": cohort_name(ctx.repo),
        "repository": normalise_url(ctx.repo),
        "proposed_at": now_iso(),
        "validators": validators,
        "criteria": criteria,
        "gate": gate_result(validators, criteria),
        "total": vpts + rpts,
        "max_total": ctx.graded.max_total,
        "warnings": run.get("warnings") if isinstance(run.get("warnings"), list) else [],
    }
    out = ctx.store / PROPOSAL_FILE
    write_json_private(out, proposal)
    print(_makeup_line(ctx, proposal["gate"], proposal["total"], proposal["max_total"]))
    print(f"proposal: {out}")
    return EXIT_OK


def _makeup_line(ctx: Makeup, gate: bool | None, total: int, max_total: int) -> str:
    word = {True: "passed", False: "NOT met yet", None: "n/a (no gate: the work exists)"}[gate]
    line = f"{ctx.participant}: further attempt at {ctx.bundle}, gate {word}"
    if ctx.kind == "final_project":
        line += f", total {total}/{max_total} (share {ctx.share}%)"
    return line


def check_makeup_proposal(proposal: Any, ctx: Makeup) -> None:
    def damaged(why: str) -> GradeError:
        return GradeError(f"the further attempt's proposal.json is damaged ({why}); run "
                          "`belay-grade makeup propose` again")

    if not isinstance(proposal, dict):
        raise damaged("it is not an object")
    for key in ("bundle", "participant", "commit", "grading_hash", "validators", "criteria", "max_total"):
        if key not in proposal:
            raise damaged(f"no `{key}`")
    if proposal["bundle"] != ctx.bundle or proposal["participant"] != ctx.participant:
        raise damaged(f"it is not for {ctx.participant}'s further attempt at {ctx.bundle}")
    if not isinstance(proposal["commit"], str) or not isinstance(proposal["validators"], dict) \
            or not isinstance(proposal["criteria"], dict):
        raise damaged("an entry is of the wrong type")
    for name, v in proposal["validators"].items():
        if not (isinstance(v, dict) and {"passed", "points", "gate"} <= set(v)):
            raise damaged(f"validator {escape_name(str(name))} is incomplete")
    for cid, c in proposal["criteria"].items():
        if not (isinstance(c, dict) and {"points", "max", "evidence", "gate"} <= set(c)
                and _is_points(c["points"]) and _is_points(c["max"])):
            raise damaged(f"criterion {escape_name(str(cid))} is incomplete")


def parse_makeup_change(participant: str, text: str) -> tuple[str, int, str]:
    """<criterion>=<points>:<reason>, read by parse_change with the participant put in front."""
    try:
        _who, cid, pts, reason = parse_change(f"{participant}:{text}")
    except GradeError as exc:
        if "has no reason" in str(exc):
            raise
        raise GradeError(f"--change {escape_name(text)!r} is not <criterion>=<points>:<reason>") from exc
    return cid, pts, reason


def cmd_makeup_confirm(args: argparse.Namespace) -> int:
    ctx = makeup_context(args)
    by = args.by.strip()
    if not by or len(by) > 200 or not by.isprintable():
        raise GradeError("--by must name who confirms: one line of printable text")
    path = ctx.store / PROPOSAL_FILE
    if not path.is_file():
        raise GradeError(f"there is no proposal for {ctx.participant}'s further attempt; run "
                         "`belay-grade makeup propose` first")
    proposal = read_json_file(path, "the proposal", JUDGEMENT_MAX_BYTES * 8)
    check_makeup_proposal(proposal, ctx)
    stale = []
    if proposal["grading_hash"] != ctx.scheme.grading_hash:
        stale.append("the bundle's `grading` block differs from the one the proposal was made under")
    ref = makeup_branch(ctx)
    if ref.commit != proposal["commit"]:
        stale.append(f"{ref.branch} moved: {proposal['commit'][:12]} -> {ref.commit[:12]}")
    if stale:
        raise GradeError("the proposal is stale, and nothing was confirmed (confirm reads the local cache "
                         "and does not fetch; run collect, then makeup run and propose again):\n  "
                         + "\n  ".join(stale))
    what = admit_attempt(ctx, proposal["commit"])
    applied: dict[tuple[str, str], tuple[int, str]] = {}
    for text in args.change or []:
        cid, pts, reason = parse_makeup_change(ctx.participant, text)
        check_change(ctx.participant, cid, pts, proposal, applied)
        applied[(ctx.participant, cid)] = (pts, reason)
    validators, criteria, gate, total = confirmed_entry(
        proposal, {cid: change for (_w, cid), change in applied.items()})
    final: dict[str, Any] = {
        "bundle": ctx.bundle,
        "kind": ctx.kind,
        "participant": ctx.participant,
        "commit": proposal["commit"],
        "gate": gate,
        "validators": validators,
        "criteria": criteria,
    }
    if ctx.kind == "final_project":
        final["total"] = total
        final["max_total"] = proposal["max_total"]
    final.update({
        "grading_hash": proposal["grading_hash"],
        "bundle_version": ctx.scheme.bundle_version,
        "confirmed_by": by,
        "confirmed_at": now_iso(),
    })
    refuse_work_tree(ctx.store)
    kept = archive_previous(ctx.store)
    out = ctx.store / FINAL_FILE
    write_json_private(out, final)
    used = attempts_used(ctx.store)
    print(f"confirmed by {by}; {len(applied)} change(s); {what}")
    for (_w, cid), (pts, reason) in applied.items():
        print(f"  changed {cid} {proposal['criteria'][cid]['points']} -> {pts}: {escape_name(reason)}")
    print(_makeup_line(ctx, gate, total, proposal["max_total"]))
    print(f"further attempts used: {len(used)} of {ctx.scheme.retries}")
    if kept:
        print(f"previous confirmation kept: {kept}")
    print(f"final: {out}")
    return EXIT_OK


MAKEUP_STEPS: dict[str, tuple[Callable[[argparse.Namespace], int], str]] = {
    "run": (cmd_makeup_run, "run what a further attempt is graded on, on <participant>/<bundle-id>-makeup"),
    "propose": (cmd_makeup_propose, "merge the run with the tutor's judgement into the attempt's proposal.json"),
    "confirm": (cmd_makeup_confirm, "write the attempt's final.json; the bundle's own final.json is left alone"),
}


def _add_makeup_args(parser: argparse.ArgumentParser) -> None:
    steps = parser.add_subparsers(dest="step", required=True)
    for name, (func, text) in MAKEUP_STEPS.items():
        p = steps.add_parser(name, help=text, description=text)
        p.add_argument("repo", help="the cohort repository's URL")
        p.add_argument("bundle_id", metavar="bundle-id", help="the module's or final project's id")
        p.add_argument("participant", help="the participant, as in their branch name")
        p.add_argument("--bundle", required=True, help="the bundle's directory")
        p.add_argument("--catalog", required=True, help="the programme's catalog.yaml, with `certificate`")
        if name == "propose":
            p.add_argument("--judgement", required=True, help="the tutor's judgement, a JSON file")
        if name == "confirm":
            p.add_argument("--by", required=True, help="who confirms")
            p.add_argument("--change", action="append", metavar="criterion=points:reason",
                           help="change a criterion's points, with a reason; repeat for more")
        p.set_defaults(makeup_func=func)


def cmd_makeup(args: argparse.Namespace) -> int:
    return args.makeup_func(args)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _add_propose_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle", required=True, help="the module's bundle directory")
    parser.add_argument("--judgement", required=True, help="the tutor's judgement, a JSON file")
    _add_collect_args(parser)


def _add_confirm_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bundle", required=True, help="the module's bundle directory")
    parser.add_argument("--by", required=True, help="who confirms")
    parser.add_argument("--exclude", action="append", metavar="participant",
                        help="leave out a participant who could not be graded because of a runtime "
                             "fault, or whose branch the proposal does not cover; repeat for more")
    parser.add_argument("--change", action="append", metavar="participant:criterion=points:reason",
                        help="change a criterion's points, with a reason; repeat for more")
    _add_collect_args(parser)


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


# name -> (function, help, argument-adder).
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
    "propose": (
        cmd_propose,
        "merge the validator results with the tutor's judgement into proposal.json",
        _add_propose_args,
    ),
    "confirm": (
        cmd_confirm,
        "write final.json from the proposal, with the trainer's changes and reasons",
        _add_confirm_args,
    ),
    "makeup": (
        cmd_makeup,
        "grade a further attempt at a module or final project: run, propose or confirm",
        _add_makeup_args,
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
    # A stream that is not UTF-8 must not stop a run over a character in a bundle's name.
    if hasattr(sys.stdout, "reconfigure"):
        # Line by line even into a file or a pipe, because a run takes hours and whoever
        # started it in the background reads this to follow it.
        sys.stdout.reconfigure(errors="backslashreplace", line_buffering=True)
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
