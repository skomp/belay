#!/usr/bin/env python3
"""The catalog's `certificate` block, and `belay-grade certificate`.

The design is docs/superpowers/specs/2026-11-05-final-project-and-certificate-design.md,
sections 3 to 5. The block's shape is the validator's business (catalog check 10); this
reads it only after `validate_catalog` reports nothing, so a malformed block is
refused with the validator's own findings and never half-read.

The certificate reads only `final.json` files: each listed bundle's, and each
further attempt's under <bundle>/makeup/<participant>/. An archived final.<date>.json
is never a result; it is read only to count the attempts used (grade.attempts_used).
Everything is computed before anything is written, so every refusal writes nothing,
and the output is built in a temporary directory beside <cohort>/certificate/ and
renamed into place.

grade.py imports this lazily, inside the commands that need it, so there is no
import cycle at load time.

Stdlib only, Python 3.11, and the shared restricted reader yamlite.py.
"""

from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import grade
    import validate_bundle
    from grade import GradeError
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import grade
    import validate_bundle
    from grade import GradeError
    from yamlite import YamlError, load_yaml


@dataclass(frozen=True)
class Certificate:
    title: str
    modules: tuple[str, ...]
    final_project: tuple[str, ...]
    share: int  # final_project_share: the percent of the final project's points required


def load_certificate(catalog: Path) -> Certificate:
    """The catalog's `certificate`, or a refusal naming every finding of the validator."""
    catalog = Path(catalog)
    report = validate_bundle.validate_catalog(catalog, portable=False)
    if report.findings:
        raise GradeError(
            f"the catalog {catalog} is refused, because the catalog validator reports it "
            "(belay-validate --catalog shows the same):\n  "
            + "\n  ".join(str(f) for f in report.findings))
    try:
        document = load_yaml(catalog.read_text(encoding="utf-8"), str(catalog))
    except (OSError, YamlError) as exc:  # the validator read it; this is a race
        raise GradeError(f"cannot read the catalog {catalog}: {exc}") from exc
    block = document.get("certificate") if isinstance(document, dict) else None
    if block is None:
        raise GradeError(
            f"the catalog {catalog} has no `certificate`, so it states no programme and no "
            "further attempt can count towards one (final-project-and-certificate spec, section 3)")
    return Certificate(
        title=block["title"],
        modules=tuple(block["modules"]),
        final_project=tuple(block["final_project"]),
        share=block["final_project_share"],
    )


def kind_of(cert: Certificate, bundle_id: str) -> Literal["module", "final_project"]:
    """Where the certificate lists a bundle; a bundle in neither list has no further attempts."""
    if bundle_id in cert.modules:
        return "module"
    if bundle_id in cert.final_project:
        return "final_project"
    raise GradeError(
        f"the certificate does not list {bundle_id} (modules: {', '.join(cert.modules)}; "
        f"final_project: {', '.join(cert.final_project)}), so nothing would read a further "
        "attempt at it")


# --------------------------------------------------------------------------
# belay-grade certificate (spec sections 3, 4 and 5)
# --------------------------------------------------------------------------

OUTPUT_DIR = "certificate"
NAMES_HEADER = ["participant", "full name"]
RESULTS_HEADER = ["full name", "result"]
PASSED, NOT_PASSED = "passed", "not passed"
PLACEHOLDERS = ("name", "programme", "date")
_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
HTML_SUFFIXES = (".html", ".htm")
# A spreadsheet runs a cell starting with one of these as a formula (the plan's second decision).
FORMULA_LEADS = ("=", "+", "-", "@", "\t", "\r")
NAMES_MAX_BYTES = 4 * 1024 * 1024
TEMPLATE_MAX_BYTES = 4 * 1024 * 1024


@dataclass
class Outcome:
    """One participant's certificate result.

    `requirements` holds (requirement, result, reason): "module <id>" for each module
    and "final project" once, with "passed" or "not passed". `further_attempts` and
    `read` are what details.json records besides.
    """
    passed: bool
    requirements: list[tuple[str, str, str]]
    further_attempts: list[dict] = field(default_factory=list)
    read: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class _Final:
    """One final.json that was read: where (relative to the cohort store), and what."""
    file: str
    data: dict

    @property
    def stamp(self) -> dict:
        at = self.data.get("confirmed_at")
        return {"file": self.file, "confirmed_at": at if isinstance(at, str) else None}


