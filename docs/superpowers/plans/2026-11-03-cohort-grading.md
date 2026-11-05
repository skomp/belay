# Cohort grading — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a trainer grade every participant's branch of a module on their own machine, with
validators in a container, a rubric the AI judges, and final grades only after the trainer
confirms.

**Architecture:** A `grading:` manifest key and an `exam:` lesson key, checked by the validator. A
new script, `skills/belay/scripts/grade.py`, reached through a `bin/belay-grade` wrapper, with one
subcommand per mechanical step. The judging and the drafted texts are the tutor's, driven by a new
protocol section; the script stores what the tutor produces and never judges.

**Tech Stack:** Python 3 standard library and `skills/belay/scripts/yamlite.py`. Tests are plain
scripts, not pytest, and never need docker.

**Spec:** `docs/superpowers/specs/2026-11-03-cohort-grading-design.md`. Read it before any task.

## Global Constraints

- No new dependency.
- `bundle_format` stays `1`.
- A bundle or instance that declares none of the new keys produces no new finding, no new warning,
  and an unchanged exit code.
- **No fallback to running participant code outside a container.** No runtime means step 2 stops.
- **Nothing is pushed, sent or published by the script.**
- **Nothing is written inside a Git work tree** by the grade store.
- Run all suites after each task: `python3 tests/test_validate_bundle.py`, `tests/test_catalogs.py`,
  `tests/test_plan_update.py`, `tests/test_evidence.py`, `tests/test_bin_wrappers.py`, and the new
  `tests/test_grade.py` once it exists.
- Stage explicit paths only. Commit with the configured git identity: no `-c user.*`, no
  `GIT_AUTHOR_*`/`GIT_COMMITTER_*`, no `git config`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and carry no
  `claude.ai/code/session_*` URL.
- Every touched `**Last amended:**` line matches the commit date. No real company or client name.

## Already measured — do not re-derive

| Fact | Where |
|---|---|
| Validator kinds are `command` (`command: [prog, arg, ...]`, exit zero is success), `file-exists` (`path`), `file-contains` (`path`, `pattern`), `git-diff`, `manual` | `bundle-format.md` section 2 |
| The last bundle check on `main` is 41. PR: belay#101 plans 42–46. Take the next free numbers on the branch you are on; whichever merges second renumbers | `CHECKS` |
| `git_env()` and `run_git()` give a non-prompting git with the user's access: reuse them for `collect` | `catalogs.py:720`, `:744` |
| Scripts import `yamlite` with the pattern in `evidence.py:56-59`; a CLI script exits `EXIT_OK = 0`, `EXIT_USAGE = 2` | `evidence.py` |
| The ownership glob dialect is the one in `bundle-format.md` section 2; `paths` uses it | |
| A wrapper is a small `sh` script copied from `bin/belay-validate`; `tests/test_bin_wrappers.py` pins each wrapper in `WRAPPERS` | `bin/`, test file `:39` |
| **Neither docker nor podman is installed on the development machine.** The real container path cannot run here. Tests use the stub; one manual run on the grading machine is an acceptance item for the owner | measured 2026-11-03 |
| A module's `validators` live in `tutorial.yaml`; a lesson's frontmatter key is read by name | |

## Review Focus

1. **A participant's branch name holding shell or path characters** (`a b/m1`, `../x/m1`,
   `-x/m1`). It is never a path component or an option. Pinned in Task 3: refused and listed, never
   graded.
2. **A participant's validator output holding secrets or huge output.** Output is truncated to a
   fixed size; a value of a declared env variable is masked in what is stored. Pinned in Task 3.
3. **A validator that hangs.** The per-branch time limit ends it and the remaining validators
   count as failed, with the reason. Pinned in Task 3 with a stub that sleeps.
4. **A confirm with a stale proposal**: the module's `grading` changed, or a branch moved, since
   the proposal. Confirm refuses and names what changed. Pinned in Task 4.
5. **`XDG_DATA_HOME` pointing inside a Git work tree.** The store refuses. Pinned in Task 4.

---

### Task 1: `grading:` and `exam:` checks

**Files:** Modify `skills/belay/scripts/validate_bundle.py` (including `KNOWN_MANIFEST_FIELDS`),
`tests/test_validate_bundle.py`, and `bundle-format.md`'s field table row (a test pins it).

**Contract:** spec section 6, all rows, including `manual` and `git-diff` as findings. The 60% rule
compares validator points with the total. Each check reports `n/a` when the key is absent. Unknown
keys inside `grading`, a validator entry or a rubric entry are findings.

- [ ] **Step 1:** Add `Case` rows: silent absent, silent valid, one firing row per finding with
  `where=`. Include exactly 60% (silent) and just under it (fires).
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement. Wire in `validate()` in both modes.
- [ ] **Step 4:** Run all suites.
- [ ] **Step 5:** Commit.

### Task 2: Reading the scheme and the store

**Files:** Create `skills/belay/scripts/grade.py`, `tests/test_grade.py`, `bin/belay-grade`. Modify
`tests/test_bin_wrappers.py`.

