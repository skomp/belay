# Task lessons — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a lesson take its tasks from a folder of task files, with lesson-declared states
and per-participant progress in `STATE.md`, without changing any existing course.

**Architecture:** Three additive lesson keys (`tasks`, `task_states`, `own_tasks`), one new
`STATE.md` section (`## Tasks`), validator checks that are silent when the keys are absent, a
`--tasks` validator mode, and protocol text in the reference documents. User stories stay course
content, shown as a worked example.

**Tech Stack:** Python 3 standard library and `skills/belay/scripts/yamlite.py`. Tests are plain
scripts, not pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-user-stories-design.md`. Read it before any task.

## Global Constraints

- No new dependency.
- `bundle_format` stays `1`.
- A bundle or instance that declares none of the new keys produces no new finding, no new
  warning, and an unchanged exit code.
- Each new check reports `n/a` when its key or section is absent.
- Task ids and state names match `[a-z0-9-]+`. `skipped` is reserved.
- Run all five suites after each task: `python3 tests/test_validate_bundle.py`,
  `tests/test_catalogs.py`, `tests/test_plan_update.py`, `tests/test_evidence.py`,
  `tests/test_bin_wrappers.py`.
- Stage explicit paths only. Never `git add -A` or `git commit -a`.
- Commit with the configured git identity: no `-c user.*`, no `GIT_AUTHOR_*`/`GIT_COMMITTER_*`,
  no `git config`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and carry
  no `claude.ai/code/session_*` URL.
- Every touched `**Last amended:**` line matches the commit date.
- No real company or client name in any text.

## Already measured — do not re-derive

| Fact | Where |
|---|---|
| Baselines at 88429ea: validate 1024, catalogs 565, plan_update 129, evidence 89, bin_wrappers 57, all passing. These grow when the `ask-start-ref` branch lands (catalogs 583, bin_wrappers 60); take the totals from the branch you are on | run 2026-11-03 |
| The last bundle check is **41**. New checks here are **42–46**. PR: belay#102 (grading) also needs numbers; whichever merges second renumbers | `CHECKS`, `validate_bundle.py:89` |
| Check 6 rejects a file in a lesson subfolder that `LESSON.md` does not name, and accepts it once the body contains its path (`stories/a.md`). Probed with a fixture copy: exit 1 unlisted, exit 0 listed. So no check 6 change is needed | `check_material_reachable` |
| Check 5 also scans task files, because they are under `lessons/`: a `Status: Complete` line in a task file is a finding. That is correct and stays | probed |
| Materialization copies `lessons/` in full, including subfolders | `state-lifecycle.md` section 3 step 2 |
| Model for path containment: `_material_path_problem` (`validate_bundle.py:2599`), `check_lesson_material` (`:2624`) | |
| Model for a ledger: `join_bullets` (`:2779`), `_ledger_lines` (`:2867`), `check_levels_ledger` (`:2893`), `_LEVEL_RECORD_RE` (`:381`). `section_lines(..., depth=2)` anchors at exactly `## ` | |
| Validator CLI modes are `--instance` and `--catalog` (`:6632` onward) | |
| A lesson-frontmatter key is read by name; a test pins only the manifest field table, not lesson keys | |
| Tests are `Case(name, check, baseline, mode, mutate, expect, kind=..., where=...)` rows; set `where` on each firing case. `cli` baseline has folder lesson `lessons/01-subcommands/` | `tests/test_validate_bundle.py` |
| `runner-protocol.md` ends at section 18 today, so the new section is **19**; `state-lifecycle.md` ends at 13, so the new one is **14**. If `ask-start-ref` or another branch has added a section, take the next free number | |

## Review Focus

1. **An existing course.** Every fixture and published bundle validates exactly as before. Pinned
   by Task 4's sweep and by each check's absent-key case.
2. **A task file listed by its path in the body, but also present under a similar name.** The
   listing rule must match exact paths, not substrings: `stories/a.md` must not satisfy
   `stories/aa.md`. Pinned in Task 1.
3. **A non-`.md` file in the `tasks` directory** (a diagram, a data file). It is not a task file;
   check 6 still applies to it. Pinned in Task 1.
4. **A `tasks` path that climbs out of the lesson folder or is a symlink.** A finding, never
   followed. Pinned in Task 1.
5. **A `## Tasks` row whose state no current lesson declares**, after the participant has moved
   on. It must not be a finding. Pinned in Task 2.

---

### Task 1: Lesson keys and task files (checks 42–45)

**Files:** Modify `skills/belay/scripts/validate_bundle.py`, `tests/test_validate_bundle.py`.

**Interfaces — produces:** constants `TASKS_KEY`, `TASK_STATES_KEY`, `OWN_TASKS_KEY`;
`task_file_problems(path: Path) -> list[str]` (frontmatter and id rules for one file, without the
listing rule); checks `check_tasks` (42), `check_task_files` (43), `check_task_states` (44),
`check_own_tasks` (45), run in both modes over all lessons including generated ones.

**Contract** — spec section 4, table rows *tasks*, *task files*, *task states*, *own tasks*:

- 42: `tasks` on a single-file lesson; not a string; absolute or with a `..` segment; a symlink on
  the way; a directory that does not exist in the lesson's folder; a directory holding no `.md`
  file directly inside it.
- 43: for each `.md` file directly in the directory: the frontmatter rules; `id` equal to the
  filename stem; `priority` an integer and not a boolean; two files with one `id`; a file the
  body does not list; a path the body lists under the directory that does not exist. Listing
  means the exact relative path appears as a token in the body (Review Focus 2). Subdirectories of
  `tasks` are not task files.