def _safe_id(ident: str, what: str) -> str:
    if not grade._PARTICIPANT.fullmatch(ident) or ident == grade.CACHE_NAME:
        raise GradeError(f"{grade.escape_name(ident)!r} is not usable as {what}")
    return ident


def _read_final(root: Path, relative: str) -> _Final:
    data = grade.read_json_file(root / relative, f"the confirmed grades {relative}",
                                grade.JUDGEMENT_MAX_BYTES * 8)
    if not isinstance(data, dict):
        raise GradeError(f"{root / relative} is damaged: it is not an object")
    return _Final(relative, data)


def _module_final(root: Path, bundle: str, final: _Final) -> tuple[dict, dict]:
    """participants and not_graded of a bundle's final.json, checked."""
    data = final.data
    people, not_graded = data.get("participants"), data.get("not_graded", {})
    if not isinstance(people, dict) or not isinstance(not_graded, dict):
        raise GradeError(f"{root / final.file} is damaged: `participants` or `not_graded` is not an object")
    if data.get("module", bundle) != bundle:
        raise GradeError(f"{root / final.file} is the grades of {grade.escape_name(str(data.get('module')))}, "
                         f"not of {bundle}")
    for who in (*people, *not_graded):
        _safe_id(who, f"a participant (in {final.file})")
    for who, entry in people.items():
        _check_entry(entry, f"the entry of {who} in {root / final.file}")
    return people, not_graded


def _check_entry(entry: Any, where: str, totals: bool = False) -> None:
    if not isinstance(entry, dict) or entry.get("gate", "absent") not in (True, False, None):
        raise GradeError(f"{where} is damaged: it has no `gate` of true, false or null")
    if totals and not (grade._is_points(entry.get("total")) and grade._is_points(entry.get("max_total"))):
        raise GradeError(f"{where} is damaged: `total` and `max_total` are not whole numbers")


def _makeups(root: Path, bundle: str, kind: str) -> dict[str, _Final]:
    """The latest confirmed further attempt of each participant at a bundle: final.json only."""
    found: dict[str, _Final] = {}
    base = root / bundle / grade.MAKEUP_DIR
    if not base.is_dir():
        return found
    for directory in sorted(base.iterdir()):
        if not (directory / grade.FINAL_FILE).is_file():
            continue  # a run or a proposal with nothing confirmed is not an attempt
        who = _safe_id(directory.name, f"a participant (the directory {directory})")
        final = _read_final(root, f"{bundle}/{grade.MAKEUP_DIR}/{who}/{grade.FINAL_FILE}")
        where = str(root / final.file)
        if final.data.get("bundle") != bundle or final.data.get("participant") != who:
            raise GradeError(f"{where} is damaged: it does not record {bundle} and {who}")
        if final.data.get("kind") != kind:
            raise GradeError(f"{where} was confirmed as a {grade.escape_name(str(final.data.get('kind')))} "
                             f"attempt, and the certificate lists {bundle} as a {kind}")
        _check_entry(final.data, where, totals=kind == "final_project")
        found[who] = final
    return found


def _attempts(root: Path, bundle: str, who: str, latest: _Final) -> dict:
    used = grade.attempts_used(root / bundle / grade.MAKEUP_DIR / who)
    return {"bundle": bundle, "attempts_used": len(used), "latest": latest.file,
            "commit": latest.data.get("commit"), "gate": latest.data.get("gate"),
            "confirmed_at": latest.stamp["confirmed_at"]}


