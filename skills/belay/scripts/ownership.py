#!/usr/bin/env python3
"""Ownership resolution: who owns a workspace path, and may the tutor write it.

Stdlib only (plus yamlite.py beside it, which is stdlib only).

The canonical rules are prose in references/runner-protocol.md section 5 and
references/bundle-format.md section 2. This module is the one place a program
resolves them, so a reader and a program get the same answer. It decides
nothing the protocol does not already decide; a host adapter (the Claude Code
hook in ownership_guard.py) is a second line under the protocol, never the
first.

    resolve(path, operation, manifest, instance_present=True, supplies=None)

returns a Resolution naming the owner, the verdict under the manifest's
ownership_policy, and the rule that decided it.

The glob dialect (bundle-format.md section 2, "The glob dialect"):

  * a pattern is relative to the workspace root and anchored there;
  * '*' matches any run of characters within one segment, '?' one character,
    and neither ever crosses '/';
  * '**' as a whole segment matches zero or more segments; '**' anywhere else
    is an error;
  * a pattern with no glob character matches that exact path;
  * a dotfile is an ordinary name ('src/**' matches 'src/.env');
  * comparison is case-sensitive, after normalisation; a path that leaves the
    workspace is 'outside' and is never matched.
"""

from __future__ import annotations

import os
import posixpath
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from yamlite import YamlError, load_yaml


# Owners
TUTOR = "tutor"
LEARNER = "learner"
READ_ONLY = "read-only"
SUPPLIES_TARGET = "supplies-target"
OUTSIDE = "outside"

# Verdicts
ALLOW = "allow"
REFUSE = "refuse"
NEEDS_LEARNER_REQUEST = "needs-learner-request"

# Operations
CREATE = "create"
MODIFY = "modify"
OPERATIONS = (CREATE, MODIFY)

STRICT = "tutor-must-not-edit-learner-owned"
ON_REQUEST = "on-request"
UNRESTRICTED = "unrestricted"
POLICY_VERDICTS = {
    STRICT: REFUSE,
    ON_REQUEST: NEEDS_LEARNER_REQUEST,
    UNRESTRICTED: ALLOW,
}

INSTANCE_DIR = "tutorial"
LESSONS_GLOB = "tutorial/lessons/**"
GENERATED_GLOB = "tutorial/lessons.generated/**"
EVENTS_PATH = "tutorial/EVENTS.jsonl"
INSTANCE_GLOB = "tutorial/**"

_PROTOCOL = "runner-protocol.md section 5"


class GlobError(ValueError):
    """An ownership glob this dialect does not accept."""


class ManifestError(ValueError):
    """The manifest cannot be resolved against: a missing or unknown policy,
    or an ownership list that is not a list of valid globs."""


@dataclass(frozen=True)
class Resolution:
    path: str | None  # the normalised workspace-relative path; None if outside
    owner: str  # TUTOR, LEARNER, READ_ONLY, SUPPLIES_TARGET or OUTSIDE
    verdict: str  # ALLOW, REFUSE or NEEDS_LEARNER_REQUEST
    rule: str  # the rule that decided it, in words a reader can check


# --------------------------------------------------------------------------
# The glob dialect
# --------------------------------------------------------------------------


def _segment_regex(segment: str) -> re.Pattern[str]:
    out = []
    for char in segment:
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(char))
    return re.compile("".join(out) + r"\Z")