- 44: `task_states` without `tasks`; not a non-empty list of strings; an entry not matching the
  pattern; a duplicate; `skipped` listed.
- 45: `own_tasks` without `tasks`; not a string; absolute or with a `..` segment.

- [ ] **Step 1:** Add `Case` rows on the `cli` baseline: silent absent (bundle and instance), silent
  valid, and one firing row per finding above with `where=`, including Review Focus 2, 3 and 4.
- [ ] **Step 2:** Run the suite; expect the new cases to fail.
- [ ] **Step 3:** Implement. Wire after check 39 with the one-line comment style used there.
- [ ] **Step 4:** Run all five suites.
- [ ] **Step 5:** Commit the two files.

### Task 2: `## Tasks` rows (check 46) and `--tasks` mode

**Files:** Modify `skills/belay/scripts/validate_bundle.py`, `tests/test_validate_bundle.py`.

**Interfaces — consumes:** `task_file_problems`, `join_bullets`, `_ledger_lines`. **Produces:**
`parse_task_records(lines)` with keys `id`, `state`, `date`, `note`; check 46 (instance only);
`--tasks <dir>`, mutually exclusive with `--instance` and `--catalog`.

**Contract:**

- Row shape: `` - `<id>` — <state> — <free text ending in YYYY-MM-DD> `` with an optional trailing
  ` (<text>)`; separators accept `[—–-]` as `## Levels` does; wrapped bullets are one row; `- None`
  is skipped; the section is anchored at exactly `## Tasks`.
- 46: no section is `n/a`. A bullet that does not parse, a state not matching the pattern, a
  non-calendar date, or two rows for one id is one finding quoting the bullet. **A state is not
  checked against any `task_states`, and an id is not checked against the bundle.**
- `--tasks <dir>`: applies `task_file_problems` to each `.md` file in the directory plus the
  duplicate-id rule, reports through the normal report path, exits 0 clean, 1 on findings, 3 on a
  missing directory following the CLI's existing convention. An empty directory is a warning.

- [ ] **Step 1:** Add `Case` rows on an instance baseline for every line above, including Review
  Focus 5, and a wrapped row, an en-dash row, and a `### Tasks` subsection that is ignored. Add
  `--tasks` tests through the real CLI: a clean directory, a bad directory reporting each finding,
  an empty directory, a missing directory, and a bad argument combination.
- [ ] **Step 2:** Run; expect failures.
- [ ] **Step 3:** Implement. Wire 46 in the instance branch after check 41.
- [ ] **Step 4:** Run all five suites.
- [ ] **Step 5:** Commit the two files.

### Task 3: Reference documents and protocol

**Files:** Modify `skills/belay/references/bundle-format.md`, `runner-protocol.md`,
`state-lifecycle.md`, `skills/belay/SKILL.md`, `README.md`,
`docs/superpowers/specs/2026-09-11-tutorial-runner-design.md` (section 18 status and pointer), the
design spec's `**Status:**` line, and the `CHECKS` text and validator limitations if they list what
the checks cover.

**Contract** — spec section 6; each rule stated in one place and referenced from the others:

- `bundle-format.md` section 6: the three keys in the frontmatter table, the task-file format, the
  listing rule and why, **Writing a task lesson** with spec section 7's worked user-story example;
  section 13: the older-runner row and the obligation that the body makes sense without the task
  machinery; section 10's self-check items. The revision table gains a changed task file as MINOR
  and a removed or renamed one as MAJOR.
- `runner-protocol.md`, new section **Task lessons**: spec section 3 in full, including 3.1.
- `state-lifecycle.md`, new section: `## Tasks` shape, when rows are written, not carried forward.
- `SKILL.md` loading table: during a task lesson, the active task file. Stay within the 3,000-word
  limit by `wc -w`; measure before and after and put both numbers in the commit message.
- `README.md`: the feature list and `--tasks`; test totals where it cites them.
- The tutor's "does not offer, allows on request" rule for participant-written tasks must read
  unambiguously.

- [ ] **Step 1:** Edit the documents.
- [ ] **Step 2:** Run all five suites; some tests read reference text.
- [ ] **Step 3:** Commit the documents.

### Task 4: Fixture programme and the compatibility sweep

**Files:** `tests/fixtures/levelled-programme/` (module 1, module 2, the instance),
`tests/test_validate_bundle.py`.

**Contract** — spec section 8, item 3:

- Module 1 gains a folder task lesson with `tasks: stories/`, three listed task files and the four
  story states. Module 2 gains a task lesson with `own_tasks`. Its body follows the worked example.
- The instance has `## Tasks` rows in several states, and its lesson copies stay identical to their
  source.
- An end-to-end test asserts checks 42–46 ran rather than `n/a`, and asserts the three ids and the
  priority order from the files.
- Main's validator, exported with `git archive` into a temporary directory outside the worktree,
  accepts both bundles with no finding.
- Run `BELAY_SWEEP_SIBLING_REPOS=1 python3 tests/test_validate_bundle.py` and report the sibling
  line. Compare the published bundles' exit codes and output between main's scripts and this
  branch's. Put both results in the commit message.

- [ ] **Step 1:** Build the fixtures and the test.
- [ ] **Step 2:** Run all five suites, then the sweep and the comparison.
- [ ] **Step 3:** Commit, with the results in the message.

### Task 5: Hand-off and branch review

- [ ] Add the worked user-story lesson to the dry run: comment on belay-authoring#43, in ASD-STE100
  wording, without changing what that issue already asks.
- [ ] Whole-branch review against the spec and this plan.
- [ ] Push; the PR is PR: belay#101. No release bump in this branch.
