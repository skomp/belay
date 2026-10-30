#!/usr/bin/env python3
"""Fetch, cache and merge the learner's tutorial catalogues.

RUNTIME script. Unlike validate_bundle.py, this one runs on a learner's
machine, so it uses the standard library and the `git` binary and nothing
else. No third-party packages, no network client of its own, no credential
handling: `git` borrows whatever access the user already granted it.

Usage:
    catalogs.py discover            refresh every catalogue, print the merged
                                    catalogue and the per-catalogue status
    catalogs.py status              print the per-catalogue status from what
                                    is already on disk; fetch nothing
    catalogs.py resolve <id>        print one merged entry and the bundle
                                    directory it resolves to; fetch nothing
    catalogs.py materialize <id>    create tutorial/ in the current directory
                                    from that bundle, and stamp it; fetch
                                    nothing
    catalogs.py place-supplies      place tutorial/tutorial.yaml's supplies
                                    from the source its stamp names; never
                                    overwrite; fetch nothing
    catalogs.py report [--runner] [--context]
                                    print a link that sends the defect
                                    report drafted in tutorial/REPORT.md to
                                    the course author, or with --runner to
                                    the runner; send nothing, fetch nothing
    catalogs.py covers <query>      print the bundles that TEACH a concept
    catalogs.py follow-ups <id>     print what could be taken after a bundle
    catalogs.py prepare <id>        print what covers the concepts a bundle
                                    assumes

The last three fetch nothing either, unless given --refresh.

Options:
    --config PATH       the catalogue of catalogues
                        (default ~/.config/belay/catalogs.yaml)
    --cache-dir PATH    (default ~/.cache/belay)
    --timeout SECONDS   per git command (default 30)
    --offline           discover without fetching; serve what is on disk
    --json              machine-readable output instead of the report

Exit codes:
    0  every configured catalogue answered
    1  at least one catalogue was served from cache or could not be served,
       and at least one entry is available
    2  usage, or the catalogue of catalogues is unusable
    3  no entry could be served at all

`materialize` and `place-supplies` have their own, in the same shape:
    0  done
    1  place-supplies only: some targets could not be created, because a
       file of the learner's is in the way; the report names each one
    2  usage or I/O error, or the configuration is unusable
    3  refused - the report says why, and nothing was written
`report` has its own as well:
    0  a link was printed
    1  there is no target: the draft is the learner's to send by hand
    2  usage, or the instance or the draft is unusable
`materialize` refuses when tutorial/ already exists, when no catalogue
supplies the id, and when the bundle is not usable. `place-supplies`
refuses when the stamp is missing or names no readable local source, and
when an entry is malformed or reaches outside the bundle or the workspace.
Neither is ever given a bundle path (belay#76): a path outside the
workspace on the command line is what makes the host ask the learner.

Three rules this script exists to keep:

  * **Discovery loads metadata only.** Nothing here opens, stats or lists
    anything under a tutorial's bundle path. `discover` cannot tell whether a
    bundle is present, and must not: that is what keeps a remote catalogue
    possible. Only `resolve`, which runs after the learner has chosen, looks
    at a bundle directory.

  * **A failed refresh never fails discovery.** The catalogues that answered
    are served, the one that did not is named, and its last successful copy
    is used and marked as cached. Stale results are never presented as
    current: every catalogue is reported with the timestamp of its last
    successful refresh.

  * **Covering is not assuming.** `covers` says what a bundle teaches;
    `assumes` says what it expects you to bring. A concept query reads
    `covers` and never `assumes`, because a bundle that assumes a concept
    starts where a learner asking about it is stuck. Every result carries
    the route it arrived by, and an inferred relation is never shown as
    something an author recommended.

  * **Failures are not collapsed.** "The host is unreachable", "you have no
    access to this repository" and "this repository has no catalogue file"
    have three different repairs. A git failure this script cannot recognise
    is reported as unclassified with git's own words, never guessed into one
    of the three.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from yamlite import YAML_READER, YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from yamlite import YAML_READER, YamlError, load_yaml

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
BUNDLED_CATALOG = SKILL_DIR / "catalog" / "builtin.yaml"

DEFAULT_CONFIG = "~/.config/belay/catalogs.yaml"
DEFAULT_CACHE_DIR = "~/.cache/belay"
DEFAULT_TIMEOUT = 30

KNOWN_CONFIG_VERSIONS = (1,)
KNOWN_CATALOG_VERSIONS = (1,)

CATALOG_SOURCE_TYPES = ("bundled", "file", "git")
CATALOG_SOURCE_REQUIRED = {
    "bundled": (),
    "file": ("path",),
    "git": ("url",),
}

# A tutorial entry's `source` says where the BUNDLE is. A catalogue entry's
# `source` says where the CATALOGUE is. They are different fields with
# different vocabularies, and conflating them is the mistake this comment
# exists to prevent. `git` and `archive` remain declared-but-unimplemented at
# the tutorial level: a git CATALOGUE brings its bundles with it by relative
# path, which is how a bundles repository is installed with one entry.
TUTORIAL_SOURCE_TYPES = ("local", "git", "archive")
TUTORIAL_SOURCE_IMPLEMENTED = ("local",)

ENTRY_REQUIRED_FIELDS = (
    "id",
    "title",
    "description",
    "subjects",
    "level",
    "workspace_kind",
    "source",
)

# Optional, and a COUNT rather than a list. It is deliberately not called
# `optional_lessons`: that name is already taken in a bundle's tutorial.yaml,
# where it is a mapping of lesson path to offer metadata. One name for two
# shapes in two files is the confusion this project keeps paying for.
OPTIONAL_LESSON_COUNT = "optional_lesson_count"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

# --------------------------------------------------------------------------
# Failure kinds
# --------------------------------------------------------------------------
#
# Every kind is a DIFFERENT REPAIR. That is the test for whether a kind earns
# its place: if two kinds would send the user to do the same thing, they are
# one kind. Collapsing them the other way - reporting every git failure as
# "could not fetch" - is the defect this table exists to prevent, because the
# learner is then told to check their network when the real answer is that
# they have no access, or that the file is simply not at that path.

FAILURE_KINDS: dict[str, tuple[str, str]] = {
    "unreachable": (
        "the host could not be reached",
        "check the network connection, and that the host name is spelt "
        "correctly, then run discover again",
    ),
    "no-access": (
        "you have no access to this repository, or it does not exist",
        "check that the repository name is right and that your git "
        "credentials reach it - the same SSH key or helper you use for "
        "`git clone` by hand. This script never prompts for credentials and "
        "never stores any",
    ),
    "no-ref": (
        "the repository has no such branch or tag",
        "correct the 'ref' field, or remove it to take the default branch",
    ),
    "no-catalogue": (
        "the repository has no catalogue file at that path",
        "correct the 'path' field to name the catalogue file inside the "
        "repository",
    ),
    "missing-file": (
        "the catalogue file is not there",
        "correct the 'path' field, or create the file",
    ),
    "unreadable": (
        "the catalogue file could not be read",
        "check the file's permissions and that it is UTF-8 text",
    ),
    "malformed": (
        "the catalogue file is not a usable catalogue",
        "correct the file, then check it with "
        "belay-validate --catalog <path>",
    ),
    "no-git": (
        "the git command is not installed",
        "install git, or remove the git catalogues from the configuration",
    ),
    "unclassified": (
        "git failed for a reason this script does not recognise",
        "read git's own message below; it has not been interpreted",
    ),
}

# Classification patterns, in the order they are tried. ORDER IS LOAD-BEARING.
#
# An SSH timeout prints BOTH "Operation timed out" and "Could not read from
# remote repository." - the second of which is also what a refused key
# prints. Testing the access patterns first would report every unreachable
# host as an access problem, which is the exact "distinguish refused from
# failed earlier" failure. So the transport patterns are tried first.

_UNREACHABLE_PATTERNS = (
    "could not resolve host",
    "could not resolve hostname",
    "name or service not known",
    "nodename nor servname provided",
    "temporary failure in name resolution",
    "no address associated with hostname",
    "connection timed out",
    "operation timed out",
    "timed out",
    "connection refused",
    "connection reset by peer",
    "network is unreachable",
    "no route to host",
    "failed to connect to",
    "unable to look up",
    "server certificate verification failed",
)

_NO_REF_PATTERNS = (
    "not found in upstream origin",
    "couldn't find remote ref",
    "could not find remote ref",
    "unknown revision or path not in the working tree",
    "did not match any file(s) known to git",
)

_NO_ACCESS_PATTERNS = (
    "permission denied",
    "publickey",
    "authentication failed",
    "repository not found",
    "access denied",
    "requested url returned error: 401",
    "requested url returned error: 403",
    "the requested url returned error: 401",
    "the requested url returned error: 403",
    "please make sure you have the correct access rights",
    "terminal prompts disabled",
    "could not read from remote repository",
    "invalid username or password",
    "you do not have permission",
)


def classify_git_error(stderr: str, stdout: str = "") -> str:
    """Map git's own words onto one of the failure kinds.

    Pure, so the classifier can be exercised directly against the messages
    real git prints. It returns "unclassified" rather than guessing, and the
    caller then reports git's message verbatim.
    """
    text = f"{stderr}\n{stdout}".lower()
    for pattern in _UNREACHABLE_PATTERNS:
        if pattern in text:
            return "unreachable"
    for pattern in _NO_REF_PATTERNS:
        if pattern in text:
            return "no-ref"
    for pattern in _NO_ACCESS_PATTERNS:
        if pattern in text:
            return "no-access"
    return "unclassified"


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------


class ConfigError(Exception):
    """The catalogue of catalogues cannot be used at all."""


@dataclass(frozen=True)
class Failure:
    kind: str
    detail: str

    @property
    def summary(self) -> str:
        return FAILURE_KINDS[self.kind][0]

    @property
    def repair(self) -> str:
        return FAILURE_KINDS[self.kind][1]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "detail": self.detail,
            "repair": self.repair,
        }


@dataclass(frozen=True)
class Source:
    type: str
    path: str | None = None
    url: str | None = None
    ref: str | None = None

    def fingerprint(self) -> str:
        return "\x00".join(
            [self.type, self.url or "", self.ref or "", self.path or ""]
        )

    def describe(self) -> str:
        if self.type == "bundled":
            return "bundled with the plugin"
        if self.type == "file":
            return str(self.path)
        ref = f"@{self.ref}" if self.ref else "@(default branch)"
        return f"{self.url}{ref}#{self.path or 'catalog.yaml'}"

    def as_dict(self) -> dict:
        out: dict[str, Any] = {"type": self.type}
        for name in ("url", "ref", "path"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        return out


@dataclass(frozen=True)
class CatalogSpec:
    id: str
    source: Source


@dataclass
class CatalogResult:
    spec: CatalogSpec
    state: str = "unavailable"  # current | cached | unavailable
    refreshed_now: bool = False
    entries: list[dict] = field(default_factory=list)
    root: Path | None = None
    fetched_at: str | None = None
    commit: str | None = None
    failure: Failure | None = None
    skipped: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.spec.id,
            "source": self.spec.source.as_dict(),
            "origin": self.spec.source.describe(),
            "state": self.state,
            "refreshed_now": self.refreshed_now,
            "entry_count": len(self.entries),
            "root": str(self.root) if self.root else None,
            "fetched_at": self.fetched_at,
            "commit": self.commit,
            "failure": self.failure.as_dict() if self.failure else None,
            "skipped": [{"where": w, "reason": r} for w, r in self.skipped],
        }


@dataclass
class MergedEntry:
    entry: dict
    catalog_id: str
    freshness: str  # current | cached
    resolved_path: str
    origin: str
    shadowed: list[tuple[str, str]] = field(default_factory=list)
    # The winning catalogue's own source, for `report`: a Git catalogue's
    # repository is where a course defect goes when nothing nearer says.
    # Not in as_dict(), so --json output is unchanged by it.
    catalog_source: Source | None = None

    @property
    def id(self) -> str:
        return str(self.entry["id"])

    def as_dict(self) -> dict:
        out = dict(self.entry)
        # Normalised, not passed through. A malformed optional_lesson_count
        # becomes null with a note beside it, so a consumer of --json can
        # never read an unusable value as a count. The key is always present
        # for the same reason: null says "this entry does not say", which is
        # a different fact from zero.
        count, notes = read_optional_lesson_count(self.entry, self.id)
        out[OPTIONAL_LESSON_COUNT] = count
        out["metadata_notes"] = notes
        out["catalog"] = self.catalog_id
        out["freshness"] = self.freshness
        out["resolved_path"] = self.resolved_path
        out["origin"] = self.origin
        out["shadows"] = [
            {"catalog": cid, "origin": origin} for cid, origin in self.shadowed
        ]
        return out


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def describe_age(stamp: str | None) -> str:
    moment = parse_stamp(stamp)
    if moment is None:
        return "never"
    seconds = int((datetime.now(timezone.utc) - moment).total_seconds())
    if seconds < 0:
        return "in the future - the clock moved"
    if seconds < 90:
        return f"{seconds} seconds ago"
    minutes = seconds // 60
    if minutes < 90:
        return f"{minutes} minutes ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} hours ago"
    return f"{hours // 24} days ago"


def expand(path: str) -> Path:
    return Path(os.path.expanduser(str(path)))


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def escapes(root: Path, relative: str) -> bool:
    """True when `relative` leaves `root`, on the strings alone.

    No filesystem call, because this runs during discovery, which must not
    touch anything under a bundle path. `os.path.normpath` collapses the
    '..' segments textually, which is what the check needs. Symlinks are
    deliberately not resolved, for the same reason.

    `root` is an anchor with no parent. A bundle path may descend into it,
    and may leave a directory and return inside it, but it may not step out
    of it - not even when the filesystem would clamp the step, which is why
    the answer cannot depend on where the root is. The parameter stays
    because it names what the path is measured against, and because
    `validate_bundle` check 7 and the discovery guard below both read
    better for passing it.

    Earlier versions compared strings: `normpath(join(root, relative))`
    against `str(root)`, and against `str(root) + os.sep`. That is the
    right question only for a root with at least one component and no
    trailing separator, and it failed in BOTH directions for the rest:

      * `Path(".")` - `normpath("./bundle")` is `"bundle"`, which shares no
        prefix with `"."`, so every contained path read as an escape.
        Issue #14, worked around on the validator's side by anchoring the
        root with `os.path.abspath` in `validate_bundle.catalog_root()`.
      * `Path("/")` - `str(root) + os.sep` is `"//"`, and no normalised
        path starts with that, so again every contained path read as an
        escape. Issue #16.
      * `Path("..")` - the dangerous direction. `normpath("../../outside")`
        does start with `"../"`, so a path that really does leave read as
        contained.

    `normpath` leaves every surviving '..' at the front of the path, with
    nothing left in front of it to cancel it. So one '..' component in the
    normalised form is exactly the escape, for every root, with no string
    prefix left to get wrong.
    """
    if os.path.isabs(relative) or relative.startswith("~"):
        return True
    return os.pardir in os.path.normpath(relative).split(os.sep)


# --------------------------------------------------------------------------
# The catalogue of catalogues
# --------------------------------------------------------------------------


def read_source(raw: Any, where: str) -> Source:
    if not isinstance(raw, dict):
        raise ConfigError(f"{where}: 'source' must be a mapping")
    kind = raw.get("type")
    if kind is None:
        raise ConfigError(f"{where}: 'source' has no 'type'")
    kind = str(kind)
    if kind not in CATALOG_SOURCE_TYPES:
        raise ConfigError(
            f"{where}: source type {kind!r} is not one of "
            f"{', '.join(CATALOG_SOURCE_TYPES)}"
        )
    for required in CATALOG_SOURCE_REQUIRED[kind]:
        if not raw.get(required):
            raise ConfigError(
                f"{where}: a {kind} source requires the field {required!r}"
            )
    unknown = sorted(set(raw) - {"type", "path", "url", "ref"})
    if unknown:
        raise ConfigError(
            f"{where}: source has unknown field(s) {', '.join(unknown)}"
        )
    if kind == "bundled" and (raw.get("path") or raw.get("url")):
        raise ConfigError(
            f"{where}: a bundled source takes no 'path' and no 'url'; it is "
            f"the catalogue that ships with the plugin"
        )
    if kind == "git":
        path = str(raw.get("path") or "catalog.yaml")
        if os.path.isabs(path) or path.startswith("~") or escapes(Path("/r"), path):
            raise ConfigError(
                f"{where}: the git source path {path!r} must stay inside the "
                f"repository; it must be relative and must not contain '..'"
            )
        return Source(type=kind, url=str(raw["url"]), ref=_opt(raw.get("ref")), path=path)
    if kind == "file":
        return Source(type=kind, path=str(raw["path"]))
    return Source(type=kind)


def _opt(value: Any) -> str | None:
    return None if value is None else str(value)


def implied_default(config_path: Path) -> tuple[list[CatalogSpec], str]:
    """What to do when there is no catalogs.yaml.

    The old two-file model is exactly this list, so an existing
    ~/.config/belay/catalog.yaml keeps working with no migration. The user
    file comes FIRST, so a user entry overrides a shipped one - which is the
    same precedence the two-file model had.

    A missing user catalogue is the normal state on a first run, so it is
    omitted rather than reported as a failure.
    """
    specs: list[CatalogSpec] = []
    # The user catalogue is a SIBLING of the catalogue of catalogues, so
    # --config stays self-consistent: pointing at another configuration
    # directory moves both files together.
    legacy = config_path.parent / "catalog.yaml"
    if legacy.is_file():
        specs.append(CatalogSpec("user", Source(type="file", path=str(legacy))))
    specs.append(CatalogSpec("builtin", Source(type="bundled")))
    note = (
        f"no {config_path} - using the implied default, which is the "
        f"two-file model this replaced"
    )
    return specs, note


def load_config(config_path: Path) -> tuple[list[CatalogSpec], str | None]:
    """Return the configured catalogues, and a note when one was implied."""
    if not config_path.exists():
        specs, note = implied_default(config_path)
        return specs, note
    raw_text = read_text(config_path)
    if raw_text is None:
        raise ConfigError(f"{config_path}: the file could not be read as UTF-8 text")
    try:
        document = load_yaml(raw_text, str(config_path))
    except YamlError as exc:
        raise ConfigError(f"{config_path}: the file does not parse: {exc}") from exc
    if not isinstance(document, dict):
        raise ConfigError(
            f"{config_path}: the file must hold a mapping with a 'catalogs' list"
        )
    version = document.get("catalogs_version", 1)
    if version not in KNOWN_CONFIG_VERSIONS:
        raise ConfigError(
            f"{config_path}: catalogs_version is {version!r}, which this "
            f"runner does not know. Known: "
            f"{', '.join(str(v) for v in KNOWN_CONFIG_VERSIONS)}"
        )
    listed = document.get("catalogs")
    if not isinstance(listed, list) or not listed:
        raise ConfigError(
            f"{config_path}: 'catalogs' must be a non-empty list of catalogues"
        )
    specs: list[CatalogSpec] = []
    seen: set[str] = set()
    for index, raw in enumerate(listed):
        where = f"{config_path}: catalogs[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{where}: each catalogue must be a mapping")
        identifier = raw.get("id")
        if identifier is None:
            raise ConfigError(f"{where}: the catalogue has no 'id'")
        identifier = str(identifier)
        # The id becomes a directory name under the cache, so it is checked
        # before it is ever joined onto a path.
        if not _SLUG_RE.match(identifier):
            raise ConfigError(
                f"{where}: the id {identifier!r} must match [a-z0-9-]+ and "
                f"start with a letter or a digit; it names a cache directory"
            )
        if identifier in seen:
            raise ConfigError(
                f"{where}: the id {identifier!r} is used more than once; "
                f"precedence is decided by order, so ids must be unique"
            )
        seen.add(identifier)
        if "source" not in raw:
            raise ConfigError(f"{where}: the catalogue has no 'source'")
        unknown = sorted(set(raw) - {"id", "source"})
        if unknown:
            raise ConfigError(
                f"{where}: unknown field(s) {', '.join(unknown)}; a catalogue "
                f"has an 'id' and a 'source'"
            )
        specs.append(CatalogSpec(identifier, read_source(raw["source"], where)))
    return specs, None


# --------------------------------------------------------------------------
# The cache
# --------------------------------------------------------------------------


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.catalogs = root / "catalogs"

    def dir_for(self, identifier: str) -> Path:
        return self.catalogs / identifier

    def meta_path(self, identifier: str) -> Path:
        return self.dir_for(identifier) / "meta.json"

    def document_path(self, identifier: str) -> Path:
        return self.dir_for(identifier) / "catalog.yaml"

    def clone_path(self, identifier: str) -> Path:
        return self.dir_for(identifier) / "repo"

    def read_meta(self, identifier: str) -> dict:
        text = read_text(self.meta_path(identifier))
        if text is None:
            return {}
        try:
            data = json.loads(text)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def write_meta(self, identifier: str, meta: dict) -> None:
        target = self.dir_for(identifier)
        target.mkdir(parents=True, exist_ok=True)
        self.meta_path(identifier).write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def store_document(self, identifier: str, text: str) -> None:
        target = self.dir_for(identifier)
        target.mkdir(parents=True, exist_ok=True)
        self.document_path(identifier).write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------


def git_env() -> dict[str, str]:
    """An environment that borrows the user's access and never prompts.

    GIT_TERMINAL_PROMPT and BatchMode turn a credential prompt into a fast,
    classifiable failure instead of a process that hangs waiting for a human
    who is not there. LC_ALL keeps git's messages in the language the
    classifier was written against.
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["LC_ALL"] = "C"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