def compile_glob(pattern: Any) -> tuple:
    """Parse one ownership glob, or raise GlobError saying why not.

    Returns a tuple of segments: the string '**' for a globstar segment,
    otherwise a compiled per-segment regex.
    """
    if not isinstance(pattern, str):
        raise GlobError(f"{pattern!r} is not a string")
    if pattern == "":
        raise GlobError("an empty pattern matches nothing")
    if pattern.startswith("/"):
        raise GlobError(
            f"{pattern!r} is absolute; ownership globs are relative to the "
            f"workspace root, so drop the leading '/'"
        )
    if pattern.endswith("/"):
        raise GlobError(
            f"{pattern!r} ends in '/'; a pattern names files, so write "
            f"{pattern + '**'!r} for everything under that directory"
        )
    segments = []
    for part in pattern.split("/"):
        if part == "":
            raise GlobError(f"{pattern!r} has an empty path segment ('//')")
        if part in (".", ".."):
            raise GlobError(
                f"{pattern!r} has a {part!r} segment; a pattern is anchored "
                f"at the workspace root and cannot step out of it"
            )
        if part == "**":
            segments.append("**")
        elif "**" in part:
            raise GlobError(
                f"{pattern!r}: '**' must be a whole path segment, as in "
                f"'src/**' or '**/*.go'; inside {part!r} it is ambiguous"
            )
        else:
            segments.append(_segment_regex(part))
    return tuple(segments)


def _match(segs: tuple, parts: list[str]) -> bool:
    memo: dict[tuple[int, int], bool] = {}

    def go(i: int, j: int) -> bool:
        key = (i, j)
        if key in memo:
            return memo[key]
        if i == len(segs):
            result = j == len(parts)
        elif segs[i] == "**":
            # zero segments, or consume one and stay on '**'
            result = go(i + 1, j) or (j < len(parts) and go(i, j + 1))
        else:
            result = j < len(parts) and bool(segs[i].match(parts[j])) and go(
                i + 1, j + 1
            )
        memo[key] = result
        return result

    return go(0, 0)


def glob_matches(pattern: str, path: str) -> bool:
    """True when the normalised workspace-relative `path` matches `pattern`."""
    return _match(compile_glob(pattern), path.split("/"))


def normalise(path: str, workspace: str | os.PathLike | None = None) -> str | None:
    """Return `path` as a normalised workspace-relative POSIX path, or None
    when it is outside the workspace.

    A relative path is taken relative to the workspace root. An absolute one
    needs `workspace`; without it, it is outside. Normalisation is lexical:
    '.' and '..' are folded, and a path that climbs above the root is outside,
    never clamped back in.
    """
    if not isinstance(path, str) or path == "":
        return None
    if os.path.isabs(path):
        if workspace is None:
            return None
        rel = os.path.relpath(os.path.normpath(path), os.path.normpath(str(workspace)))
        rel = rel.replace(os.sep, "/")
    else:
        rel = path.replace(os.sep, "/") if os.sep != "/" else path
    rel = posixpath.normpath(rel)
    if rel == "." or rel == ".." or rel.startswith("../") or rel.startswith("/"):
        return None
    return rel


# --------------------------------------------------------------------------
# Supplies targets
# --------------------------------------------------------------------------


@dataclass
class SuppliesTargets:
    """The workspace paths `supplies` entries declare.

    `files` holds every exact target. A directory entry whose source could
    not be listed contributes its `to` to `unlisted_dirs` instead: what it
    placed is unknown, so no path under it is treated as a declared target.
    """

    files: set
    unlisted_dirs: list

    def __contains__(self, path: str) -> bool:
        return path in self.files


def _join_target(to: str, rel: str) -> str:
    return rel if to in (".", "") else f"{to.rstrip('/')}/{rel}"


def _list_files(directory: Path) -> list[str] | None:
    if not directory.is_dir():
        return None
    out = []
    for dirpath, dirnames, filenames in os.walk(directory):
        dirnames.sort()
        for name in sorted(filenames):
            full = Path(dirpath) / name
            out.append(full.relative_to(directory).as_posix())
    return out


def _bundle_root(manifest: dict, workspace: Path) -> Path | None:
    stamp = manifest.get("instance")
    if not isinstance(stamp, dict):
        return None
    source = stamp.get("materialized_from")
    if not isinstance(source, str) or not source.startswith("local:"):
        return None
    root = Path(source[len("local:"):])
    if not root.is_absolute():
        root = workspace / root
    return root if root.is_dir() else None


_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(?P<fm>.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)


