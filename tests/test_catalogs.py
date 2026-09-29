#!/usr/bin/env python3
"""Test suite for skills/belay/scripts/catalogs.py.

Run it with:  python3 tests/test_catalogs.py

No pytest and NO NETWORK - nothing here contacts a host. PyYAML may or
may not be installed; it makes no difference, because the scripts never
use it (belay#29).

The point of this suite is not to show the script working. Every failure kind
gets a fixture that makes it fire, with a message a learner could act on, and
the meta-test at the end fails if any kind in catalogs.FAILURE_KINDS has no
fixture behind it. A kind that can only be shown passing is a false oracle,
and this script's whole job is to tell three failures apart.

How the git failures are produced, and why two ways:

  * REAL git, against a local repository over a file:// URL. That covers
    success, a missing catalogue file inside a real clone, and a ref that is
    really not there. It exercises clone, fetch, checkout and rev-parse for
    real, with no network.

  * A FAKE git on PATH, printing the stderr real git prints, exiting 128.
    That covers the failures a local repository cannot produce: an
    unreachable host, a refused credential, and a message the classifier has
    never seen. Each canned message is copied from what git actually prints,
    and the test asserts git's own words reach the report, so a fake that was
    never invoked cannot pass.

The trap this suite is built around: an SSH failure prints BOTH the transport
error AND "Could not read from remote repository. Please make sure you have
the correct access rights" - the same words a refused key prints. A
classifier that tests access first calls every unreachable host an access
problem. That case has its own test.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / "skills" / "belay" / "scripts"

sys.path.insert(0, str(SCRIPTS))
import catalogs as cat  # noqa: E402
import validate_bundle as vb  # noqa: E402

# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------

_failures: list[str] = []
_notes: list[str] = []
_passed = 0
_fired_kinds: set[str] = set()
_fired_catalog_checks: set[int] = set()
_fired_provenance: set[str] = set()


def record(ok: bool, label: str, detail: str = "") -> None:
    global _passed
    if ok:
        _passed += 1
        print(f"  ok   {label}")
    else:
        _failures.append(f"{label}\n       {detail}")
        print(f"  FAIL {label}")
        if detail:
            print(f"       {detail}")


def note(text: str) -> None:
    _notes.append(text)


FAKE_GIT = """#!/usr/bin/env python3
import os
import sys

