# Final project and certificate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a trainer compute who earned a programme's certificate from confirmed grades, let a
participant make further attempts where the course allows them, and write a result list and filled
certificates.

**Architecture:** Two validator additions (`grading.retries`, catalog `certificate`). In
`grade.py`, a `makeup` subcommand group that reuses the run, propose and confirm machinery on one
participant's `-makeup` branch. A new module, `skills/belay/scripts/certificate.py`, holds the
catalog reading, the pass rule and the output writing; `grade.py certificate` calls it. The tutor's
part goes in `runner-protocol.md` section 20.

**Tech Stack:** Python 3.11 standard library and `skills/belay/scripts/yamlite.py`. Tests are plain
scripts, not pytest, and never need docker.

**Spec:** `docs/superpowers/specs/2026-11-05-final-project-and-certificate-design.md`. Read it
before any task. Where this plan and the spec disagree, the spec wins; report the disagreement.

## Global Constraints

- No new dependency. `bundle_format` and `catalog_version` stay `1`.
- A bundle or catalog that declares none of the new keys produces no new finding, no new warning,
  and an unchanged exit code. All suites pass unchanged apart from added cases.
- **`results.csv` holds two columns only: full name, and `passed` or `not passed`.**
- **A template may use only `{{name}}`, `{{programme}}` and `{{date}}`.**
- **Nothing is sent, pushed or published by the script. Nothing is written inside a Git work tree.**
- **Every refusal writes nothing.** Compute everything, then write.
- `SKILL.md` is at its 3,000-word limit: do not add to it. Tutor guidance goes in
  `runner-protocol.md`.
- Run all six suites after each task: `python3 tests/test_validate_bundle.py`,
  `tests/test_catalogs.py`, `tests/test_plan_update.py`, `tests/test_evidence.py`,
  `tests/test_bin_wrappers.py`, `tests/test_grade.py`. New tests go in these files, so the release
  checklist's six suites stay six.
- Stage explicit paths only. Commit with the configured git identity: no `-c user.*`, no
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, no `git config`. Messages end with
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and carry no `claude.ai/code/session_*`
  URL.
- Every touched spec's `**Last amended:**` line matches its last commit date. No real company or
  client name anywhere.

## Already measured — do not re-derive

| Fact | Where |
|---|---|
| Last bundle check is 51; the `grading` shape check is 47, with `GRADING_KEYS` and an unknown-key finding | `validate_bundle.py`, `GRADING_KEYS` |
| Last catalog check is 9. The table is `CATALOG_CHECKS`; known top-level keys are `CATALOG_KNOWN_TOP_LEVEL_FIELDS` (`catalog_version`, `goals`, `tutorials`) | `validate_bundle.py` |
| Check 6 resolves a bundle path relative to `catalog_root(target)` with `os.path.expanduser` and `os.path.normpath`, inside `validate_catalog`; it iterates a local `resolvable` list of `(where, path)` | `validate_bundle.py`, `# -- check 6` |
| `validate_catalog(target, portable) -> Report`; `Report.findings` is a list | `validate_bundle.py` |
| `load_scheme` hashes the whole `grading` block: `sha256(json.dumps(grading, sort_keys=True, default=str))` | `grade.py`, `load_scheme` |
| `classify_branch(branch, module)` returns `participant`, `refused` or `other`; a `<p>/<m>-makeup` branch is `other` for module `m` today | `grade.py` |
| `confirm` refuses when any module branch moved since the proposal (`changes_since`) | `grade.py` |
| `archive_previous(store)` keeps `final.json` as `final.<date>.json`, then `-2`, `-3`; it works on any directory | `grade.py` |
| `store_dir(repo, module)` refuses `.`, `..`, `CACHE_NAME` (`.repo.git`) and separators | `grade.py` |
| `read_judgement(path, scheme, known, ungradable)`, `gate_result(validators, criteria)`, `parse_change(text) -> (who, cid, pts, reason)`, `write_json_private`, `refuse_work_tree`, `now_iso` exist and are reused | `grade.py` |
| `final.json` today has no `grading_hash` | `grade.py`, `cmd_confirm` |
| Tests: `tests/test_grade.py` has `Scene` (a fake cohort in a local bare repository, a runtime stub), `graded()`, `propose()`, `confirm()`, `load()` helpers; each test is registered in the tuple in `main()` | `tests/test_grade.py` |
| **Neither docker nor podman is installed here.** Tests use the stub runtime; the real run stays belay#106 | measured 2026-11-03 |

## Two decisions this plan adds to the spec

Recorded here and in Task 5's amendment to the spec:

1. **A module id `certificate` is refused**, by `store_dir` and by the new catalog check, because the
   certificate's output directory `<store>/<cohort>/certificate/` would collide with it.
