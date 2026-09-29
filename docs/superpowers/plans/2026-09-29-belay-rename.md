# Belay Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename this repository's project identity from `tutorAIl` to `Belay`, leaving the bundle format contract untouched.

**Architecture:** One proven mechanical substitution does the bulk of the work (Task 1), and it has already been executed and verified against a throwaway copy of `HEAD` — the numbers below are measurements, not estimates. Tasks 2 and 3 are the copy and version work the substitution cannot do. Task 4 is verification and the hand-off of the steps only a person can take.

**Tech Stack:** Python 3 standard library only (no pytest — the suites are plain scripts), BSD `sed` (macOS), `git`, `gh`.

**Spec:** `docs/superpowers/specs/2026-09-29-belay-rename-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **The bundle format does not change.** `tutorial/`, `tutorial.yaml`, `STATE.md`, `lessons.generated/`, `catalog.yaml`, and the terms **course** and **lesson** keep their current spelling everywhere. They name the subject, not the brand.
- **Never run a case-insensitive substitution on a stem shorter than the four brand literals.** `tutorail` and `tutorial` differ by one transposition and share every file.
- **The 10 occurrences of `tutorails` are protected.** They are a deliberate misspelling of the format key `tutorials`, not the brand. See "Protected set" below.
- **`docs/superpowers/specs/2026-09-29-belay-rename-design.md` is never substituted.** It names the old brand 54 times because the old brand is its subject.
- **Do not `git add -A` or `git commit -a`.** A worktree is live at `.claude/worktrees/output-style-spike` and `.claude/` is untracked. Stage explicit paths only.
- **Commit messages end with `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` and contain no `claude.ai/code/session_*` URL.**
- **No closing keyword** (`close`/`fixes`/`resolves`) beside an issue number unless you mean it. This plan does not close tutorAIl#54; Task 4 does, by hand.

## Already measured — do not re-derive

Every number here was produced by running the command against a `git archive HEAD` copy on 2026-09-29. Trust them; re-measuring costs time and the counts are subtle.

| Fact | Value | Why it matters |
|---|---|---|
| Distinct brand spellings in the tree | exactly **4**: `tutorail`, `tutorAIl`, `TutorAIl`, `TUTORAIL` | Enumerated, not assumed. No `Tutorail` or `TUTORAIl` exists. |
| Brand occurrences to remove | **263** | Excludes the design doc. |
| Brand occurrences in the design doc | **54** | These stay. |
| Brand occurrences in the whole tree today | **317** | 263 + 54. A count of 317 is not a bug. |
| `tutorial` repo-wide | **838** | Must be **838** after. Unchanged. |
| `tutorial` in `references/` + `tests/` | **543** | Must be **543** after. This is the invariant that catches a bad substitution. |
| `tutorAIl` occurrences by context | 60 issue refs `tutorAIl#NN`, 13 `skomp/tutorAIl`, ~7 prose | Issue refs dominate; only ~7 need the capitalised `Belay`. |
| `tutorails` (protected) | **10** | 6 in `tests/test_validate_bundle.py`, 3 in the misspelling fixture, 1 in `catalogue-format.md`. |
| `__tutorail_decoy__` sites | **2** | `tests/test_validate_bundle.py:4726` and `:4805`. Renamed automatically by rule 7. |
| Suite sizes | `test_validate_bundle.py` **702** assertions, `test_catalogs.py` **338** | Both pass after the proven substitution. |
| Version before | `0.8.0`, in 4 files | `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `README.md:327`. |

### Protected set — the `tutorails` occurrences

`tests/fixtures/catalog-toplevel-misspelling/catalog.yaml` exists to test that check 1 reports a near-miss for a misspelled top-level key. The misspelling it uses is `tutorails`, which its own comment describes as *"a transposition, which plain Levenshtein scores as two edits"*. It is the format key `tutorials` spelled wrong — it is not the brand, despite being spelled identically.

**A substitution that changes these to `belays` destroys the only test of near-miss key detection**, and the resulting failure looks trivial to fix by editing the expected string. That fix would permanently delete the test's purpose. This was observed: an unguarded run failed 2 of 702 assertions in exactly this way.

| File | Lines |
|---|---|
| `tests/test_validate_bundle.py` | 5489, 5697, 5701, 5712, 5853, 5859 |
| `tests/fixtures/catalog-toplevel-misspelling/catalog.yaml` | 3, 8, 21 |
| `skills/belay/references/catalogue-format.md` (post-move) | 204 |

Rule 1 of the substitution script masks them and rule 8 restores them. Do not remove those two rules.

---

### Task 1: The mechanical rename

**Files:**
- Modify: every file matched by `grep -rliI 'tutorail'` except the design doc (23 files)
- Move: `skills/tutorail/` → `skills/belay/`
- Test: `tests/test_validate_bundle.py`, `tests/test_catalogs.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the directory `skills/belay/`, the environment variable names `BELAY_SWEEP_SIBLING_REPOS` and `BELAY_FAKE_GIT_STDERR`, the identifier `__belay_decoy__`, and the config paths `~/.config/belay/`, `~/.cache/belay/`. Tasks 2–4 rely on `skills/belay/` existing.

