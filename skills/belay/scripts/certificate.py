#!/usr/bin/env python3
"""The catalog's `certificate` block, as the grader reads it.

The design is docs/superpowers/specs/2026-11-05-final-project-and-certificate-design.md,
section 3. The block's shape is the validator's business (catalog check 10); this
reads it only after `validate_catalog` reports nothing, so a malformed block is
refused with the validator's own findings and never half-read.

grade.py imports this lazily, inside the commands that need it, so there is no
import cycle at load time.

Stdlib only, Python 3.11, and the shared restricted reader yamlite.py.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

try:
    import validate_bundle
    from grade import GradeError
    from yamlite import YamlError, load_yaml
except ImportError:  # pragma: no cover - only when sys.path lacks this dir
    sys.path.insert(0, str(Path(__file__).resolve().parent))
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