def evaluate(store_root: Path, cert: Certificate) -> dict[str, Outcome]:
    """Each participant's result under the certificate's rule (spec section 3).

    `store_root` is the cohort's store, <data home>/belay/grading/<cohort>/. Refuses
    when a module has no confirmed final.json, or no final project has one.
    """
    root = Path(store_root)
    for ident in (*cert.modules, *cert.final_project):
        if ident == OUTPUT_DIR:
            raise GradeError("`certificate` is not usable as a module id")
        _safe_id(ident, "a bundle id")
    missing = [m for m in cert.modules if not (root / m / grade.FINAL_FILE).is_file()]
    if missing:
        raise GradeError(
            "these modules have no confirmed final.json in this cohort's store, and results over an "
            "unfinished programme would mislead; confirm their grading first: " + ", ".join(missing))
    present = [f for f in cert.final_project if (root / f / grade.FINAL_FILE).is_file()]
    if not present:
        raise GradeError(
            "no final project has a confirmed final.json in this cohort's store ("
            + ", ".join(cert.final_project) + "); confirm the grading of the one the cohort chose first")

    finals: dict[str, _Final] = {}
    tables: dict[str, tuple[dict, dict]] = {}
    for bundle in (*cert.modules, *present):
        finals[bundle] = _read_final(root, f"{bundle}/{grade.FINAL_FILE}")
        tables[bundle] = _module_final(root, bundle, finals[bundle])
    for bundle in present:
        for who, entry in tables[bundle][0].items():
            _check_entry(entry, f"the entry of {who} in {root / finals[bundle].file}", totals=True)
    makeups = {b: _makeups(root, b, "module") for b in cert.modules}
    makeups |= {b: _makeups(root, b, "final_project") for b in present}

    everyone: set[str] = set()
    for bundle, (people, not_graded) in tables.items():
        everyone |= set(people) | set(not_graded)
    for found in makeups.values():
        everyone |= set(found)

    outcomes: dict[str, Outcome] = {}
    for who in sorted(everyone):
        reqs: list[tuple[str, str, str]] = []
        attempts: list[dict] = []
        read = [finals[b].stamp for b in finals]
        for bundle in cert.modules:
            people, not_graded = tables[bundle]
            latest = makeups[bundle].get(who)
            here = finals[bundle].file
            first = people[who]["gate"] if who in people else False
            if latest is not None:
                attempts.append(_attempts(root, bundle, who, latest))
                read.append(latest.stamp)
            # Rule 1 is either/or: a first result that met the gate passes whatever a further
            # attempt says, because a result that met it is never replaced (section 3.1). A
            # trainer may re-confirm the module after an attempt, turning the first into a pass.
            if who in people and first is not False:
                reason = (f"gate met in {here}" if first
                          else f"graded in {here}; the module declares no gate")
                ok = True
            elif latest is not None:
                gate = latest.data["gate"]
                reason = (f"gate met in the further attempt {latest.file}" if gate
                          else f"graded in the further attempt {latest.file}; the module declares no gate"
                          if gate is None else f"gate not met in the further attempt {latest.file}")
                ok = gate is not False
            elif who in people:
                reason, ok = f"gate not met in {here}, with no further attempt", False
            elif who in not_graded:
                why = not_graded[who].get("reason") if isinstance(not_graded[who], dict) else None
                reason = f"in not_graded of {here}" + (f" ({why})" if isinstance(why, str) else "") \
                    + ", with no further attempt"
                ok = False
            else:
                reason = f"absent from {here}: no branch at the checkpoint, and no further attempt"
                ok = False
            reqs.append((f"module {bundle}", PASSED if ok else NOT_PASSED, reason))

        taken = [f for f in present if who in tables[f][0] or who in tables[f][1]]
        if not taken:
            ok, reason = False, "no final project: in none of " + ", ".join(cert.final_project)
        elif len(taken) > 1:
            count = "two" if len(taken) == 2 else str(len(taken))
            ok, reason = False, (f"{count} final projects: {', '.join(taken)}; Belay cannot know which "
                                 "one counts, so the trainer removes one through the grading steps")
        else:
            bundle = taken[0]
            people, not_graded = tables[bundle]
            latest = makeups[bundle].get(who)
            if latest is not None:
                attempts.append(_attempts(root, bundle, who, latest))
                read.append(latest.stamp)
                entry, where = latest.data, f"in the further attempt {latest.file}"
            elif who in people:
                entry, where = people[who], f"in {finals[bundle].file}"
            else:
                entry, where = None, ""
            if entry is None:
                ok, reason = False, f"in not_graded of {finals[bundle].file}, with no result"
            elif entry["gate"] is False:
                ok, reason = False, f"gate not met {where}"
            else:
                total, max_total = entry["total"], entry["max_total"]
                ok = total * 100 >= cert.share * max_total
                reason = (f"{total} of {max_total} points {where}, "
                          f"{'at least' if ok else 'under'} the share of {cert.share}%")
        reqs.append(("final project", PASSED if ok else NOT_PASSED, reason))
        outcomes[who] = Outcome(passed=all(r[1] == PASSED for r in reqs), requirements=reqs,
                                further_attempts=attempts, read=read)
    return outcomes