**This substitution script was executed against a copy of `HEAD` and verified.** It is a measurement, not a proposal. Use it verbatim; the rule order is load-bearing.

- [ ] **Step 1: Write the substitution script**

```bash
cat > /tmp/belay-rename.sed <<'SED'
s|tutorails|@@KEEPKEY@@|g
s|TUTORAIL|BELAY|g
s|TutorAIl|Belay|g
s|tutorAIl#|belay#|g
s|skomp/tutorAIl|skomp/belay|g
s|tutorAIl|Belay|g
s|tutorail|belay|g
s|@@KEEPKEY@@|tutorails|g
SED
```

Rule order matters and each rule earns its place:
- rule 1 + rule 8 mask and restore the protected format-key misspelling
- rule 2 catches the environment variables before rule 7 lowercases anything
- rule 4 handles the 60 issue references (`tutorAIl#33` → `belay#33`; a repo-qualified ref is lowercase)
- rule 5 handles the 13 repository URLs before rule 6 would capitalise them
- rule 6 handles the ~7 remaining prose mentions as `Belay`
- rule 7 handles all 189 lowercase identifier occurrences

- [ ] **Step 2: Record the before-counts, and prove the probe can see a positive**

```bash
cd /Users/robert/src/github.com/skomp/tutorAIl
grep -rhoiI 'tutorail' --exclude-dir=.git --exclude-dir=worktrees \
  --exclude=2026-09-29-belay-rename-design.md . | wc -l   # expect 263
grep -rhoiI 'tutorial' --exclude-dir=.git --exclude-dir=worktrees . | wc -l  # expect 838
```

Expected: `263` and `838`. If either differs, STOP and report — the tree moved since this plan was measured.

- [ ] **Step 3: Apply the substitution**

The `-i` in `-rliI` is load-bearing. A case-sensitive file list silently skips every file containing only `tutorAIl` — this was observed leaving 5 occurrences behind in `TODO.md` and `skills/tutorail/scripts/yamlite.py`.

```bash
grep -rliI 'tutorail' --exclude-dir=.git --exclude-dir=worktrees \
  --exclude=2026-09-29-belay-rename-design.md . \
  | while read -r f; do sed -i '' -f /tmp/belay-rename.sed "$f"; done
git mv skills/tutorail skills/belay
```

- [ ] **Step 4: Verify all six invariants**