sys.stderr.write(os.environ.get("BELAY_FAKE_GIT_STDERR", ""))
sys.exit(128)
"""


class Env:
    """A throwaway config directory, cache and remote repository."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.config_dir = root / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.cache = root / "cache"
        self.bin = root / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        fake = self.bin / "git"
        fake.write_text(FAKE_GIT, encoding="utf-8")
        fake.chmod(0o755)
        self.empty_bin = root / "emptybin"
        self.empty_bin.mkdir(parents=True, exist_ok=True)

    @property
    def config(self) -> Path:
        return self.config_dir / "catalogs.yaml"

    def write_config(self, text: str) -> None:
        self.config.write_text(text, encoding="utf-8")

    def write_catalog(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def make_bundle(self, relative: str) -> Path:
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        (path / "tutorial.yaml").write_text("id: x\n", encoding="utf-8")
        (path / "STATE.template.md").write_text(
            "---\nstatus: not-started\n---\n", encoding="utf-8"
        )
        return path

    def run(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        err = io.StringIO()
        full = [
            "--config",
            str(self.config),
            "--cache-dir",
            str(self.cache),
            "--timeout",
            "20",
            *argv,
        ]
        with redirect_stderr(err):
            code = cat.main(full, stream=out)
        return code, out.getvalue() + err.getvalue()

    def run_json(self, *argv: str) -> tuple[int, dict]:
        code, text = self.run("--json", *argv)
        try:
            return code, json.loads(text)
        except ValueError:
            return code, {"_unparsed": text}


@contextmanager
def temp_env():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Env(Path(tmpdir))


@contextmanager
def path_prefixed(directory: Path, stderr: str = ""):
    """Put `directory` first on PATH for the duration."""
    old_path = os.environ.get("PATH", "")
    old_stderr = os.environ.get("BELAY_FAKE_GIT_STDERR")
    os.environ["PATH"] = f"{directory}{os.pathsep}{old_path}"
    os.environ["BELAY_FAKE_GIT_STDERR"] = stderr
    try:
        yield
    finally:
        os.environ["PATH"] = old_path
        if old_stderr is None:
            os.environ.pop("BELAY_FAKE_GIT_STDERR", None)
        else:
            os.environ["BELAY_FAKE_GIT_STDERR"] = old_stderr


@contextmanager
def path_only(directory: Path):
    """Replace PATH entirely, so `git` cannot be found at all."""
    old_path = os.environ.get("PATH", "")
    os.environ["PATH"] = str(directory)
    try:
        yield
    finally:
        os.environ["PATH"] = old_path


def make_repo(root: Path, files: dict[str, str], branch: str = "main") -> str:
    """A real git repository on disk, reachable by a file:// URL."""
    root.mkdir(parents=True, exist_ok=True)
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    git("init", "--quiet", "-b", branch)
    git("add", "-A")
    git(
        "-c",
        "user.email=suite@example.invalid",
        "-c",
        "user.name=suite",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    return f"file://{root}"


# --------------------------------------------------------------------------
# Catalogue documents
# --------------------------------------------------------------------------


def catalog_doc(*entries: tuple[str, str]) -> str:
    lines = ["catalog_version: 1", "tutorials:"]
    for identifier, path in entries:
        lines += [
            f"  - id: {identifier}",
            f"    title: The {identifier} course",
            f"    description: A course about {identifier}.",
            "    subjects: [testing]",
            "    level: beginner",
            "    workspace_kind: new-repository",
            "    source:",
            "      type: local",
            f"      path: {path}",
        ]
    return "\n".join(lines) + "\n"


def with_optional_count(document: str, value: str) -> str:
    """Put `optional_lesson_count: <value>` into every entry of a catalogue.

    Written as a replace on a line every entry carries, so the value lands
    inside the entry mapping at the right indentation whatever
    `catalog_doc` grows later.
    """
    return document.replace(
        "    level: beginner\n",
        f"    level: beginner\n    optional_lesson_count: {value}\n",
    )


def file_config(*pairs: tuple[str, Path]) -> str:
    lines = ["catalogs_version: 1", "catalogs:"]
    for identifier, path in pairs:
        lines += [
            f"  - id: {identifier}",
            f"    source: {{ type: file, path: {path} }}",
        ]
    return "\n".join(lines) + "\n"


def git_config(
    identifier: str, url: str, ref: str = "main", path: str = "catalog.yaml"
) -> str:
    return (
        "catalogs_version: 1\n"
        "catalogs:\n"
        f"  - id: {identifier}\n"
        "    source:\n"
        "      type: git\n"
        f"      url: {url}\n"
        f"      ref: {ref}\n"
        f"      path: {path}\n"
    )


# --------------------------------------------------------------------------
# The canned git failures, copied from what real git prints
# --------------------------------------------------------------------------

GIT_MESSAGES: list[tuple[str, str, str]] = [
    (
        "ssh cannot resolve the host name",
        "unreachable",
        "ssh: Could not resolve hostname github.invalid: nodename nor "
        "servname provided, or not known\r\n"
        "fatal: Could not read from remote repository.\n"
        "\n"
        "Please make sure you have the correct access rights\n"
        "and the repository exists.\n",
    ),
    (
        "https cannot resolve the host name",
        "unreachable",
        "fatal: unable to access 'https://git.invalid/bundles.git/': "
        "Could not resolve host: git.invalid\n",
    ),
    (
        "ssh connects to nothing and times out",
        "unreachable",
        "ssh: connect to host github.com port 22: Operation timed out\r\n"
        "fatal: Could not read from remote repository.\n"
        "\n"
        "Please make sure you have the correct access rights\n"
        "and the repository exists.\n",
    ),
    (
        "the ssh key is refused",
        "no-access",
        "git@github.com: Permission denied (publickey).\r\n"
        "fatal: Could not read from remote repository.\n"
        "\n"
        "Please make sure you have the correct access rights\n"
        "and the repository exists.\n",
    ),
    (
        "the repository is private, or is not there",
        "no-access",
        "ERROR: Repository not found.\r\n"
        "fatal: Could not read from remote repository.\n",
    ),
    (
        "https authentication is refused",
        "no-access",
        "fatal: Authentication failed for "
        "'https://github.com/skomp/private.git/'\n",
    ),
    (
        "git wants to prompt for a password and may not",
        "no-access",
        "fatal: could not read Username for 'https://github.com': "
        "terminal prompts disabled\n",
    ),
    (
        "the branch is not in the repository",
        "no-ref",
        "fatal: Remote branch nope not found in upstream origin\n",
    ),
    (
        "a transfer broke in a way this script has never seen",
        "unclassified",
        "remote: aborting due to possible repository corruption on the "
        "remote side.\nfatal: early EOF\nfatal: index-pack failed\n",
    ),
]


def test_classifier() -> None:
    """The classifier, on its own, against messages real git prints."""
    print("\nthe git-error classifier, on real git messages:")
    for label, expected, message in GIT_MESSAGES:
        got = cat.classify_git_error(message)
        record(
            got == expected,
            f"{label!r} classifies as {expected}",
            f"got {got!r}; the message was:\n       "
            + message.replace("\n", "\n       "),
        )

    # The order test. This message contains the ACCESS wording verbatim and
    # is still a transport failure. If the access patterns were tried first,
    # every unreachable host would be reported as a permissions problem and
    # the learner would be sent to fix credentials that are already correct.
    timeout = GIT_MESSAGES[2][2]
    record(
        "correct access rights" in timeout
        and cat.classify_git_error(timeout) == "unreachable",
        "an ssh timeout that ALSO says 'correct access rights' is still "
        "unreachable, not no-access",
        f"got {cat.classify_git_error(timeout)!r}",
    )

    # And the classifier must be able to say it does not know. A classifier
    # that matched everything would pass every case above and be worthless.
    record(
        cat.classify_git_error("fatal: something nobody has ever seen")
        == "unclassified",
        "an unrecognised message is reported as unclassified, not guessed",
        f"got {cat.classify_git_error('fatal: something nobody has ever seen')!r}",
    )

    # Every kind must send the reader somewhere different. Two kinds with one
    # repair are one kind wearing two names.
    repairs = {kind: repair for kind, (_, repair) in cat.FAILURE_KINDS.items()}
    record(
        len(set(repairs.values())) == len(repairs),
        "every failure kind has a repair no other kind has",
        f"{len(set(repairs.values()))} distinct repairs for {len(repairs)} kinds",
    )
    summaries = {kind: summary for kind, (summary, _) in cat.FAILURE_KINDS.items()}
    record(
        len(set(summaries.values())) == len(summaries),
        "every failure kind has a summary no other kind has",
        repr(sorted(summaries.values())),
    )


# --------------------------------------------------------------------------
# The failure kinds, end to end
# --------------------------------------------------------------------------


def kind_of(payload: dict, identifier: str) -> str | None:
    for entry in payload.get("catalogs", []):
        if entry["id"] == identifier:
            failure = entry.get("failure")
            return failure["kind"] if failure else None
    return "(no such catalogue in the report)"


def state_of(payload: dict, identifier: str) -> str:
    for entry in payload.get("catalogs", []):
        if entry["id"] == identifier:
            return entry["state"]
    return "(no such catalogue in the report)"


def expect_kind(
    label: str, payload: dict, identifier: str, expected: str, text: str = ""
) -> None:
    got = kind_of(payload, identifier)
    if got == expected:
        _fired_kinds.add(expected)
        record(True, label)
    else:
        record(
            False,
            label,
            f"expected kind {expected!r}, got {got!r}. Report:\n"
            + json.dumps(payload.get("catalogs", []), indent=2)[:1800]
            + (f"\n{text[:800]}" if text else ""),
        )


def test_unreachable_and_no_access() -> None:
    print("\nthe git failures a local repository cannot produce:")
    for label, expected, message in GIT_MESSAGES:
        if expected == "no-ref":
            continue  # produced for real, below
        with temp_env() as env:
            env.write_config(git_config("remote", "git@github.com:skomp/x.git"))
            with path_prefixed(env.bin, message):
                code, payload = env.run_json("discover")
            expect_kind(
                f"{label!r} reaches the report as {expected}", payload, "remote", expected
            )
            # The fake git must really have been invoked: git's own words are
            # in the detail. Without this, a run in which git was never called
            # at all would pass.
            detail = ""
            for entry in payload.get("catalogs", []):
                if entry["id"] == "remote" and entry.get("failure"):
                    detail = entry["failure"]["detail"]
            first_line = message.splitlines()[0].strip()
            record(
                first_line in detail,
                f"  git's own first line reaches the report: {first_line[:54]!r}",
                f"detail was {detail!r}",
            )
            record(
                code == 3,
                "  a catalogue that fails with no cache leaves nothing to serve "
                "(exit 3)",
                f"exit was {code}",
            )


def test_no_git_binary() -> None:
    print("\ngit is not installed:")
    with temp_env() as env:
        env.write_config(git_config("remote", "git@github.com:skomp/x.git"))
        with path_only(env.empty_bin):
            record(
                shutil.which("git") is None,
                "the fixture really hides git from PATH",
                f"which('git') = {shutil.which('git')!r}",
            )
            code, payload = env.run_json("discover")
        expect_kind("a missing git binary is its own kind", payload, "remote", "no-git")


def test_real_git_success_and_failures() -> None:
    print("\nreal git, against a local repository over file://:")
    with temp_env() as env:
        url = make_repo(
            env.root / "remote",
            {
                "catalog.yaml": catalog_doc(("demo-course", "demo-bundle")),
                "demo-bundle/tutorial.yaml": "id: demo-course\n",
                "demo-bundle/STATE.template.md": "---\nstatus: not-started\n---\n",
            },
        )

        # -- success
        env.write_config(git_config("demo", url))
        code, payload = env.run_json("discover")
        record(
            code == 0 and state_of(payload, "demo") == "current",
            "a real clone answers, and the catalogue is current",
            f"exit {code}, state {state_of(payload, 'demo')!r}, "
            f"failure {kind_of(payload, 'demo')!r}",
        )
        ids = [e["id"] for e in payload.get("tutorials", [])]
        record(
            ids == ["demo-course"],
            "the repository's own catalogue supplies its own bundle",
            f"tutorials = {ids}",
        )
        entry = payload["tutorials"][0]
        record(
            entry["resolved_path"].endswith("/repo/demo-bundle")
            and str(env.cache) in entry["resolved_path"],
            "the bundle path resolves inside the cached clone, relative to "
            "the catalogue's own root",
            f"resolved_path = {entry['resolved_path']!r}",
        )
        record(
            bool(payload["catalogs"][0]["commit"]),
            "the report names the commit that was fetched",
            repr(payload["catalogs"][0]),
        )

        # -- a second run updates the clone rather than re-cloning
        code, payload = env.run_json("discover")
        record(
            code == 0 and state_of(payload, "demo") == "current",
            "a second refresh of an existing clone succeeds",
            f"exit {code}, failure {kind_of(payload, 'demo')!r}",
        )

        # -- the ref is not in the repository. REAL git says so.
        env.write_config(git_config("demo2", url, ref="no-such-branch"))
        code, payload = env.run_json("discover")
        expect_kind(
            "a branch that is not in the repository is its own kind",
            payload,
            "demo2",
            "no-ref",
        )

        # -- the repository is fine; the catalogue file is not at that path
        env.write_config(git_config("demo3", url, path="somewhere/catalog.yaml"))
        code, payload = env.run_json("discover")
        expect_kind(
            "a repository with no catalogue file at that path is its own kind",
            payload,
            "demo3",
            "no-catalogue",
        )
        detail = payload["catalogs"][0]["failure"]["detail"]
        record(
            "demo-bundle" in detail and "catalog.yaml" in detail,
            "  and the message lists what the repository DOES hold, so the "
            "path can be corrected",
            f"detail = {detail!r}",
        )


def test_file_catalogue_failures() -> None:
    print("\nthe failures of a local catalogue file:")
    with temp_env() as env:
        env.write_config(file_config(("mine", env.root / "nowhere.yaml")))
        code, payload = env.run_json("discover")
        expect_kind(
            "a catalogue file that is not there is its own kind",
            payload,
            "mine",
            "missing-file",
        )

    with temp_env() as env:
        broken = env.root / "broken.yaml"
        broken.write_bytes(b"catalog_version: 1\ntutorials: []\n\xff\xfe not text\n")
        env.write_config(file_config(("mine", broken)))
        code, payload = env.run_json("discover")
        expect_kind(
            "a catalogue that is not UTF-8 text is its own kind",
            payload,
            "mine",
            "unreadable",
        )

    with temp_env() as env:
        env.write_catalog("mine.yaml", "catalog_version: 2\ntutorials: []\n")
        env.write_config(file_config(("mine", env.root / "mine.yaml")))
        code, payload = env.run_json("discover")
        expect_kind(
            "a catalog_version this runner does not know is malformed, not a "
            "guess",
            payload,
            "mine",
            "malformed",
        )
        record(
            "catalog_version" in payload["catalogs"][0]["failure"]["detail"],
            "  and the message names the field",
            repr(payload["catalogs"][0]["failure"]["detail"]),
        )

    with temp_env() as env:
        env.write_catalog("mine.yaml", "catalog_version: 1\ntutorials:\n\t- id: x\n")
        env.write_config(file_config(("mine", env.root / "mine.yaml")))
        code, payload = env.run_json("discover")
        expect_kind(
            "a catalogue that does not parse is malformed",
            payload,
            "mine",
            "malformed",
        )


def test_bundled_catalogue() -> None:
    print("\nthe catalogue that ships with the plugin:")
    with temp_env() as env:
        env.write_config(
            "catalogs_version: 1\ncatalogs:\n  - id: builtin\n"
            "    source: { type: bundled }\n"
        )
        code, payload = env.run_json("discover")
        record(
            code == 0 and state_of(payload, "builtin") == "current",
            "the bundled catalogue is served",
            f"exit {code}, {payload.get('catalogs')}",
        )
        ids = [e["id"] for e in payload["tutorials"]]
        record(
            "rust-cli-basics" in ids,
            "and it carries the example bundle",
            f"tutorials = {ids}",
        )
        entry = payload["tutorials"][0]
        expected = str(
            (REPO / "skills" / "belay" / "examples" / "rust-cli-basics").resolve()
        )
        record(
            entry["resolved_path"] == expected,
            "its bundle path resolves from the directory that holds the "
            "catalogue file",
            f"resolved_path = {entry['resolved_path']!r}, expected {expected!r}",
        )


# --------------------------------------------------------------------------
# The cache, and staleness
# --------------------------------------------------------------------------


def test_stale_fallback() -> None:
    print("\na failed refresh falls back to the cache, and says so:")
    with temp_env() as env:
        url = make_repo(
            env.root / "remote",
            {
                "catalog.yaml": catalog_doc(("demo-course", "demo-bundle")),
                "demo-bundle/tutorial.yaml": "id: demo-course\n",
                "demo-bundle/STATE.template.md": "---\nstatus: not-started\n---\n",
            },
        )
        env.write_config(git_config("demo", url))

        code, first = env.run_json("discover")
        record(
            code == 0 and state_of(first, "demo") == "current",
            "the first refresh succeeds and is current",
            f"exit {code}, state {state_of(first, 'demo')!r}",
        )
        fetched_at = first["catalogs"][0]["fetched_at"]

        # Now the host is unreachable. The catalogue must still be served.
        message = GIT_MESSAGES[0][2]
        with path_prefixed(env.bin, message):
            code, second = env.run_json("discover")
            _, text = env.run("discover")

        record(
            state_of(second, "demo") == "cached",
            "the failed refresh serves the last successful copy, marked cached",
            f"state {state_of(second, 'demo')!r}",
        )
        expect_kind(
            "  and the failure that caused it is still reported by kind",
            second,
            "demo",
            "unreachable",
        )
        ids = [e["id"] for e in second["tutorials"]]
        record(
            ids == ["demo-course"],
            "  the entries are still offered - discovery did not fail",
            f"tutorials = {ids}",
        )
        record(
            all(e["freshness"] == "cached" for e in second["tutorials"]),
            "  every entry from it is marked cached, never current",
            repr([(e["id"], e["freshness"]) for e in second["tutorials"]]),
        )
        record(
            second["catalogs"][0]["fetched_at"] == fetched_at,
            "  and the report carries the timestamp of the last SUCCESSFUL "
            "refresh, not of the failed attempt",
            f"{second['catalogs'][0]['fetched_at']!r} vs {fetched_at!r}",
        )
        record(code == 1, "  exit 1 says the result is partial", f"exit {code}")
        record(
            "SERVED FROM CACHE" in text
            and "demo" in text
            and "not current" in text,
            "  the human report names the catalogue and says the entries are "
            "not current",
            text[:1200],
        )

        # A later run that fetches nothing must NOT forget that the last
        # attempt failed. This is the quiet way "never present stale results
        # as current" gets broken: the success timestamp is still there.
        code, third = env.run_json("status")
        record(
            state_of(third, "demo") == "cached",
            "a later status, which fetches nothing, still reports it cached",
            f"state {state_of(third, 'demo')!r}",
        )

        # And a successful refresh clears the mark again.
        code, fourth = env.run_json("discover")
        record(
            code == 0 and state_of(fourth, "demo") == "current",
            "a refresh that succeeds again clears the cached marking",
            f"exit {code}, state {state_of(fourth, 'demo')!r}",
        )


def test_cache_is_not_reused_across_sources() -> None:
    print("\nthe cache belongs to a source, not to an id:")
    with temp_env() as env:
        url = make_repo(
            env.root / "remote",
            {"catalog.yaml": catalog_doc(("demo-course", "demo-bundle"))},
        )
        env.write_config(git_config("demo", url))
        code, _ = env.run_json("discover")
        record(code == 0, "the first source is cached", f"exit {code}")

        # Same id, different url. The cached copy answers for the OLD source,
        # so serving it would silently present one repository's courses as
        # another's.
        env.write_config(git_config("demo", "git@github.com:someone/else.git"))
        with path_prefixed(env.bin, GIT_MESSAGES[0][2]):
            code, payload = env.run_json("discover")
        record(
            state_of(payload, "demo") == "unavailable"
            and not payload["tutorials"],
            "a cached copy from a DIFFERENT source is not served",
            f"state {state_of(payload, 'demo')!r}, "
            f"tutorials {[e['id'] for e in payload['tutorials']]}",
        )
        detail = payload["catalogs"][0]["failure"]["detail"]
        record(
            "different source" in detail,
            "  and the report says why the cache was not used",
            repr(detail),
        )
        record(code == 3, "  exit 3 says nothing could be served", f"exit {code}")


def test_unavailable_is_reported() -> None:
    print("\na catalogue with nothing to fall back on:")
    with temp_env() as env:
        good = env.write_catalog("mine.yaml", catalog_doc(("mine-course", "b")))
        env.make_bundle("b")
        env.write_config(
            "catalogs_version: 1\ncatalogs:\n"
            f"  - id: mine\n    source: {{ type: file, path: {good} }}\n"
            "  - id: remote\n    source:\n      type: git\n"
            "      url: git@github.com:skomp/x.git\n      ref: main\n"
        )
        with path_prefixed(env.bin, GIT_MESSAGES[4][2]):
            code, payload = env.run_json("discover")
            _, text = env.run("discover")
        record(
            [e["id"] for e in payload["tutorials"]] == ["mine-course"],
            "the catalogue that answered is still served",
            repr([e["id"] for e in payload["tutorials"]]),
        )
        record(
            state_of(payload, "remote") == "unavailable" and code == 1,
            "the one that did not is reported unavailable, and the exit code "
            "says the result is partial",
            f"state {state_of(payload, 'remote')!r}, exit {code}",
        )
        record(
            "remote" in text and "could not be served at all" in text,
            "the human report names it, so 'nothing matched' is never said "
            "when a catalogue is simply missing",
            text[:1200],
        )


# --------------------------------------------------------------------------
# Precedence
# --------------------------------------------------------------------------


def test_precedence_and_override_reporting() -> None:
    print("\nprecedence: first match wins, and the override is announced:")
    with temp_env() as env:
        env.make_bundle("bundles/from-a")
        env.make_bundle("bundles/from-b")
        a = env.write_catalog(
            "a.yaml", catalog_doc(("shared", "bundles/from-a"), ("only-a", "bundles/from-a"))
        )
        b = env.write_catalog(
            "b.yaml", catalog_doc(("shared", "bundles/from-b"), ("only-b", "bundles/from-b"))
        )

        env.write_config(file_config(("alpha", a), ("beta", b)))
        code, payload = env.run_json("discover")
        _, text = env.run("discover")
        winner = next(e for e in payload["tutorials"] if e["id"] == "shared")
        record(
            winner["catalog"] == "alpha",
            "the catalogue listed first supplies a contested id",
            f"catalog = {winner['catalog']!r}",
        )
        record(
            winner["resolved_path"].endswith("from-a"),
            "  and the bundle really is the first catalogue's bundle, not "
            "just its name",
            f"resolved_path = {winner['resolved_path']!r}",
        )
        record(
            [s["catalog"] for s in winner["shadows"]] == ["beta"],
            "  the entry records which catalogue it shadowed",
            repr(winner["shadows"]),
        )
        record(
            len(payload["shadowed"]) == 1
            and payload["shadowed"][0]["id"] == "shared"
            and payload["shadowed"][0]["catalog"] == "beta",
            "  the shadowed entry is listed rather than dropped silently",
            repr(payload["shadowed"]),
        )
        record(
            "OVERRIDES" in text and "beta" in text and "alpha" in text,
            "  and the human report says which catalogue supplied it and "
            "which was shadowed",
            text[:1600],
        )
        record(
            sorted(e["id"] for e in payload["tutorials"])
            == ["only-a", "only-b", "shared"],
            "  uncontested entries from both catalogues are still offered",
            repr([e["id"] for e in payload["tutorials"]]),
        )

        # Reverse the order. Precedence must follow the FILE, not the ids.
        env.write_config(file_config(("beta", b), ("alpha", a)))
        code, payload = env.run_json("discover")
        winner = next(e for e in payload["tutorials"] if e["id"] == "shared")
        record(
            winner["catalog"] == "beta"
            and winner["resolved_path"].endswith("from-b"),
            "reversing the order in catalogs.yaml reverses which entry wins",
            f"catalog = {winner['catalog']!r}, path = {winner['resolved_path']!r}",
        )

        # The negative direction: with no contest there must be NO override
        # notice. A reporter that always announces one proves nothing.
        env.write_config(file_config(("alpha", a)))
        code, payload = env.run_json("discover")
        _, text = env.run("discover")
        winner = next(e for e in payload["tutorials"] if e["id"] == "shared")
        record(
            winner["shadows"] == [] and not payload["shadowed"],
            "an id only one catalogue carries records no override",
            repr(winner["shadows"]),
        )
        record(
            "OVERRIDES" not in text and "shadowed entries" not in text,
            "  and the human report does not announce one",
            text[:1200],
        )


def test_implied_default_keeps_the_old_two_file_model() -> None:
    print("\nno catalogs.yaml: the two-file model keeps working:")
    with temp_env() as env:
        env.make_bundle("bundles/mine")
        (env.config_dir / "catalog.yaml").write_text(
            catalog_doc(("mine-course", str(env.root / "bundles" / "mine")),
                        ("rust-cli-basics", str(env.root / "bundles" / "mine"))),
            encoding="utf-8",
        )
        record(
            not env.config.exists(),
            "the fixture really has no catalogs.yaml",
            f"{env.config} exists",
        )
        code, payload = env.run_json("discover")
        record(
            payload["implied_default"] and code == 0,
            "the implied default is used, and discovery succeeds",
            f"exit {code}, implied {payload.get('implied_default')!r}",
        )
        listed = [c["id"] for c in payload["catalogs"]]
        record(
            listed == ["user", "builtin"],
            "it is the user catalogue followed by the bundled one",
            f"catalogs = {listed}",
        )
        winner = next(e for e in payload["tutorials"] if e["id"] == "rust-cli-basics")
        record(
            winner["catalog"] == "user"
            and [s["catalog"] for s in winner["shadows"]] == ["builtin"],
            "the user's entry overrides the shipped one, and says so",
            f"catalog = {winner['catalog']!r}, shadows = {winner['shadows']!r}",
        )

        _, text = env.run("status")
        record(
            "catalogs_version: 1" in text and "type: bundled" in text,
            "status prints the configuration the default implies, so it can "
            "be written down before a catalogue is added",
            text[:1400],
        )

    # And with no user file either, only the bundled catalogue is listed. A
    # missing user catalogue is the normal first run, not a failure.
    with temp_env() as env:
        code, payload = env.run_json("discover")
        record(
            [c["id"] for c in payload["catalogs"]] == ["builtin"]
            and code == 0
            and not any(c["failure"] for c in payload["catalogs"]),
            "a first run with neither file reports no failure at all",
            f"exit {code}, catalogs = {payload.get('catalogs')}",
        )


# --------------------------------------------------------------------------
# The provider boundary
# --------------------------------------------------------------------------


def test_discovery_never_opens_a_bundle() -> None:
    print("\ndiscovery loads metadata only:")
    with temp_env() as env:
        # The bundle path does not exist at all. Discovery must not care.
        mine = env.write_catalog("mine.yaml", catalog_doc(("ghost", "bundles/ghost")))
        env.write_config(file_config(("mine", mine)))
        record(
            not (env.root / "bundles" / "ghost").exists(),
            "the fixture's bundle directory really is absent",
            "it exists",
        )
        code, payload = env.run_json("discover")
        record(
            code == 0 and [e["id"] for e in payload["tutorials"]] == ["ghost"],
            "discovery offers an entry whose bundle is not on disk - it never "
            "looked",
            f"exit {code}, tutorials {[e['id'] for e in payload['tutorials']]}",
        )

        # resolve is the step that IS allowed to look, and it reports the gap.
        code, payload = env.run_json("resolve", "ghost")
        record(
            code == 1
            and payload["found"]
            and not payload["bundle_present"]
            and payload["problems"],
            "resolve, which runs after the learner has chosen, reports the "
            "missing bundle",
            repr(payload),
        )

        code, payload = env.run_json("resolve", "no-such-course")
        record(
            code == 3 and payload["found"] is False,
            "resolve names what is available when the id is unknown",
            repr(payload),
        )

        env.make_bundle("bundles/ghost")
        code, payload = env.run_json("resolve", "ghost")
        record(
            code == 0 and payload["bundle_present"] and not payload["problems"],
            "and it passes once the bundle carries tutorial.yaml and "
            "STATE.template.md",
            repr(payload),
        )


def test_remote_catalogue_cannot_reach_outside_itself() -> None:
    print("\na catalogue fetched from a repository may only name its own bundles:")
    with temp_env() as env:
        url = make_repo(
            env.root / "remote",
            {
                "catalog.yaml": catalog_doc(
                    ("escaping", "../../../../etc"),
                    ("absolute", "/etc"),
                    ("good", "demo-bundle"),
                ),
                "demo-bundle/tutorial.yaml": "id: good\n",
                "demo-bundle/STATE.template.md": "---\nstatus: not-started\n---\n",
            },
        )
        env.write_config(git_config("demo", url))
        code, payload = env.run_json("discover")
        _, text = env.run("discover")
        offered = [e["id"] for e in payload["tutorials"]]
        record(
            offered == ["good"],
            "an entry naming a path outside the clone is skipped; the rest "
            "of the catalogue is still served",
            f"tutorials = {offered}",
        )
        skipped = payload["catalogs"][0]["skipped"]
        record(
            len(skipped) == 2
            and all("leaves the catalogue" in s["reason"] for s in skipped),
            "  both the '..' path and the absolute path are skipped, with a "
            "reason",
            repr(skipped),
        )
        record(
            "skipped" in text and "escaping" in text,
            "  and the skip is visible in the human report, not silent",
            text[:1400],
        )

    # The negative direction: a LOCAL catalogue is the user's own file and may
    # legitimately name bundles anywhere on their machine. A guard that fired
    # here would break every existing user catalogue.
    with temp_env() as env:
        outside = env.make_bundle("elsewhere/course")
        mine = env.write_catalog(
            "cat/mine.yaml", catalog_doc(("outside", str(outside)))
        )
        env.write_config(file_config(("mine", mine)))
        code, payload = env.run_json("discover")
        record(
            code == 0 and [e["id"] for e in payload["tutorials"]] == ["outside"],
            "the user's own catalogue may name a bundle anywhere",
            f"exit {code}, skipped "
            f"{payload['catalogs'][0]['skipped'] if payload.get('catalogs') else '?'}",
        )


def test_malformed_entries_are_skipped_not_fatal() -> None:
    print("\none bad entry does not hide a catalogue:")
    with temp_env() as env:
        env.make_bundle("b")
        mine = env.write_catalog(
            "mine.yaml",
            "catalog_version: 1\n"
            "tutorials:\n"
            "  - id: no-title\n"
            "    description: It has no title.\n"
            "    subjects: [testing]\n"
            "    level: beginner\n"
            "    workspace_kind: new-repository\n"
            "    source: { type: local, path: b }\n"
            "  - id: remote-bundle\n"
            "    title: A bundle in a repository\n"
            "    description: Declared but not implemented.\n"
            "    subjects: [testing]\n"
            "    level: beginner\n"
            "    workspace_kind: new-repository\n"
            "    source: { type: git, url: git@example.invalid:x.git }\n"
            + catalog_doc(("fine", "b")).split("tutorials:\n", 1)[1],
        )
        env.write_config(file_config(("mine", mine)))
        code, payload = env.run_json("discover")
        _, text = env.run("discover")
        record(
            [e["id"] for e in payload["tutorials"]] == ["fine"],
            "the well-formed entry is served",
            repr([e["id"] for e in payload["tutorials"]]),
        )
        reasons = " ".join(s["reason"] for s in payload["catalogs"][0]["skipped"])
        record(
            "title" in reasons and "not implemented" in reasons,
            "the malformed entry and the unimplemented source type are each "
            "named, with their own reason",
            repr(payload["catalogs"][0]["skipped"]),
        )
        record(
            "no-title" in text and "remote-bundle" in text,
            "and both are visible in the human report",
            text[:1400],
        )


# --------------------------------------------------------------------------
# The containment predicate itself
# --------------------------------------------------------------------------

# The roots escapes() has to answer for. The predicate is a string test with
# no filesystem behind it, so a root is only ever a spelling, and every
# defect found in it so far was one spelling the string comparison did not
# fit. Each root here is a spelling, not a place: nothing below creates,
# opens or stats any of them.
#
# On the trailing separator: Path() removes one, so Path('/a/b/') IS
# Path('/a/b') and cannot exercise the case. Path('/') and Path('//') are
# the only roots that reach escapes() with a trailing separator still on
# them, and the assertion below records that fact so the next reader does
# not add Path('/a/b/') believing it covers anything new.
CONTAINMENT_ROOTS = (
    ("the filesystem root", Path("/")),  # issue #16
    ("the current directory", Path(".")),  # issue #14
    ("an ordinary absolute path", Path("/srv/catalogues/demo")),
    ("a root that keeps its trailing separator", Path("//")),
    ("a relative path with a directory component", Path("bundles/demo")),
    ("a root that starts above itself", Path("..")),
)

# Paths that stay inside the root, whatever the root is.
CONTAINMENT_INSIDE = (
    "bundle",  # the bare form issues #14 and #16 both rejected
    "./bundle",
    "nested/deeper",  # a directory component, so normpath has work to do
    "nested/../bundle",  # leaves and returns inside the root
)

# Paths that really do leave the root. This direction is the oracle: a fix
# that answered False for everything would satisfy the direction above and
# fail every assertion here.
CONTAINMENT_OUTSIDE = (
    "../outside",
    "a/../../outside",  # the same escape, only visible after normpath
    "/etc/passwd",  # absolute
    "~/outside",  # the home directory, which is somebody else's absolute
)


def test_containment_is_decided_the_same_way_for_every_root() -> None:
    """Issues #14 and #16: escapes() must not depend on how a root is spelled.

    Both defects were the same mistake - deciding containment by comparing
    `str(root)` and `str(root) + os.sep` against the joined path, which is
    the right question only for a root with at least one component and no
    trailing separator. The roots below are the ones that are not that.
    """
    print("\nescapes(): one answer per path, whatever the root is:")
    record(
        str(Path("/a/b/")) == "/a/b" and str(Path("//")) == "//",
        "Path() removes a trailing separator except on the root itself, so "
        "Path('//') is what carries that case",
        f"Path('/a/b/') = {str(Path('/a/b/'))!r}, Path('//') = {str(Path('//'))!r}",
    )
    for label, root in CONTAINMENT_ROOTS:
        wrong = [p for p in CONTAINMENT_INSIDE if cat.escapes(root, p)]
        record(
            not wrong,
            f"{label} ({str(root)!r}): a contained path is not an escape",
            f"reported as escaping: {wrong}",
        )
        missed = [p for p in CONTAINMENT_OUTSIDE if not cat.escapes(root, p)]
        record(
            not missed,
            f"{label} ({str(root)!r}): a path that leaves IS an escape",
            f"reported as contained: {missed}",
        )


def test_the_validator_root_and_escapes_agree() -> None:
    """`validate_bundle.catalog_root()` and `escapes()` must not disagree.

    Issue #14 was fixed on the validator's side, by anchoring the root with
    `os.path.abspath`. Issue #16 is fixed inside `escapes()`. Both now
    normalise, so this checks that they did not end up double-anchoring or
    parting company at an edge: for one catalogue file named five ways, and
    for the unanchored `target.parent` the validator used to pass, every
    bundle path must get one verdict.
    """
    print("\nthe validator's root and the runtime's predicate agree:")
    paths = CONTAINMENT_INSIDE + CONTAINMENT_OUTSIDE
    expected = {
        "bundle": False,
        "./bundle": False,
        "nested/deeper": False,
        "nested/../bundle": False,
        "../outside": True,
        "a/../../outside": True,
        "/etc/passwd": True,
        "~/outside": True,
    }
    previous = Path.cwd()
    with tempfile.TemporaryDirectory() as tmpdir:
        home = Path(tmpdir).resolve() / "home"
        (home / "nested" / "deeper").mkdir(parents=True)
        spellings = [
            ("a bare filename", home, "catalog.yaml"),
            ("'./' before the filename", home, "./catalog.yaml"),
            (
                "a relative path with a directory component",
                home,
                f"../{home.name}/catalog.yaml",
            ),
            ("an absolute path", home, str(home / "catalog.yaml")),
            (
                "a relative path typed from another directory",
                home.parent,
                f"{home.name}/catalog.yaml",
            ),
            # The spelling that makes the two roots differ the most: from the
            # filesystem root, target.parent is Path('.') and catalog_root()
            # is Path('/'). Those are the two roots of issues #14 and #16.
            ("a bare filename typed from '/'", Path("/"), "catalog.yaml"),
        ]
        for label, cwd, spelling in spellings:
            try:
                os.chdir(cwd)
                anchored = vb.catalog_root(Path(spelling))
                plain = Path(spelling).parent
            finally:
                os.chdir(previous)
            disagreed = [
                f"{p!r}: catalog_root={cat.escapes(anchored, p)} "
                f"parent={cat.escapes(plain, p)} expected={expected[p]}"
                for p in paths
                if not (
                    cat.escapes(anchored, p)
                    == cat.escapes(plain, p)
                    == expected[p]
                )
            ]
            record(
                not disagreed,
                f"{label}: catalog_root() and target.parent give the same "
                f"verdict for every bundle path",
                f"root {str(anchored)!r} vs {str(plain)!r}: "
                + "; ".join(disagreed),
            )


# --------------------------------------------------------------------------
# The catalogue of catalogues itself
# --------------------------------------------------------------------------


def test_configuration_errors() -> None:
    print("\nthe catalogue of catalogues decides everything, so it fails loudly:")
    cases = [
        (
            "a tab indents the file",
            "catalogs_version: 1\ncatalogs:\n\t- id: a\n",
            "tab",
        ),
        (
            "catalogs is empty",
            "catalogs_version: 1\ncatalogs: []\n",
            "non-empty list",
        ),
        (
            "two catalogues share an id",
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: a\n    source: { type: bundled }\n"
            "  - id: a\n    source: { type: file, path: /tmp/x.yaml }\n",
            "used more than once",
        ),
        (
            "an id that would escape the cache directory",
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: ../../evil\n    source: { type: bundled }\n",
            "names a cache directory",
        ),
        (
            "an unknown source type",
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: a\n    source: { type: ftp, path: x }\n",
            "is not one of",
        ),
        (
            "a git source with no url",
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: a\n    source: { type: git, ref: main }\n",
            "requires the field 'url'",
        ),
        (
            "a git path that climbs out of the repository",
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: a\n    source:\n      type: git\n"
            "      url: git@example.invalid:x.git\n"
            "      path: ../../etc/passwd\n",
            "must stay inside the repository",
        ),
        (
            "a catalogs_version this runner does not know",
            "catalogs_version: 9\ncatalogs:\n"
            "  - id: a\n    source: { type: bundled }\n",
            "does not know",
        ),
        (
            "a catalogue with no source",
            "catalogs_version: 1\ncatalogs:\n  - id: a\n",
            "has no 'source'",
        ),
    ]
    for label, text, expected in cases:
        with temp_env() as env:
            env.write_config(text)
            code, output = env.run("discover")
            record(
                code == 2 and expected in output,
                f"{label} is refused (exit 2), naming the reason",
                f"exit {code}; output was:\n       "
                + output.replace("\n", "\n       ")[:900],
            )

    # The positive control: a configuration of the same shape, correct, is
    # accepted. Without it, every case above would also pass a parser that
    # rejected everything.
    with temp_env() as env:
        env.write_config(
            "catalogs_version: 1\ncatalogs:\n"
            "  - id: builtin\n    source: { type: bundled }\n"
        )
        code, _ = env.run("discover")
        record(code == 0, "a correct configuration of the same shape is accepted",
               f"exit {code}")


def test_offline() -> None:
    print("\n--offline serves what is on disk and fetches nothing:")
    with temp_env() as env:
        url = make_repo(
            env.root / "remote",
            {"catalog.yaml": catalog_doc(("demo-course", "demo-bundle"))},
        )
        env.write_config(git_config("demo", url))
        code, _ = env.run_json("discover")
        record(code == 0, "seeded the cache", f"exit {code}")
        # No git at all. Offline must still answer from the clone.
        with path_only(env.empty_bin):
            code, payload = env.run_json("discover", "--offline")
        record(
            code == 0 and [e["id"] for e in payload["tutorials"]] == ["demo-course"],
            "with git removed entirely, --offline still serves the clone",
            f"exit {code}, {payload.get('catalogs')}",
        )


# --------------------------------------------------------------------------
# The validator's catalogue mode
# --------------------------------------------------------------------------

CATALOG_CASES: list[tuple[str, int, str, str, bool]] = [
    (
        "1: the catalogue does not parse",
        1,
        "catalog_version: 1\ntutorials:\n\t- id: a\n",
        "a tab is used for indentation",
        False,
    ),
    (
        "1: catalog_version is missing",
        1,
        "tutorials: []\n",
        "'catalog_version' is missing",
        False,
    ),
    (
        "1: catalog_version is unknown",
        1,
        "catalog_version: 7\ntutorials: []\n",
        "not a guess",
        False,
    ),
    (
        "2: tutorials is missing",
        2,
        "catalog_version: 1\n",
        "'tutorials' is missing",
        False,
    ),
    (
        "2: the tutorials list is empty",
        2,
        "catalog_version: 1\ntutorials: []\n",
        "offers nothing",
        False,
    ),
    (
        "2: an entry is not a mapping",
        2,
        "catalog_version: 1\ntutorials:\n  - just-a-string\n",
        "must be a mapping",
        False,
    ),
    (
        "3: a required field is missing",
        3,
        catalog_doc(("a", "bundle")).replace("    level: beginner\n", ""),
        "the required field 'level' is missing",
        False,
    ),
    (
        "3: subjects is a bare string, not a list",
        3,
        catalog_doc(("a", "bundle")).replace(
            "    subjects: [testing]", "    subjects: testing"
        ),
        "'subjects' must be a non-empty list of strings",
        False,
    ),
    (
        "3: an unknown workspace_kind",
        3,
        catalog_doc(("a", "bundle")).replace(
            "new-repository", "existing-repository"
        ),
        "not one of",
        False,
    ),
    (
        "3: optional_lesson_count is a word, not a number",
        3,
        with_optional_count(catalog_doc(("a", "bundle")), "several"),
        "must be a whole number that is zero or more",
        False,
    ),
    (
        "3: optional_lesson_count is negative",
        3,
        with_optional_count(catalog_doc(("a", "bundle")), "-1"),
        "it is -1",
        False,
    ),
    (
        "3: optional_lesson_count is a YAML boolean",
        3,
        # `true` is an int in Python, so a bare isinstance check would take
        # this as a count of one. The message must name the boolean.
        with_optional_count(catalog_doc(("a", "bundle")), "true"),
        "it is True",
        False,
    ),
    (
        "3: optional_lesson_count is a decimal",
        3,
        with_optional_count(catalog_doc(("a", "bundle")), "2.5"),
        "it is 2.5",
        False,
    ),
    (
        "4: two entries share an id",
        4,
        catalog_doc(("a", "bundle"), ("a", "bundle")),
        "precedence undecidable",
        False,
    ),
    (
        "4: an id that is not [a-z0-9-]+",
        4,
        catalog_doc(("A_Course", "bundle")),
        "must match [a-z0-9-]+",
        False,
    ),
    (
        "5: a source type the runner does not implement",
        5,
        catalog_doc(("a", "bundle")).replace(
            "      type: local", "      type: archive"
        ),
        "declared but not implemented",
        False,
    ),
    (
        "5: a local source with no path",
        5,
        catalog_doc(("a", "bundle")).replace("      path: bundle\n", ""),
        "requires a non-empty 'path'",
        False,
    ),
    (
        "6: the bundle directory is not there",
        6,
        catalog_doc(("a", "no-such-bundle")),
        "which is not a directory",
        False,
    ),
    (
        "6: the directory is not a bundle",
        6,
        catalog_doc(("a", "empty-dir")),
        "tutorial.yaml is missing",
        False,
    ),
    (
        "7: a bundle path leaves the catalogue's directory",
        7,
        catalog_doc(("a", "../outside-bundle")),
        "may only name bundles that travel with it",
        True,
    ),
]


def test_validator_catalog_mode() -> None:
    print("\nthe validator's catalogue mode, each check firing:")
    for label, check, text, expected, portable in CATALOG_CASES:
        with temp_env() as env:
            base = env.root / "cat"
            base.mkdir(parents=True, exist_ok=True)
            (base / "bundle").mkdir(exist_ok=True)
            (base / "bundle" / "tutorial.yaml").write_text("id: a\n")
            (base / "bundle" / "STATE.template.md").write_text("---\n---\n")
            (base / "empty-dir").mkdir(exist_ok=True)
            outside = env.root / "outside-bundle"
            outside.mkdir(exist_ok=True)
            (outside / "tutorial.yaml").write_text("id: a\n")
            (outside / "STATE.template.md").write_text("---\n---\n")
            target = base / "catalog.yaml"
            target.write_text(text, encoding="utf-8")
            report = vb.validate_catalog(target, portable)
            hits = [f for f in report.findings if f.check == check]
            if not hits:
                record(
                    False,
                    label,
                    f"check {check} did not fire. Findings: "
                    + ("; ".join(str(f) for f in report.findings) or "(none)"),
                )
                continue
            if not any(expected in h.message for h in hits):
                record(
                    False,
                    label,
                    f"check {check} fired but no message contained "
                    f"{expected!r}: " + " || ".join(h.message for h in hits),
                )
                continue
            _fired_catalog_checks.add(check)
            record(True, label)

    # The positive controls. Without them every case above would pass a
    # validator that rejected every catalogue.
    with temp_env() as env:
        base = env.root / "cat"
        base.mkdir(parents=True)
        env.make_bundle("cat/bundle")
        target = base / "catalog.yaml"
        target.write_text(catalog_doc(("a", "bundle")), encoding="utf-8")
        report = vb.validate_catalog(target, portable=False)
        record(
            report.exit_code() == 0,
            "a well-formed catalogue passes",
            "; ".join(str(f) for f in report.findings)
            or f"blocked = {report.blocked_checks}",
        )
        report = vb.validate_catalog(target, portable=True)
        record(
            report.exit_code() == 0,
            "and it passes --portable too, since its bundle travels with it",
            "; ".join(str(f) for f in report.findings),
        )
        record(
            report.status.get(7, ("", ""))[0] == vb.RAN,
            "check 7 actually RAN under --portable",
            repr(report.status.get(7)),
        )
        report = vb.validate_catalog(target, portable=False)
        record(
            report.status.get(7, ("", ""))[0] == vb.NOT_APPLICABLE,
            "and reports n/a without it, rather than quietly passing",
            repr(report.status.get(7)),
        )

        # optional_lesson_count: the four rejections above mean nothing
        # unless a well-formed count passes. Zero is legal and means the same
        # as omitting the field, so a generator that writes it is not fought.
        for value, label in (
            ("6", "a count of six passes"),
            ("0", "a count of zero passes - it says the same as omitting it"),
            ("1", "a count of one passes"),
        ):
            target.write_text(
                with_optional_count(catalog_doc(("a", "bundle")), value),
                encoding="utf-8",
            )
            report = vb.validate_catalog(target, portable=False)
            record(
                report.exit_code() == 0,
                f"optional_lesson_count: {label}",
                "; ".join(str(f) for f in report.findings),
            )
        target.write_text(catalog_doc(("a", "bundle")), encoding="utf-8")

    shipped = REPO / "skills" / "belay" / "catalog" / "builtin.yaml"
    report = vb.validate_catalog(shipped, portable=False)
    record(
        report.exit_code() == 0,
        "the shipped catalogue validates",
        "; ".join(str(f) for f in report.findings)
        or f"blocked = {report.blocked_checks}",
    )

    # The mode is never inferred: a bundle handed to catalogue mode fails,
    # and a catalogue handed to bundle mode fails.
    example = REPO / "skills" / "belay" / "examples" / "rust-cli-basics"
    quiet = io.StringIO()
    with redirect_stderr(quiet), redirect_stdout(quiet):
        as_bundle = vb.main([str(shipped)])
        bundle_as_catalog = vb.main(["--catalog", str(example)])
        portable_alone = vb.main(["--portable", str(example)])
    record(as_bundle != 0, "a catalogue checked as a BUNDLE fails", f"exit {as_bundle}")
    record(
        bundle_as_catalog == 2,
        "a bundle directory handed to --catalog is refused as a usage error",
        f"exit {bundle_as_catalog}",
    )
    record(
        portable_alone == 2,
        "--portable without --catalog is refused",
        f"exit {portable_alone}",
    )


# --------------------------------------------------------------------------
# The command-line surface
# --------------------------------------------------------------------------


def test_cli() -> None:
    print("\nthe command line:")
    with temp_env() as env:
        env.write_config(
            "catalogs_version: 1\ncatalogs:\n  - id: builtin\n"
            "    source: { type: bundled }\n"
        )
        code, text = env.run("discover")
        record(
            "Nothing under a bundle path was opened" in text,
            "discover states the rule it kept",
            text[:600],
        )
        code, text = env.run("status")
        record(
            "Nothing was fetched" in text and code == 0,
            "status says it fetched nothing",
            text[:600],
        )
    for argv in (["discover"], ["status"], ["resolve", "x"]):
        parser = cat.build_parser()
        args = parser.parse_args(argv)
        record(
            callable(getattr(args, "run", None)),
            f"the {argv[0]!r} subcommand is wired to a command",
            repr(args),
        )
    out = io.StringIO()
    err = io.StringIO()
    try:
        with redirect_stderr(err):
            cat.main([], stream=out)
        record(False, "a missing subcommand is refused", "it was accepted")
    except SystemExit as exc:
        record(exc.code == 2, "a missing subcommand is refused", f"exit {exc.code}")


# --------------------------------------------------------------------------
# Concept-based discovery and the relationship index
# --------------------------------------------------------------------------
#
# The fixture is the design's normative example: a broker that TEACHES the
# log model, a query engine that ASSUMES it, and a third-party course that
# names the broker as a previous bundle although the broker has never heard
# of it. Every behaviour below is one a reviewer can get wrong silently, so
# each has a fixture that would fail loudly if it were got wrong.

RELATIONSHIP_CATALOG = HERE / "fixtures" / "catalog-relationships" / "catalog.yaml"
OPTIONAL_CATALOG = HERE / "fixtures" / "catalog-optional-lessons" / "catalog.yaml"


def relationship_env(env: "Env") -> None:
    env.write_config(file_config(("rel", RELATIONSHIP_CATALOG)))


def why_kinds(match: dict) -> list[str]:
    kinds = [w["kind"] for w in match.get("why", [])]
    _fired_provenance.update(kinds)
    return kinds


def matched_ids(payload: dict) -> list[str]:
    for match in payload.get("matches", []):
        why_kinds(match)
    return [m["id"] for m in payload.get("matches", [])]


def find_match(payload: dict, identifier: str) -> dict | None:
    for match in payload.get("matches", []):
        if match["id"] == identifier:
            why_kinds(match)
            return match
    return None


def test_concept_query_exact_and_alias() -> None:
    print("\nconcept discovery, tiers 1 to 3:")
    with temp_env() as env:
        relationship_env(env)

        code, payload = env.run_json("covers", "partition-offsets")
        record(
            code == 0 and matched_ids(payload) == ["durable-event-broker"],
            "an exact covers id finds the bundle that teaches it",
            f"exit {code}, {matched_ids(payload)}",
        )
        match = find_match(payload, "durable-event-broker")
        record(
            "exact-concept" in why_kinds(match),
            "and the result says it was an exact concept match",
            repr(why_kinds(match)),
        )
        detail = next(
            w["detail"] for w in match["why"] if w["kind"] == "exact-concept"
        )
        record(
            detail == "Exact concept match: partition-offsets",
            "the explanation names the concept, in the design's own words",
            detail,
        )

        # The same concept, written the way a person says it out loud.
        code, spoken = env.run_json("covers", "Partition Offsets")
        record(
            matched_ids(spoken) == ["durable-event-broker"]
            and "exact-concept" in why_kinds(find_match(spoken, "durable-event-broker")),
            "a spoken phrase normalises onto the exact id, with no fuzzy match",
            f"{matched_ids(spoken)}",
        )

        code, payload = env.run_json("covers", "stream-offsets")
        match = find_match(payload, "durable-event-broker")
        record(
            code == 0 and matched_ids(payload) == ["durable-event-broker"],
            "a per-concept alias finds the bundle",
            f"exit {code}, {matched_ids(payload)}",
        )
        detail = next(
            (w["detail"] for w in match["why"] if w["kind"] == "concept-alias"), ""
        )
        record(
            detail.startswith("Alias match: stream-offsets"),
            "and it says which alias matched, and of which concept",
            detail,
        )

        code, payload = env.run_json("covers", "logical offsets")
        match = find_match(payload, "durable-event-broker")
        record(
            code == 0 and match is not None and "concept-text" in why_kinds(match),
            "words from a concept summary match at the text tier",
            f"exit {code}, {matched_ids(payload)}",
        )
        record(
            match is not None
            and any(
                "summary of retained-event-logs" in w["detail"]
                for w in match["why"]
                if w["kind"] == "concept-text"
            ),
            "and the explanation names the field the words were found in",
            repr(match and [w["detail"] for w in match["why"]]),
        )


def test_a_bundle_that_only_assumes_a_concept_does_not_teach_it() -> None:
    print("\nthe distinction the whole feature rests on:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("covers", "retained-event-logs")
        ids = matched_ids(payload)

        # streaming-query-engine assumes retained-event-logs at level
        # conceptual and covers nothing of the sort. A learner asking who
        # TEACHES it must never be sent to the course that starts where they
        # are stuck.
        record(
            "streaming-query-engine" not in ids,
            "a bundle that only ASSUMES the concept is not returned as "
            "covering it",
            f"it was returned: {ids}",
        )
        # Positive control: the same probe, against the same query, does find
        # the bundles that really do cover it. Without this, the assertion
        # above would pass just as well if the query matched nothing at all.
        record(
            ids == ["durable-event-broker", "log-replay-forensics"],
            "and the same query does find both bundles that DO cover it",
            f"{ids}",
        )
        engine = find_match(payload, "streaming-query-engine")
        record(engine is None, "no result at all carries that bundle", repr(engine))

        # The concept IS in its assumes - so the fixture really does exercise
        # the case, rather than passing because the metadata is absent.
        code, entries = env.run_json("discover")
        entry = next(
            e for e in entries["tutorials"] if e["id"] == "streaming-query-engine"
        )
        record(
            "retained-event-logs" in (entry.get("assumes") or {}),
            "the fixture really does assume the concept it must not be "
            "returned for",
            repr(sorted(entry.get("assumes") or {})),
        )
        record(
            "retained-event-logs" not in (entry.get("covers") or {}),
            "and really does not cover it",
            repr(sorted(entry.get("covers") or {})),
        )

        # A bundle may legally do both. log-replay-forensics assumes
        # retained-event-logs at working level AND teaches it deeper, and the
        # covering query must still return it.
        entry = next(
            e for e in entries["tutorials"] if e["id"] == "log-replay-forensics"
        )
        record(
            "retained-event-logs" in (entry.get("assumes") or {})
            and "retained-event-logs" in (entry.get("covers") or {}),
            "the overlap case is in the fixture: one bundle both assumes and "
            "covers one concept",
            repr(entry.get("assumes")),
        )
        record(
            "log-replay-forensics" in ids,
            "and it is returned, because what decides is `covers`",
            f"{ids}",
        )


def test_more_than_one_bundle_covers_a_concept() -> None:
    print("\nnever collapse to one result:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("covers", "retained event logs")
        ids = matched_ids(payload)
        record(
            len(ids) == 2 and set(ids) == {"durable-event-broker", "log-replay-forensics"},
            "two bundles cover one concept and both are returned",
            f"{ids}",
        )
        record(
            payload["match_count"] == 2,
            "the count in the machine-readable form agrees",
            repr(payload["match_count"]),
        )
        # durable-event-broker is the one named in
        # recommended_previous_bundles. The result must not shrink to it.
        record(
            ids[0] == "durable-event-broker" and ids[1] == "log-replay-forensics",
            "the recommended one ranks first without hiding the other",
            f"{ids}",
        )


def test_broad_subject_is_the_last_tier_and_never_a_recommendation() -> None:
    print("\nbroad subject fallback:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("covers", "event-streaming")
        ids = matched_ids(payload)
        record(
            code == 0 and len(ids) == 3,
            "a subject nobody declares as a concept still finds the bundles",
            f"exit {code}, {ids}",
        )
        for identifier in ids:
            match = find_match(payload, identifier)
            record(
                [w["kind"] for w in match["why"]] == ["broad-subject"],
                f"{identifier} matched only at the broad-subject tier",
                repr(match["why"]),
            )
            record(
                match["author_recommended"] is False,
                f"and {identifier} is NOT presented as an author recommendation",
                repr(match["author_recommended"]),
            )
            record(
                all(w["rank"] == 5 for w in match["why"]),
                f"and {identifier} ranks below every concept tier",
                repr(match["why"]),
            )
        _, text = env.run("covers", "event-streaming")
        record(
            "NOT author recommendations" in text
            and "[not an author recommendation]" in text,
            "the report says so on the section AND on every line",
            text[:400],
        )
        record(
            "recommended by an author" not in text,
            "and prints no author-recommendation section at all here",
            text[:400],
        )


def test_provenance_is_kept_when_a_bundle_arrives_by_several_routes() -> None:
    print("\nprovenance survives deduplication:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("covers", "retained-event-logs")
        ids = matched_ids(payload)
        record(
            ids.count("durable-event-broker") == 1,
            "the bundle appears exactly once, however many routes reached it",
            f"{ids}",
        )
        match = find_match(payload, "durable-event-broker")
        kinds = why_kinds(match)
        record(
            "exact-concept" in kinds and "recommended-previous" in kinds,
            "and it keeps BOTH the concept route and the recommendation route",
            repr(kinds),
        )
        declaring = sorted(
            w.get("bundle")
            for w in match["why"]
            if w["kind"] == "recommended-previous"
        )
        record(
            declaring == ["log-replay-forensics", "streaming-query-engine"],
            "two different authors recommended it, and both are kept "
            "separately",
            repr(declaring),
        )
        record(
            all(
                w.get("because")
                for w in match["why"]
                if w["kind"] == "recommended-previous"
            ),
            "each author's own reason travels with their recommendation",
            repr(match["why"]),
        )
        record(
            match["author_recommended"] is False,
            "and no route in a CONCEPT query is an author recommendation: "
            "both authors recommended a course ORDER, neither claimed this "
            "bundle teaches retained-event-logs",
            repr(match["author_recommended"]),
        )
        record(
            all(w["author_recommendation"] is False for w in match["why"]),
            "so every line is tagged as an inference while every author's own "
            "`because` still travels with it - the tag is narrowed, and no "
            "provenance is dropped",
            repr(match["why"]),
        )
        concept_routes = [
            w for w in match["why"] if w["kind"] == "exact-concept"
        ]
        record(
            concept_routes and all(
                w["author_recommendation"] is False for w in concept_routes
            ),
            "and the concept route is marked as NOT a recommendation, so the "
            "two claims never merge into one",
            repr(concept_routes),
        )


def test_follow_ups_read_the_reverse_index() -> None:
    print("\nthe reverse index - a third party attaches itself:")
    with temp_env() as env:
        relationship_env(env)
        code, entries = env.run_json("discover")
        broker = next(
            e for e in entries["tutorials"] if e["id"] == "durable-event-broker"
        )
        named = [r["bundle"] for r in broker.get("recommended_follow_ups") or []]
        record(
            "log-replay-forensics" not in named,
            "the broker does NOT name the third-party bundle anywhere",
            repr(named),
        )

        code, payload = env.run_json("follow-ups", "durable-event-broker")
        ids = matched_ids(payload)
        record(
            "log-replay-forensics" in ids,
            "yet follow-up discovery finds it, through its own "
            "recommended_previous_bundles",
            f"exit {code}, {ids}",
        )
        match = find_match(payload, "log-replay-forensics")
        record(
            "declared-previous" in why_kinds(match),
            "and says which direction the declaration came from",
            repr(match["why"]),
        )
        record(
            "log-replay-forensics names durable-event-broker"
            in match["why"][0]["detail"],
            "in words that name both bundles, so it cannot be mistaken for "
            "the broker's own recommendation",
            repr(match["why"][0]["detail"]),
        )
        record(
            match["why"][0]["because"].startswith("It builds the retained log"),
            "carrying the third party's own reason",
            repr(match["why"][0].get("because")),
        )


def test_forward_recommendations_keep_manifest_order() -> None:
    print("\nauthor order is display order:")
    doc = """catalog_version: 1
tutorials:
  - id: origin
    title: The origin course
    description: A course that recommends two follow-ups.
    subjects: [ordering]
    level: beginner
    workspace_kind: new-repository
    recommended_follow_ups:
      - bundle: zeta-course
        because: Take this one second in the alphabet but FIRST by the author.
      - bundle: alpha-course
        because: Take this one first in the alphabet but SECOND by the author.
    source: { type: local, path: origin }
  - id: alpha-course
    title: The alpha course
    description: Alphabetically first, and listed first in the catalogue.
    subjects: [ordering]
    level: beginner
    workspace_kind: new-repository
    source: { type: local, path: alpha }
  - id: zeta-course
    title: The zeta course
    description: Alphabetically last, and listed last in the catalogue.
    subjects: [ordering]
    level: beginner
    workspace_kind: new-repository
    source: { type: local, path: zeta }
"""
    with temp_env() as env:
        path = env.write_catalog("ordered.yaml", doc)
        env.write_config(file_config(("ordered", path)))
        code, payload = env.run_json("follow-ups", "origin")
        ids = matched_ids(payload)
        # Author order is zeta then alpha, which is neither alphabetical order
        # nor the order the catalogue lists them in. A sort by anything else
        # fails here.
        record(
            ids == ["zeta-course", "alpha-course"],
            "forward recommendations come back in the author's order, not "
            "alphabetical and not catalogue order",
            f"{ids}",
        )
        orders = [
            find_match(payload, i)["why"][0]["detail"] for i in ids
        ]
        record(
            all(d == "Recommended by origin as a follow-up" for d in orders),
            "and each says who recommended it",
            repr(orders),
        )


def test_follow_ups_put_the_authors_own_list_first() -> None:
    print("\nauthor-curated first, reverse-declared second, inferred last:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("follow-ups", "durable-event-broker")
        ids = matched_ids(payload)
        record(
            ids == ["streaming-query-engine", "log-replay-forensics"],
            "the bundle the author named comes before the one that named "
            "itself",
            f"{ids}",
        )
        engine = find_match(payload, "streaming-query-engine")
        kinds = why_kinds(engine)
        record(
            kinds[0] == "author-follow-up",
            "the author's own route ranks first on the bundle itself",
            repr(kinds),
        )
        record(
            "declared-previous" in kinds and "assumes-covered" in kinds,
            "and the other two routes to the same bundle are kept as well",
            repr(kinds),
        )
        inferred = [w for w in engine["why"] if w["kind"] == "assumes-covered"]
        record(
            inferred and all(w["author_recommendation"] is False for w in inferred),
            "the inferred route is flagged as inferred even on a bundle the "
            "author did recommend",
            repr(inferred),
        )
        record(
            any("Assumes retained-event-logs" in w["detail"] for w in inferred),
            "and it says which concept connects them",
            repr([w["detail"] for w in inferred]),
        )


def test_an_unavailable_recommendation_is_reported_not_fatal() -> None:
    print("\na recommendation nothing carries:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("follow-ups", "durable-event-broker")
        record(
            code == 0 and payload["matches"],
            "an unresolved forward recommendation does not fail the query",
            f"exit {code}",
        )
        unresolved = [u["bundle"] for u in payload["unresolved"]]
        record(
            unresolved == ["distributed-log-broker"],
            "the unresolved reference is named rather than dropped",
            repr(payload["unresolved"]),
        )
        record(
            all(m["id"] != "distributed-log-broker" for m in payload["matches"]),
            "and it is not offered as though it were available",
            repr(matched_ids(payload)),
        )
        _, text = env.run("follow-ups", "durable-event-broker")
        record(
            "no configured catalogue carries it" in text,
            "the report says why it is not in the list",
            text[-500:],
        )


def test_prepare_searches_covers_against_assumes() -> None:
    print("\npreparing for a bundle:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("prepare", "streaming-query-engine")
        ids = matched_ids(payload)
        record(
            code == 0 and ids == ["durable-event-broker", "log-replay-forensics"],
            "every bundle covering an assumed concept is offered, not just "
            "the one the author named",
            f"exit {code}, {ids}",
        )
        broker = find_match(payload, "durable-event-broker")
        kinds = why_kinds(broker)
        record(
            "author-previous" in kinds,
            "the author's own previous-bundle recommendation is there",
            repr(kinds),
        )
        record(
            "declared-follow-up" in kinds,
            "so is the reverse route, because the broker names it as a "
            "follow-up",
            repr(kinds),
        )
        record(
            "covers-assumed" in kinds,
            "so is the concept route",
            repr(kinds),
        )
        concepts = sorted(
            w["concept"] for w in broker["why"] if w["kind"] == "covers-assumed"
        )
        record(
            concepts == ["partition-offsets", "retained-event-logs", "topic-partitions"],
            "with one entry per assumed concept it covers",
            repr(concepts),
        )
        other = find_match(payload, "log-replay-forensics")
        record(
            other["author_recommended"] is False
            and why_kinds(other) == ["covers-assumed"],
            "a bundle reached only by concept is not shown as recommended",
            repr(other["why"]),
        )
        uncovered = " ".join(payload["notes"])
        record(
            "go-programming" in uncovered and "consumer-offsets" in uncovered,
            "an assumed concept nothing covers is said out loud, not left as "
            "a silent gap in the list",
            repr(payload["notes"]),
        )


def test_tier_4_never_answers_covers_with_a_bundle_that_only_assumes() -> None:
    """Regression. Tier 4 returned a bundle that only ASSUMED the concept.

    `go-programming` is assumed at level `working` by durable-event-broker and
    by streaming-query-engine, and is covered by nothing in this catalogue.
    Tier 4 read `assumes` to find who NEEDS the concept, then returned the
    predecessor that author recommends without ever checking whether that
    predecessor TEACHES it - so `covers go-programming` answered
    durable-event-broker, tagged `[author recommendation]`, although that
    bundle covers only group-commit, partition-offsets, retained-event-logs
    and topic-partitions and assumes working Go.

    A learner stuck on Go was sent to a course that requires working Go: the
    first entry on catalogue-format.md section 12.8's refusal list.
    """
    print("\nregression: `covers` never answers with a bundle that only assumes:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json("covers", "go-programming")
        ids = matched_ids(payload)
        record(
            ids == [],
            "a concept every bundle only ASSUMES has no answer at all",
            f"exit {code}, {ids}",
        )
        record(
            "durable-event-broker" not in ids,
            "and in particular not the predecessor an author recommends, "
            "which assumes go-programming and never covers it",
            f"{ids}",
        )
        record(
            code == 3,
            "the command reports 'nothing matched' rather than success",
            repr(code),
        )
        _, prep = env.run_json("prepare", "streaming-query-engine")
        record(
            any(
                "no available bundle covers go-programming" in note
                for note in prep["notes"]
            ),
            "and the sibling `prepare` command agrees about the same fact "
            "instead of contradicting it",
            repr(prep["notes"]),
        )
        # POSITIVE CONTROLS, in the same test. The cheap wrong repair here is
        # to switch tier 4 off; both of these fail if it is off.
        code, payload = env.run_json("covers", "group-commit")
        ids = matched_ids(payload)
        record(
            code == 0 and ids == ["durable-event-broker"],
            "control: the same query shape still returns the bundle for a "
            "concept that bundle genuinely covers",
            f"exit {code}, {ids}",
        )
        code, payload = env.run_json("covers", "retained-event-logs")
        match = find_match(payload, "durable-event-broker")
        kinds = why_kinds(match)
        record(
            code == 0 and "recommended-previous" in kinds,
            "control: tier 4 was narrowed, not disabled - it still fires "
            "where the recommended predecessor really does cover the concept",
            repr(kinds),
        )
        _, prep = env.run_json("prepare", "streaming-query-engine")
        previous = find_match(prep, "durable-event-broker")
        record(
            previous["author_recommended"] is True
            and any(w["kind"] == "author-previous" for w in previous["why"]),
            "control: the author's sentence is STILL an author recommendation "
            "in `prepare`, where it answers the question it was written for",
            repr(previous["why"]),
        )


def test_a_recommended_previous_bundle_answers_a_concept_query() -> None:
    print("\ntier 4 - a recommended bundle that COVERS the concept:")
    # The design ranks at 4 an "explicit recommended previous bundle THAT
    # COVERS THE CONCEPT". Both halves are exercised here: `thin-broker` is
    # recommended AND covers group-commit, `hollow-broker` is recommended by
    # the same author and does NOT.
    #
    # The query is deliberately wording that appears ONLY in the assuming
    # bundle's summary, so no other tier can reach thin-broker. That is what
    # makes this tier worth having: the course that teaches a concept and the
    # course that assumes it often describe it in different words, and tier 4
    # is the bridge between the two vocabularies.
    doc = """catalog_version: 1
tutorials:
  - id: thin-broker
    title: The thin broker course
    description: A course that teaches the commit path.
    subjects: [messaging]
    level: beginner
    workspace_kind: new-repository
    covers:
      group-commit:
        summary: One fsync is shared by many writes, which is what makes a log fast.
    source: { type: local, path: thin }
  - id: hollow-broker
    title: The hollow broker course
    description: A course the same author recommends, teaching something else.
    subjects: [messaging]
    level: beginner
    workspace_kind: new-repository
    covers:
      message-framing:
        summary: Where one message ends and the next one begins.
    source: { type: local, path: hollow }
  - id: engine
    title: The engine course
    description: A course that assumes a concept and says where to learn it.
    subjects: [querying]
    level: advanced
    workspace_kind: new-repository
    assumes:
      group-commit:
        level: working
        summary: Many writes share one fsync, and you can reason about the durability window.
    recommended_previous_bundles:
      - bundle: thin-broker
        because: It builds the commit path this course measures.
      - bundle: hollow-broker
        because: It is a gentler introduction to the broker itself.
    source: { type: local, path: engine }
"""
    with temp_env() as env:
        path = env.write_catalog("tier4.yaml", doc)
        env.write_config(file_config(("tier4", path)))
        code, payload = env.run_json("covers", "durability window")
        ids = matched_ids(payload)
        record(
            ids == ["thin-broker"],
            "the recommended bundle that COVERS the concept is returned, and "
            "the bundle that merely assumes it is not",
            f"exit {code}, {ids}",
        )
        record(
            "hollow-broker" not in ids,
            "and neither is the bundle the same author recommends in the same "
            "list that does NOT cover the concept",
            f"{ids}",
        )
        match = find_match(payload, "thin-broker")
        record(
            why_kinds(match) == ["recommended-previous"],
            "tier 4 is the ONLY route that reached it, so this tier really is "
            "doing work no other tier does",
            repr(match["why"]),
        )
        record(
            "group-commit" in match["covers"],
            "and the bundle returned declares the concept in its own `covers`",
            repr(sorted(match["covers"])),
        )
        record(
            match["why"][0]["rank"] == 4,
            "it ranks below every direct concept match",
            repr(match["why"][0]["rank"]),
        )
        record(
            match["why"][0]["author_recommendation"] is False
            and match["author_recommended"] is False,
            "and it is honestly labelled: engine's author recommended a course "
            "ORDER, never that thin-broker teaches group-commit, so inside a "
            "concept query this route is an inference",
            repr(match["why"][0]),
        )
        record(
            "engine" in match["why"][0]["detail"]
            and match["why"][0]["because"].startswith("It builds the commit path"),
            "the explanation still names the author who recommended it and "
            "carries that author's own reason, so nothing is lost",
            repr(match["why"][0]),
        )


def test_the_query_needle_is_guarded() -> None:
    print("\nthe needle is guarded, and the probe is shown finding something:")
    with temp_env() as env:
        relationship_env(env)
        # Positive control FIRST: this probe can and does report a match.
        code, payload = env.run_json("covers", "group-commit")
        record(
            code == 0 and matched_ids(payload) == ["durable-event-broker"],
            "the probe finds a concept that is really there",
            f"exit {code}, {matched_ids(payload)}",
        )
        for empty in ("   ", "!!", "?? ..."):
            code, payload = env.run_json("covers", empty)
            record(
                code == 2 and payload.get("found") is False,
                f"a query of {empty!r} is refused as a usage error, not "
                f"answered with every bundle",
                f"exit {code}, {payload}",
            )
        code, payload = env.run_json("covers", "no-such-concept-anywhere")
        record(
            code == 3 and payload["matches"] == [],
            "a query that names nothing returns nothing, and says so with "
            "exit 3",
            f"exit {code}, {payload.get('match_count')}",
        )
        code, payload = env.run_json("follow-ups", "no-such-bundle")
        record(
            code == 3 and payload.get("found") is False,
            "an unknown bundle id is refused and the available ids are named",
            repr(payload),
        )
        record(
            "durable-event-broker" in (payload.get("available") or []),
            "including the ones that do exist",
            repr(payload.get("available")),
        )


def test_question_words_are_a_second_pass_and_are_announced() -> None:
    print("\na whole question, rather than a concept id:")
    with temp_env() as env:
        relationship_env(env)
        code, payload = env.run_json(
            "covers", "which tutorial teaches retained event logs"
        )
        ids = matched_ids(payload)
        record(
            ids == ["durable-event-broker", "log-replay-forensics"],
            "a question sentence still reaches the exact concept",
            f"exit {code}, {ids}",
        )
        record(
            any("question words removed" in n for n in payload["notes"]),
            "and the looser pass is announced, never passed off as a direct "
            "hit",
            repr(payload["notes"]),
        )
        match = find_match(payload, "durable-event-broker")
        record(
            "exact-concept" in why_kinds(match),
            "the second pass still uses the exact tiers, not a fuzzy match",
            repr(match["why"]),
        )
        # The stripping never damages a query that already works.
        code, direct = env.run_json("covers", "retained-event-logs")
        record(
            direct["notes"] == [],
            "a query that works as written is never re-run with words removed",
            repr(direct["notes"]),
        )


def test_concept_discovery_needs_no_service_and_no_bundle() -> None:
    print("\ndeterministic, offline, and still metadata-only:")
    with temp_env() as env:
        relationship_env(env)
        for path in ("durable-event-broker", "streaming-query-engine"):
            record(
                not (RELATIONSHIP_CATALOG.parent / path).exists(),
                f"the fixture's {path} bundle directory really is absent",
                "it exists",
            )
        with path_only(env.empty_bin):
            record(
                shutil.which("git") is None,
                "git is not on PATH for this check",
                repr(shutil.which("git")),
            )
            code, payload = env.run_json("covers", "partition-offsets")
            record(
                code == 0 and matched_ids(payload) == ["durable-event-broker"],
                "an exact concept query answers with no git, no network and "
                "no bundle on disk",
                f"exit {code}, {matched_ids(payload)}",
            )
            record(
                payload["semantic_matching"] is False,
                "and it reports that no semantic matcher was involved",
                repr(payload.get("semantic_matching")),
            )
        first = env.run_json("covers", "offsets")[1]
        second = env.run_json("covers", "offsets")[1]
        record(
            matched_ids(first) == matched_ids(second)
            and [w["kind"] for m in first["matches"] for w in m["why"]]
            == [w["kind"] for m in second["matches"] for w in m["why"]],
            "the same query gives the same answer, in the same order",
            f"{matched_ids(first)} vs {matched_ids(second)}",
        )
        record(
            matched_ids(first) == ["durable-event-broker"]
            and "concept-text" in why_kinds(first["matches"][0]),
            "a bare word reaches the concept whose id carries it, at the "
            "text tier and not as an exact match",
            f"{matched_ids(first)}: "
            f"{first['matches'] and first['matches'][0]['why']}",
        )


def test_relationship_metadata_never_removes_a_tutorial() -> None:
    print("\nmalformed relationship metadata is a note, not a lost course:")
    doc = """catalog_version: 1
tutorials:
  - id: broken-metadata
    title: The broken metadata course
    description: A course whose optional relationship metadata is wrong.
    subjects: [testing]
    level: beginner
    workspace_kind: new-repository
    covers:
      Not A Concept Id:
        summary: The id is not [a-z0-9-]+.
      no-summary-here:
        aliases: [something]
      fine-concept:
        summary: This one is correct and must survive its broken neighbours.
    assumes:
      wrong-level:
        level: expert
        summary: There is no such level as expert.
    recommended_follow_ups:
      - bundle: broken-metadata
        because: A bundle may not recommend itself.
      - bundle: no-reason-given
    source: { type: local, path: broken }
"""
    with temp_env() as env:
        path = env.write_catalog("broken.yaml", doc)
        env.write_config(file_config(("broken", path)))
        code, payload = env.run_json("discover")
        record(
            code == 0 and [e["id"] for e in payload["tutorials"]] == ["broken-metadata"],
            "the tutorial is still offered - relationship metadata is "
            "optional, and a mistake in it must not hide a working course",
            f"exit {code}",
        )
        code, payload = env.run_json("covers", "fine-concept")
        record(
            matched_ids(payload) == ["broken-metadata"],
            "the concepts that are well formed still match",
            f"{matched_ids(payload)}",
        )
        notes = " ".join(payload["index_notes"])
        for fragment, label in (
            ("Not A Concept Id", "a concept id that is not [a-z0-9-]+"),
            ("no-summary-here", "a concept with no summary"),
            ("expert", "an assumes level that is not one of the four"),
            ("recommends the bundle itself", "a self-recommendation"),
            ("no 'because'", "a recommendation with no reason"),
        ):
            record(
                fragment in notes,
                f"{label} is reported rather than silently dropped",
                notes[:600],
            )
        code, payload = env.run_json("covers", "no-summary-here")
        record(
            code == 3 and payload["matches"] == [],
            "and a concept that was dropped does not match, so the note is "
            "the only place it appears",
            f"exit {code}",
        )


def test_entries_without_the_new_fields_still_work() -> None:
    print("\nbackward compatibility:")
    with temp_env() as env:
        mine = env.write_catalog("plain.yaml", catalog_doc(("plain", "bundles/plain")))
        env.write_config(file_config(("plain", mine)))
        code, payload = env.run_json("discover")
        record(
            code == 0 and [e["id"] for e in payload["tutorials"]] == ["plain"],
            "a catalogue with none of the four new fields still discovers",
            f"exit {code}",
        )
        code, payload = env.run_json("follow-ups", "plain")
        record(
            code == 3 and payload["matches"] == [] and payload["unresolved"] == [],
            "asking for its follow-ups is an empty answer, not an error",
            repr(payload),
        )
        code, payload = env.run_json("prepare", "plain")
        record(
            code == 3 and payload["matches"] == [],
            "and so is asking how to prepare for it",
            repr(payload),
        )
        code, payload = env.run_json("covers", "testing")
        record(
            code == 0 and matched_ids(payload) == ["plain"],
            "its `subjects` still match, at the broad tier",
            f"exit {code}, {matched_ids(payload)}",
        )


def entry_block(text: str, identifier: str) -> str:
    """The lines of one entry in a `discover` listing.

    A listing is one block per entry, each starting at a line whose first
    non-blank token is the id. Slicing to the block is what lets a test
    assert that a line is ABSENT from one entry while present in another; a
    substring search over the whole listing cannot tell those apart.
    """
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith(f"  {identifier}  [")
    ]
    if not starts:
        return ""
    start = starts[0]
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("  ") and not lines[index].startswith("    "):
            return "\n".join(lines[start:index])
    return "\n".join(lines[start:])


def test_optional_lesson_count_is_carried_by_the_entry() -> None:
    """`scope` counts the main path; this is what says there is more.

    Three entries with the SAME `scope`, differing only in what they say
    about optional lessons. Without the field the first two are
    indistinguishable at discovery time, and a runner may not open a bundle
    to tell them apart.
    """
    print("\noptional lessons are visible in the entry, not in the bundle:")
    with temp_env() as env:
        env.write_config(file_config(("opt", OPTIONAL_CATALOG)))
        code, payload = env.run_json("discover")
        offered = [e["id"] for e in payload["tutorials"]]
        record(
            code == 0
            and offered == ["with-optional", "without-optional", "broken-optional"],
            "every entry is offered, including the one whose count is "
            "unusable - a typo in optional metadata never removes a course",
            f"exit {code}, {offered}",
        )
        by_id = {e["id"]: e for e in payload["tutorials"]}

        record(
            by_id["with-optional"]["optional_lesson_count"] == 6
            and by_id["with-optional"]["metadata_notes"] == [],
            "an entry that carries the field reports the count, with no note",
            repr(by_id["with-optional"].get("optional_lesson_count")),
        )
        record(
            by_id["without-optional"]["optional_lesson_count"] is None
            and by_id["without-optional"]["metadata_notes"] == [],
            "an entry that omits it reports null - 'this catalogue does not "
            "say', which is not the same claim as zero",
            repr(by_id["without-optional"].get("optional_lesson_count")),
        )
        record(
            by_id["broken-optional"]["optional_lesson_count"] is None,
            "an unusable value is normalised to null rather than handed on, "
            "so no consumer can read 'several' as a count",
            repr(by_id["broken-optional"].get("optional_lesson_count")),
        )
        notes = " ".join(by_id["broken-optional"]["metadata_notes"])
        record(
            "optional_lesson_count" in notes and "several" in notes,
            "and the note names the field and the value that was refused",
            notes or "(no note)",
        )
        record(
            "still offered" in notes,
            "the note says the course is still offered, so the runner does "
            "not report it as broken",
            notes or "(no note)",
        )

        # The same three facts in the text a runner actually reads.
        code, text = env.run("discover")
        with_block = entry_block(text, "with-optional")
        without_block = entry_block(text, "without-optional")
        broken_block = entry_block(text, "broken-optional")
        record(
            bool(with_block) and bool(without_block) and bool(broken_block),
            "the listing carries a block for each of the three entries",
            f"{len(with_block)}, {len(without_block)}, {len(broken_block)}",
        )
        record(
            "6 optional lessons beside the main path" in with_block,
            "the count is rendered as a sentence a learner can act on",
            with_block,
        )
        record(
            "optional:" not in without_block
            and "metadata problem" not in without_block,
            "and the entry that says nothing renders nothing - the line is "
            "not printed with a zero or an 'unknown'",
            without_block,
        )
        record(
            with_block.index("scope:") < with_block.index("optional:")
            < with_block.index("workspace_kind:"),
            "it sits directly after `scope`, which it qualifies, and does "
            "not push in among the fields a choice is made on",
            with_block,
        )
        record(
            "metadata problem" in broken_block
            and "optional_lesson_count" in broken_block,
            "the unusable value is a note on the entry, not a lost course",
            broken_block,
        )
        record(
            "title:" in broken_block and "scope:" in broken_block,
            "which still shows every sound field it has",
            broken_block,
        )

        # Nothing above may have opened a bundle. The fixture's bundle
        # directories do not exist, so a reader that counted lessons itself
        # could not have produced any of these answers.
        for entry in payload["tutorials"]:
            record(
                not (OPTIONAL_CATALOG.parent / entry["id"]).exists(),
                f"{entry['id']}: its bundle is not on disk, so the count can "
                f"only have come from the catalogue entry",
                str(OPTIONAL_CATALOG.parent / entry["id"]),
            )


def test_the_tolerant_reader_accepts_only_a_whole_count() -> None:
    """The reader, on its own, against the values an entry can carry.

    Every rejected value must come back as `(None, one note)` - dropped, and
    said out loud. Every accepted value must come back as the number with no
    note. Both halves are here because a reader that rejected everything
    would pass a table of rejections alone.
    """
    print("\nthe tolerant reader, value by value:")
    accepted: list[tuple[Any, int]] = [(0, 0), (1, 1), (6, 6), (140, 140)]
    for value, expected in accepted:
        count, notes = cat.read_optional_lesson_count(
            {"optional_lesson_count": value}, "an-entry"
        )
        record(
            count == expected and type(count) is int and notes == [],
            f"{value!r} is read as the count {expected}",
            f"count={count!r} notes={notes}",
        )
    rejected: list[tuple[Any, str]] = [
        ("6", "a count written as a string is not a count"),
        ("several", "a word is not a count"),
        (-1, "a negative count"),
        (2.5, "a fraction of a lesson"),
        (True, "a YAML boolean, which is an int in Python"),
        (False, "the other boolean, which would otherwise read as zero"),
        ([6], "a list"),
        ({"count": 6}, "a mapping"),
        (None, "an explicit null, which says nothing usable"),
    ]
    for value, label in rejected:
        count, notes = cat.read_optional_lesson_count(
            {"optional_lesson_count": value}, "an-entry"
        )
        record(
            count is None and len(notes) == 1 and "an-entry" in notes[0],
            f"{label} is dropped with one note naming the entry  ({value!r})",
            f"count={count!r} notes={notes}",
        )
    count, notes = cat.read_optional_lesson_count({"id": "an-entry"}, "an-entry")
    record(
        count is None and notes == [],
        "an entry that does not carry the field is silent, not a note - "
        "omitting it is the normal way to write a course with none",
        f"count={count!r} notes={notes}",
    )


def test_an_optional_lesson_count_of_zero_says_nothing_extra() -> None:
    print("\na count of zero reads as the course scope already did:")
    with temp_env() as env:
        doc = with_optional_count(catalog_doc(("plain", "bundles/plain")), "0")
        path = env.write_catalog("zero.yaml", doc)
        env.write_config(file_config(("zero", path)))
        code, payload = env.run_json("discover")
        record(
            code == 0 and payload["tutorials"][0]["optional_lesson_count"] == 0,
            "zero is a legal value and is read as zero, not refused",
            f"exit {code}, {payload['tutorials'][0].get('optional_lesson_count')}",
        )
        record(
            payload["tutorials"][0]["metadata_notes"] == [],
            "and carries no note, because nothing is wrong with it",
            repr(payload["tutorials"][0]["metadata_notes"]),
        )
        code, text = env.run("discover")
        record(
            "optional:" not in entry_block(text, "plain"),
            "it renders no optional line - 0 optional lessons is the course "
            "`scope` already described",
            entry_block(text, "plain"),
        )


def test_a_bad_optional_lesson_count_is_refused_by_the_validator() -> None:
    """The other half of "the reader is tolerant; the validator is strict".

    The reader kept `broken-optional` discoverable above. The validator must
    reject the very same file, or the split is only half implemented and an
    author is never told.
    """
    print("\nthe validator rejects the value the reader tolerated:")
    report = vb.validate_catalog(OPTIONAL_CATALOG, portable=False)
    hits = [
        f
        for f in report.findings
        if f.check == 3 and "optional_lesson_count" in f.message
    ]
    record(
        len(hits) == 1 and "broken-optional" in hits[0].where,
        "exactly the broken entry is reported, by name, under check 3",
        "; ".join(str(f) for f in report.findings) or "(no findings)",
    )
    if hits:
        _fired_catalog_checks.add(3)
    record(
        report.exit_code() != 0,
        "and the catalogue does not pass, because an author asked to be told",
        f"exit_code {report.exit_code()}",
    )
    sound = [
        f
        for f in report.findings
        if f.check == 3 and "optional_lesson_count" in f.message
        and ("with-optional" in f.where or "without-optional" in f.where)
    ]
    record(
        not sound,
        "the two sound entries are not reported - a check that flagged all "
        "three would pass this test while meaning nothing",
        "; ".join(str(f) for f in sound),
    )


def test_a_cached_catalogue_is_said_so_before_nothing_matched() -> None:
    print("\nhonesty when a catalogue is missing from a concept query:")
    with temp_env() as env:
        env.write_config(
            file_config(
                ("rel", RELATIONSHIP_CATALOG),
                ("gone", env.root / "not-written.yaml"),
            )
        )
        code, text = env.run("covers", "partition-offsets")
        record(
            code == 1,
            "a query whose catalogues did not all answer exits 1, not 0",
            f"exit {code}",
        )
        record(
            "could not be served at all" in text,
            "and says which catalogue is missing from the answer",
            text[:600],
        )
        record(
            text.index("could not be served at all") < text.index("bundles that COVER"),
            "before the results, so 'nothing matched' can never be read as "
            "'nothing exists'",
            text[:600],
        )
        code, text = env.run("covers", "nothing-here-at-all")
        record(
            "could not be served at all" in text and "(no bundle matched)" in text,
            "the same holds when the answer really is empty",
            text[:600],
        )


def test_provenance_kind_coverage() -> None:
    print("\nmeta: every provenance kind has a fixture that makes it fire:")
    for kind, (rank, recommendation, description) in sorted(
        cat.PROVENANCE_KINDS.items()
    ):
        record(
            kind in _fired_provenance,
            f"provenance kind {kind!r} was demonstrated firing  "
            f"({description[:48]})",
            "NO fixture in this suite produces this kind, so it is a false "
            "oracle: it can only be shown not happening.",
        )
    record(
        cat.SEMANTIC_MATCHING_AVAILABLE is False
        and "semantic" not in cat.PROVENANCE_KINDS,
        "the semantic tier is absent rather than declared-and-never-fired",
        repr(cat.SEMANTIC_MATCHING_AVAILABLE),
    )


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------


def test_kind_coverage() -> None:
    print("\nmeta: every failure kind has a fixture that makes it fire:")
    for kind in sorted(cat.FAILURE_KINDS):
        record(
            kind in _fired_kinds,
            f"kind {kind!r} was demonstrated firing",
            "NO fixture in this suite produces this kind, so it is a false "
            "oracle: it can only be shown not happening.",
        )


def test_catalog_check_coverage() -> None:
    print("\nmeta: every catalogue check has a fixture that makes it fire:")
    for number, description in sorted(vb.CATALOG_CHECKS.items()):
        record(
            number in _fired_catalog_checks,
            f"catalogue check {number} was demonstrated firing  "
            f"({description[:52]})",
            "NO fixture in this suite makes this check report a finding.",
        )


# --------------------------------------------------------------------------


def main() -> int:
    print("catalogs.py test suite")
    print(f"  script:      {SCRIPTS / 'catalogs.py'}")
    print(f"  yaml reader: {cat.YAML_READER}")
    print(f"  python:      {sys.version.split()[0]}")
    real_git = shutil.which("git")
    print(f"  git:         {real_git}")
    if real_git is None:
        print("\nFAILED - this suite needs a real git for its positive control.")
        return 1

    for test in (
        test_classifier,
        test_unreachable_and_no_access,
        test_no_git_binary,
        test_real_git_success_and_failures,
        test_file_catalogue_failures,
        test_bundled_catalogue,
        test_stale_fallback,
        test_cache_is_not_reused_across_sources,
        test_unavailable_is_reported,
        test_precedence_and_override_reporting,
        test_implied_default_keeps_the_old_two_file_model,
        test_discovery_never_opens_a_bundle,
        test_remote_catalogue_cannot_reach_outside_itself,
        test_malformed_entries_are_skipped_not_fatal,
        test_containment_is_decided_the_same_way_for_every_root,
        test_the_validator_root_and_escapes_agree,
        test_configuration_errors,
        test_offline,
        test_validator_catalog_mode,
        test_cli,
        test_concept_query_exact_and_alias,
        test_a_bundle_that_only_assumes_a_concept_does_not_teach_it,
        test_more_than_one_bundle_covers_a_concept,
        test_broad_subject_is_the_last_tier_and_never_a_recommendation,
        test_provenance_is_kept_when_a_bundle_arrives_by_several_routes,
        test_follow_ups_read_the_reverse_index,
        test_forward_recommendations_keep_manifest_order,
        test_follow_ups_put_the_authors_own_list_first,
        test_an_unavailable_recommendation_is_reported_not_fatal,
        test_prepare_searches_covers_against_assumes,
        test_tier_4_never_answers_covers_with_a_bundle_that_only_assumes,
        test_a_recommended_previous_bundle_answers_a_concept_query,
        test_the_query_needle_is_guarded,
        test_question_words_are_a_second_pass_and_are_announced,
        test_concept_discovery_needs_no_service_and_no_bundle,
        test_relationship_metadata_never_removes_a_tutorial,
        test_entries_without_the_new_fields_still_work,
        test_optional_lesson_count_is_carried_by_the_entry,
        test_the_tolerant_reader_accepts_only_a_whole_count,
        test_an_optional_lesson_count_of_zero_says_nothing_extra,
        test_a_bad_optional_lesson_count_is_refused_by_the_validator,
        test_a_cached_catalogue_is_said_so_before_nothing_matched,
    ):
        try:
            test()
        except Exception:  # pragma: no cover
            record(False, test.__name__, "raised:\n" + traceback.format_exc())

    test_kind_coverage()
    test_catalog_check_coverage()
    test_provenance_kind_coverage()

    if _notes:
        print("\nnotes:")
        for text in _notes:
            print(text)

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
