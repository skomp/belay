# Per-objective levels and modules as bundles — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the format, validator, catalogue and protocol changes of the levels and
modules-as-bundles design, without changing the behaviour of any existing course.

**Architecture:** Every addition is an optional key. The validator gains checks that are
silent when their key is absent; the catalogue reader passes a normalised `start_from`
through `resolve --json`; the tutor's behaviour is protocol text in the reference documents.

**Tech Stack:** Python 3 standard library only (the scripts must run without PyYAML; the
repo's own `yamlite.py` parses YAML). Tests are plain scripts, not pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-levels-and-course-structure-design.md` — read it
before any task. Sections 2.1 to 2.8 are the behaviour; section 3 is the check list; section
5 is the acceptance criteria.

## Global Constraints

- No new dependency. Standard library and `skills/belay/scripts/yamlite.py` only.
- `bundle_format` stays `1`; `catalog_version` stays `1`.
- A bundle, instance or catalogue that declares none of the new keys produces **no new
  finding, no new warning, and an unchanged exit code**.
- Every new check is silent and reports `n/a` when its key is absent.
- Concept and goal ids match `[a-z0-9-]+`. Levels are exactly `A`, `B`, `C`.
- Run every suite after each task: `python3 tests/test_validate_bundle.py`,
  `python3 tests/test_catalogs.py`, `python3 tests/test_plan_update.py`,
  `python3 tests/test_evidence.py`, `python3 tests/test_bin_wrappers.py`. There is no pytest.
- Stage explicit paths only. Never `git add -A` or `git commit -a`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`
  and carry **no** `claude.ai/code/session_*` URL.
- Every spec or reference document you edit that has a `**Last amended:**` line gets it set
  to the date of your commit.

## Already measured — do not re-derive

| Fact | Where |
|---|---|
| Suite baselines on this branch: validate 873, catalogs 482, plan_update 129, evidence 89, bin_wrappers 57 assertions, all passing | run 2026-11-03 |
| The last bundle check on `main` is **34** (`report`). New bundle checks here are **35–41**. PR: belay#72 also claims 35; whichever merges second renumbers | `CHECKS` in `validate_bundle.py:89` |
| The last catalogue check is **7**. New catalogue checks here are **8** and **9** | `CATALOG_CHECKS`, `validate_bundle.py:5145` |
| An unknown **top-level** manifest key WARNS (check 28) via `KNOWN_MANIFEST_FIELDS` (`validate_bundle.py:249`) | check 28 |
| An unknown key **inside a `covers` concept** is a check 23 **finding**. This is why the design puts nothing on a concept | `check_concepts`, `validate_bundle.py:4132` |
| Lesson frontmatter has no list of known keys; `assesses` is read by name (`ASSESSES_KEY`) | `validate_bundle.py:337` |
| Unknown catalogue top-level keys and entry fields WARN, via `CATALOG_KNOWN_TOP_LEVEL_FIELDS` and `CATALOG_KNOWN_ENTRY_FIELDS` | `validate_bundle.py:5196`, `:5200` |
| Check 6 (every file in a lesson folder is named) already exempts files a `supplies` entry covers | `check_material_reachable`, `validate_bundle.py:1666` |
| `## Assessments` rows are parsed by `parse_assessment_records`, which joins wrapped bullets and skips a `- None` bullet | `validate_bundle.py:2455` |
| Validator checks are wired in order in `validate()` (`validate_bundle.py:4963`); instance-only checks sit in its `else:` branch | `validate_bundle.py:5112` onward |
| Tests are `Case(name, check, baseline, mode, mutate, expect, kind=..., where=...)` rows in `CASES`; `kind` is `fires`, `silent`, `warns` or `indeterminate`; set `where` on every case that targets one place | `tests/test_validate_bundle.py:3677` |
| Bundle baseline `cli` is `tests/fixtures/rust-cli-basics` (has a folder lesson `lessons/01-subcommands/`); instance baselines are in `INSTANCE_BASELINES` | `tests/test_validate_bundle.py:105`, `:143` |
| `belay-catalogs resolve <id> --json` prints `MergedEntry.as_dict()`, which copies the whole entry, so an unknown entry field already passes through unchanged | `catalogs.py:414`, `:2568` |

## Review Focus

1. **An existing course.** Every published bundle in `skomp/belay-bundles` and every existing
   fixture must validate exactly as before. Pinned by Task 5's sweep and by every check's
   "absent key is silent" case.
2. **A `## Levels` row naming an objective this bundle does not cover.** It was set in an
   earlier module and must not be reported. Pinned in Task 3.
3. **A wrapped `## Levels` or `## Modules` bullet.** Must parse as one row, as `## Assessments`
   bullets do. Pinned in Task 3.
4. **A `material` path that climbs out of the lesson folder** (`../other/x.md`, an absolute
   path). Must be a finding, never followed. Pinned in Task 2.
5. **A malformed `start_from`** (missing `ref`, a `repo` that is not a Git URL). `resolve
   --json` must never hand the tutor an unusable value as if it were usable: it prints `null`
   with a note. Pinned in Task 4.

---

### Task 1: Manifest keys `levels` and `starts_from`

**Files:**
- Modify: `skills/belay/scripts/validate_bundle.py` (`CHECKS`, `KNOWN_MANIFEST_FIELDS`, new
  check functions, wiring in `validate()`)
- Test: `tests/test_validate_bundle.py`

**Interfaces:**
- Produces: constants `LEVELS_KEY = "levels"`, `STARTS_FROM_KEY = "starts_from"`; functions
  `check_levels_key(manifest: Any, report: Report) -> None` (check 35) and
  `check_starts_from(manifest: Any, report: Report) -> None` (check 36). Task 3 reads
  `LEVELS_KEY`.

**Contract:**
- Check 35, both modes: `levels` absent → `n/a`. Present and not a boolean → finding at
  `tutorial.yaml`, message containing `'levels' must be true or false`. Note that `yamlite`
  may parse `yes` differently from PyYAML; test with `true`, `false`, `"true"` (a string,
  must fire) and `1` (must fire).
- Check 36, both modes: `starts_from` absent → `n/a`. Any value other than the string `ref`
  → finding at `tutorial.yaml`, message containing `'starts_from' must be 'ref'`.
- Both keys added to `KNOWN_MANIFEST_FIELDS`, so check 28 stays silent on them.
- `CHECKS[35]` and `CHECKS[36]` carry one-line descriptions in the style of the table.

- [ ] **Step 1:** Add `Case` rows: 35 silent when absent (bundle and instance), silent on
  `true` and on `false`, fires on `"true"` and on `1`; 36 silent when absent, silent on `ref`,
  fires on `branch` and on a mapping. Add a case proving check 28 does **not** warn on either
  key. Mutators edit `tutorial.yaml` of the `cli` baseline.
- [ ] **Step 2:** Run `python3 tests/test_validate_bundle.py`; expect the new cases to fail.
- [ ] **Step 3:** Implement the contract above. Wire both checks in `validate()` beside check
  34, with the one-line comment style used there.
- [ ] **Step 4:** Run all five suites; expect all to pass.
- [ ] **Step 5:** Commit: `git add skills/belay/scripts/validate_bundle.py tests/test_validate_bundle.py`.

### Task 2: Lesson frontmatter `teaches`, `material` and `placement`

**Files:**
- Modify: `skills/belay/scripts/validate_bundle.py`
- Test: `tests/test_validate_bundle.py`

**Interfaces:**
- Consumes: `_lesson_frontmatter(lesson)`, `concept_declarations(manifest)`,
  `optional_lesson_keys(manifest)` (existing).
- Produces: constants `TEACHES_KEY`, `MATERIAL_KEY`, `PLACEMENT_KEY`; functions
  `check_teaches(lessons, manifest, report) -> None` (check 37),
  `check_lesson_material(root, lessons, report) -> set[str]` (check 38; returns the
  workspace-relative paths of declared material files, for check 6),
  `check_placement(lessons, manifest, report) -> None` (check 39).

**Contract:**
- Check 37, both modes, over all lessons including generated ones: `teaches` must be a
  non-empty list of strings, each a key in `covers`. A non-list or empty list → finding at
  the lesson's path. An id not in `covers` → finding naming the id. Same "why" wording as
  check 31 when the id is in `assumes` or `covers` is absent.
- Check 38, both modes: `material` must be a mapping of objective id → mapping of level →
  path.
  - On a single-file lesson → finding: material needs a folder lesson.
  - An objective key not in that lesson's `teaches` → finding.
  - A level key other than `A`, `B`, `C` → finding.
  - A path that is absolute, contains a `..` segment, or does not exist inside the lesson's
    own folder → finding. Never resolve symlinks outward; reuse the path-component guard
    that `check_supplies` uses if it fits, and say so in the commit if it does not.
- Check 6 treats every path returned by check 38 as named, exactly as it treats a
  `supplies`-covered file. A material file that is **not** declared keeps check 6's existing
  behaviour.
- Check 39, both modes: `placement` must be a boolean. `placement: true` without `assesses` →
  finding. More than one lesson with `placement: true` → one finding naming all of them.
  `placement: true` on a key of `optional_lessons` → finding.
- All three are `n/a` when no lesson declares the key.

- [ ] **Step 1:** Add `Case` rows on the `cli` baseline, using its folder lesson
  `lessons/01-subcommands/` for material:
  - 37: silent absent; silent on a valid list; fires on a string; fires on `[]`; fires on an
    unknown id; fires with the `assumes` wording.
  - 38: silent absent; silent with A and C declared and the files present; fires on a
    single-file lesson; fires on objective not in `teaches`; fires on level `D`; fires on a
    missing file; fires on `../00-hello-args.md`; fires on `/etc/passwd`.
  - 6: a material file declared by check 38 does not fire check 6; the same file undeclared
    still fires check 6.
  - 39: silent absent; silent on one valid placement lesson; fires without `assesses`; fires
    on two placement lessons; fires on an optional lesson; fires on `placement: "yes"`.
- [ ] **Step 2:** Run the suite; expect the new cases to fail.
- [ ] **Step 3:** Implement. Wire 37–39 after check 31 in `validate()`; pass check 38's
  returned set into `check_material_reachable` (add a keyword parameter with default
  `frozenset()` so existing callers are unchanged).
- [ ] **Step 4:** Run all five suites.
- [ ] **Step 5:** Commit the two files.

### Task 3: Instance sections `## Levels` and `## Modules`

**Files:**
- Modify: `skills/belay/scripts/validate_bundle.py`
- Test: `tests/test_validate_bundle.py`

**Interfaces:**
- Consumes: the bullet-joining behaviour of `parse_assessment_records` (reuse the joining
  loop; factor it into a shared helper if that is the smaller change).
- Produces: `parse_level_records(lines) -> list[tuple[str, dict | None]]` with keys `id`,
  `level`, `source`, `date`, `note`; `parse_module_records(lines)` with keys `id`, `date`,
  `branch`; checks 40 and 41.

**Contract:**
- Row shape for `## Levels`: `` - `<id>` — <A|B|C> — <source> <YYYY-MM-DD> `` with an optional
  trailing ` (<text>)`. `<source>` is `placement`, `learner`, or a lesson path starting
  `lessons/` or `lessons.generated/`. The separator is ` — ` (em dash, as in
  `## Assessments`).
- Row shape for `## Modules`: `` - `<id>` — complete <YYYY-MM-DD> — branch <name>`` followed
  optionally by `;` and free text.
- Check 40, instance mode only: no section → `n/a`. Each bullet that does not parse → one
  finding quoting the bullet. A level outside `A`/`B`/`C` → finding. **An id not in this
  bundle's `covers` is not a finding** (spec 2.4 and section 3). A `- None` bullet is skipped.
  Two rows for the same id → finding (the ledger is updated in place).
- Check 41, instance mode only: no section → `n/a`. A bullet that does not parse → finding.
  Two rows for the same module id → finding.
- Neither check depends on `levels: true`: a carried-forward ledger may sit in an instance of
  a bundle that does not use levels.

- [ ] **Step 1:** Add `Case` rows on an instance baseline: 40 silent absent; silent on three
  valid rows (one per source kind); silent on a row whose id is not in `covers`; silent on a
  row wrapped over two lines; fires on level `D`; fires on a row without a date; fires on a
  duplicate id. 41 silent absent; silent on a valid row with and without the `;` tail; fires
  on a row without `branch`; fires on a duplicate. A case asserting a bundle-mode run never
  reports 40 or 41.
- [ ] **Step 2:** Run the suite; expect failures.
- [ ] **Step 3:** Implement and wire in the instance branch of `validate()`, after check 32.
- [ ] **Step 4:** Run all five suites.
- [ ] **Step 5:** Commit the two files.

### Task 4: Catalogue `goals` and `start_from`

**Files:**
- Modify: `skills/belay/scripts/validate_bundle.py` (catalogue part),
  `skills/belay/scripts/catalogs.py` (`MergedEntry.as_dict`)
- Test: `tests/test_validate_bundle.py` (catalogue cases), `tests/test_catalogs.py`
- Create: catalogue fixtures under `tests/fixtures/` following the `catalog-*` naming

**Interfaces:**
- Produces: `CATALOG_CHECKS[8]` (goals), `CATALOG_CHECKS[9]` (start_from);
  `read_start_from(entry: dict, where: str) -> tuple[dict | None, list[str]]` in `catalogs.py`,
  returning `{"repo": str, "ref": str}` or `None` with notes, in the shape of
  `read_optional_lesson_count`.

**Contract:**
- `goals` added to `CATALOG_KNOWN_TOP_LEVEL_FIELDS`; `start_from` added to
  `CATALOG_KNOWN_ENTRY_FIELDS`.
- Catalogue check 8: absent → `n/a`. `goals` not a mapping → finding. A goal id not matching
  `[a-z0-9-]+`, a goal without a non-empty string `title`, `objectives` not a non-empty list
  of strings, or an unknown key inside a goal (known: `title`, `summary`, `objectives`) →
  finding. An objective that is not a `covers` key of **any** entry in the same catalogue →
  finding. An objective under two goals → finding. An entry's `covers` key under no goal is
  silent.
- Catalogue check 9: absent → silent. Not a mapping, missing `repo` or `ref`, an empty
  string, an unknown key, or a `repo` that is not `https://…`, `ssh://…` or scp-style
  `user@host:path` → finding.
- `resolve --json` and `discover --json` output carries `start_from` normalised by
  `read_start_from`: the mapping when valid, `null` plus a `metadata_notes` entry when
  malformed, and the key **always present** (`null` when absent), for the reason
  `optional_lesson_count` gives at `catalogs.py:416`.

- [ ] **Step 1:** Add catalogue cases for every finding above and a silent case for a valid
  `goals` and a valid `start_from`. Add `test_catalogs.py` assertions: `resolve --json` shows
  the valid mapping; shows `null` and a note for a `start_from` missing `ref`; shows `null`
  and no note when absent.
- [ ] **Step 2:** Run both suites; expect failures.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all five suites.
- [ ] **Step 5:** Commit the changed and created paths.

### Task 5: The fixture programme, and the compatibility sweep

**Files:**
- Create: `tests/fixtures/levelled-programme/catalogs.yaml` (or the catalogue file name the
  existing `catalog-*` fixtures use), `tests/fixtures/levelled-programme/module-1/` and
  `module-2/` bundles
- Modify: `tests/test_validate_bundle.py`, `tests/test_catalogs.py` (baselines and one
  end-to-end test each)

**Contract (spec section 5, items 3 and 4):**
- The catalogue declares `goals` covering every objective of both modules, and module 2's
  entry carries `start_from`.
- Module 1: `levels: true`, a setup lesson, a placement lesson (`placement: true`,
  `assesses` listing every objective), `teaches` on every lesson, one folder lesson with
  `material` for A and C but not B.
- Module 2: `levels: true`, `starts_from: ref`, `recommended_previous_bundles` naming module 1,
  a placement lesson assessing only objectives new in module 2.
- An instance of module 2 whose `STATE.md` has a `## Levels` row for a module-1 objective and
  a `## Modules` row for module 1 validates clean.
- Both bundles validate clean in bundle mode; the catalogue validates clean.
- Then run `BELAY_SWEEP_SIBLING_REPOS=1 python3 tests/test_validate_bundle.py` and confirm the
  line reporting the sibling sweep shows **no new findings and no new warnings** compared
  with the same command on `main` (run it on `main` first, in a scratch worktree, and paste
  both lines into the commit message).

- [ ] **Step 1:** Build the fixtures; add them as baselines so every existing "baseline
  passes" test covers them.
- [ ] **Step 2:** Run all five suites, then the sweep on `main` and on this branch.
- [ ] **Step 3:** Commit, with both sweep lines in the message.

### Task 6: Reference documents and protocol

**Files:**
- Modify: `skills/belay/references/bundle-format.md`, `catalogue-format.md`,
  `runner-protocol.md`, `state-lifecycle.md`, `skills/belay/SKILL.md`, `README.md`,
  `docs/superpowers/specs/2026-09-11-tutorial-runner-design.md` (section 18 status and a
  pointer), and the design spec's `**Status:**` line to `implemented`.

**Contract** — each item stated in exactly one place and referenced from the others:
- `bundle-format.md` section 2: `levels`, `starts_from`, with the field-reference rows; section
  6: `teaches`, `material`, `placement` rows in the frontmatter table, and a **Writing a
  placement lesson** subsection; section 10 self-check items; section 13 rows for an older
  runner, including the plain statement that a `starts_from: ref` module needs a runner that
  knows it.
- `catalogue-format.md`: `goals` at the top level, `start_from` on an entry, checks 8 and 9,
  and that `resolve --json` always carries `start_from`.
- `runner-protocol.md`: a new section **Levels** — reading `## Levels`, the guidance table
  (spec 2.6), the lowest-level rule, the C ceiling at rung 3, material selection and the
  fallback order (spec 2.7), the participant's override. Section 15: the placement lesson's
  three differences, placing only objectives without a row, the `skipped` case, and the
  outcome-to-level rule (spec 2.5). A subsection on starting a `starts_from: ref` module (spec
  2.2: read `start_from` from `belay-catalogs resolve <id> --json`; stop when it is `null`;
  propose, never run, the Git commands; remove the winner's `tutorial/`).
- `state-lifecycle.md`: `## Levels` and `## Modules` — shape, when each is written, the
  absent-row rule, the carry-forward steps and its never-borrow rule (spec 2.4), and the
  `remote` requirement.
- `SKILL.md`: the loading table gains one material file per taught objective at the
  participant's level. Check the file stays under the size limit in spec 15d of the
  2026-09-11 design; report the measured size in the commit message.
- Use the terms *learning goal* and *learning objective* in prose; `covers` concept in YAML.

- [ ] **Step 1:** Edit the documents.
- [ ] **Step 2:** `grep -n 'goal:' skills/belay/references/*.md` returns nothing (the rejected
  design must not reappear); every `**Last amended:**` line you touched matches
  `git log -1 --format=%ad --date=short -- <file>` after the commit.
- [ ] **Step 3:** Run all five suites (the validator's tests read some reference text).
- [ ] **Step 4:** Commit the documents.

### Task 7: Hand-off issue and branch review

- [ ] File an issue in `skomp/belay-authoring`, labelled `created-by-claude`, in ASD-STE100
  wording: a dry run of `tests/fixtures/levelled-programme` in its harness that exercises
  placement, the outcome-to-level rule, guidance at A and C, the material fallback and the
  carry-forward. Link it from the spec's section 5.
- [ ] Whole-branch review against the spec and this plan.
- [ ] Push; the PR is PR: belay#91.

No release bump in this branch. A release is a separate step after merge (`CLAUDE.md`,
**Releasing**).