2. **The names file has a header row `participant,full name`**, and a UTF-8 byte-order mark is
   accepted, because a spreadsheet exports one. A full name starting with `=`, `+`, `-`, `@`, a tab
   or a carriage return is refused, because `results.csv` is opened in a spreadsheet, where such a
   value runs as a formula.

## Review Focus

1. **A names file exported from a spreadsheet**: a byte-order mark, a quoted name with a comma, a
   Windows line ending. Expected: read correctly. Pinned in Task 4.
2. **A full name starting with `=`** reaching `results.csv`. Expected: refused, naming the row.
   Pinned in Task 4.
3. **Archived files beside a current one** (`final.2026-11-01.json`). Expected: the certificate reads
   only `final.json`; the attempt count reads both. Pinned in Tasks 3 and 4.
4. **A trainer confirming the same attempt twice**, to correct a criterion. Expected: one attempt
   used, not two. Pinned in Task 3.
5. **Two certificate runs on one day.** Expected: `certificate.<date>/`, then `certificate.<date>-2/`,
   and the current output is the newest. Pinned in Task 4.

---

### Task 1: The validator: `grading.retries` and catalog `certificate`

**Files:** Modify `skills/belay/scripts/validate_bundle.py`, `tests/test_validate_bundle.py`,
`skills/belay/references/bundle-format.md` and `skills/belay/references/catalogue-format.md`
(wherever a test pins a check table or a field table against the code, update the document in this
task).

**Contract:**
- Check 47: `retries` joins `GRADING_KEYS`. It is a whole number from 0; a boolean is refused.
- Catalog check 10, added to `CATALOG_CHECKS`; `certificate` joins
  `CATALOG_KNOWN_TOP_LEVEL_FIELDS`. It reports `n/a` when `certificate` is absent. Findings: every
  item in spec section 6, plus an id equal to `certificate`. The two rules that read bundles use
  check 6's resolution and are silent for a bundle that does not resolve. Absent `retries` counts
  as 0.

- [ ] **Step 1:** Add cases: absent (silent), valid (silent), and one firing case per finding, each
  asserting the check number and the message's subject. Include `retries: 0` (silent),
  `retries: true` (fires), `final_project_share: 100` (silent) and `101` (fires), and two use cases
  with `retries` 1 and absent (fires).
- [ ] **Step 2:** Run the validator suite; expect the new cases to fail.
- [ ] **Step 3:** Implement. A helper that resolves one catalog entry's bundle directory, shared by
  check 6 and check 10, so the two cannot drift.
- [ ] **Step 4:** Run all suites; then commit.

### Task 2: The grader's groundwork

**Files:** Modify `skills/belay/scripts/grade.py`, `tests/test_grade.py`.

**Interfaces — Produces:**
- `Scheme.retries: int` (0 when absent).
- `grading_hash` computed over the `grading` block **without `retries`**.
- `final.json` gains `"grading_hash"`.
- `Listing.makeup: list[BranchRef]`, the branches `<p>/<module>-makeup` with a usable participant
  part; `collect` prints them under the heading `further attempts (<n>):`.
- `store_dir` refuses the module id `certificate`.

- [ ] **Step 1:** Tests: two bundles differing only in `retries` give the same `grading_hash`; a
  confirmed `final.json` holds it; a proposal made before raising `retries` still confirms; `collect`
  lists `alice/m1-makeup` under further attempts and not under no convention; `store_dir(repo,
  "certificate")` is refused.
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all suites; then commit.

### Task 3: `belay-grade makeup run|propose|confirm`

**Files:** Create `skills/belay/scripts/certificate.py`; modify `skills/belay/scripts/grade.py`,
`tests/test_grade.py`.

**Interfaces — Produces, in `certificate.py`:**
- `@dataclass(frozen=True) class Certificate: title: str; modules: tuple[str, ...];
  final_project: tuple[str, ...]; share: int`
- `load_certificate(catalog: Path) -> Certificate`: runs `validate_bundle.validate_catalog(catalog,
  portable=False)` and raises `GradeError` listing the findings when there are any, or when the
  catalog has no `certificate`.
- `kind_of(cert: Certificate, bundle_id: str) -> Literal["module", "final_project"]`, raising
  `GradeError` when the bundle is in neither list.

**Interfaces — Produces, in `grade.py`:**
- Store: `store_dir(repo, bundle) / "makeup" / <participant>/` with `run.json`, `proposal.json`,
  `final.json`, archived as module grading does.
- `attempts_used(store: Path) -> set[str]`: the distinct `commit` values in `final.json` and every
  `final.*.json` in that directory.
- Make-up `final.json`: `bundle`, `kind`, `participant`, `commit`, `gate`, `validators`,
  `criteria` (as in module `final.json`), `total` and `max_total` (final project only, else
  absent), `grading_hash`, `bundle_version`, `confirmed_by`, `confirmed_at`.