```bash
grep -rniI 'tutorail' --exclude-dir=.git --exclude-dir=worktrees \
  --exclude=2026-09-29-belay-rename-design.md . | grep -vi 'tutorails' | wc -l  # 0
grep -rhoiI 'tutorails' --exclude-dir=.git --exclude-dir=worktrees \
  --exclude=2026-09-29-belay-rename-design.md . | wc -l                          # 10
grep -rhoiI 'tutorial' --exclude-dir=.git --exclude-dir=worktrees . | wc -l      # 838
grep -rhoiI 'tutorial' skills/belay/references/ tests/ | wc -l                   # 543
find . -path ./.git -prune -o -iname '*tutorail*' -print | wc -l                 # 0
grep -rhoI '__belay_decoy__' --exclude-dir=.git --exclude-dir=worktrees . | wc -l # 2
```

Expected, in order: `0`, `10`, `838`, `543`, `0`, `2`. **Any deviation stops the task.** In particular a `tutorial` count other than 838 or 543 means the format contract was damaged — revert with `git checkout -- .` and report.

- [ ] **Step 5: Run both suites**

```bash
python3 tests/test_validate_bundle.py 2>&1 | tail -3
python3 tests/test_catalogs.py 2>&1 | tail -2
```

Expected: `OK - 702 assertions passed.` and `OK - 338 assertions passed.`

If you see `FAILED - 2 of 702` mentioning `'belays' -> ['tutorials']`, rule 1 or rule 8 was dropped. **Do not fix this by editing the test's expected string** — that deletes the test's purpose. Revert and re-apply the script with all eight rules.

- [ ] **Step 6: Commit**

```bash
git add -u
git add skills/belay
git status --short   # confirm .claude/ is NOT staged
git commit -F - <<'EOF'
Rename the project identity from tutorAIl to Belay

Mechanical substitution across 23 files plus the move of skills/tutorail
to skills/belay. Four brand spellings existed and all four are gone:
tutorail, tutorAIl, TutorAIl and TUTORAIL.

The bundle format is untouched. tutorial/, tutorial.yaml, STATE.md,
catalog.yaml and the terms course and lesson keep their spelling, and
the count of "tutorial" is 838 before and after, 543 of them in
references/ and tests/. Those counts are the check; the tests are not,
because a bad substitution rewrites the tests in the same pass.

The ten occurrences of `tutorails` are preserved deliberately. They are
the format key `tutorials` spelled wrong, in the fixture that tests
near-miss key detection, and they only look like the brand.

Part of tutorAIl#54.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: The README header and the claim

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `skills/belay/` from Task 1.
- Produces: the approved title block. Task 3 relies on `README.md:327` still carrying a `Version N.N.N.` line.

The substitution already changed the title to `# Belay`. What it could not do is the positioning: the functional line still says "tutorials" where the domain word now competes with nothing, and the claim line does not exist yet.

- [ ] **Step 1: Replace the title block**

Current `README.md` lines 1–3:

```markdown
# TutorAIl

**Structured, adaptive tutorials for coding agents.**
```

After Task 1 that reads `# Belay`. Replace lines 1–3 with exactly:

```markdown
# Belay

**Structured, adaptive courses that run inside your coding agent.**

It catches you. It doesn't climb for you.
```

This wording is approved and is not open for improvement. "courses" replaces "tutorials" so the brand word and the domain word stop competing.

- [ ] **Step 2: Read the rest of the README and fix only what the rename made wrong**

Read `README.md` in full. The sed handled every brand occurrence. Change a remaining "tutorial" to "course" **only** where it names the product's offering to a reader, never where it names the format (`tutorial/`, `tutorial.yaml`) or the learner's own directory.

The comparison table near the top has a `| TutorAIl |` column header, now `| Belay |` — verify it reads correctly. The install commands must now read:

```
/plugin marketplace add skomp/belay
/plugin install belay@belay
```

and the Codex block must clone `skomp/belay` into `~/.local/share/belay` and link `~/.agents/skills/belay`.

- [ ] **Step 3: Verify no brand word returned**

