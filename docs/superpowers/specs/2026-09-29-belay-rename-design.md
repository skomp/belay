# Renaming tutorAIl to Belay — Design

**Date:** 2026-09-29
**Last amended:** 2026-09-29
**Status:** approved in brainstorm, not implemented
**Issue:** tutorAIl#54
**Sibling issues:** tutorail-bundles#31, tutorail-authoring#29

---

## 1. The problem

The project is called `tutorAIl`. The name was chosen for a pun — "tutorial" with `AI`
set into the middle of it — and the pun is the whole of the problem.

**The name does not survive being spoken.** The `AI` exists only in writing. Said aloud,
`tutorAIl` is "tutorial", so the name cannot be given to someone over a coffee, in a talk,
or on a call. A name you can only transmit in writing is not a name; it is a logo.

**The repository already spells it four ways.** `tutorAIl` (101 occurrences), `tutorail`
(the plugin id, the skill directory, the config paths), `TutorAIl` (README prose) and
`TUTORAIL` (environment variables). The GitHub repository is `skomp/tutorAIl` while the
plugin it publishes is `tutorail`. There is no spelling that is correct everywhere, which
means every reference is a small decision and some of them are wrong.

**It is unsearchable.** The name is one transposition from the most SEO-saturated word on
the internet. A search engine will correct the query; a human reader will assume a typo
and "fix" it in an issue, a link, or a commit message.

**It describes the generic half.** The interesting property of this project is that the
agent hands you one task at a time, reads what you actually wrote, and refuses to write
the exercise for you. "Tutorial" is the part it shares with every other teaching tool.

The name is also, as of today, the name under which three public repositories are
published. It costs less to change now than at any later point.

## 2. The new name

The project is renamed **Belay**.

A belayer manages the rope for a climber. They take in slack, hold a fall, and watch every
move of the route. They never climb the route for the climber. That is not an approximate
metaphor for this project — it is the runner's defining rule restated in one word: the
escalating-help ladder catches a stuck learner, and the refusal to write the exercise is
absolute.

Three secondary properties earned it the choice over the alternatives:

- **It is a verb**, so invocations read as English rather than as a product placement.
- **Two syllables, spelled as it sounds.** It survives a noisy room and a phone call.
- **Its explanation is its pitch.** Every name costs one line of explanation on first
  contact. `tutorAIl`'s line — *"it's 'tutorial' with AI in the middle"* — teaches the
  reader nothing. `Belay`'s line — *"the agent holds your rope; it doesn't climb for
  you"* — is the entire product thesis. The tax becomes the tagline.

The nautical sense (*belay that line* — make fast, secure it so it cannot slip) is a
happy accident that suits a runner whose other trick is pinning progress into the
learner's own repository so a fresh session cannot lose it.

### Names considered and rejected

Each was checked against GitHub (star-ranked) and npm. Domains and trademarks were not
checked.

| Name | Rejected because |
|---|---|
| `cairn` | `cairn-dev/cairn` is "a background agent system for automating end-to-end software engineering tasks" — the same shelf, the opposite thesis. Also a 3.1k-star AI search engine and `project-cairn`, a Claude Code skill. |
| `paideia` | `OPTIMETA/PAIDEIA` is a Claude Code plugin for learning. Same shelf, same shop. |
| `trellis` | 14.8k-star "the best agent harness", plus Microsoft TRELLIS. |
| `crux` | 2.7k-star Rust framework, 1k-star Emacs package. |
| `didact` | 6.8k-star DIY-React guide owns the word. |
| `piton` | Free on GitHub, and apt — the spike hammered in and left behind to mark the route. Reads as "Python" misspelled, which is fatal for a teaching tool. |
| `switchback` | Survived. The zigzag route up the steep slope is a good match for a pedagogy that refuses the direct answer, and its search results are the cleanest of any candidate. Lost on precision: it describes the path, not the relationship. |
| `whetstone` | Survived. Best single line about the refusal — you sharpen yourself against it, it does no cutting. Lost to a 218-star Android DI framework, a `whetstone.chatgpt` library, and being a passive object where Belay is an active partner. |
| `jumar` | Survived, and near-free on GitHub. Rejected because it re-buys the exact problem being solved: unspellable and undecodable on first contact. |

## 3. The claim

`README.md` gets two lines under the title, because they do different jobs. The first is
functional and must be parseable by a stranger and a search engine; the second is the
claim that makes the name pay for itself.