**Interfaces — produces:** `load_scheme(bundle: Path) -> Scheme`; `store_dir(repo_url: str,
module: str) -> Path`, honouring `XDG_DATA_HOME`, with the cohort name derived from the URL and
never containing a path separator; `refuse_work_tree(path)`. Subcommand `forget <cohort>`.

**Contract:** spec section 5. A bundle with no `grading` is refused with a message naming the key.

- [ ] **Step 1:** Write failing tests: URL-to-cohort for https, ssh and scp forms, including two
  different URLs that must not collide; the work-tree refusal (Review Focus 5); `forget` deletes one
  cohort and no other, and says so when there is none.
- [ ] **Step 2:** Run; expect failures. **Step 3:** Implement. **Step 4:** Run all suites.
- [ ] **Step 5:** Commit.

### Task 3: `collect` and `run`

**Files:** Modify `grade.py`, `tests/test_grade.py`.

**Interfaces — produces:** `collect <repo> <module-id>` prints participants, branches, last commit
and date, and lists non-matching branches apart; `run --bundle <dir> <repo> <module-id>
[--only <participant>...]` writes per-branch results to a working file in the store.

**Contract:** spec sections 3 (steps 1 and 2) and 4.

- `collect` uses a local cache outside any work tree and treats the repository URL with
  `catalogs.start_from_problems`' rules. A branch matches `<participant>/<module-id>` with a
  participant of `[A-Za-z0-9._-]+` not starting with `-` (Review Focus 1).
- `run` checks each branch out into a fresh temporary directory, with no remote credentials and its
  hooks disabled.
- The runtime is `BELAY_CONTAINER_RUNTIME` if set, else `docker`, else `podman`. None found stops
  with a clear message and runs nothing.
- The container command has exactly: the image, one mount of the checkout at a fixed path, that path
  as the working directory, the declared env by name, `--network none` unless `network: true`, and
  the command as an argument list. No shell string.
- `file-exists` and `file-contains` are evaluated on the checkout with no container, using the
  path containment rules: no symlink out of the checkout.
- Results per validator: passed, truncated output, gate flag, with declared env values masked
  (Review Focus 2). A missing declared env variable warns and continues.
- The time limit applies per branch (Review Focus 3).

- [ ] **Step 1:** Build a fake cohort in `tests/test_grade.py`: a local bare repository with three
  participant branches for a fixture module (one passing everything, one failing a gate validator)
  and one branch outside the convention. Write a stub runtime script that records its arguments and
  environment and runs the command directly.
- [ ] **Step 2:** Write failing tests that assert, from the stub's record: only the checkout is
  mounted, only declared variables are passed, `--network none` follows the key; no runtime stops
  the run; plus Review Focus 1, 2 and 3.
- [ ] **Step 3:** Implement. **Step 4:** Run all suites. **Step 5:** Commit.

### Task 4: `propose` and `confirm`

**Files:** Modify `grade.py`, `tests/test_grade.py`.

**Interfaces — produces:** `propose --judgement <file>` merges the validator results with the
tutor's rubric judgement, and writes `proposal.json`; `confirm [--change <participant>:<criterion>=
<points>:<reason>...] --by <name>` writes `final.json`.

**Contract:** spec sections 3 (steps 3 to 5) and 5, and the `final.json` shape in section 5.

- `propose` refuses a judgement that misses a participant or criterion, gives points outside
  `0..max`, or has no evidence. It computes totals and the ranking itself and takes neither from the
  judgement.
- `confirm` refuses a change with no reason, and a stale proposal (Review Focus 4). It records every
  change and keeps the previous `final.json` beside it with its date.
- Ties in the ranking are shown as ties and the trainer picks; the script never breaks one silently.

- [ ] **Step 1:** Write failing tests through the CLI, asserting values: the totals for the three
  branches, gate results, ranking, a change with its reason, a re-grade keeping the old file, each
  refusal.
- [ ] **Step 2:** Run. **Step 3:** Implement. **Step 4:** Run all suites. **Step 5:** Commit.

### Task 5: Protocol and documents

**Files:** `bundle-format.md`, `runner-protocol.md`, `README.md`, the 09-11 spec's status, the levels
spec section 1.2, the design spec's `**Status:**`.

**Contract:** spec section 8, each rule in one place. The protocol section **Grading a cohort**
covers the six steps; the side-by-side judging in one pass, with evidence per criterion; the shared
review carrying no names and no grades; the never-publish rule; the separate limited key; how long
grades are kept being the trainer's decision. Section 15 gains exam lessons. The worked example shows
an exam lesson naming a folder and a criterion pointing at it with `paths`.

- [ ] **Step 1:** Edit. **Step 2:** Run all suites. **Step 3:** Commit.

### Task 6: Hand-off and branch review

- [ ] Add judging and the drafted texts to the dry run: comment on belay-authoring#43, in ASD-STE100
  wording.
- [ ] Run the sibling sweep and compare the published bundles with main's scripts.
- [ ] Whole-branch review against the spec and this plan.
- [ ] Push; the PR is PR: belay#102. No release bump.
- [ ] State in the PR that the real container path needs one manual run on the grading machine.
