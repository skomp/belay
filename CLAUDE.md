# Belay

## Scope — one session per repository

Three sessions run in parallel, one per repository. **This repository is the runner.**

| Repository | Session owns | Holds |
|---|---|---|
| `skomp/belay` | **this one** | the runner plugin, the bundle format contract, the validator, the catalogue and discovery |
| `skomp/belay-authoring` | the authoring-tools session | the authoring skill, the toolkit, the course-quality checker, the dry-run harness |
| `skomp/belay-bundles` | the bundles session | the courses themselves, and the repository catalogue |

Work that belongs to another repository goes to that repository as an issue. Do not build
it here because it is adjacent.

Between sessions, a signal is fine — which files are held, a branch has landed, an issue
has moved. A **question about another session's work is not**: it belongs in that session's
own chat. A peer session is not a channel to Robert, and not a second opinion to consult
when you dislike an answer you were given. See `~/.claude/CLAUDE.md`.

## Tracking

This project tracks work as **GitHub issues**, not in `TODO.md`. Label every issue Claude
files with `created-by-claude`.

`TODO.md` holds only settled decisions and measured facts, and is usually empty. A design
decision belongs in `docs/superpowers/specs/2026-09-11-tutorial-runner-design.md` instead.

## Two rules this repository keeps learning the hard way

**A spent checkpoint or a superseded document does not get to stay.** This project has
three times found a document that was accurate when written and wrong afterwards: a resume
marker naming a task finished several lessons earlier, a material-naming rule that outlived
the `supplies` exemption, and a runner instruction telling the tutor to work around a defect
that had been fixed. Guidance describing a fixed bug teaches a reader to distrust correct
output. Delete it, or correct it in place, in the same change that makes it stale.

**A spec's filename is its creation date, and it is amended in place.** So
`2026-09-14-validator-trust-and-setup-checks-design.md` holds content added on the 16th, and
the 09-11 spec was corrected on the 19th. That is the convention and it is worth keeping —
one document per decision, not one per revision. But it misled a reader on 2026-09-19, who
opened a permalink whose header said `Date: 2026-09-14`, found none of the sections he had
been asked to review, and had no way to tell whether he was early or the document was wrong.

Every spec therefore carries a **`**Last amended:**` line under its `**Date:**`, and it moves
with any edit to that file.** It is hand-maintained and git already knows the answer, so it
will go stale exactly the way the version number in `README.md` did — check it against
`git log -1 --format=%ad --date=short -- <file>` when you touch a spec.

**It means the last commit that touched the file, not the last *substantive* amendment.**
That distinction produced a false alarm on 2026-09-21: the 09-12 spec's header said 09-12
because its content had not moved, while git said 09-19 because the commit that added these
headers had touched it. A date whose significance a reader must judge is not checkable, and
a rule carrying an exception is the kind this repository keeps having to relearn. A typo fix
moves the line. That is the cost, and it is the right one.

Two related habits, same root: **link to a branch when you want something reviewed, and to a
sha when you want to cite evidence.** A permalink is frozen by design, so a review request
pinned to one shows the reviewer whatever was true when you sent it and never what is true
when they read it.

**A check that cannot report a positive is worse than no check.** Prove a probe can see the
thing it looks for before you trust its silence. This repository has caught it in a
validator that could not fail, a test harness that matched a message from the wrong file, a
grep whose zero came from an untested pattern, and a merge watch that errored on every
iteration while reporting itself healthy.

## Releasing

An installed copy receives a change only when the **version number** moves. Claude Code
compares manifest versions, not commit shas: refreshing the marketplace pulls the new
commits and then reports the plugin as already current. Thirty commits sat unreachable
behind 0.4.0 this way, and nothing reported a problem.

The version lives in four files and they move together:

| File | Read by |
|---|---|
| `.claude-plugin/marketplace.json` (`plugins[0].version`) | Claude Code, resolving the marketplace entry |
| `.claude-plugin/plugin.json` | Claude Code, after install |
| `.codex-plugin/plugin.json` | Codex |
| `README.md`, the `Version N.N.N.` line | a person deciding whether to install |

`claude plugin validate .` checks the first two agree. **Nothing checks the third or the
fourth.** The Codex manifest and the README line are the two to remember, and the README
line is the easier to miss because it is prose rather than a manifest.

This table said *three files* until 0.8.0, and the README line was left at 0.7.0 through
the bump. Nothing caught it: the validator passed, both suites passed, and the plugin
installed. It was found by grepping the old version string across the repository
afterwards — which is now a step rather than an accident:

```bash
grep -rn '0\.7\.0' --include='*.json' --include='*.md' --exclude=CLAUDE.md \
  --exclude-dir=superpowers . | grep -v worktrees        # expect none
```

`--exclude-dir=superpowers` is load-bearing for the same reason: the specs and plans under
`docs/superpowers/` are dated records, and one of them describes the release it planned,
version number included. Found at the 0.9.1 bump, when the grep for `0.9.0` hit 13 lines of
the rename's spec and plan, all correct as history.

Run it with the version you are leaving, after the bump, and expect zero hits.
`--exclude=CLAUDE.md` is load-bearing: the paragraph above names real version numbers, so
without it this check reports a hit on its own documentation every time and teaches you to
ignore it.

Releasing is: bump all four, run both suites (`python3 tests/test_validate_bundle.py` and
`python3 tests/test_catalogs.py` — there is no pytest here), commit, **push**, then
`claude plugin marketplace update belay && claude plugin update belay@belay`.
The push is not optional: the marketplace source is the GitHub repository, so an unpushed
bump is invisible to it.

Run the validator suite once more with `BELAY_SWEEP_SIBLING_REPOS=1` before you push a
release. The plain run validates only this commit, by design (belay#37); that run also
validates the published bundles in `skomp/belay-bundles`, which is the only place a
format change is seen against real courses. It reports what it added on its own line and
never folds it into the total.

Minor for added format surface, patch for a fix. Verify by diffing the installed cache
under `~/.claude/plugins/cache/belay/belay/<version>/` against the working tree —
and probe for something the previous version lacks, so a silent no-op cannot pass as a
success.