@dataclass
class GitRun:
    ok: bool
    stdout: str
    stderr: str
    timed_out: bool = False


def run_git(args: list[str], timeout: int) -> GitRun:
    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            env=git_env(),
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GitRun(
            ok=False,
            stdout="",
            stderr=f"the git command did not finish within {timeout} seconds",
            timed_out=True,
        )
    except OSError as exc:  # pragma: no cover - git was checked for already
        return GitRun(ok=False, stdout="", stderr=str(exc))
    return GitRun(
        ok=completed.returncode == 0,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )


def git_failure(run: GitRun, what: str) -> Failure:
    if run.timed_out:
        return Failure("unreachable", f"{what}: {run.stderr}")
    kind = classify_git_error(run.stderr, run.stdout)
    detail = (run.stderr or run.stdout).strip() or "git failed and said nothing"
    return Failure(kind, f"{what}: {detail}")


def refresh_clone(
    spec: CatalogSpec, clone: Path, timeout: int
) -> tuple[bool, Failure | None]:
    """Bring the cached clone up to date, or create it.

    A FAILED update never destroys the clone. The clone is the only copy of
    the bundles a git catalogue carries, so wiping it on a transient failure
    would turn "cannot refresh" into "cannot teach".
    """
    ref = spec.source.ref
    if (clone / ".git").exists():
        fetch_args = ["-C", str(clone), "fetch", "--quiet", "--depth", "1", "origin"]
        fetch_args.append(ref if ref else "HEAD")
        run = run_git(fetch_args, timeout)
        if not run.ok:
            return False, git_failure(run, "git fetch")
        run = run_git(
            ["-C", str(clone), "checkout", "--quiet", "--force", "FETCH_HEAD"],
            timeout,
        )
        if not run.ok:
            return False, git_failure(run, "git checkout")
        return True, None

    # No usable clone. Anything already there is a half-written clone from an
    # interrupted run, not a fallback copy, so it is safe to remove.
    if clone.exists():
        shutil.rmtree(clone, ignore_errors=True)
    clone.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--quiet", "--depth", "1", "--single-branch"]
    if ref:
        args += ["--branch", ref]
    args += ["--", str(spec.source.url), str(clone)]
    run = run_git(args, timeout)
    if not run.ok:
        shutil.rmtree(clone, ignore_errors=True)
        return False, git_failure(run, "git clone")
    return True, None


def clone_commit(clone: Path, timeout: int) -> str | None:
    run = run_git(["-C", str(clone), "rev-parse", "--short", "HEAD"], timeout)
    return run.stdout.strip() if run.ok else None


# --------------------------------------------------------------------------
# Reading one catalogue document
# --------------------------------------------------------------------------