```
# Belay
**Structured, adaptive courses that run inside your coding agent.**

It catches you. It doesn't climb for you.
```

The functional line changes only one word from today's: "tutorials" becomes "courses", so
that the brand word and the domain word stop competing.

The claim is six words and both clauses are literally true of the runner. "Catches you"
is the escalating-help ladder — goal restated, expected against actual, the concept named,
the wrong line, the smallest true statement. "Doesn't climb for you" is the refusal to
write the exercise, and the `solution_code` setting that governs the one exception. It
needs no climbing knowledge to parse.

## 4. What changes

Brand-namespaced identifiers only.

| From | To |
|---|---|
| `skills/tutorail/` | `skills/belay/` |
| plugin and marketplace name `tutorail` | `belay` |
| install target `tutorail@tutorail` | `belay@belay` |
| `TUTORAIL_SWEEP_SIBLING_REPOS` | `BELAY_SWEEP_SIBLING_REPOS` |
| `TUTORAIL_FAKE_GIT_STDERR` | `BELAY_FAKE_GIT_STDERR` |
| `~/.config/tutorail/catalogs.yaml` | `~/.config/belay/catalogs.yaml` |
| `~/.cache/tutorail/catalogs/` | `~/.cache/belay/catalogs/` |
| `~/.local/share/tutorail` | `~/.local/share/belay` |
| `~/.agents/skills/tutorail` | `~/.agents/skills/belay` |
| `skomp/tutorAIl` | `skomp/belay` |
| `skomp/tutorail-bundles` | `skomp/belay-bundles` |
| `skomp/tutorail-authoring` | `skomp/belay-authoring` |

## 5. What deliberately does not change

The bundle format contract keeps every word it has today:

- the `tutorial/` directory materialised into the learner's workspace
- the `tutorial.yaml` manifest
- `STATE.md` and `lessons.generated/`
- `catalog.yaml`
- the terms **course** and **lesson**, in the manifest and in the tutor's speech

These name the subject matter; they were never the brand. The reason `tutorial/` reads
ambiguously today is precisely that the product is *also* called tutorAIl. Renaming the
product to Belay resolves that ambiguity for free, in the same change, at no cost.

Nothing in the six published bundles needs to change.

### Rejected: climbing vocabulary in the format

Adopting `route` for course, `pitch` for lesson, `guidebook` for catalogue and `variation`
for optional lesson was considered seriously, and the mapping is uncannily good. A route
genuinely is a named, graded, guidebook-documented line; a pitch genuinely is one section,
anchored at both ends, that cannot be skipped — which is the lesson model exactly.

It was rejected on pedagogy, not on cost. **Course** and **lesson** are words the learner
already owns. Belay earns its keep through the name and the claim; it does not need the
rest of the climbing dictionary imported behind it. Requiring a learner to decode "three
pitches left on this route" in order to find their next Rust exercise taxes the one reader
with the least patience for it. The metaphor is the name; the interface stays plain.

A split — climbing words in prose, plain words in YAML — was rejected outright. It
recreates the exact defect being fixed: two vocabularies for one concept, with no way for
a reader to tell which is authoritative.

### Rejected: name-only

Changing the prose while keeping `tutorail` as the internal plugin id and directory name
was rejected. It leaves the bad name in the one place developers actually type it —
`/plugin install tutorail@tutorail`, `skills/tutorail/` — and forfeits most of the benefit.

### Rejected: a phased rollout

A runner-first rollout, with the two sibling repositories following later behind GitHub's
repository redirects, was designed and then dropped. It was built on a compatibility
argument that does not apply: the project has no users outside this account. A phased
rollout would buy a safety margin nobody needs, in exchange for a period in which the
documentation says Belay and half the repository names say tutorail.

### Rejected: a configuration-path fallback

Reading the old `~/.config/tutorail/catalogs.yaml` as a fallback, or detecting it and
reporting loudly, was dropped for the same reason. There is one installation and it is
going to be reinstalled as part of this change.

## 6. The central risk: one transposition

`tutorail` and `tutorial` differ by a single transposition, and they are not in separate
files — **every file that contains one contains the other**:

| File | brand | domain word |
|---|---|---|
| `tests/test_validate_bundle.py` | 42 | 283 |
| `README.md` | 60 | 13 |
| `docs/.../2026-09-11-tutorial-runner-design.md` | 45 | 51 |
| `skills/tutorail/scripts/validate_bundle.py` | 5 | 133 |
| `skills/tutorail/references/bundle-format.md` | 1 | 53 |