def _lesson_files(instance: Path) -> list[Path]:
    lessons = instance / "lessons"
    out: list[Path] = []
    try:
        names = sorted(os.listdir(lessons))
    except OSError:
        return out
    for name in names:
        child = lessons / name
        if child.is_file() and name.endswith(".md"):
            out.append(child)
        elif (child / "LESSON.md").is_file():
            out.append(child / "LESSON.md")
    return out


def _entries(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [
        e for e in raw
        if isinstance(e, dict) and isinstance(e.get("from"), str)
        and isinstance(e.get("to"), str)
    ]


def collect_supplies_targets(manifest: dict, workspace: str | os.PathLike) -> SuppliesTargets:
    """Every declared supplies target in an instance, manifest and lesson
    scope alike, as workspace-relative paths.

    A file entry's target is its `to`. A directory entry (a `from` ending in
    '/') places that directory's contents under `to`, so its targets are
    found by listing the source: inside the instance's `tutorial/` copy for a
    `from` under `lessons/`, otherwise in the bundle the stamp's
    `materialized_from` names, when that is a `local:` path still on disk.
    """
    ws = Path(workspace)
    instance = ws / INSTANCE_DIR
    sites: list[dict] = list(_entries(manifest.get("supplies")))
    for lesson in _lesson_files(instance):
        try:
            text = lesson.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        match = _FRONTMATTER_RE.match(text)
        if not match:
            continue
        try:
            fm = load_yaml(match.group("fm"), str(lesson))
        except YamlError:
            continue
        if isinstance(fm, dict):
            sites.extend(_entries(fm.get("supplies")))

    bundle = _bundle_root(manifest, ws)
    files: set = set()
    unlisted: list = []
    for entry in sites:
        to = normalise(entry["to"])
        if to is None and entry["to"].strip() not in (".", "./"):
            continue
        to = to or "."
        source = entry["from"]
        if not source.endswith("/"):
            if to != ".":
                files.add(to)
            continue
        listed = None
        if bundle is not None:
            listed = _list_files(bundle / source)
        if listed is None and source.startswith("lessons/"):
            listed = _list_files(instance / source)
        if listed is None:
            unlisted.append(to)
            continue
        files.update(_join_target(to, rel) for rel in listed)
    return SuppliesTargets(files, unlisted)


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def _globs(manifest: dict, key: str) -> list[tuple[str, tuple]]:
    raw = manifest.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ManifestError(f"{key} is not a list")
    out = []
    for pattern in raw:
        try:
            out.append((pattern, compile_glob(pattern)))
        except GlobError as exc:
            raise ManifestError(f"{key}: {exc}") from exc
    return out


def glob_problems(manifest: Any) -> list[str]:
    """Every ownership glob in `manifest` that does not parse, as messages.

    Validator check 10 calls this. It reports; it never resolves a path."""
    problems = []
    if not isinstance(manifest, dict):
        return problems
    for key in ("tutor_owned", "learner_owned"):
        raw = manifest.get(key)
        if not isinstance(raw, list):
            continue
        for pattern in raw:
            try:
                compile_glob(pattern)
            except GlobError as exc:
                problems.append(f"{key}: {exc}")
    return problems


def _first_match(globs: Iterable[tuple[str, tuple]], parts: list[str]) -> str | None:
    for pattern, segs in globs:
        if _match(segs, parts):
            return pattern
    return None


def resolve(
    path: str,
    operation: str,
    manifest: dict,
    instance_present: bool = True,
    supplies: SuppliesTargets | Iterable[str] | None = None,
) -> Resolution:
    """Resolve one workspace-relative path for one write.

    `operation` is CREATE (the path does not exist) or MODIFY (it does).
    `manifest` is the parsed tutorial.yaml. `instance_present` says whether a
    materialized instance exists; the three runner-settled rules and the
    instance rule apply only then, because they describe an instance.
    `supplies` is the set of declared supplies targets
    (collect_supplies_targets builds it for an instance).

    Precedence, first match wins:
      1. outside the workspace         -> outside, allow (ownership does not reach it)
      2. tutorial/lessons/**           -> read-only, refuse
      3. tutorial/lessons.generated/** -> tutor, allow
      4. tutorial/EVENTS.jsonl         -> tutor, allow
      5. the rest of tutorial/**       -> tutor, allow (the instance)
      6. a declared supplies target    -> create allow, modify refuse, every policy
      7. a tutor_owned glob            -> tutor, allow
      8. a learner_owned glob          -> learner, by policy
      9. unlisted                      -> learner, by policy
    """
    if operation not in OPERATIONS:
        raise ValueError(f"operation must be one of {OPERATIONS}, not {operation!r}")
    if not isinstance(manifest, dict):
        raise ManifestError("the manifest is not a mapping")
    policy = manifest.get("ownership_policy")
    if policy not in POLICY_VERDICTS:
        raise ManifestError(f"ownership_policy is {policy!r}, not a known value")
    tutor_globs = _globs(manifest, "tutor_owned")
    learner_globs = _globs(manifest, "learner_owned")

    rel = normalise(path)
    if rel is None:
        return Resolution(None, OUTSIDE, ALLOW,
                          "outside the workspace: ownership does not reach it")
    parts = rel.split("/")

    if instance_present:
        if _match(compile_glob(LESSONS_GLOB), parts):
            return Resolution(rel, READ_ONLY, REFUSE,
                              f"{LESSONS_GLOB} is read-only in every instance, "
                              f"whatever tutor_owned lists ({_PROTOCOL})")
        if _match(compile_glob(GENERATED_GLOB), parts):
            return Resolution(rel, TUTOR, ALLOW,
                              f"{GENERATED_GLOB} is tutor-owned in every instance "
                              f"({_PROTOCOL})")
        if rel == EVENTS_PATH:
            return Resolution(rel, TUTOR, ALLOW,
                              f"{EVENTS_PATH} is tutor-owned in every instance "
                              f"({_PROTOCOL})")
        if _match(compile_glob(INSTANCE_GLOB), parts):
            return Resolution(rel, TUTOR, ALLOW,
                              f"{INSTANCE_GLOB} outside lessons/ is the instance, "
                              f"not the learner's workspace ({_PROTOCOL})")

    if supplies is not None and rel in supplies:
        if operation == CREATE:
            return Resolution(rel, SUPPLIES_TARGET, ALLOW,
                              "a declared supplies target may be created under "
                              "every policy (runner-protocol.md section 10)")
        return Resolution(rel, SUPPLIES_TARGET, REFUSE,
                          "a declared supplies target that exists is never "
                          "modified, under every policy (runner-protocol.md "
                          "section 10)")

    hit = _first_match(tutor_globs, parts)
    if hit is not None:
        return Resolution(rel, TUTOR, ALLOW, f"tutor_owned lists {hit!r}")

    hit = _first_match(learner_globs, parts)
    why = (f"learner_owned lists {hit!r}" if hit is not None
           else "unlisted, so the learner's by default")
    return Resolution(rel, LEARNER, POLICY_VERDICTS[policy],
                      f"{why}; ownership_policy is {policy} ({_PROTOCOL})")


# --------------------------------------------------------------------------
# Reading an instance
# --------------------------------------------------------------------------


def load_instance_manifest(workspace: str | os.PathLike) -> dict | None:
    """The instance manifest at <workspace>/tutorial/tutorial.yaml, or None
    when there is no instance: no file, or no `instance:` stamp.

    Raises YamlError or OSError when a file is there and cannot be read; a
    caller that must fail open catches those."""
    manifest_path = Path(workspace) / INSTANCE_DIR / "tutorial.yaml"
    if not manifest_path.is_file():
        return None
    data = load_yaml(manifest_path.read_text(encoding="utf-8"), str(manifest_path))
    if not isinstance(data, dict) or not isinstance(data.get("instance"), dict):
        return None
    return data