```bash
grep -niI 'tutorail' README.md | grep -vi 'tutorails'   # expect no output
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -F - <<'EOF'
Give the README Belay's name and its claim

The functional line now says "courses" rather than "tutorials", so the
brand word and the domain word stop competing for the same slot, and
the claim line carries what the name is for: it catches you, it doesn't
climb for you.

Part of tutorAIl#54.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Manifest copy and the version bump to 0.9.0

**Files:**
- Modify: `.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, `README.md`

**Interfaces:**
- Consumes: Tasks 1 and 2.
- Produces: version `0.9.0` in all four files. Task 4's release grep depends on `0.8.0` being gone.

`CLAUDE.md` records that the version lives in four files and that nothing checks the third or the fourth. `claude plugin validate .` checks only the two under `.claude-plugin/`.

- [ ] **Step 1: Bump the version in all four files**

```bash
sed -i '' 's|"version": "0.8.0"|"version": "0.9.0"|' \
  .claude-plugin/marketplace.json .claude-plugin/plugin.json .codex-plugin/plugin.json
sed -i '' 's|^Version 0\.8\.0\.|Version 0.9.0.|' README.md
```

`0.9.0` and not `1.0.0` — the reasoning is in §7 of the spec. 1.0.0 is a statement about the stability of the bundle format, and the format is still moving.

- [ ] **Step 2: Update the copy that still says "tutorials"**

Three strings describe the product to a stranger and should adopt the new positioning. Change the value only; leave every key alone.

| File | Key | New value |
|---|---|---|
| `.claude-plugin/marketplace.json` | top-level `description` | `Course runner for coding agents` |
| `.codex-plugin/plugin.json` | `interface.shortDescription` | `Interactive courses that run inside your coding agent` |
| all three manifests | `description` | Change the leading `Runs interactive, project-driven tutorials inside a coding agent.` to `Runs interactive, project-driven courses inside a coding agent.` Leave the rest of the sentence exactly as it is. |

Leave `interface.defaultPrompt` unchanged. `"Continue the tutorial."` is a phrase a learner types, and it must keep matching the skill's trigger vocabulary.

Leave `skills/belay/SKILL.md`'s `description` frontmatter unchanged for the same reason: its trigger words are how the skill is routed.

- [ ] **Step 3: Verify the manifests**

```bash
claude plugin validate .
python3 -c "import json;[print(f, json.load(open(f))['version']) for f in ['.claude-plugin/marketplace.json','.claude-plugin/plugin.json','.codex-plugin/plugin.json']]" 2>/dev/null \
  || python3 -c "
import json
for f in ['.claude-plugin/plugin.json','.codex-plugin/plugin.json']:
    print(f, json.load(open(f))['version'])
print('.claude-plugin/marketplace.json', json.load(open('.claude-plugin/marketplace.json'))['plugins'][0]['version'])"
```

Expected: validate passes, and all three print `0.9.0`.

- [ ] **Step 4: Run the leaving-version grep**

`CLAUDE.md` requires this after every bump, with the version you are leaving. `--exclude=CLAUDE.md` is load-bearing, and the design doc is excluded for the same reason — it cites `0.8.0` deliberately.

```bash
grep -rn '0\.8\.0' --include='*.json' --include='*.md' \
  --exclude=CLAUDE.md --exclude=2026-09-29-belay-rename-design.md . | grep -v worktrees
```

Expected: no output. Before trusting that zero, prove the grep works by running it for `0.9.0` and confirming it finds the four files you just changed.

- [ ] **Step 5: Run both suites again**

```bash
python3 tests/test_validate_bundle.py 2>&1 | tail -3
python3 tests/test_catalogs.py 2>&1 | tail -2
```

Expected: `OK - 702 assertions passed.` and `OK - 338 assertions passed.`

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin/marketplace.json .claude-plugin/plugin.json .codex-plugin/plugin.json README.md
git commit -F - <<'EOF'
Release Belay as 0.9.0

All four version files move together: both plugin manifests, the Codex
manifest and the README line. Nothing checks the last two, so they are
the two to remember.