Repository totals: **263** brand occurrences, **824** domain occurrences.

A substitution that matches `tutorial` rewrites the bundle format contract, the validator
and the test fixtures, and does so silently — the tests would be rewritten in the same
pass that breaks them, so they would still pass. This is the failure this repository keeps
writing rules about: a check that cannot report a positive.

**The rule:** the substitution matches exactly four literal strings — `tutorail`,
`tutorAIl`, `TutorAIl`, `TUTORAIL` — and is never case-insensitive on a shorter stem.

**The proof:** `tutorial` is counted in `skills/*/references/` and `tests/` before and
after the change. The count is **543** and it must be 543 afterwards. This invariant
catches a botched substitution that no test would catch. A repository-wide count of
`tutorial` is *not* a valid invariant, because README prose deliberately changes some
occurrences to "course".

## 7. Version

**0.9.0**, not 1.0.0.

The plugin identity changes, so this is breaking by construction — an installed
`tutorail@tutorail` cannot be updated into `belay@belay`. But 1.0.0 is a statement about
the stability of the bundle format, and the format is still moving: assessments were
designed on 2026-09-19 and the disclosure block landed with tutorAIl#45. Claiming 1.0.0
at the moment of open-sourcing would be a promise this contract cannot yet keep. 1.0.0 is
the launch version, once the format settles.

All four version files move together, per `CLAUDE.md`: `.claude-plugin/marketplace.json`,
`.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`, and the `Version N.N.N.` line
in `README.md`. After the bump, the leaving-version grep runs and must return zero.

## 8. Sequencing

One window, three repositories, no phasing.

1. **Merge or park** tutorail-bundles#29 and tutorail-bundles#30 first. Both touch
   `README.md` and `catalog.yaml`, which the rename also touches.
2. **Rename the three repositories on GitHub.** GitHub keeps a permanent redirect, so
   nothing breaks between this step and the content changes.
3. **Content rename in each repository**, each by its own session — this repository here,
   the other two under tutorail-bundles#31 and tutorail-authoring#29.
4. **Version bump and release** in this repository.
5. **Reinstall** the plugin under its new identity.

The one-session-per-repository rule in `CLAUDE.md` still holds. "Big bang" means one
coordinated window, not one session reaching into three working trees.

## 9. Steps only a person can take

1. `gh repo rename belay --repo skomp/tutorAIl` (and the two siblings).
2. Remove `tutorail@tutorail` and install `belay@belay`. A plugin identity change is not
   carried by `claude plugin update`; the old plugin must be uninstalled explicitly.
3. Update the local remote, and re-add the marketplace under the new name.

## 10. Verification

- The sweep returns zero lines, and is first proven able to report a positive:

  ```bash
  grep -rni 'tutorail' --exclude-dir=.git \
       --exclude=2026-09-29-belay-rename-design.md . | grep -v worktrees
  ```

  **The exclusion is load-bearing, for the same reason `--exclude=CLAUDE.md` is in the
  release check.** This document names the old brand 37 times because the old brand is
  its subject. Without the exclusion the check reports a hit on its own design document
  on every run, and teaches the reader to ignore it.

  The exclusion covers this file and no other. Every *other* spec's `tutorAIl#NN` issue
  references are live references, not history — after the repository is renamed the
  correct spelling is `belay#NN`, so those are rewritten like any other occurrence.
- `tutorial` in `skills/belay/references/` and `tests/` counts **543**, unchanged.
- `python3 tests/test_validate_bundle.py` passes.
- `python3 tests/test_catalogs.py` passes.
- `BELAY_SWEEP_SIBLING_REPOS=1 python3 tests/test_validate_bundle.py` passes, and reports
  its sibling-repository additions on their own line.
- `claude plugin validate .` passes.
- The installed cache under `~/.claude/plugins/cache/belay/belay/0.9.0/` is diffed against
  the working tree, and probed for something 0.8.0 lacked, so a silent no-op cannot pass
  as success.

## 11. Out of scope

- The open-source launch itself — announcement, contribution guide, issue templates. The
  repositories are already public; the launch is separate work and is not blocked by
  anything in this document.
- The three worktrees (`tutorAIl-supplies`, `.claude/worktrees/output-style-spike`) carry
  their own copies of the old name. They are renamed when they land, not before.
