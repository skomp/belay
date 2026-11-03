#!/usr/bin/env python3
"""Cohort grading: the scheme reader and the local grade store.

Usage:
    grade.py forget <cohort>     delete one cohort's stored grades
    grade.py --help

Later subcommands (collect, run, propose, confirm) are added to SUBCOMMANDS
below; each is a function taking the parsed arguments and returning an exit
code. The design is docs/superpowers/specs/2026-11-03-cohort-grading-design.md;
section 2.1 is the `grading` key this reads, section 5 is the store.

The store is  <data home>/belay/grading/<cohort>/<module-id>/  where the data
home is $XDG_DATA_HOME, else ~/.local/share. The cohort name is DERIVED from
the repository URL (cohort_name) and is always one safe path component. The
store refuses to exist inside a Git work tree (refuse_work_tree), so grades
cannot be committed by accident, and `forget` accepts only a bare cohort name
so it cannot delete anything outside the store.

Exit codes:
    0  done
    1  refused: the bundle has no `grading`, the store is in a work tree,
       or the cohort name is not a bare name
    2  usage or I/O error

Stdlib only, Python 3.11, and the shared restricted reader yamlite.py.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

try:
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from yamlite import YamlError, load_yaml

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_USAGE = 2

MANIFEST = "tutorial.yaml"
STORE_SUBDIR = ("belay", "grading")


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


def normalise_url(repo_url: str) -> str:
    """host/path of a repository URL, whatever its form.

    https://Host/o/r.git, ssh://git@host/o/r and git@host:o/r all give
    host/o/r, so one repository is one cohort however it was typed.
    """
    url = repo_url.strip()
    if "://" in url:
        url = url.split("://", 1)[1]
    elif re.match(r"^[^/@:]*@?[^/:]+:(?!//)", url) and not url.startswith(("/", ".")):
        url = url.replace(":", "/", 1)  # scp form host:path
    url = url.split("@", 1)[1] if "@" in url.split("/", 1)[0] else url
    host, _, path = url.partition("/")
    host = host.split(":", 1)[0].lower() if "/" in url else host.lower()
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return f"{host}/{path}".strip("/")


def cohort_name(repo_url: str) -> str:
    """A single safe path component derived from the URL.

    A readable slug of the last two path parts, then a short hash of the whole
    normalised URL, so two URLs that slug alike ("a/b-c" and "a-b/c") differ.
    """
    norm = normalise_url(repo_url)
    if not norm:
        raise GradeError("the repository URL is empty", EXIT_USAGE)
    tail = "-".join(norm.split("/")[-2:])
    slug = _SAFE.sub("-", tail).strip("-.") or "cohort"
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
    if not module or module in (".", "..") or re.search(r"[/\\\0]", module):
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
    if target.is_symlink() or not target.is_dir():
        return f"no grades stored for cohort {cohort}; nothing deleted"
    if target.resolve().parent != root.resolve():  # belt and braces
        raise GradeError(f"{target} is not directly inside the store; not deleting")
    shutil.rmtree(target)
    return f"deleted the grades of cohort {cohort}"


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def cmd_forget(args: argparse.Namespace) -> int:
    print(forget(args.cohort))
    return EXIT_OK


# name -> (function, help, argument-adder). Add collect/run/propose/confirm here.
SUBCOMMANDS: dict[str, tuple[Callable[[argparse.Namespace], int], str,
                             Callable[[argparse.ArgumentParser], None]]] = {
    "forget": (
        cmd_forget,
        "delete one cohort's stored grades",
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