0.9.0 rather than 1.0.0. The plugin identity changes, so this is
breaking by construction, but 1.0.0 is a claim about the stability of
the bundle format and the format is still moving. 1.0.0 is the launch
version, once it settles.

The three strings that describe the product to a stranger now say
"courses" rather than "tutorials". The trigger vocabulary in
defaultPrompt and in the skill description is deliberately unchanged:
those words are how a learner reaches the skill.

Part of tutorAIl#54.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: Full verification, and the hand-off

**Files:**
- Modify: none, unless verification finds a defect.

**Interfaces:**
- Consumes: Tasks 1–3.

- [ ] **Step 1: Run the sibling-repository sweep**

`CLAUDE.md` requires this once before a release is pushed. It validates the published bundles, which is the only place a format change meets real courses.

```bash
BELAY_SWEEP_SIBLING_REPOS=1 python3 tests/test_validate_bundle.py 2>&1 | tail -5
```

Expected: it passes, and reports what the sweep added on its own line rather than folded into the total. If the sibling repository has not been renamed yet it will report paths under `skomp/belay-bundles` as skipped or missing — that is expected and is not a failure of this task. Record what it said.

- [ ] **Step 2: Confirm the whole-repository sweep is clean, and that it can report a positive**

```bash
echo 'tutorAIl' > PLANTED.md
grep -rniI 'tutorail' --exclude-dir=.git --exclude-dir=worktrees \
  --exclude=2026-09-29-belay-rename-design.md . | grep -vi 'tutorails'
rm PLANTED.md
```

Expected: the planted line is found. Then re-run without `PLANTED.md` and expect no output. A zero from a probe you have not seen produce a one is not evidence.

- [ ] **Step 3: Report the state and hand off the human steps**

Write a short report naming: the three invariant counts, both suite results, the sweep result, and the commits made. Then state the steps only a person can take, which are **not** part of this plan:

1. `gh repo rename belay --repo skomp/tutorAIl`, and the two siblings under tutorail-bundles#31 and tutorail-authoring#29.
2. `git remote set-url origin` to the new name, then push.
3. `claude plugin marketplace update belay && claude plugin install belay@belay`, having first removed `tutorail@tutorail`. A plugin identity change is not carried by `claude plugin update`.
4. Diff the installed cache at `~/.claude/plugins/cache/belay/belay/0.9.0/` against the working tree, and probe for something `0.8.0` lacked so a silent no-op cannot pass as success.
5. Close tutorAIl#54 by hand after confirming the acceptance criteria. Do not rely on a closing keyword — this repository has three recorded cases of a correct keyword closing nothing.

---

## Self-review

**Spec coverage.** §2 name → Tasks 1–3. §3 claim → Task 2. §4 what changes → Task 1 (identifiers), Task 3 (manifests). §5 what does not change → Global Constraints and the Task 1 invariants. §6 the transposition risk → Task 1 Steps 2, 4, 5 and the Protected set. §7 version → Task 3. §8 sequencing → out of scope for this repository's plan; it is tutorail-bundles#31 and tutorail-authoring#29. §9 human steps → Task 4 Step 3. §10 verification → Tasks 1, 3, 4. §11 out of scope → not implemented, correctly.

**Placeholder scan.** No TBD, no "add error handling", no "similar to Task N". Every command is literal and every expected value is a number.

**Type consistency.** `skills/belay/` is produced in Task 1 Step 3 and consumed by name in Task 1 Step 4, Task 3 Step 2 and the Protected set table. `BELAY_SWEEP_SIBLING_REPOS` is produced by rule 2 in Task 1 and consumed in Task 4 Step 1. The version string `0.9.0` is produced in Task 3 Step 1 and checked in Steps 3 and 4.

**One gap accepted deliberately.** The plan does not verify that the runner still discovers the bundles catalogue end-to-end, because that depends on `skomp/belay-bundles` existing, which is another session's work. It is listed in Task 4 Step 1 as an expected skip rather than silently omitted.