def _read_text(path: Path, what: str, limit: int) -> str:
    try:
        with open(path, "rb") as stream:
            raw = stream.read(limit + 1)
    except OSError as exc:
        raise GradeError(f"cannot read {what} {path}: {exc}") from exc
    if len(raw) > limit:
        raise GradeError(f"{what} {path} is larger than {limit} bytes")
    try:
        return raw.decode("utf-8-sig")  # a spreadsheet's byte-order mark is accepted
    except UnicodeDecodeError as exc:
        raise GradeError(f"{what} {path} is not UTF-8: {exc}") from exc


def read_names(path: Path) -> dict[str, str]:
    """participant -> full name, from a CSV with the header `participant,full name`.

    Rows are counted as a spreadsheet counts them, the header being row 1. A full name
    starting with =, +, -, @, a tab or a carriage return is refused, because
    results.csv is opened in a spreadsheet, where such a value runs as a formula.
    """
    text = _read_text(Path(path), "the names file", NAMES_MAX_BYTES)
    names: dict[str, str] = {}
    first: dict[str, int] = {}
    try:
        records = list(csv.reader(io.StringIO(text, newline="")))
    except csv.Error as exc:
        raise GradeError(f"the names file {path} is not a CSV file: {exc}") from exc
    for row in records:  # a spreadsheet may export empty columns after the last one
        while row and not row[-1].strip():
            row.pop()
    if not records or [c.strip() for c in records[0]] != NAMES_HEADER:
        raise GradeError(f"the names file {path} must start with the header row `participant,full name`")
    for number, row in enumerate(records[1:], start=2):
        if not row:
            continue  # a blank line, or a spreadsheet's empty row
        if len(row) == 1:
            raise GradeError(f"row {number} of the names file has no full name")
        if len(row) != 2:
            raise GradeError(f"row {number} of the names file has {len(row)} fields; it must be "
                             "participant,full name (quote a name holding a comma)")
        who, name = row[0].strip(), row[1].strip(" ")
        if not name.strip():
            raise GradeError(f"row {number} of the names file has no full name")
        if name.startswith(FORMULA_LEADS):
            raise GradeError(f"row {number} of the names file has a full name starting with "
                             f"{name[0]!r}, which a spreadsheet runs as a formula; write it without")
        if any(unicodedata.category(ch) == "Cc" for ch in name):
            raise GradeError(f"row {number} of the names file has a control character in its full name")
        if who in names:
            raise GradeError(f"row {number} of the names file names {grade.escape_name(who)} again "
                             f"(first in row {first[who]})")
        names[who], first[who] = name, number
    return names


def read_template(path: Path) -> str:
    """The template's text; refuses any {{...}} other than the three placeholders."""
    text = _read_text(Path(path), "the template", TEMPLATE_MAX_BYTES)
    unknown = sorted({m.group(0) for m in _PLACEHOLDER.finditer(text) if m.group(1) not in PLACEHOLDERS})
    if unknown:
        raise GradeError(f"the template {path} has placeholders other than "
                         + ", ".join("{{" + p + "}}" for p in PLACEHOLDERS) + ", so a grade cannot reach "
                         "a certificate by accident: " + ", ".join(grade.escape_name(u) for u in unknown))
    return text


def fill(template: str, values: dict[str, str], escape: bool) -> str:
    """One pass, so a value holding a placeholder is never expanded again."""
    return _PLACEHOLDER.sub(lambda m: html.escape(values[m.group(1)]) if escape else values[m.group(1)],
                            template)