**Contract:** spec section 3.1. Each subcommand takes `<repo> <bundle-id> <participant> --bundle
<dir> --catalog <file>`. For a module, grade with a scheme reduced to gate validators and gate
criteria (`dataclasses.replace`); for a final project, the whole scheme. `makeup confirm` takes
`--by` and `--change <criterion>=<points>:<reason>`, repeatable, reusing `parse_change` with the
participant put in front. A runtime fault leaves no proposal: `makeup propose` refuses with the
reason. `makeup confirm` refuses when the branch moved or the grading hash changed since the
proposal.

- [ ] **Step 1:** Tests, on a `Scene` with a confirmed module `final.json` (alice passed, bob failed
  the gate, carol absent) and a final project (dave under the share):
  - bob: run, propose, confirm passes the gate; module `final.json` is byte for byte unchanged, and a
    `--change` to the module still confirms afterwards.
  - carol, absent: an attempt is allowed and uses one.
  - alice: refused, nothing open.
  - `retries` absent: refused. `retries: 1`: a second commit refused; confirming the first commit
    again with a `--change` is allowed, and `attempts_used` holds one commit.
  - Raising `retries` to 2 in the bundle opens a second attempt with no version change.
  - dave: graded in full; `total` and `max_total` recorded; no ranking written anywhere.
  - Refusals, each asserting nothing was written: no `certificate` in the catalog; bundle not
    listed; no module `final.json`; no branch; grading changed (a validator's points); branch moved
    before `confirm`.
  - A runtime fault (stub exit 125): `makeup propose` refuses, and no attempt is used.
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all suites; then commit.

### Task 4: `belay-grade certificate`

**Files:** Modify `skills/belay/scripts/certificate.py`, `skills/belay/scripts/grade.py`,
`tests/test_grade.py`.

**Interfaces — Consumes:** `load_certificate`, the make-up `final.json` from Task 3.
**Produces:** `evaluate(store_root: Path, cert: Certificate) -> dict[str, Outcome]`, where
`Outcome` holds `passed: bool` and a list of `(requirement, result, reason)`; and the command
`certificate <repo> --catalog <file> --names <file> [--template <file>]`.

**Contract:** spec sections 3, 4 and 5, and the two decisions above. Reads only `final.json`, never
archives. The participant set and the pass rule are section 3's. `details.json` lists every
`final.json` read with its `confirmed_at`. Output is built in a temporary directory beside the
target and renamed into place; a previous `certificate/` is first renamed to
`certificate.<date>/` (`-2`, `-3`). Placeholders are `{{name}}`, `{{programme}}` and `{{date}}`
exactly; any other `{{...}}` refuses. An `.html` or `.htm` template has its values escaped with
`html.escape`. Without `--template`, no `certificates/` directory is written. A names-file row for
someone who is not a participant is printed as a warning.

- [ ] **Step 1:** Tests: the end-to-end set of spec acceptance criterion 3, each asserting the
  participant's row in `results.csv` and the reason in `details.json`. Then: `results.csv` is
  exactly `full name,result` plus one row each, for passed and not passed alike, and nothing else in
  it (no digits apart from those in a name); a name holding `<` in an `.html` template is escaped;
  `{{total}}` refused; each refusal of section 4 writes nothing; Review Focus 1, 2, 3 and 5; output
  under a work tree refused.
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all suites; then commit.

### Task 5: Protocol and documents

**Files:** `skills/belay/references/runner-protocol.md` (section 20), `bundle-format.md`,
`catalogue-format.md`, `README.md`, the spec, `docs/superpowers/specs/2026-09-11-tutorial-runner-design.md`,
`docs/superpowers/specs/2026-11-03-levels-and-course-structure-design.md`.

**Contract:** spec section 7, every row. In section 20: the make-up steps, "not met yet" as the
wording for an open requirement and attempts left named in checkpoint feedback, the shared review
skipped for a cohort of one, the certificate step, and that `results.csv` is what goes to the
employer and nothing else. `bundle-format.md`: **Writing a final project**. `README.md`: the
commands, the feature list, and the suites' new totals, counted from the runs. Amend the spec with
this plan's two decisions, and set its status to implemented once Task 6 is done. Move each touched
spec's `**Last amended:**`.

- [ ] **Step 1:** Edit the documents.
- [ ] **Step 2:** Run all suites; check every `**Last amended:**` against `git log -1 --format=%ad
  --date=short -- <file>` after committing.
- [ ] **Step 3:** Commit.

### Task 6: Hand-off

- [ ] **Step 1:** Run the validator suite with `BELAY_SWEEP_SIBLING_REPOS=1`; expect no new finding
  and no new warning.
- [ ] **Step 2:** Whole-branch review.
- [ ] **Step 3:** Comment on belay-authoring#43 with the make-up and certificate steps the dry run
  must cover (spec acceptance criterion 7).
- [ ] **Step 4:** Push and open the PR with `Closes skomp/belay#95` on its own line; after the merge,
  verify the issue's state.