def parse_catalog(
    text: str, where: str, root: Path, portable: bool
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Parse a catalogue document into entries, skipping malformed ones.

    Raises YamlError or ConfigError when the DOCUMENT is unusable. An entry
    that is unusable is skipped with a reason, because one bad entry must not
    hide the rest of a catalogue.

    `portable` is true for a catalogue that was fetched from a repository. A
    bundle path there must stay inside the catalogue's own root, so a remote
    catalogue cannot point the runner at an arbitrary directory on the
    learner's machine.
    """
    document = load_yaml(text, where)
    if not isinstance(document, dict):
        raise ConfigError(
            f"{where}: a catalogue must be a mapping with a 'tutorials' list"
        )
    version = document.get("catalog_version")
    if version is None:
        raise ConfigError(f"{where}: 'catalog_version' is missing")
    if version not in KNOWN_CATALOG_VERSIONS:
        raise ConfigError(
            f"{where}: catalog_version is {version!r}, which this runner does "
            f"not know. Known: "
            f"{', '.join(str(v) for v in KNOWN_CATALOG_VERSIONS)}"
        )
    listed = document.get("tutorials")
    if listed is None:
        raise ConfigError(f"{where}: 'tutorials' is missing")
    if not isinstance(listed, list):
        raise ConfigError(f"{where}: 'tutorials' must be a list")

    entries: list[dict] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(listed):
        label = f"tutorials[{index}]"
        if not isinstance(raw, dict):
            skipped.append((label, "the entry is not a mapping"))
            continue
        identifier = raw.get("id")
        if identifier is not None:
            label = f"{label} ({identifier})"
        missing = [f for f in ENTRY_REQUIRED_FIELDS if raw.get(f) in (None, "", [])]
        if missing:
            skipped.append(
                (label, f"the required field(s) {', '.join(missing)} are missing")
            )
            continue
        identifier = str(identifier)
        if identifier in seen:
            skipped.append((label, f"the id {identifier!r} appears twice in this file"))
            continue
        source = raw.get("source")
        if not isinstance(source, dict):
            skipped.append((label, "'source' must be a mapping"))
            continue
        kind = str(source.get("type", ""))
        if kind not in TUTORIAL_SOURCE_TYPES:
            skipped.append(
                (
                    label,
                    f"source type {kind!r} is not one of "
                    f"{', '.join(TUTORIAL_SOURCE_TYPES)}",
                )
            )
            continue
        if kind not in TUTORIAL_SOURCE_IMPLEMENTED:
            skipped.append(
                (
                    label,
                    f"source type {kind!r} is declared but not implemented; a "
                    f"bundle in a repository is reached by adding that "
                    f"repository as a catalogue instead",
                )
            )
            continue
        path = source.get("path")
        if not path:
            skipped.append((label, "a local source requires the field 'path'"))
            continue
        path = str(path)
        if portable and escapes(root, path):
            skipped.append(
                (
                    label,
                    f"the bundle path {path!r} leaves the catalogue's own "
                    f"directory; a catalogue fetched from a repository may "
                    f"only name bundles inside it",
                )
            )
            continue
        seen.add(identifier)
        entries.append(dict(raw))
    return entries, skipped


def resolve_bundle_path(root: Path, path: str) -> str:
    candidate = expand(path)
    if candidate.is_absolute():
        return os.path.normpath(str(candidate))
    return os.path.normpath(str(root / candidate))


def read_optional_lesson_count(
    entry: dict, where: str
) -> tuple[int | None, list[str]]:
    """How many optional lessons the entry says the course carries.

    `scope` counts the main path only, so a course with eight main lessons
    and six optional ones reads exactly like a course with eight lessons and
    nothing else. This field is the difference, and it has to live in the
    ENTRY: section 1 forbids opening a bundle to count anything before the
    learner has chosen, and a remote catalogue's bundles may not be on this
    machine at all.

    Returns `(count, notes)`. The count is None when the entry does not say,
    and ALSO None - with a note - when it says something unusable. That is
    the tolerant half of the split in "The reader is tolerant; the validator
    is strict": optional metadata is optional, so a mistake in it drops the
    field and keeps the course discoverable. `validate_bundle.py --catalog`
    rejects the same value, because an author is asking to be told.

    `bool` is rejected even though it is an `int` in Python: `true` in YAML
    is an author writing something other than a count, and `1 optional
    lesson` is a worse answer than a note saying the field is unusable.
    """
    if OPTIONAL_LESSON_COUNT not in entry:
        return None, []
    value = entry[OPTIONAL_LESSON_COUNT]
    reason: str | None = None
    if isinstance(value, bool) or not isinstance(value, int):
        reason = f"is {value!r}, which is not a whole number"
    elif value < 0:
        reason = f"is {value!r}, and a count cannot be negative"
    if reason is not None:
        return None, [
            f"{where}: {OPTIONAL_LESSON_COUNT!r} {reason}. The course is "
            f"still offered, without it. Say that its optional lessons are "
            f"unknown rather than that it has none, and report the entry to "
            f"whoever can fix it"
        ]
    return int(value), []


# --------------------------------------------------------------------------
# Fetching one catalogue
# --------------------------------------------------------------------------


def serve_from_cache(
    spec: CatalogSpec, cache: Cache, failure: Failure, attempted: bool = True
) -> CatalogResult:
    """Fall back to the last successful copy, and say that it is cached.

    A failed refresh is REMEMBERED in the cache metadata. Without that, a
    later `status` or `resolve` - which fetch nothing - would read the last
    successful copy, see a success timestamp, and report the catalogue as
    current when the most recent attempt had in fact failed. That is exactly
    the "never present stale results as current" rule, and it is broken by
    omission rather than by a wrong message.
    """
    result = CatalogResult(spec=spec, failure=failure)
    meta = cache.read_meta(spec.id)
    if attempted and meta.get("fingerprint") == spec.source.fingerprint():
        meta = dict(meta)
        meta["stale"] = True
        meta["last_attempt_at"] = now_stamp()
        meta["last_attempt_kind"] = failure.kind
        cache.write_meta(spec.id, meta)
    if meta.get("fingerprint") != spec.source.fingerprint():
        if meta:
            result.failure = Failure(
                failure.kind,
                f"{failure.detail}\n"
                f"    the cached copy was fetched from a different source "
                f"({meta.get('origin', 'unknown')}), so it is not this "
                f"catalogue and was not used",
            )
        return result
    text = read_text(cache.document_path(spec.id))
    if text is None:
        return result
    root = Path(meta.get("root", "")) if meta.get("root") else None
    if root is None:
        return result
    try:
        entries, skipped = parse_catalog(
            text,
            f"cached copy of {spec.id}",
            root,
            portable=spec.source.type == "git",
        )
    except (YamlError, ConfigError):
        return result
    result.state = "cached"
    result.entries = entries
    result.skipped = skipped
    result.root = root
    result.fetched_at = meta.get("fetched_at")
    result.commit = meta.get("commit")
    return result


def record_success(
    spec: CatalogSpec,
    cache: Cache,
    text: str,
    root: Path,
    commit: str | None,
    entries: list[dict],
) -> str:
    stamp = now_stamp()
    if spec.source.type != "bundled":
        cache.store_document(spec.id, text)
        cache.write_meta(
            spec.id,
            {
                "id": spec.id,
                "fingerprint": spec.source.fingerprint(),
                "origin": spec.source.describe(),
                "root": str(root),
                "fetched_at": stamp,
                "commit": commit,
                "entry_count": len(entries),
                "stale": False,
                "last_attempt_at": stamp,
                "last_attempt_kind": None,
            },
        )
    return stamp


def load_one(
    spec: CatalogSpec, cache: Cache, fetch: bool, timeout: int
) -> CatalogResult:
    if spec.source.type == "bundled":
        return load_bundled(spec)
    if spec.source.type == "file":
        return load_file(spec, cache)
    return load_git(spec, cache, fetch, timeout)


def load_bundled(spec: CatalogSpec) -> CatalogResult:
    """The catalogue that ships with the plugin.

    It is never cached: it is part of the installation, so a missing or
    broken one is a packaging fault, and serving a cached copy over it would
    hide exactly that.
    """
    result = CatalogResult(spec=spec)
    path = BUNDLED_CATALOG
    if not path.is_file():
        result.failure = Failure(
            "missing-file",
            f"{path} is not there. The catalogue ships with the plugin, so "
            f"this is a packaging problem, not a configuration problem",
        )
        return result
    text = read_text(path)
    if text is None:
        result.failure = Failure("unreadable", f"{path} is not UTF-8 text")
        return result
    root = path.parent
    try:
        entries, skipped = parse_catalog(text, str(path), root, portable=False)
    except (YamlError, ConfigError) as exc:
        result.failure = Failure("malformed", str(exc))
        return result
    result.state = "current"
    result.refreshed_now = True
    result.entries = entries
    result.skipped = skipped
    result.root = root
    result.fetched_at = now_stamp()
    return result


def load_file(spec: CatalogSpec, cache: Cache) -> CatalogResult:
    assert spec.source.path is not None
    path = expand(spec.source.path)
    if not path.is_file():
        return serve_from_cache(
            spec,
            cache,
            Failure("missing-file", f"{path} is not a file"),
        )
    text = read_text(path)
    if text is None:
        return serve_from_cache(
            spec, cache, Failure("unreadable", f"{path} is not UTF-8 text")
        )
    root = path.parent
    try:
        entries, skipped = parse_catalog(text, str(path), root, portable=False)
    except (YamlError, ConfigError) as exc:
        return serve_from_cache(spec, cache, Failure("malformed", str(exc)))
    result = CatalogResult(spec=spec, state="current", refreshed_now=True)
    result.entries = entries
    result.skipped = skipped
    result.root = root
    result.fetched_at = record_success(spec, cache, text, root, None, entries)
    return result


def load_git(
    spec: CatalogSpec, cache: Cache, fetch: bool, timeout: int
) -> CatalogResult:
    clone = cache.clone_path(spec.id)
    if fetch:
        if shutil.which("git") is None:
            return serve_from_cache(
                spec,
                cache,
                Failure("no-git", "`git` was not found on the PATH"),
            )
        meta = cache.read_meta(spec.id)
        if meta and meta.get("fingerprint") != spec.source.fingerprint():
            # The configured source changed under this id. The old clone
            # answers to a different url or ref, so it is not a fallback for
            # this catalogue and must not be fetched into.
            shutil.rmtree(clone, ignore_errors=True)
        ok, failure = refresh_clone(spec, clone, timeout)
        if not ok:
            assert failure is not None
            return serve_from_cache(spec, cache, failure)

    if not (clone / ".git").exists():
        return serve_from_cache(
            spec,
            cache,
            Failure(
                "missing-file",
                f"there is no clone at {clone} and this run did not fetch",
            ),
            attempted=fetch,
        )

    relative = spec.source.path or "catalog.yaml"
    document = clone / relative
    if not document.is_file():
        listing = sorted(p.name for p in clone.iterdir() if p.name != ".git")[:20]
        return serve_from_cache(
            spec,
            cache,
            Failure(
                "no-catalogue",
                f"the repository was fetched, but it holds no file at "
                f"{relative!r}. Its top level holds: "
                f"{', '.join(listing) if listing else '(nothing)'}",
            ),
        )
    text = read_text(document)
    if text is None:
        return serve_from_cache(
            spec, cache, Failure("unreadable", f"{relative} is not UTF-8 text")
        )
    root = document.parent
    try:
        entries, skipped = parse_catalog(
            text, f"{spec.id}:{relative}", root, portable=True
        )
    except (YamlError, ConfigError) as exc:
        return serve_from_cache(spec, cache, Failure("malformed", str(exc)))

    commit = clone_commit(clone, timeout)
    result = CatalogResult(spec=spec, state="current", refreshed_now=fetch)
    result.entries = entries
    result.skipped = skipped
    result.root = root
    result.commit = commit
    if fetch:
        result.fetched_at = record_success(spec, cache, text, root, commit, entries)
    else:
        meta = cache.read_meta(spec.id)
        result.fetched_at = meta.get("fetched_at")
        result.state = (
            "current"
            if result.fetched_at and not meta.get("stale")
            else "cached"
        )
        if meta.get("stale"):
            kind = str(meta.get("last_attempt_kind") or "unclassified")
            result.failure = Failure(
                kind if kind in FAILURE_KINDS else "unclassified",
                f"the last refresh, at {meta.get('last_attempt_at')}, failed; "
                f"this run fetched nothing, so the clone is whatever that "
                f"failure left behind",
            )
    return result


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------


def merge(results: list[CatalogResult]) -> tuple[list[MergedEntry], list[dict]]:
    """First match wins, by tutorial id, in configuration order.

    A shadowed entry is never dropped silently: the winner records which
    catalogues also carry that id, so the runner can say which catalogue
    supplied the tutorial it is about to offer.
    """
    merged: dict[str, MergedEntry] = {}
    order: list[str] = []
    shadowed: list[dict] = []
    for result in results:
        if result.state == "unavailable":
            continue
        assert result.root is not None
        for entry in result.entries:
            identifier = str(entry["id"])
            path = str(entry["source"]["path"])
            resolved = resolve_bundle_path(result.root, path)
            if identifier in merged:
                winner = merged[identifier]
                winner.shadowed.append((result.spec.id, result.spec.source.describe()))
                shadowed.append(
                    {
                        "id": identifier,
                        "catalog": result.spec.id,
                        "origin": result.spec.source.describe(),
                        "resolved_path": resolved,
                        "title": entry.get("title"),
                        "shadowed_by": winner.catalog_id,
                        "winning_path": winner.resolved_path,
                    }
                )
                continue
            merged[identifier] = MergedEntry(
                entry=entry,
                catalog_id=result.spec.id,
                freshness="current" if result.state == "current" else "cached",
                resolved_path=resolved,
                origin=result.spec.source.describe(),
                catalog_source=result.spec.source,
            )
            order.append(identifier)
    return [merged[i] for i in order], shadowed


# --------------------------------------------------------------------------
# Relationships: concepts, recommendations, and the reverse index
# --------------------------------------------------------------------------
#
# Four optional catalogue fields carry this: `covers`, `assumes`,
# `recommended_follow_ups` and `recommended_previous_bundles`. They are
# entry-level metadata for the same reason `subjects` is: discovery loads
# metadata only, and a bundle's own tutorial.yaml may not even be on this
# machine yet.
#
# Three rules this section exists to keep, each of which is easy to break by
# accident and impossible to notice afterwards:
#
#   * **A query for bundles COVERING a concept searches `covers`, never
#     `assumes`.** A bundle that assumes retained-event-logs does not teach
#     it, and returning it as though it did sends a learner to a course that
#     starts where they are stuck.
#
#   * **Provenance is kept, never flattened.** Every result says which route
#     it arrived by, and a bundle that arrives by several routes keeps all of
#     them. An inferred relation is NEVER presented as an author
#     recommendation; the two are rendered in separate sections and carry a
#     separate flag in the JSON.
#
#   * **The reverse index is the point.** A third party publishes a follow-up
#     to someone else's bundle by naming it in
#     `recommended_previous_bundles`, without touching the original. So
#     follow-up discovery reads that field BACKWARDS, across every configured
#     catalogue, and the original author never has to know.
#
# No semantic-search service is required, or used. The ranking ladder in the
# design ends with an optional semantic tier "only if the architecture
# already has it"; this architecture does not have one, so that tier is never
# produced. Everything below is exact string work on normalised text, which
# means the same catalogues always give the same answer.
SEMANTIC_MATCHING_AVAILABLE = False

CONCEPT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ASSUMES_LEVELS = ("awareness", "conceptual", "working", "advanced")

# Every provenance kind, with the rank it carries inside the query that
# produces it, and whether it is an AUTHOR RECOMMENDATION - a human wrote
# this bundle down - or an inference this script made.
#
# The rank is meaningful within one query type. A concept query ranks
# 1 exact concept id, 2 exact per-concept alias, 3 normalised text,
# 4 a recommended previous bundle THAT COVERS THE CONCEPT, 5 broad subject;
# that is the design's ladder, and tier 6, semantic, is never produced. A
# relationship query ranks the author's own list first, the reverse-declared
# list second and the inferred relatives third.
#
# `recommendation` is load-bearing and not cosmetic: it is what keeps a broad
# subject match from being shown as something an author recommended.
PROVENANCE_KINDS: dict[str, tuple[int, bool, str]] = {
    # concept queries
    "exact-concept": (1, False, "the query is a concept id the bundle covers"),
    "concept-alias": (2, False, "the query is an alias of a concept it covers"),
    "concept-text": (3, False, "the query's words appear in a covered concept"),
    # Rank 4 is a JOIN of two independent declarations: this bundle's own
    # `covers`, and another author's `recommended_previous_bundles`. Neither
    # author wrote the conjunction, and the author who wrote the
    # recommendation recommended a course ORDER, not a teacher of this
    # concept - so inside a concept query this route is an inference and is
    # flagged as one. The same author's sentence IS an author recommendation
    # in `prepare` and `follow-ups`, where it answers the question it was
    # written to answer; see "author-previous" and "declared-previous".
    "recommended-previous": (
        4,
        False,
        "it covers the concept, and a bundle assuming it recommends it first",
    ),
    "broad-subject": (5, False, "the query matches a subject or a bundle alias"),
    # "what could I take after X"
    "author-follow-up": (1, True, "X's author recommends it as a follow-up"),
    "declared-previous": (2, True, "it names X as a recommended previous bundle"),
    "assumes-covered": (3, False, "it assumes a concept X covers"),
    # "how do I prepare for X"
    "author-previous": (1, True, "X's author recommends it as a previous bundle"),
    "declared-follow-up": (2, True, "it names X as a recommended follow-up"),
    "covers-assumed": (3, False, "it covers a concept X assumes"),
}

_WORD_RE = re.compile(r"[a-z0-9]+")

# Stripped from a QUERY only, and only on a second pass after the query as
# written found nothing. The corpus is never stripped, so an exact concept id
# or alias can never be damaged by this list.
QUESTION_WORDS = frozenset(
    """
    a an and any are as at be bundle bundles by can could course courses do
    does for from how i in is it me more of on or should show take teach
    teaches tell that the their them then there these this to tutorial
    tutorials want what when where which who whose will with would you your
    about after before cover covers covering learn learning need next
    prepare find list please available
    """.split()
)


def normalise(text: Any) -> str:
    """Fold any phrasing onto the shape a concept id has.

    "Partition Offsets", "partition offsets" and "partition-offsets" are all
    `partition-offsets`, which is what lets a learner's words hit an exact id
    without a fuzzy matcher anywhere.
    """
    return "-".join(_WORD_RE.findall(str(text).lower()))


def tokenise(text: Any) -> list[str]:
    return _WORD_RE.findall(str(text).lower())


class QueryError(Exception):
    """The query itself cannot be used - it is empty, or names nothing."""


@dataclass(frozen=True)
class Concept:
    """One entry of `covers` or `assumes`."""

    id: str
    summary: str
    aliases: tuple[str, ...] = ()
    level: str | None = None

    @property
    def alias_slugs(self) -> tuple[str, ...]:
        return tuple(normalise(a) for a in self.aliases)

    def id_tokens(self) -> set[str]:
        return set(tokenise(self.id))

    def alias_tokens(self) -> set[str]:
        out: set[str] = set()
        for alias in self.aliases:
            out |= set(tokenise(alias))
        return out

    def summary_tokens(self) -> set[str]:
        return set(tokenise(self.summary))

    def as_dict(self) -> dict:
        out: dict[str, Any] = {"id": self.id, "summary": self.summary}
        if self.aliases:
            out["aliases"] = list(self.aliases)
        if self.level is not None:
            out["level"] = self.level
        return out


@dataclass(frozen=True)
class Recommendation:
    """One entry of a recommendation list, with its place in author order."""

    bundle: str
    because: str
    order: int

    def as_dict(self) -> dict:
        return {"bundle": self.bundle, "because": self.because, "order": self.order}


@dataclass
class IndexedBundle:
    """One merged catalogue entry, with its relationship metadata read out."""

    merged: MergedEntry
    position: int
    covers: dict[str, Concept] = field(default_factory=dict)
    assumes: dict[str, Concept] = field(default_factory=dict)
    follow_ups: list[Recommendation] = field(default_factory=list)
    previous: list[Recommendation] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.merged.id

    @property
    def title(self) -> str:
        return str(self.merged.entry.get("title", self.id))

    @property
    def subjects(self) -> list[str]:
        return [str(s) for s in _as_list(self.merged.entry.get("subjects"))]

    @property
    def aliases(self) -> list[str]:
        return [str(s) for s in _as_list(self.merged.entry.get("aliases"))]

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "catalog": self.merged.catalog_id,
            "freshness": self.merged.freshness,
            "subjects": self.subjects,
            "aliases": self.aliases,
            "covers": {k: v.as_dict() for k, v in self.covers.items()},
            "assumes": {k: v.as_dict() for k, v in self.assumes.items()},
            "recommended_follow_ups": [r.as_dict() for r in self.follow_ups],
            "recommended_previous_bundles": [r.as_dict() for r in self.previous],
        }


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def read_concepts(
    raw: Any, where: str, kind: str
) -> tuple[dict[str, Concept], list[str]]:
    """Read `covers` or `assumes`, tolerantly.

    This is the RUNTIME reader, not the validator. A malformed concept is
    dropped with a note and the tutorial is still offered: relationship
    metadata is optional, so a mistake in it must never take a working course
    out of the catalogue. Rejecting the same shapes outright is
    validate_bundle.py's job, where an author is asking to be told.
    """
    concepts: dict[str, Concept] = {}
    notes: list[str] = []
    if raw is None:
        return concepts, notes
    if not isinstance(raw, dict):
        notes.append(f"{where}: '{kind}' is not a mapping of concept id to detail")
        return concepts, notes
    for concept_id, detail in raw.items():
        cid = str(concept_id)
        if not CONCEPT_ID_RE.match(cid):
            notes.append(
                f"{where}: the {kind} concept id {cid!r} is not [a-z0-9-]+, so it "
                f"was left out of the index"
            )
            continue
        if not isinstance(detail, dict):
            notes.append(f"{where}: the {kind} concept {cid!r} has no detail mapping")
            continue
        summary = detail.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            notes.append(
                f"{where}: the {kind} concept {cid!r} has no summary, so a learner "
                f"could not tell what it means; it was left out of the index"
            )
            continue
        aliases: list[str] = []
        raw_aliases = detail.get("aliases")
        if raw_aliases is not None:
            if not isinstance(raw_aliases, list):
                notes.append(
                    f"{where}: the aliases of {kind} concept {cid!r} are not a list"
                )
            else:
                seen: set[str] = set()
                for alias in raw_aliases:
                    text = str(alias).strip()
                    slug = normalise(text)
                    if not slug:
                        notes.append(
                            f"{where}: an empty alias on {kind} concept {cid!r}"
                        )
                        continue
                    if slug in seen:
                        notes.append(
                            f"{where}: the alias {text!r} on {kind} concept {cid!r} "
                            f"repeats after normalisation"
                        )
                        continue
                    seen.add(slug)
                    aliases.append(text)
        level = None
        if kind == "assumes":
            level = detail.get("level")
            level = str(level) if level is not None else None
            if level not in ASSUMES_LEVELS:
                notes.append(
                    f"{where}: the assumed concept {cid!r} has level {level!r}, "
                    f"which is not one of {', '.join(ASSUMES_LEVELS)}; it is "
                    f"indexed without a level"
                )
                level = None
        concepts[cid] = Concept(
            id=cid,
            summary=" ".join(summary.split()),
            aliases=tuple(aliases),
            level=level,
        )
    return concepts, notes


def read_recommendations(
    raw: Any, where: str, field_name: str, self_id: str
) -> tuple[list[Recommendation], list[str]]:
    """Read one recommendation list, keeping AUTHOR ORDER.

    Author order is display order, so the index keeps each entry's position
    and never sorts a recommendation list by anything else.
    """
    out: list[Recommendation] = []
    notes: list[str] = []
    if raw is None:
        return out, notes
    if not isinstance(raw, list):
        notes.append(f"{where}: '{field_name}' is not a list")
        return out, notes
    seen: set[str] = set()
    for position, item in enumerate(raw):
        label = f"{where}: {field_name}[{position}]"
        if not isinstance(item, dict):
            notes.append(f"{label} is not a mapping with 'bundle' and 'because'")
            continue
        bundle = item.get("bundle")
        because = item.get("because")
        if not bundle or not str(bundle).strip():
            notes.append(f"{label} names no bundle")
            continue
        bundle = str(bundle).strip()
        if not because or not str(because).strip():
            notes.append(
                f"{label} recommends {bundle!r} with no 'because'; a "
                f"recommendation with no reason is not shown"
            )
            continue
        if bundle == self_id:
            notes.append(f"{label} recommends the bundle itself, which was ignored")
            continue
        if bundle in seen:
            notes.append(
                f"{label} repeats {bundle!r}, which is already in this list; the "
                f"first one is kept"
            )
            continue
        seen.add(bundle)
        out.append(
            Recommendation(
                bundle=bundle,
                because=" ".join(str(because).split()),
                order=len(out),
            )
        )
    return out, notes


@dataclass(frozen=True)
class Provenance:
    """WHY one bundle is in one result list. Never flattened away."""

    kind: str
    detail: str
    concept: str | None = None
    bundle: str | None = None
    because: str | None = None
    order: int = 0

    @property
    def rank(self) -> int:
        return PROVENANCE_KINDS[self.kind][0]

    @property
    def recommendation(self) -> bool:
        """True only when a human author wrote this relationship down."""
        return PROVENANCE_KINDS[self.kind][1]

    def key(self) -> tuple:
        return (self.kind, self.concept, self.bundle)

    def as_dict(self) -> dict:
        out: dict[str, Any] = {
            "kind": self.kind,
            "rank": self.rank,
            "author_recommendation": self.recommendation,
            "detail": self.detail,
        }
        for name in ("concept", "bundle", "because"):
            value = getattr(self, name)
            if value is not None:
                out[name] = value
        return out


@dataclass
class Match:
    """One bundle, and EVERY route by which this query reached it."""

    bundle: IndexedBundle
    provenance: list[Provenance] = field(default_factory=list)

    def add(self, item: Provenance) -> None:
        if any(p.key() == item.key() for p in self.provenance):
            return
        self.provenance.append(item)

    @property
    def id(self) -> str:
        return self.bundle.id

    @property
    def rank(self) -> int:
        return min(p.rank for p in self.provenance)

    @property
    def order(self) -> int:
        best = min(p.rank for p in self.provenance)
        return min(p.order for p in self.provenance if p.rank == best)

    @property
    def author_recommended(self) -> bool:
        return any(p.recommendation for p in self.provenance)

    def sort_key(self) -> tuple:
        return (self.rank, self.order, self.bundle.position)

    def as_dict(self) -> dict:
        out = self.bundle.as_dict()
        out["rank"] = self.rank
        out["author_recommended"] = self.author_recommended
        out["why"] = [p.as_dict() for p in self.provenance]
        out["resolved_path"] = self.bundle.merged.resolved_path
        return out


class Collector:
    """Deduplicate by bundle id while keeping every provenance."""

    def __init__(self) -> None:
        self._matches: dict[str, Match] = {}

    def add(self, bundle: IndexedBundle, item: Provenance) -> None:
        match = self._matches.get(bundle.id)
        if match is None:
            match = Match(bundle=bundle)
            self._matches[bundle.id] = match
        match.add(item)

    def sorted(self) -> list[Match]:
        return sorted(self._matches.values(), key=lambda m: m.sort_key())


@dataclass
class QueryResult:
    kind: str
    query: str
    matches: list[Match]
    notes: list[str] = field(default_factory=list)
    unresolved: list[dict] = field(default_factory=list)
    subject_of: str | None = None

    @property
    def recommended(self) -> list[Match]:
        return [m for m in self.matches if m.author_recommended]

    @property
    def inferred(self) -> list[Match]:
        return [m for m in self.matches if not m.author_recommended]

    def as_dict(self) -> dict:
        return {
            "query_kind": self.kind,
            "query": self.query,
            "subject_of": self.subject_of,
            "match_count": len(self.matches),
            "matches": [m.as_dict() for m in self.matches],
            "notes": list(self.notes),
            "unresolved": list(self.unresolved),
        }


class RelationshipIndex:
    """Every relationship the merged catalogues declare, both ways round."""

    def __init__(self, entries: list[MergedEntry]) -> None:
        self.bundles: dict[str, IndexedBundle] = {}
        self.order: list[str] = []
        self.notes: list[str] = []
        # The reverse index. `declared_previous[a]` holds the bundles that
        # name `a` under recommended_previous_bundles - the third-party
        # follow-ups `a` has never heard of.
        self.declared_previous: dict[str, list[tuple[str, Recommendation]]] = {}
        self.declared_follow_up: dict[str, list[tuple[str, Recommendation]]] = {}
        for position, merged in enumerate(entries):
            entry = merged.entry
            where = f"{merged.id} (from the {merged.catalog_id} catalogue)"
            indexed = IndexedBundle(merged=merged, position=position)
            covers, notes = read_concepts(entry.get("covers"), where, "covers")
            indexed.covers = covers
            self.notes += notes
            assumes, notes = read_concepts(entry.get("assumes"), where, "assumes")
            indexed.assumes = assumes
            self.notes += notes
            follow_ups, notes = read_recommendations(
                entry.get("recommended_follow_ups"),
                where,
                "recommended_follow_ups",
                merged.id,
            )
            indexed.follow_ups = follow_ups
            self.notes += notes
            previous, notes = read_recommendations(
                entry.get("recommended_previous_bundles"),
                where,
                "recommended_previous_bundles",
                merged.id,
            )
            indexed.previous = previous
            self.notes += notes
            self.bundles[merged.id] = indexed
            self.order.append(merged.id)
        for identifier in self.order:
            indexed = self.bundles[identifier]
            for rec in indexed.previous:
                self.declared_previous.setdefault(rec.bundle, []).append(
                    (identifier, rec)
                )
            for rec in indexed.follow_ups:
                self.declared_follow_up.setdefault(rec.bundle, []).append(
                    (identifier, rec)
                )

    # -- concept matching ------------------------------------------------

    def _concept_hit(
        self, concept: Concept, slug: str, tokens: list[str]
    ) -> tuple[str, str, str] | None:
        """Which tier of the ladder this concept answers on, if any.

        Returns (kind, matched-term, where-it-matched), or None. Tiers 1 and 2
        are exact on normalised text, so an identifier or an alias always
        wins, deterministically and with no service of any kind.
        """
        if slug and slug == concept.id:
            return ("exact-concept", concept.id, "id")
        if slug:
            for alias, alias_slug in zip(concept.aliases, concept.alias_slugs):
                if slug == alias_slug:
                    return ("concept-alias", alias, "alias")
        if not tokens:
            return None
        wanted = set(tokens)
        if wanted <= concept.id_tokens():
            return ("concept-text", concept.id, "id")
        if wanted <= concept.alias_tokens():
            return ("concept-text", ", ".join(concept.aliases), "aliases")
        if wanted <= concept.summary_tokens():
            return ("concept-text", concept.id, "summary")
        return None

    def _covering_pass(self, query: str, collector: Collector) -> bool:
        """Tiers 1-5 for one spelling of the query. True if anything matched.

        THE `covers` LOOP READS `covers` AND NOTHING ELSE. A bundle that only
        assumes the concept is not teaching it, and tier 4 below is the one
        route by which an assuming bundle contributes - and even then it
        contributes the bundle its AUTHOR recommends, never itself, and only
        when that recommended bundle COVERS the concept. Every bundle in the
        answer, by every tier, declares the concept in its own `covers`.
        """
        slug = normalise(query)
        tokens = tokenise(query)
        found = False
        for identifier in self.order:
            bundle = self.bundles[identifier]
            for concept in bundle.covers.values():
                hit = self._concept_hit(concept, slug, tokens)
                if hit is None:
                    continue
                kind, term, where = hit
                if kind == "exact-concept":
                    detail = f"Exact concept match: {concept.id}"
                elif kind == "concept-alias":
                    detail = f"Alias match: {term} (an alias of {concept.id})"
                else:
                    detail = (
                        f"Text match on the {where} of {concept.id}: "
                        f"\"{query.strip()}\""
                    )
                collector.add(
                    bundle, Provenance(kind=kind, detail=detail, concept=concept.id)
                )
                found = True

        # Tier 4. An author who says "take that bundle first" can point at
        # where a concept they ASSUME is taught. The assuming bundle is never
        # returned; the bundle its author points at is - AND ONLY IF THAT
        # BUNDLE ITSELF COVERS THE CONCEPT.
        #
        # That last qualifier is the whole tier. The design ranks "explicit
        # recommended previous bundle THAT COVERS THE CONCEPT" at 4, and
        # without the qualifier this route answers "who teaches C" with a
        # course that merely NEEDS C - the first failure section 12.8 of
        # catalogue-format.md refuses, and the one it names by name.
        #
        # The test is `concept.id in target.covers`, the concept id and
        # nothing looser, because a concept id is the identity that crosses
        # authors. `prepare_for` below asks the same question the same way,
        # so the two commands cannot disagree about who covers what.
        #
        # The tier still earns its place: the query may reach the ASSUMING
        # bundle's wording - its summary, its aliases - when the covering
        # bundle describes the same concept in other words, and then tier 4
        # is the only route that finds the course that teaches it.
        for identifier in self.order:
            bundle = self.bundles[identifier]
            for concept in bundle.assumes.values():
                if self._concept_hit(concept, slug, tokens) is None:
                    continue
                for rec in bundle.previous:
                    target = self.bundles.get(rec.bundle)
                    if target is None or target.id == identifier:
                        continue
                    if concept.id not in target.covers:
                        continue
                    collector.add(
                        target,
                        Provenance(
                            kind="recommended-previous",
                            detail=(
                                f"Covers {concept.id}, and {identifier} - "
                                f"which assumes {concept.id} - names it as a "
                                f"previous bundle"
                            ),
                            concept=concept.id,
                            bundle=identifier,
                            because=rec.because,
                            order=rec.order,
                        ),
                    )
                    found = True

        # Tier 5. Broad classification, and never an author recommendation.
        for identifier in self.order:
            bundle = self.bundles[identifier]
            for label, values in (
                ("subject", bundle.subjects),
                ("alias", bundle.aliases),
            ):
                for value in values:
                    if not self._broad_hit(value, slug, tokens):
                        continue
                    detail = (
                        f"Related subject: {value}"
                        if label == "subject"
                        else f"Related bundle alias: {value}"
                    )
                    collector.add(
                        bundle,
                        Provenance(
                            kind="broad-subject", detail=detail, concept=value
                        ),
                    )
                    found = True
        return found

    @staticmethod
    def _broad_hit(value: str, slug: str, tokens: list[str]) -> bool:
        if slug and slug == normalise(value):
            return True
        return bool(tokens) and set(tokens) <= set(tokenise(value))

    def covering(self, query: str) -> QueryResult:
        """Bundles that TEACH the concept the query names.

        Two passes at most: the query exactly as the learner wrote it, then -
        only if that found nothing - the same query with the question words
        removed. The second pass is announced in the result's notes, so a
        looser match is never passed off as a direct hit.
        """
        if not tokenise(query):
            raise QueryError(
                "the query holds no letters or digits, so it names no concept. "
                "An empty query would match every bundle, which is worse than "
                "no answer"
            )
        collector = Collector()
        notes: list[str] = []
        if not self._covering_pass(query, collector):
            stripped = " ".join(
                t for t in tokenise(query) if t not in QUESTION_WORDS
            )
            if stripped and normalise(stripped) != normalise(query):
                if self._covering_pass(stripped, collector):
                    notes.append(
                        f"nothing matched {query.strip()!r} as written; these "
                        f"matched {stripped!r}, the same query with the question "
                        f"words removed"
                    )
        return QueryResult(
            kind="covering", query=query, matches=collector.sorted(), notes=notes
        )

    # -- relationship queries --------------------------------------------

    def follow_ups(self, bundle_id: str) -> QueryResult:
        """What a learner could take AFTER this bundle.

        The author's own list first, in author order. Then the reverse index:
        every available bundle that names this one as a recommended previous
        bundle, which is how a third party attaches a follow-up to a course
        whose author has never heard of them. Inferred relatives last, and
        marked as inferred.
        """
        bundle = self._require(bundle_id)
        collector = Collector()
        unresolved: list[dict] = []
        for rec in bundle.follow_ups:
            target = self.bundles.get(rec.bundle)
            if target is None:
                unresolved.append(
                    {
                        "bundle": rec.bundle,
                        "because": rec.because,
                        "declared_by": bundle.id,
                        "field": "recommended_follow_ups",
                    }
                )
                continue
            collector.add(
                target,
                Provenance(
                    kind="author-follow-up",
                    detail=f"Recommended by {bundle.id} as a follow-up",
                    bundle=bundle.id,
                    because=rec.because,
                    order=rec.order,
                ),
            )
        for other_id, rec in self.declared_previous.get(bundle.id, []):
            other = self.bundles[other_id]
            if other.id == bundle.id:
                continue
            collector.add(
                other,
                Provenance(
                    kind="declared-previous",
                    detail=(
                        f"{other.id} names {bundle.id} as a recommended previous "
                        f"bundle"
                    ),
                    bundle=other.id,
                    because=rec.because,
                    order=rec.order,
                ),
            )
        for identifier in self.order:
            other = self.bundles[identifier]
            if other.id == bundle.id:
                continue
            for concept in other.assumes.values():
                if concept.id not in bundle.covers:
                    continue
                level = f" at level {concept.level}" if concept.level else ""
                collector.add(
                    other,
                    Provenance(
                        kind="assumes-covered",
                        detail=(
                            f"Assumes {concept.id}{level}, which {bundle.id} "
                            f"covers"
                        ),
                        concept=concept.id,
                        order=0,
                    ),
                )
        return QueryResult(
            kind="follow-ups",
            query=bundle.id,
            subject_of=bundle.id,
            matches=collector.sorted(),
            notes=[],
            unresolved=unresolved,
        )

    def prepare_for(self, bundle_id: str) -> QueryResult:
        """What a learner could take BEFORE this bundle.

        The author's own `recommended_previous_bundles` first, in author
        order; then bundles whose author names this one as a follow-up; then
        every available bundle that COVERS a concept this one ASSUMES, which
        is the concept-level answer and the reason `assumes` carries a summary
        at all.
        """
        bundle = self._require(bundle_id)
        collector = Collector()
        unresolved: list[dict] = []
        for rec in bundle.previous:
            target = self.bundles.get(rec.bundle)
            if target is None:
                unresolved.append(
                    {
                        "bundle": rec.bundle,
                        "because": rec.because,
                        "declared_by": bundle.id,
                        "field": "recommended_previous_bundles",
                    }
                )
                continue
            collector.add(
                target,
                Provenance(
                    kind="author-previous",
                    detail=f"Recommended by {bundle.id} as a previous bundle",
                    bundle=bundle.id,
                    because=rec.because,
                    order=rec.order,
                ),
            )
        for other_id, rec in self.declared_follow_up.get(bundle.id, []):
            other = self.bundles[other_id]
            if other.id == bundle.id:
                continue
            collector.add(
                other,
                Provenance(
                    kind="declared-follow-up",
                    detail=(
                        f"{other.id} names {bundle.id} as a recommended follow-up"
                    ),
                    bundle=other.id,
                    because=rec.because,
                    order=rec.order,
                ),
            )
        notes: list[str] = []
        for concept in bundle.assumes.values():
            level = f" at level {concept.level}" if concept.level else ""
            covered = False
            for identifier in self.order:
                other = self.bundles[identifier]
                if other.id == bundle.id:
                    continue
                if concept.id not in other.covers:
                    continue
                covered = True
                collector.add(
                    other,
                    Provenance(
                        kind="covers-assumed",
                        detail=(
                            f"Covers {concept.id}, which {bundle.id} assumes"
                            f"{level}"
                        ),
                        concept=concept.id,
                        order=0,
                    ),
                )
            if not covered:
                # Said out loud, because the alternative is a list that looks
                # complete. An assumed concept nothing here teaches is a real
                # answer to "how do I prepare", and it is not a blocker: the
                # learner decides, and may already know it.
                notes.append(
                    f"no available bundle covers {concept.id}, which "
                    f"{bundle.id} assumes{level}: {concept.summary}"
                )
        return QueryResult(
            kind="prepare",
            query=bundle.id,
            subject_of=bundle.id,
            matches=collector.sorted(),
            notes=notes,
            unresolved=unresolved,
        )

    def _require(self, bundle_id: str) -> IndexedBundle:
        bundle = self.bundles.get(bundle_id)
        if bundle is None:
            available = ", ".join(self.order) or "(none)"
            raise QueryError(
                f"no catalogue supplies {bundle_id!r}. Available: {available}"
            )
        return bundle


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

STATE_LABEL = {
    "current": "current",
    "cached": "CACHED",
    "unavailable": "UNAVAILABLE",
}


def _join(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def render_catalogs(
    results: list[CatalogResult], stream, refreshed: bool
) -> None:
    print("catalogues:", file=stream)
    for result in results:
        spec = result.spec
        head = (
            f"  [{STATE_LABEL[result.state]}] {spec.id}  ({spec.source.type}) "
            f"{spec.source.describe()}"
        )
        print(head, file=stream)
        if result.state == "current":
            when = "refreshed just now" if result.refreshed_now else "read just now"
            if not refreshed and spec.source.type == "git":
                when = (
                    f"not refreshed in this run; last refreshed "
                    f"{result.fetched_at} ({describe_age(result.fetched_at)})"
                )
            print(
                f"      {len(result.entries)} entr"
                f"{'y' if len(result.entries) == 1 else 'ies'}; {when}",
                file=stream,
            )
        elif result.state == "cached":
            print(
                f"      {len(result.entries)} entr"
                f"{'y' if len(result.entries) == 1 else 'ies'}, SERVED FROM "
                f"CACHE; last refreshed {result.fetched_at} "
                f"({describe_age(result.fetched_at)})",
                file=stream,
            )
        else:
            print("      nothing could be served for this catalogue", file=stream)
        if result.failure is not None:
            print(
                f"      the refresh failed: {result.failure.summary}",
                file=stream,
            )
            for line in result.failure.detail.splitlines():
                print(f"      | {line}", file=stream)
            print(f"      repair: {result.failure.repair}", file=stream)
        if result.commit and result.state != "unavailable":
            print(f"      commit: {result.commit}", file=stream)
        for where, reason in result.skipped:
            print(f"      skipped {where}: {reason}", file=stream)
    print("", file=stream)


def render_warnings(results: list[CatalogResult], stream) -> None:
    cached = [r for r in results if r.state == "cached"]
    gone = [r for r in results if r.state == "unavailable"]
    for result in cached:
        print(
            f"WARNING - {result.spec.id} was served from cache. Its entries "
            f"are as of {result.fetched_at} "
            f"({describe_age(result.fetched_at)}), not current. Say so when "
            f"you offer them.",
            file=stream,
        )
    for result in gone:
        print(
            f"WARNING - {result.spec.id} could not be served at all. Any "
            f"tutorial it holds is missing from this list. Say so rather "
            f"than reporting that nothing matched.",
            file=stream,
        )
    if cached or gone:
        print("", file=stream)


def render_entries(
    entries: list[MergedEntry], shadowed: list[dict], stream
) -> None:
    count = len(entries)
    print(
        f"tutorials ({count}, first match wins, in configuration order):",
        file=stream,
    )
    if not entries:
        print("  (none)", file=stream)
    for item in entries:
        entry = item.entry
        print("", file=stream)
        print(
            f"  {item.id}  [{item.freshness}]  from the {item.catalog_id} "
            f"catalogue",
            file=stream,
        )
        for label, key in (
            ("title", "title"),
            ("description", "description"),
            ("subjects", "subjects"),
            ("aliases", "aliases"),
            ("level", "level"),
            ("style", "style"),
            ("scope", "scope"),
            ("workspace_kind", "workspace_kind"),
        ):
            if key in entry and entry[key] not in (None, "", []):
                text = " ".join(_join(entry[key]).split())
                print(f"      {label + ':':<16}{text}", file=stream)
            if key == "scope":
                # Immediately after `scope`, because it qualifies `scope` and
                # nothing else: `scope` counts the main path, and this counts
                # what is beside it. It is not a sixth field to choose on, so
                # it does not push in among title, level and workspace_kind.
                render_optional_lesson_count(entry, item.id, stream)
        render_entry_relationships(entry, stream)
        for catalog_id, origin in item.shadowed:
            print(
                f"      OVERRIDES:      the {catalog_id} catalogue also "
                f"carries {item.id}; this one comes from {item.catalog_id} "
                f"({item.origin}) and the {catalog_id} entry ({origin}) is "
                f"shadowed. Say this when you offer it.",
                file=stream,
            )
    print("", file=stream)
    if shadowed:
        print("shadowed entries (not offered):", file=stream)
        for item in shadowed:
            print(
                f"  {item['id']} from {item['catalog']} - the "
                f"{item['shadowed_by']} catalogue supplies this id instead",
                file=stream,
            )
        print("", file=stream)


def render_optional_lesson_count(entry: dict, where: str, stream) -> None:
    """The one line that says a course carries more than its main path.

    Silent when the entry does not carry the field, because silence there
    means "this catalogue does not say", not "this course has none". Silent
    at zero too: a course with no optional lessons is exactly the course
    `scope` already described.
    """
    count, notes = read_optional_lesson_count(entry, where)
    if count:
        print(
            f"      {'optional:':<16}{count} optional lesson"
            f"{'' if count == 1 else 's'} beside the main path, offered "
            f"rather than sequenced (`scope` counts the main path only)",
            file=stream,
        )
    for text in notes:
        print(f"      {'':<16}metadata problem: {text}", file=stream)


def render_entry_relationships(entry: dict, stream) -> None:
    """The relationship metadata of one entry, in one line per field.

    Concept ids only. The summaries belong in a concept query's answer, where
    the learner asked about a concept; repeating them for every entry in a
    discovery listing buries the fields a learner chooses on.
    """
    where = str(entry.get("id", "an entry"))
    covers, _ = read_concepts(entry.get("covers"), where, "covers")
    assumes, _ = read_concepts(entry.get("assumes"), where, "assumes")
    follow_ups, _ = read_recommendations(
        entry.get("recommended_follow_ups"), where, "recommended_follow_ups", where
    )
    previous, _ = read_recommendations(
        entry.get("recommended_previous_bundles"),
        where,
        "recommended_previous_bundles",
        where,
    )
    if covers:
        print(f"      {'covers:':<16}{', '.join(covers)}", file=stream)
    if assumes:
        shown = ", ".join(
            f"{c.id} ({c.level})" if c.level else c.id for c in assumes.values()
        )
        print(f"      {'assumes:':<16}{shown}", file=stream)
    if follow_ups:
        print(
            f"      {'after this:':<16}"
            f"{', '.join(r.bundle for r in follow_ups)} (recommended by the author)",
            file=stream,
        )
    if previous:
        print(
            f"      {'before this:':<16}"
            f"{', '.join(r.bundle for r in previous)} (recommended by the author)",
            file=stream,
        )


def render_match(match: Match, stream) -> None:
    merged = match.bundle.merged
    print("", file=stream)
    print(
        f"  {match.id}  [{merged.freshness}]  from the {merged.catalog_id} "
        f"catalogue",
        file=stream,
    )
    print(f"      {'title:':<16}{match.bundle.title}", file=stream)
    for item in match.provenance:
        # The tag is the whole of rule "an inferred match is never presented
        # as an author recommendation", written on every single line rather
        # than once at the top of a section.
        tag = (
            "[author recommendation]"
            if item.recommendation
            else "[not an author recommendation]"
        )
        print(f"      {'why:':<16}{item.detail}  {tag}", file=stream)
        if item.because:
            print(
                f"      {'':<16}  because ({item.bundle}): {item.because}",
                file=stream,
            )


def render_query(result: QueryResult, heading: str, stream) -> None:
    """One query's answer, with the author-curated part kept separate.

    The two sections are not decoration. A broad subject match and an author's
    written recommendation are different claims about a course, and merging
    them into one ranked list is the failure this split exists to prevent.
    """
    print(heading, file=stream)
    print("", file=stream)
    for text in result.notes:
        print(f"note: {text}", file=stream)
    if result.notes:
        print("", file=stream)
    if not result.matches:
        print("  (no bundle matched)", file=stream)
    recommended = result.recommended
    inferred = result.inferred
    if recommended:
        print(
            f"recommended by an author ({len(recommended)}), in author order:",
            file=stream,
        )
        for match in recommended:
            render_match(match, stream)
        print("", file=stream)
    if inferred:
        print(
            f"related, found by matching metadata ({len(inferred)}) - these are "
            f"NOT author recommendations:",
            file=stream,
        )
        for match in inferred:
            render_match(match, stream)
        print("", file=stream)
    for item in result.unresolved:
        print(
            f"unresolved: {item['declared_by']} recommends {item['bundle']!r} "
            f"under {item['field']}, and no configured catalogue carries it. "
            f"Say so; it is a pointer, not a requirement.",
            file=stream,
        )
    if result.unresolved:
        print("", file=stream)


def render_header(
    command: str, config: Path, note: str | None, cache: Cache, stream
) -> None:
    print(f"Belay catalogues - {command}", file=stream)
    print(f"config:      {config}", file=stream)
    if note:
        print(f"             {note}", file=stream)
    print(f"cache:       {cache.catalogs}", file=stream)
    print(f"yaml reader: {YAML_READER}", file=stream)
    print("", file=stream)


def render_implied(specs: list[CatalogSpec], stream) -> None:
    print(
        "The implied default is equivalent to this file. Write it before you "
        "add a catalogue, so nothing already in use is lost:",
        file=stream,
    )
    print("", file=stream)
    print("  catalogs_version: 1", file=stream)
    print("  catalogs:", file=stream)
    for spec in specs:
        print(f"    - id: {spec.id}", file=stream)
        if spec.source.type == "bundled":
            print("      source: { type: bundled }", file=stream)
        else:
            print(
                f"      source: {{ type: file, path: {spec.source.path} }}",
                file=stream,
            )
    print("", file=stream)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def exit_code_for(results: list[CatalogResult], entries: list[MergedEntry]) -> int:
    if not entries:
        return 3
    if any(r.state != "current" for r in results):
        return 1
    return 0


@dataclass
class Run:
    specs: list[CatalogSpec]
    note: str | None
    results: list[CatalogResult]
    entries: list[MergedEntry]
    shadowed: list[dict]


def gather(
    config: Path, cache: Cache, fetch: bool, timeout: int
) -> Run:
    specs, note = load_config(config)
    results = [load_one(spec, cache, fetch, timeout) for spec in specs]
    entries, shadowed = merge(results)
    return Run(specs, note, results, entries, shadowed)


def command_discover(args, stream) -> int:
    cache = Cache(expand(args.cache_dir))
    config = expand(args.config)
    run = gather(config, cache, not args.offline, args.timeout)
    code = exit_code_for(run.results, run.entries)
    if args.json:
        print(
            json.dumps(
                {
                    "command": "discover",
                    "config": str(config),
                    "implied_default": run.note is not None,
                    "cache_dir": str(cache.catalogs),
                    "offline": bool(args.offline),
                    "catalogs": [r.as_dict() for r in run.results],
                    "tutorials": [e.as_dict() for e in run.entries],
                    "shadowed": run.shadowed,
                    "exit_code": code,
                },
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
        return code
    render_header("discover", config, run.note, cache, stream)
    render_catalogs(run.results, stream, refreshed=not args.offline)
    render_warnings(run.results, stream)
    render_entries(run.entries, run.shadowed, stream)
    print(
        "Discovery read catalogue metadata only. Nothing under a bundle path "
        "was opened. Use `resolve <id>` after the learner has chosen.",
        file=stream,
    )
    return code


def command_status(args, stream) -> int:
    cache = Cache(expand(args.cache_dir))
    config = expand(args.config)
    run = gather(config, cache, False, args.timeout)
    code = exit_code_for(run.results, run.entries)
    if args.json:
        print(
            json.dumps(
                {
                    "command": "status",
                    "config": str(config),
                    "implied_default": run.note is not None,
                    "cache_dir": str(cache.catalogs),
                    "catalogs": [r.as_dict() for r in run.results],
                    "exit_code": code,
                },
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
        return code
    render_header("status", config, run.note, cache, stream)
    render_catalogs(run.results, stream, refreshed=False)
    render_warnings(run.results, stream)
    if run.note is not None:
        render_implied(run.specs, stream)
    print(
        "Nothing was fetched. Run `discover` to refresh, which is what a "
        "discovery request does.",
        file=stream,
    )
    return code


def bundle_problems(bundle: Path) -> list[str]:
    """Why `bundle` cannot be materialized from, or [] when it can.

    The test `resolve` has always applied: a directory holding tutorial.yaml
    and STATE.template.md. `materialize` and `place-supplies` apply the same
    one, so the three commands cannot disagree about what a bundle is.
    """
    if not bundle.is_dir():
        return [f"{bundle} is not a directory"]
    problems: list[str] = []
    if not (bundle / "tutorial.yaml").is_file():
        problems.append(f"{bundle}/tutorial.yaml is missing")
    if not (bundle / "STATE.template.md").is_file():
        problems.append(f"{bundle}/STATE.template.md is missing")
    return problems


def command_resolve(args, stream) -> int:
    cache = Cache(expand(args.cache_dir))
    config = expand(args.config)
    run = gather(config, cache, False, args.timeout)
    wanted = args.id
    match = next((e for e in run.entries if e.id == wanted), None)
    if match is None:
        available = ", ".join(e.id for e in run.entries) or "(none)"
        payload = {
            "command": "resolve",
            "id": wanted,
            "found": False,
            "available": [e.id for e in run.entries],
            "exit_code": 3,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True), file=stream)
        else:
            print(f"Belay catalogues - resolve {wanted}", file=stream)
            print("", file=stream)
            print(
                f"No catalogue supplies {wanted!r}. Available: {available}",
                file=stream,
            )
            render_warnings(run.results, stream)
        return 3

    bundle = Path(match.resolved_path)
    present = bundle.is_dir()
    problems = bundle_problems(bundle)
    code = 0 if not problems else 1

    if args.json:
        payload = match.as_dict()
        payload.update(
            {
                "command": "resolve",
                "found": True,
                "bundle_present": present,
                "problems": problems,
                "exit_code": code,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True), file=stream)
        return code

    print(f"Belay catalogues - resolve {wanted}", file=stream)
    print("", file=stream)
    print(f"  id:             {match.id}", file=stream)
    print(f"  title:          {match.entry.get('title')}", file=stream)
    print(f"  catalogue:      {match.catalog_id} ({match.origin})", file=stream)
    print(f"  freshness:      {match.freshness}", file=stream)
    print(f"  bundle:         {match.resolved_path}", file=stream)
    for catalog_id, origin in match.shadowed:
        print(
            f"  OVERRIDES:      the {catalog_id} catalogue ({origin}) also "
            f"carries {match.id}; it is shadowed by this one",
            file=stream,
        )
    print("", file=stream)
    if problems:
        print("The bundle is not usable:", file=stream)
        for problem in problems:
            print(f"  - {problem}", file=stream)
        if match.freshness == "cached":
            print(
                "  This catalogue was served from cache, so the entry may "
                "name a bundle that the last successful fetch did not carry.",
                file=stream,
            )
    else:
        print(
            "The bundle carries tutorial.yaml and STATE.template.md. "
            "Materialization may open it now.",
            file=stream,
        )
    return code


# --------------------------------------------------------------------------
# Reading a bundle source: `materialize` and `place-supplies`
# --------------------------------------------------------------------------
#
# belay#76. Under permissions.blockReadsOutsideWorkingDirectories the host
# asks the learner before any command that NAMES a path outside the
# workspace, and a bundle source always is one: a git catalogue's bundle sits
# in the cache clone, a local one is usually a checkout beside the workspace.
# A command that reads such a path inside its own process is not asked about.
# So these two take a tutorial id, or read the instance stamp, and are never
# given a bundle path. Both work on the current directory, which is the
# workspace root, and on `tutorial/` inside it.
#
# Neither one fetches. `materialize` resolves exactly as `resolve` does, from
# what `discover` left on disk, and `place-supplies` reads the source the
# stamp names. Neither one runs anything a bundle declares
# (runner-protocol.md section 14). Both check everything before they write
# anything, so a refusal leaves the workspace exactly as it was.

INSTANCE_DIR = "tutorial"
LOCAL_PREFIX = "local:"
RUNNER_VERSION = 1
VERSION_ABSENT = "1.0"

EXIT_DONE = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3

_PLAIN_SCALAR_RE = re.compile(r"[A-Za-z0-9_./~][A-Za-z0-9_./~+@:-]*")
# A plain scalar YAML would read back as something other than a string.
_LOOKS_TYPED_RE = re.compile(
    r"[-+]?[0-9][0-9_.]*|true|false|yes|no|on|off|null|~", re.IGNORECASE
)


class Refusal(Exception):
    """The command will not act, and has changed nothing."""


def yaml_scalar(text: str) -> str:
    """`text` as a YAML scalar: plain when that is unambiguous, else quoted.

    A JSON string is a valid YAML double-quoted scalar, which is what makes
    json.dumps the safe fallback for a path holding a space, a '#' or ': '.
    """
    if (
        _PLAIN_SCALAR_RE.fullmatch(text)
        and not text.endswith(":")
        and not _LOOKS_TYPED_RE.fullmatch(text)
    ):
        return text
    return json.dumps(text)


def locator_for(bundle: Path) -> str:
    """The provider-qualified form the stamp records (state-lifecycle.md 3.5)."""
    return LOCAL_PREFIX + os.path.normpath(str(bundle.absolute()))


def inside(root: Path, path: Path) -> bool:
    """True when `path`, with every symbolic link followed, is under `root`.

    escapes() answers the same question on the strings alone, which is right
    for discovery and wrong here: a bundle fetched from a repository can carry
    a symbolic link, and copying through one would hand the learner's
    workspace a file from anywhere on the machine.
    """
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    return real == real_root or real.startswith(real_root.rstrip(os.sep) + os.sep)


def read_manifest(path: Path, what: str) -> dict:
    text = read_text(path)
    if text is None:
        raise Refusal(f"{what} {path} could not be read as UTF-8 text")
    try:
        document = load_yaml(text, str(path))
    except YamlError as exc:
        raise Refusal(f"{what} {path} does not parse: {exc}") from exc
    if not isinstance(document, dict):
        raise Refusal(f"{what} {path} is not a mapping")
    return document


def read_stamp(instance: Path) -> dict:
    manifest = read_manifest(instance / "tutorial.yaml", "the instance manifest")
    stamp = manifest.get("instance")
    if not isinstance(stamp, dict):
        raise Refusal(
            f"{instance / 'tutorial.yaml'} carries no 'instance:' stamp, so "
            f"nothing records where this instance came from"
        )
    return stamp


def source_from_stamp(instance: Path) -> tuple[Path, str]:
    """The bundle directory the instance stamp names, and its locator.

    A relative `local:` path is relative to the workspace root, which is the
    instance's parent (state-lifecycle.md section 3 step 5). `local:` is the
    only locator this runner reads; any other would be a provider it does not
    have, and reaching one would mean contacting a host.
    """
    locator = read_stamp(instance).get("materialized_from")
    if (
        not isinstance(locator, str)
        or not locator.startswith(LOCAL_PREFIX)
        or not locator[len(LOCAL_PREFIX):]
    ):
        raise Refusal(
            f"the stamp's materialized_from is {locator!r}; this runner reads "
            f"only a 'local:' path. An instance stamped before 0.11.0 can name "
            f"a Git source here: belay-plan-update takes the source from the "
            f"catalogues instead with --from-catalogs"
        )
    path = expand(locator[len(LOCAL_PREFIX):])
    if not path.is_absolute():
        path = instance.absolute().parent / path
    return Path(os.path.normpath(str(path))), locator


def usable_source(bundle: Path, locator: str) -> None:
    """Refuse a source that is not there or is not a bundle."""
    problems = bundle_problems(bundle)
    if problems:
        raise Refusal(
            f"the source {locator} is not usable: " + "; ".join(problems)
        )
    if (bundle / "STATE.md").exists():
        raise Refusal(
            f"the source {locator} holds STATE.md, so it is an instance, not "
            f"a bundle"
        )


def bundle_version(manifest: dict) -> str:
    """The bundle's `version` exactly as written, or "1.0" when absent."""
    value = manifest.get("version")
    if value is None:
        return VERSION_ABSENT
    return value if isinstance(value, str) else str(value)


def stamp_block(locator: str, version: str, today: str) -> str:
    return (
        "instance:\n"
        f"  materialized_from: {yaml_scalar(locator)}\n"
        f"  materialized_version: {json.dumps(version)}\n"
        f"  materialized_at: {today}\n"
        f"  runner_version: {RUNNER_VERSION}\n"
    )


def today_stamp() -> str:
    return datetime.now().date().isoformat()


def find_entry(args) -> MergedEntry:
    """The merged entry for args.id, read from disk. Fetches nothing."""
    cache = Cache(expand(args.cache_dir))
    run = gather(expand(args.config), cache, False, args.timeout)
    match = next((e for e in run.entries if e.id == args.id), None)
    if match is None:
        available = ", ".join(e.id for e in run.entries) or "(none)"
        raise Refusal(f"no catalogue supplies {args.id!r}. Available: {available}")
    return match


def _refuse(command: str, exc: Refusal, args, stream) -> int:
    if args.json:
        print(
            json.dumps(
                {"command": command, "refused": str(exc), "exit_code": EXIT_REFUSED},
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
    else:
        print(f"Belay catalogues - {command}", file=stream)
        print("", file=stream)
        print(f"refused: {exc}", file=stream)
        print("Nothing was written.", file=stream)
    return EXIT_REFUSED


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def command_materialize(args, stream) -> int:
    """state-lifecycle.md section 3, steps 1, 2, 3 and 5, in one command.

    Builds the instance in a hidden staging directory inside the workspace and
    renames it into place, so an interrupted run never leaves a half-copied
    `tutorial/` that a later session would take for an instance.
    """
    import plan_update  # the same file set the update compares

    workspace = Path.cwd()
    instance = workspace / INSTANCE_DIR
    try:
        if os.path.lexists(instance):
            raise Refusal(
                "tutorial/ already exists here. It is singular, and "
                "materializing over it would destroy a learner's progress. "
                "When it is this course and the learner wants its newer "
                "version, that is an update (state-lifecycle.md section 3.2); "
                "otherwise ask"
            )
        match = find_entry(args)
        bundle = Path(match.resolved_path)
        locator = locator_for(bundle)
        usable_source(bundle, locator)
        manifest = read_manifest(bundle / "tutorial.yaml", "the bundle manifest")
        if "instance" in manifest:
            raise Refusal(
                f"the bundle's tutorial.yaml already carries an 'instance:' "
                f"stamp, which only an instance has (validator check 7)"
            )
        files = plan_update.bundle_owned_files(bundle)
        for rel in [*files, "STATE.template.md"]:
            if not inside(bundle, bundle / rel):
                raise Refusal(
                    f"{rel} in the bundle is a symbolic link that leads "
                    f"outside the bundle; nothing outside a bundle is copied"
                )
        version = bundle_version(manifest)
        today = today_stamp()
    except Refusal as exc:
        return _refuse(f"materialize {args.id}", exc, args, stream)

    staging = Path(
        tempfile.mkdtemp(prefix=".tutorial-materializing-", dir=workspace)
    )
    try:
        os.chmod(staging, 0o777 & ~_umask())
        for rel in files:
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / rel, target)
        shutil.copyfile(bundle / "STATE.template.md", staging / "STATE.md")
        manifest_copy = staging / "tutorial.yaml"
        text = manifest_copy.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        block = stamp_block(locator, version, today)
        manifest_copy.write_text(text + "\n" + block, encoding="utf-8")
        if os.path.lexists(instance):
            raise OSError(f"{instance} appeared while the instance was being built")
        os.rename(staging, instance)
    except (OSError, UnicodeDecodeError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        print(f"error: {exc}", file=sys.stderr)
        print("Nothing was left behind in the workspace.", file=sys.stderr)
        return EXIT_USAGE

    lesson_files = [rel for rel in files if rel.startswith("lessons/")]
    top = [rel for rel in files if not rel.startswith("lessons/")]
    if args.json:
        print(
            json.dumps(
                {
                    "command": "materialize",
                    "id": match.id,
                    "catalog": match.catalog_id,
                    "freshness": match.freshness,
                    "instance": INSTANCE_DIR,
                    "copied": files,
                    "state": "STATE.md",
                    "stamp": {
                        "materialized_from": locator,
                        "materialized_version": version,
                        "materialized_at": today,
                        "runner_version": RUNNER_VERSION,
                    },
                    "exit_code": EXIT_DONE,
                },
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
        return EXIT_DONE
    print(f"Belay catalogues - materialize {match.id}", file=stream)
    print("", file=stream)
    print(f"  id:             {match.id}", file=stream)
    print(f"  title:          {match.entry.get('title')}", file=stream)
    print(f"  catalogue:      {match.catalog_id} ({match.origin})", file=stream)
    print(f"  freshness:      {match.freshness}", file=stream)
    for catalog_id, origin in match.shadowed:
        print(
            f"  OVERRIDES:      the {catalog_id} catalogue ({origin}) also "
            f"carries {match.id}; it is shadowed by this one",
            file=stream,
        )
    print("", file=stream)
    print("Created tutorial/:", file=stream)
    print(
        f"  copied:  {', '.join(top)}, and {len(lesson_files)} file(s) under lessons/",
        file=stream,
    )
    print(
        "  state:   STATE.template.md became tutorial/STATE.md; the instance "
        "holds no STATE.template.md",
        file=stream,
    )
    print("  stamp:   appended to tutorial/tutorial.yaml", file=stream)
    for line in block.splitlines():
        print(f"             {line}", file=stream)
    print("", file=stream)
    print(
        "Nothing was fetched, nothing outside tutorial/ was written, and "
        "nothing the bundle declares was run. Next: state-lifecycle.md "
        "section 3 step 4, then `belay-validate --instance tutorial`. Place "
        "supplies after validation, with `belay-catalogs place-supplies`.",
        file=stream,
    )
    return EXIT_DONE


@dataclass
class Supply:
    """One manifest-scope `supplies` entry, planned before anything is written."""

    index: int
    from_: str
    to: str
    describe: str
    pairs: list[tuple[Path, str]] = field(default_factory=list)  # (source, target rel)
    placed: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "from": self.from_,
            "to": self.to,
            "describe": self.describe,
            "placed": self.placed,
            "already_present": self.present,
            "blocked": self.blocked,
        }


def _target_rel(to: str, rel: str | None) -> str:
    base = "" if to == "." else to.rstrip("/")
    if rel is None:
        return base or "."
    return f"{base}/{rel}" if base else rel


def plan_supplies(workspace: Path, bundle: Path, manifest: dict) -> list[Supply]:
    """Every manifest-scope entry with its file pairs, or a Refusal.

    The rules are the validator's check 22 (bundle-format.md section 2,
    **supplies** and **Where a `from` may point**), applied again here
    because this is the moment the files are actually read: an instance
    validated once may have been edited since, and a malformed entry must
    stop the placement before the first file lands rather than after it.
    """
    import validate_bundle as vb

    raw = manifest.get("supplies")
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise Refusal(
            "tutorial.yaml's 'supplies' is not a list of entries (validator "
            "check 22)"
        )
    planned: list[Supply] = []
    for index, entry in enumerate(raw, start=1):
        where = f"supplies entry {index}"
        if not isinstance(entry, dict):
            raise Refusal(f"{where} is not a mapping of from, to and describe")
        unknown = sorted(set(entry) - {"from", "to", "describe"})
        if unknown:
            raise Refusal(f"{where} carries unknown key(s) {', '.join(unknown)}")
        from_, to, describe = entry.get("from"), entry.get("to"), entry.get("describe")
        if not isinstance(describe, str) or not describe.strip():
            raise Refusal(f"{where} has no 'describe' line to tell the learner")
        if not isinstance(from_, str) or not from_.rstrip("/"):
            raise Refusal(f"{where}'s 'from' must be a non-empty path")
        to_error = vb._supplies_to_error(to)
        if to_error is not None:
            raise Refusal(f"{where}: {to_error}")
        bare = from_.rstrip("/")
        if escapes(bundle, bare):
            raise Refusal(
                f"{where}'s 'from' {from_!r} leaves the bundle; supplies reach "
                f"only as far as the bundle itself"
            )
        if bare.split("/", 1)[0] == vb.GENERATED_DIR:
            raise Refusal(
                f"{where}'s 'from' {from_!r} points inside "
                f"{vb.GENERATED_DIR}/, which no bundle ships"
            )
        resolved, reason = vb.resolve_exact(bundle, bare)
        if resolved is None:
            raise Refusal(f"{where}'s 'from' {from_!r} does not resolve: {reason}")
        if not inside(bundle, resolved):
            raise Refusal(
                f"{where}'s 'from' {from_!r} is a symbolic link that leads "
                f"outside the bundle"
            )
        is_dir = resolved.is_dir()
        if from_.endswith("/") != is_dir:
            raise Refusal(
                f"{where}'s 'from' {from_!r} "
                + ("ends in '/' but names a file" if not is_dir
                   else "names a directory, and a directory's 'from' must end in '/'")
            )
        supply = Supply(index, from_, str(to), describe.strip())
        if not is_dir:
            supply.pairs.append((resolved, _target_rel(str(to), None)))
        else:
            for current, dirs, names in os.walk(resolved):
                here = Path(current)
                for name in sorted(dirs):
                    if (here / name).is_symlink():
                        raise Refusal(
                            f"{where}: {(here / name).relative_to(bundle)} is a "
                            f"symbolic link to a directory, which placement "
                            f"does not follow"
                        )
                dirs.sort()
                for name in sorted(names):
                    source = here / name
                    if not inside(bundle, source):
                        raise Refusal(
                            f"{where}: {source.relative_to(bundle)} is a "
                            f"symbolic link that leads outside the bundle"
                        )
                    rel = source.relative_to(resolved).as_posix()
                    supply.pairs.append((source, _target_rel(str(to), rel)))
        for _, target_rel in supply.pairs:
            target = workspace / target_rel
            ancestor = target
            while not os.path.lexists(ancestor) and ancestor != workspace:
                ancestor = ancestor.parent
            if not inside(workspace, ancestor):
                raise Refusal(
                    f"{where}: the target {target_rel} would land outside the "
                    f"workspace through a symbolic link"
                )
        planned.append(supply)
    return planned


def _blocked_by(workspace: Path, target: Path) -> str | None:
    """The existing non-directory in the way of `target`'s parents, if any."""
    current = target.parent
    while current != workspace and current != current.parent:
        if os.path.lexists(current) and not current.is_dir():
            return current.relative_to(workspace).as_posix()
        current = current.parent
    return None


def place(workspace: Path, supplies: list[Supply]) -> None:
    """Create each missing target. Never overwrites: O_EXCL is the last word."""
    for supply in supplies:
        for source, target_rel in supply.pairs:
            target = workspace / target_rel
            if os.path.lexists(target):
                supply.present.append(target_rel)
                continue
            blocker = _blocked_by(workspace, target)
            if blocker is not None:
                supply.blocked.append(f"{target_rel} (the file {blocker} is in the way)")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            try:
                with open(target, "xb") as handle:
                    handle.write(data)
            except FileExistsError:
                supply.present.append(target_rel)
                continue
            shutil.copymode(source, target)
            supply.placed.append(target_rel)


def command_place_supplies(args, stream) -> int:
    """state-lifecycle.md section 3 step 8, from the source the stamp names."""
    workspace = Path.cwd()
    instance = workspace / INSTANCE_DIR
    if not (instance / "tutorial.yaml").is_file():
        print(
            f"error: there is no {INSTANCE_DIR}/tutorial.yaml in {workspace}. "
            f"Run this from the workspace root, after materialization",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        bundle, locator = source_from_stamp(instance)
        usable_source(bundle, locator)
        manifest = read_manifest(instance / "tutorial.yaml", "the instance manifest")
        supplies = plan_supplies(workspace, bundle, manifest)
    except Refusal as exc:
        return _refuse("place-supplies", exc, args, stream)
    try:
        place(workspace, supplies)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    code = EXIT_PARTIAL if any(s.blocked for s in supplies) else EXIT_DONE

    if args.json:
        print(
            json.dumps(
                {
                    "command": "place-supplies",
                    "source": locator,
                    "entries": [s.as_dict() for s in supplies],
                    "exit_code": code,
                },
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
        return code
    print("Belay catalogues - place-supplies", file=stream)
    print("", file=stream)
    print(f"  instance:  {INSTANCE_DIR}", file=stream)
    print(f"  source:    {locator}  (the instance stamp's materialized_from)", file=stream)
    print("", file=stream)
    if not supplies:
        print("tutorial.yaml declares no supplies. Nothing to place.", file=stream)
        return code
    for supply in supplies:
        print(
            f"entry {supply.index}: from {supply.from_} to {supply.to}",
            file=stream,
        )
        print(f"  describe:      {supply.describe}", file=stream)
        if not supply.placed and not supply.blocked:
            print(
                "  every target was already here and was left alone; say "
                "nothing about this entry",
                file=stream,
            )
        else:
            for label, items in (
                ("placed", supply.placed),
                ("already here", supply.present),
                ("NOT placed", supply.blocked),
            ):
                if items:
                    print(f"  {label + ':':<14} {items[0]}", file=stream)
                    for item in items[1:]:
                        print(f"  {'':<14} {item}", file=stream)
        print("", file=stream)
    placed = sum(len(s.placed) for s in supplies)
    present = sum(len(s.present) for s in supplies)
    blocked = sum(len(s.blocked) for s in supplies)
    print(
        f"summary: {placed} placed, {present} already here and left alone, "
        f"{blocked} not placed",
        file=stream,
    )
    print(
        "No file that already existed was changed. Report this as setup, not "
        "as a lesson, and write nothing about it into STATE.md.",
        file=stream,
    )
    return code


# --------------------------------------------------------------------------
# report: a link the learner opens to send a defect report themselves
# --------------------------------------------------------------------------
#
# runner-protocol.md section 17. The tutor drafts tutorial/REPORT.md with the
# Write tool, the learner reads all of it, and this command turns it into a
# link. It never opens a browser, never calls `gh`, never sends anything and
# writes nothing: the learner sends the report, or nobody does. Like
# `place-supplies` it works from the current directory and takes no path, so
# under permissions.blockReadsOutsideWorkingDirectories it starts without a
# prompt (belay#76). It fetches nothing: the catalogue tiers read what
# `discover` left on disk, exactly as `materialize` does.

REPORT_DRAFT = "REPORT.md"
RUNNER_REPORT_URL = "https://github.com/skomp/belay/issues/new"
# Longer than this and a prefilled link is not reliably accepted: browsers,
# proxies and the issue trackers themselves cut a URL off somewhere past it.
REPORT_LINK_LIMIT = 8000

EXIT_REPORT_LINK = 0
EXIT_REPORT_NO_TARGET = 1

_SCP_URL_RE = re.compile(r"(?:[A-Za-z0-9._-]+@)?([A-Za-z0-9.-]+):(?!//)(.+)")
_REPO_SEGMENT_RE = re.compile(r"[A-Za-z0-9._-]+")


class ReportUsage(Exception):
    """The command cannot build a report from what is in the workspace."""


@dataclass
class ReportTarget:
    tier: str  # manifest | catalogue-entry | catalogue-repository | runner | none
    where: str
    url: str | None = None
    prefill: str = "none"


def repository_issue_page(url: str) -> tuple[str, str] | None:
    """The new-issue page of a Git repository on github.com or gitlab.com.

    Accepts the three spellings a catalogue's `source.url` takes for such a
    host: https://host/owner/repo(.git), ssh://[user@]host[:port]/owner/repo
    and scp-style [user@]host:owner/repo(.git). Any other host, scheme or
    shape gives None: guessing an issue page for a host this does not know
    would send a learner's report to a page that may not exist.
    """
    if url.startswith(("https://", "ssh://")):
        parts = urllib.parse.urlsplit(url)
        host = (parts.hostname or "").lower()
        path = parts.path
    else:
        match = _SCP_URL_RE.fullmatch(url)
        if match is None:
            return None
        host, path = match.group(1).lower(), match.group(2)
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    segments = path.split("/")
    if not all(
        _REPO_SEGMENT_RE.fullmatch(segment) and segment not in (".", "..")
        for segment in segments
    ):
        return None
    if host == "github.com" and len(segments) == 2:
        return f"https://github.com/{path}/issues/new", "github"
    if host == "gitlab.com" and len(segments) >= 2:
        return f"https://gitlab.com/{path}/-/issues/new", "gitlab"
    return None


def runner_release() -> str | None:
    """The plugin's version, from its own manifest, or None without one.

    Read in this process so the tutor need not open a file in the plugin
    cache, which is outside the workspace. A skill installed without its
    plugin (the Codex route) carries no manifest, and then nobody knows.
    """
    for rel in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
        try:
            data = json.loads((SKILL_DIR.parent.parent / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version:
            return version
    return None


def read_draft(instance: Path) -> tuple[str, str]:
    """The title and the body of tutorial/REPORT.md.

    The first line is `# <title>`; everything after it, less the blank lines
    around it, is the body. The link carries exactly these two strings, so
    what the learner read is what is sent.
    """
    path = instance / REPORT_DRAFT
    shown = f"{INSTANCE_DIR}/{REPORT_DRAFT}"
    how = (
        "Write the draft with the Write tool: its first line '# <title>', "
        "then the body (runner-protocol.md section 17)"
    )
    if not path.is_file():
        raise ReportUsage(f"there is no {shown}. {how}")
    text = read_text(path)
    if text is None:
        raise ReportUsage(f"{shown} could not be read as UTF-8 text")
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    if not text.strip():
        raise ReportUsage(f"{shown} is empty. {how}")
    first, _, rest = text.partition("\n")
    if not first.startswith("# ") or not first[2:].strip():
        raise ReportUsage(
            f"{shown} has no title: its first line is {first!r}, and it must "
            f"be '# <title>'"
        )
    body = rest.lstrip("\n").rstrip()
    if not body:
        raise ReportUsage(
            f"{shown} has a title and no body. The body carries the context "
            f"an author needs to find the defect"
        )
    return first[2:].strip(), body


def prefilled_link(url: str, prefill: str, title: str, body: str) -> str | None:
    """`url` with the title and the body in its query, or None for `none`.

    Every value is percent-encoded with urllib.parse.quote and safe="", so a
    space is %20, never '+', and '&', '#', '+' and '%' in the text cannot
    end or change the query.
    """
    if url.startswith("mailto:"):
        params = (("subject", title), ("body", body))
    elif prefill == "github":
        params = (("title", title), ("body", body))
    elif prefill == "gitlab":
        params = (("issue[title]", title), ("issue[description]", body))
    else:
        return None
    base, hash_, fragment = url.partition("#")
    query = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in params)
    return f"{base}{'&' if '?' in base else '?'}{query}{hash_}{fragment}"


def report_target(args, manifest: dict, notes: list[str]) -> ReportTarget:
    """The first target that exists, in the order section 17 fixes.

    A malformed `report` at a tier is skipped with a note rather than
    refused: the reader is tolerant (catalogue-format.md, last section), and
    a learner with a report to send is better served by the next tier than
    by an error. The validator is where an author is told.
    """
    import validate_bundle as vb

    if args.runner:
        return ReportTarget(
            "runner",
            "the Belay runner's own repository, because --runner was given; "
            "a runner defect never goes to a course",
            RUNNER_REPORT_URL,
            "github",
        )
    if vb.REPORT_KEY in manifest:
        raw = manifest[vb.REPORT_KEY]
        problems = vb.report_problems(raw)
        if not problems:
            return ReportTarget(
                "manifest", "the course's own tutorial.yaml (report)",
                raw["url"], raw.get("prefill", "none"),
            )
        notes.append(
            f"the instance's tutorial.yaml declares a report that cannot be "
            f"used, so it was skipped: {problems[0]} (validator check 34)"
        )
    course = manifest.get("id")
    if not isinstance(course, str) or not course:
        notes.append("the instance manifest has no id, so no catalogue entry "
                     "can be looked up")
        return ReportTarget("none", "nowhere")
    try:
        run = gather(expand(args.config), Cache(expand(args.cache_dir)), False, args.timeout)
    except ConfigError as exc:
        notes.append(f"the catalogue configuration could not be read, so no "
                     f"catalogue was asked: {exc}")
        return ReportTarget("none", "nowhere")
    match = next((e for e in run.entries if e.id == course), None)
    if match is None:
        notes.append(f"no catalogue on disk carries {course!r}")
        return ReportTarget("none", "nowhere")
    if vb.REPORT_KEY in match.entry:
        raw = match.entry[vb.REPORT_KEY]
        problems = vb.report_problems(raw)
        if not problems:
            return ReportTarget(
                "catalogue-entry",
                f"the {match.catalog_id} catalogue's entry for {course} (report)",
                raw["url"], raw.get("prefill", "none"),
            )
        notes.append(
            f"the {match.catalog_id} catalogue's entry for {course} declares "
            f"a report that cannot be used, so it was skipped: {problems[0]}"
        )
    source = match.catalog_source
    if source is not None and source.type == "git" and source.url:
        page = repository_issue_page(source.url)
        if page is not None:
            return ReportTarget(
                "catalogue-repository",
                f"the issue page of the {match.catalog_id} catalogue's "
                f"repository, {source.url}",
                page[0], page[1],
            )
        notes.append(
            f"the {match.catalog_id} catalogue is the Git repository "
            f"{source.url}, which is not on github.com or gitlab.com, so no "
            f"issue page can be derived from it"
        )
    else:
        notes.append(
            f"the {match.catalog_id} catalogue, which carries {course}, is "
            f"not a Git repository, so it has no issue page"
        )
    return ReportTarget("none", "nowhere")


def command_report(args, stream) -> int:
    """runner-protocol.md section 17: print the link; send nothing."""
    workspace = Path.cwd()
    instance = workspace / INSTANCE_DIR
    if not (instance / "tutorial.yaml").is_file():
        print(
            f"error: there is no {INSTANCE_DIR}/tutorial.yaml in {workspace}. "
            f"Run this from the workspace root of a course. Without an "
            f"instance there is no draft: show the report in the conversation "
            f"instead, and never create {INSTANCE_DIR}/ for one",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        manifest = read_manifest(instance / "tutorial.yaml", "the instance manifest")
        title, body = ("", "") if args.context else read_draft(instance)
    except (Refusal, ReportUsage) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE

    notes: list[str] = []
    target = report_target(args, manifest, notes)
    stamp = manifest.get("instance") if isinstance(manifest.get("instance"), dict) else {}
    context = {
        "course": manifest.get("id"),
        "materialized_version": stamp.get("materialized_version"),
        "runner_version": runner_release(),
    }
    link = None
    fallback = None
    if target.url is not None and not args.context:
        full = prefilled_link(target.url, target.prefill, title, body)
        if full is None:
            fallback = (
                f"this target takes no prefilled text (prefill: "
                f"{target.prefill}), so the learner pastes the title and the "
                f"body from {INSTANCE_DIR}/{REPORT_DRAFT}"
            )
            link = target.url
        elif len(full) > REPORT_LINK_LIMIT:
            fallback = (
                f"the prefilled link would be {len(full)} characters, more "
                f"than the {REPORT_LINK_LIMIT} a browser or an issue tracker "
                f"reliably accepts, so this is the bare link and the learner "
                f"pastes the title and the body from "
                f"{INSTANCE_DIR}/{REPORT_DRAFT}"
            )
            link = target.url
        else:
            link = full
    code = EXIT_REPORT_LINK if target.url is not None else EXIT_REPORT_NO_TARGET

    if args.json:
        print(
            json.dumps(
                {
                    "command": "report",
                    "context_only": bool(args.context),
                    **context,
                    "tier": target.tier,
                    "target": target.where,
                    "url": target.url,
                    "prefill": target.prefill if target.url else None,
                    "link": link,
                    "prefilled": link is not None and fallback is None,
                    "fallback": fallback,
                    "notes": notes,
                    "title": title or None,
                    "exit_code": code,
                },
                indent=2,
                sort_keys=True,
            ),
            file=stream,
        )
        return code

    w = stream.write
    w("Belay catalogues - report" + (" --context" if args.context else "") + "\n\n")
    w(f"  course:               {context['course']}\n")
    w(f"  materialized_version: {context['materialized_version']}\n")
    w(f"  runner:               belay {context['runner_version'] or '(unknown: no plugin manifest)'}\n")
    if not args.context:
        w(f"  draft:                {INSTANCE_DIR}/{REPORT_DRAFT}\n")
        w(f"  title:                {title}\n")
    w(f"  target:               {target.where}\n")
    w(f"  tier:                 {target.tier}\n")
    if target.url is not None:
        w(f"  url:                  {target.url}\n")
        w(f"  prefill:              {target.prefill}\n")
    w("\n")
    for text in notes:
        w(f"note: {text}\n")
    if notes:
        w("\n")
    if args.context:
        if target.url is None:
            w("There is no target: the report will be the learner's to send by hand.\n")
        w("Put the course, version and runner lines above into the draft, then "
          "write tutorial/REPORT.md and run this again without --context.\n")
        return code
    if target.url is None:
        w(
            f"There is no target for this report. It is in "
            f"{INSTANCE_DIR}/{REPORT_DRAFT}: give the learner its text to send "
            f"by hand, to whoever publishes the course.\n"
        )
    else:
        if fallback is not None:
            w(f"Bare link: {fallback}.\n")
        else:
            w("Link, with the title and the body filled in:\n")
        w(f"{link}\n\n")
        w(
            "Give the learner this link. They open it, read the report, and "
            "send it themselves.\n"
        )
    w(
        "Nothing was sent, no browser was opened, and nothing was written. "
        "Never submit it for them.\n"
    )
    return code


# --------------------------------------------------------------------------
# The relationship commands
# --------------------------------------------------------------------------
#
# None of these fetches by default. A concept query is asked in the middle of
# a conversation, often several times, and refreshing once per question is
# the "refresh per turn" failure the catalogue document forbids. `discover`
# refreshes; these read what that left behind, exactly as `resolve` does.
# `--refresh` is there for a learner who has just added a catalogue.


def query_exit_code(results: list[CatalogResult], matches: list) -> int:
    if not matches:
        return 3
    if any(r.state != "current" for r in results):
        return 1
    return 0


def run_query(args, stream, build, heading, missing_code: int) -> int:
    cache = Cache(expand(args.cache_dir))
    config = expand(args.config)
    run = gather(config, cache, bool(getattr(args, "refresh", False)), args.timeout)
    index = RelationshipIndex(run.entries)
    try:
        result = build(index)
    except QueryError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "command": args.command,
                        "found": False,
                        "error": str(exc),
                        "available": [e.id for e in run.entries],
                        "exit_code": missing_code,
                    },
                    indent=2,
                    sort_keys=True,
                ),
                file=stream,
            )
        else:
            print(f"error: {exc}", file=sys.stderr)
            render_warnings(run.results, stream)
        return missing_code
    code = query_exit_code(run.results, result.matches)
    if args.json:
        payload = result.as_dict()
        payload.update(
            {
                "command": args.command,
                "config": str(config),
                "index_notes": index.notes,
                "catalogs": [r.as_dict() for r in run.results],
                "semantic_matching": SEMANTIC_MATCHING_AVAILABLE,
                "exit_code": code,
            }
        )
        print(json.dumps(payload, indent=2, sort_keys=True), file=stream)
        return code
    render_header(args.command, config, run.note, cache, stream)
    render_warnings(run.results, stream)
    render_query(result, heading, stream)
    for text in index.notes:
        print(f"metadata problem: {text}", file=stream)
    if index.notes:
        print("", file=stream)
    print(
        "Matching used concept ids, aliases and subjects only - no semantic "
        "search and no service. Every line above says why that bundle is "
        "there. Offer them; never auto-start one.",
        file=stream,
    )
    return code


def command_covers(args, stream) -> int:
    return run_query(
        args,
        stream,
        lambda index: index.covering(args.query),
        f"bundles that COVER {args.query.strip()!r} "
        f"(what they teach, never what they assume):",
        missing_code=2,
    )


def command_follow_ups(args, stream) -> int:
    return run_query(
        args,
        stream,
        lambda index: index.follow_ups(args.id),
        f"bundles to take AFTER {args.id}:",
        missing_code=3,
    )


def command_prepare(args, stream) -> int:
    return run_query(
        args,
        stream,
        lambda index: index.prepare_for(args.id),
        f"bundles that prepare for {args.id} "
        f"(they cover what it assumes; none of them is required):",
        missing_code=3,
    )


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="catalogs.py",
        description=(
            "Fetch, cache and merge the learner's tutorial catalogues."
        ),
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser(
        "discover", help="refresh every catalogue and print the merged catalogue"
    )
    discover.add_argument(
        "--offline",
        action="store_true",
        help="serve what is on disk; fetch nothing",
    )
    discover.set_defaults(run=command_discover)

    status = sub.add_parser(
        "status", help="report each catalogue from disk, without fetching"
    )
    status.set_defaults(run=command_status, offline=True)

    resolve = sub.add_parser(
        "resolve", help="print one entry and the bundle directory it names"
    )
    resolve.add_argument("id", help="the tutorial id the learner chose")
    resolve.set_defaults(run=command_resolve, offline=True)

    materialize = sub.add_parser(
        "materialize",
        help="create tutorial/ in the current directory from a chosen tutorial",
    )
    materialize.add_argument("id", help="the tutorial id the learner chose")
    materialize.set_defaults(run=command_materialize, offline=True)

    place_supplies = sub.add_parser(
        "place-supplies",
        help="place tutorial.yaml's supplies from the source the instance "
        "stamp names; never overwrites",
    )
    place_supplies.set_defaults(run=command_place_supplies, offline=True)

    report = sub.add_parser(
        "report",
        help="print a link that sends the defect report in tutorial/REPORT.md "
        "to the course author; sends nothing",
    )
    report.add_argument(
        "--runner",
        action="store_true",
        help="the defect is in the runner: send it to skomp/belay, never to "
        "the course",
    )
    report.add_argument(
        "--context",
        action="store_true",
        help="print the course, versions and target to put in the draft; "
        "needs no draft",
    )
    report.set_defaults(run=command_report, offline=True)

    covers = sub.add_parser(
        "covers", help="which bundles TEACH a concept (never which assume it)"
    )
    covers.add_argument("query", help="a concept id, an alias, or a phrase")
    covers.add_argument(
        "--refresh",
        action="store_true",
        help="refresh the catalogues first; by default this reads what "
        "`discover` left on disk",
    )
    covers.set_defaults(run=command_covers)

    follow_ups = sub.add_parser(
        "follow-ups", help="what a learner could take after a bundle"
    )
    follow_ups.add_argument("id", help="the bundle just finished")
    follow_ups.add_argument("--refresh", action="store_true")
    follow_ups.set_defaults(run=command_follow_ups)

    prepare = sub.add_parser(
        "prepare", help="what covers the concepts a bundle assumes"
    )
    prepare.add_argument("id", help="the bundle the learner wants to be ready for")
    prepare.add_argument("--refresh", action="store_true")
    prepare.set_defaults(run=command_prepare)
    return parser


def main(argv: list[str] | None = None, stream=None) -> int:
    stream = stream if stream is not None else sys.stdout
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        print("error: --timeout must be a positive number of seconds", file=sys.stderr)
        return 2
    try:
        return args.run(args, stream)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "The catalogue of catalogues decides every other step, so nothing "
            "was fetched. Correct the file, or remove it to fall back to the "
            "implied default.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