def results_csv(outcomes: dict[str, Outcome], names: dict[str, str]) -> str:
    """The header and one row per participant: full name, passed or not passed. Nothing else."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(RESULTS_HEADER)
    for who in sorted(outcomes, key=lambda w: (names[w].casefold(), w)):
        writer.writerow([names[who], PASSED if outcomes[who].passed else NOT_PASSED])
    return buf.getvalue()


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def _previous_date(target: Path, today: str) -> str:
    try:
        stamp = json.loads((target / "details.json").read_text(encoding="utf-8")).get("date")
    except (OSError, ValueError, AttributeError):
        return today
    return stamp if isinstance(stamp, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", stamp) else today


def write_output(store_root: Path, files: dict[str, str], today: str) -> tuple[Path, Path | None]:
    """Build the output beside <cohort>/certificate/, keep a previous one, rename it in.

    Returns the output directory and where the previous output went, if there was one.
    """
    target = store_root / OUTPUT_DIR
    grade.refuse_work_tree(target)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise GradeError(f"{target} is not a directory; left alone, nothing written")
    grade.make_private(store_root)
    building = Path(tempfile.mkdtemp(dir=store_root, prefix=f".{OUTPUT_DIR}."))
    kept = None
    try:
        for relative, text in files.items():
            path = building / relative
            if path.parent != building:
                path.parent.mkdir(mode=0o700, exist_ok=True)
            _write_private(path, text)
        if target.exists():
            day = _previous_date(target, today)
            for n in range(1, 10000):
                candidate = store_root / (f"{OUTPUT_DIR}.{day}" if n == 1 else f"{OUTPUT_DIR}.{day}-{n}")
                if not os.path.lexists(candidate):
                    break
            else:
                raise GradeError(f"cannot find a free name for the previous {target}")
            os.rename(target, candidate)
            kept = candidate
        try:
            os.rename(building, target)
        except BaseException:
            if kept is not None and not os.path.lexists(target):
                os.rename(kept, target)
                kept = None
            raise
    except BaseException:
        shutil.rmtree(building, ignore_errors=True)
        raise
    return target, kept


def run(repo: str, catalog: Path, names_file: Path, template_file: Path | None) -> int:
    """`belay-grade certificate`: compute everything, refuse or write it all."""
    repo = grade.checked_url(repo)
    cohort = grade.cohort_name(repo)
    store_root = grade.grading_root() / cohort
    grade.refuse_work_tree(store_root / OUTPUT_DIR)
    cert = load_certificate(Path(catalog))
    template = read_template(Path(template_file)) if template_file is not None else None
    outcomes = evaluate(store_root, cert)
    names = read_names(Path(names_file))
    missing = sorted(set(outcomes) - set(names))
    if missing:
        raise GradeError(f"these participants have no entry in the names file {names_file}, so their "
                         "result has no name to go with it: " + ", ".join(missing))
    warnings = [f"the names file has a row for {grade.escape_name(w)}, who is not a participant of this "
                "cohort; it is ignored (often a typo)" for w in sorted(set(names) - set(outcomes))]
    today = grade.now_iso()[:10]
    files = {"results.csv": results_csv(outcomes, names)}
    read = {r["file"]: r for o in outcomes.values() for r in o.read}
    details = {
        "programme": cert.title,
        "date": today,
        "cohort": cohort,
        "final_project_share": cert.share,
        "read": sorted(read.values(), key=lambda r: r["file"]),
        "participants": {who: {
            "full_name": names[who],
            "result": PASSED if o.passed else NOT_PASSED,
            "requirements": [{"requirement": q, "result": r, "reason": why} for q, r, why in o.requirements],
            "further_attempts": o.further_attempts,
            "read": o.read,
        } for who, o in outcomes.items()},
        "warnings": warnings,
    }
    files["details.json"] = json.dumps(details, indent=2, ensure_ascii=False) + "\n"
    if template is not None:
        suffix = Path(template_file).suffix
        escape = suffix.lower() in HTML_SUFFIXES
        for who, o in outcomes.items():
            if o.passed:
                files[f"certificates/{who}{suffix}"] = fill(
                    template, {"name": names[who], "programme": cert.title, "date": today}, escape)
    target, kept = write_output(store_root, files, today)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for who, o in sorted(outcomes.items()):
        failing = [why for _, r, why in o.requirements if r == NOT_PASSED]
        print(f"{who}: {PASSED if o.passed else NOT_PASSED}" + (f" ({'; '.join(failing)})" if failing else ""))
    passed = sum(o.passed for o in outcomes.values())
    print(f"{passed} of {len(outcomes)} passed")
    if kept is not None:
        print(f"previous output kept: {kept}")
    print(f"results: {target / 'results.csv'} (hand this on; details.json is for the trainer only)")
    if template is not None:
        print(f"certificates: {target / 'certificates'}")
    return grade.EXIT_OK
