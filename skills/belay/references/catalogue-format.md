# Catalogue Format — Finding a Tutorial to Offer

**Status:** normative for the runner. Load this when no active instance was found and you
must find a tutorial to offer, or when the learner asks what tutorials are available.

A catalogue is a list of tutorials the runner can offer. It holds **metadata only**. It
is not a course, and reading it must never require reading a course.

A learner configures **many** catalogues, and any of them may live in a Git repository.
The `belay-catalogs` command fetches, caches and merges them, and you act on what it
prints. Fetching, precedence, staleness and failure classification are deterministic and
easy to get subtly wrong, so they are in code and not in your judgement.

---

## 1. The rule that makes catalogues cheap

> **Discovery loads metadata only. Do not open anything under a candidate's bundle path
> until the learner has chosen.**

Not the bundle's `tutorial.yaml`, not `COURSE.md`, not the lesson list, not a lesson
file. Everything needed to present a choice is already in the catalogue entry.

This is not merely a context saving. It is what makes a remote catalogue work: a
catalogue fetched from a repository returns the same entry shape, and its bundles may not
even be on the machine yet. A runner that peeks into the bundle to enrich a choice works
only for local sources and silently breaks the provider boundary.

`belay-catalogs discover` keeps the rule mechanically: it never opens, lists or stats
anything under a bundle path. `belay-catalogs resolve <id>` and `belay-catalogs materialize
<id>`, which run **after** the learner has chosen, are the steps that are allowed to look.

---

## 2. Where catalogues live

| File | Ships | Holds |
|---|---|---|
| `~/.config/belay/catalogs.yaml` | no | the list of catalogues, in priority order |
| `catalog/builtin.yaml`, relative to this skill | yes | only tutorials shipped with the plugin |
| `~/.config/belay/catalog.yaml` | no — created on first registration | the user's own registrations |
| `~/.cache/belay/catalogs/<id>/` | no | the last successful copy of each catalogue, and any clone |

**When `catalogs.yaml` is absent**, the runner behaves as though it listed
`~/.config/belay/catalog.yaml` first and the bundled catalogue second. That is exactly
the two-file model this replaced, so an existing user catalogue keeps working with no
migration and no action from you. A missing user catalogue is the normal state on a first
run: it is left out rather than reported as a failure.

`belay-catalogs status` prints the configuration that the default implies. Use that text when
you write a real `catalogs.yaml`, so nothing already in use is dropped.

---

## 3. `catalogs.yaml` — the catalogue of catalogues

```yaml
catalogs_version: 1
catalogs:
  - id: mine
    source: { type: file, path: ~/tutorials/catalog.yaml }
  - id: skomp
    source:
      type: git
      url: git@github.com:skomp/belay-bundles.git
      ref: main
      path: catalog.yaml          # repository root, or any subfolder
  - id: builtin
    source: { type: bundled }
```

| Field | Required | Meaning |
|---|---|---|
| `catalogs_version` | SHOULD | `1` for this document. A version the runner does not know is an error, not a guess. |
| `id` | MUST | `[a-z0-9-]+`, unique. It names a cache directory and it is how failures are reported. |
| `source.type` | MUST | `bundled`, `file` or `git`. |

| `source.type` | Extra fields | Where the catalogue comes from |
|---|---|---|
| `bundled` | none | `catalog/builtin.yaml`, which ships with the plugin |
| `file` | `path` | a path on this machine; `~` is expanded |
| `git` | `url`, `ref` (optional), `path` (optional, default `catalog.yaml`) | a clone of that repository |

**The order is the priority order.** Put the user's own sources before `builtin`, so a
user can override a shipped tutorial. Section 6 covers what that obliges you to say.

**Authentication.** A `git` catalogue uses the Git credentials the user already has — an
SSH key, a credential helper, `gh`. The runner manages no tokens, stores no secrets and
never prompts for credentials; a request for one is turned into a reported failure rather
than a process that waits for a human who is not there. A private repository installs by
exactly the same mechanism as a public one. If a repository the user can clone by hand
fails here, the failure is real and worth reporting, not worth working around.

---

## 4. The script, and the three things it does

Run it as the bare command `belay-catalogs`, which the plugin puts on the host's `PATH`.
When that reports `command not found` — a host without plugin `bin/` support, such as the
Codex skill route — run `python3 <skill dir>/scripts/catalogs.py` with the same arguments,
where `<skill dir>` holds `SKILL.md`; `runner-protocol.md` section 1 has the same fallback
for the other three commands. It needs Python 3 and the `git` command, and nothing else.

| Command | When | What it does |
|---|---|---|
| `belay-catalogs discover` | a discovery request starts | refreshes every catalogue, then prints the merged catalogue and the status of each source |
| `belay-catalogs status` | the learner asks what is configured, or a failure needs explaining | prints each catalogue's state from disk; fetches nothing |
| `belay-catalogs resolve <id>` | the learner has chosen, and wants to know where the course comes from | prints that entry and the bundle directory it resolves to, and checks the bundle is really there |
| `belay-catalogs materialize <id>` | the learner has chosen | resolves the entry as `resolve` does and creates `tutorial/` in the current directory from it: copy, `STATE.md`, stamp (`state-lifecycle.md` section 3) |
| `belay-catalogs place-supplies` | materialization, after validation; and after an update | places the manifest's `supplies` from the source the instance stamp names, never overwriting (`state-lifecycle.md` section 3 step 8) |
| `belay-catalogs report` | the learner wants to send a defect report the tutor drafted in `tutorial/REPORT.md` | prints which target it chose and a link the learner opens to send it; `--runner` for a defect in the runner, `--context` for what goes in the draft. Sends nothing (`runner-protocol.md` section 17) |
| `belay-catalogs covers <query>` | the learner asks who **teaches** a concept | prints every bundle whose `covers` answers, with the reason each one matched |
| `belay-catalogs follow-ups <id>` | a course finished, or the learner asks what comes next | prints the author's follow-ups, then the bundles that name this one as a previous bundle |
| `belay-catalogs prepare <id>` | the learner asks how to get ready for a course | prints the bundles that cover what it `assumes` |

The last three are **section 12**, and they fetch nothing unless given `--refresh`. A
concept question is asked in the middle of a conversation, often several times, and
refreshing once per question is the per-turn refresh this document forbids below.

Useful options: `--json` for an exact machine-readable form, `--offline` to serve what is
on disk without fetching, `--timeout SECONDS` for a slow host. A query that starts with a
`-` needs `--` before it, as with any command.

Exit codes: `0` every catalogue answered; `1` at least one was served from cache or could
not be served, and there is still something to offer; `2` the configuration is unusable and
nothing was fetched; `3` there is nothing to offer at all. `materialize` and
`place-supplies` have their own, tabled in `state-lifecycle.md` section 3: `0` done, `2`
usage, `3` refused with nothing written, and for `place-supplies` `1` when a learner's file
stands in the way of a target. `report` has its own, tabled in `runner-protocol.md` section
17.5: `0` a link was printed, `1` there is no target and the draft is the learner's to
send by hand, `2` usage, or no instance or no usable draft. It writes nothing, so it has no
refusal.

**No command here is given a bundle path** (belay#76). A bundle sits outside the learner's
workspace, and under `permissions.blockReadsOutsideWorkingDirectories` the host asks before
any command that names such a path. `materialize` takes the id and `place-supplies` reads
the instance stamp; both open the bundle inside their own process, fetch nothing, and run
nothing the bundle declares. `report` reads the instance, its draft and the catalogues on
disk, and opens no bundle at all.

### When to refresh

**Refresh when a discovery request starts. Once.** Never once per turn, and never during
a resume — a resume reads no catalogue at all, so a learner continuing a course pays
nothing for any of this. The one read during a course is `report`, and only when the learner
wants to send a defect report: it reads the copies already on disk and fetches nothing.

An exit code of `2` is the one case where you stop and ask: the catalogue of catalogues
decides every other step, so nothing was fetched. Say which line is wrong, and offer to
correct it or to remove the file and fall back to the implied default.

---

## 5. Entry schema

```yaml
catalog_version: 1
tutorials:
  - id: rust-automaton-db
    title: Learn Rust by Building AutomatonDB
    description: >
      Project-driven Rust taught by building a serious automaton-native,
      partitioned database with storage-engine and distributed-systems depth.
    subjects: [rust, databases, distributed-systems, automata, storage-engines]
    aliases: [cassandra-like, key-value-store, database-internals]
    level: intermediate-to-advanced
    style: [project-driven, interactive, long-form]
    scope: "23 lessons; months of work"
    workspace_kind: existing-or-new-repository
    source:
      type: local
      path: rust-automaton-db
```

| Field | Required | Meaning |
|---|---|---|
| `catalog_version` | MUST | Top level. `1` for this document. A version you do not recognise is an error, not a guess. |
| `tutorials` | MUST | Top level. The list of entries. These two are the only top-level keys; every row below is a field of one entry. |
| `id` | MUST | Stable identity, `[a-z0-9-]+`. Matches the bundle's `id`. |
| `title` | MUST | Human-facing course name. |
| `description` | MUST | One or two sentences. This is what a learner reads when choosing. |
| `subjects` | MUST | Lowercase topic tags. The primary matching signal. |
| `aliases` | SHOULD | Terms a learner might say instead of a subject. |
| `level` | MUST | `beginner`, `intermediate`, `intermediate-to-advanced`, and so on. |
| `style` | SHOULD | `project-driven`, `exercise-based`, `interactive`, `long-form`. |
| `scope` | SHOULD | Honest size, on the **main path**. "23 lessons; months of work" is a service to the learner. |
| `optional_lesson_count` | MAY | How many lessons the course carries **beside** the main path, which `scope` does not count. A whole number, zero or more. A generator writes it in every entry, `0` included; absence means the catalogue predates the field. Section 5.2. |
| `workspace_kind` | MUST | What the course needs of a workspace. Surfaced at choice time. |
| `covers` | SHOULD | The concepts the course **teaches**, each with a `summary` and optional `aliases`. Section 12. |
| `assumes` | SHOULD | The concepts the course **expects you to bring**, each with a `level` and a `summary`. Never a gate. Section 12. |
| `recommended_follow_ups` | MAY | Courses the author suggests **after** this one, each with a `because`. Author order is display order. |
| `recommended_previous_bundles` | MAY | Courses the author suggests **before** this one, each with a `because`. This is how a course attaches itself to an earlier one. |
| `report` | MAY | Where a learner's defect report about this course goes, when the bundle's own `tutorial.yaml` says nothing: a `url` starting `https://` or `mailto:`, and an optional `prefill` of `github`, `gitlab` or `none`. The same shape and rules as the manifest key (`bundle-format.md` section 2, **Defect reports**). |
| `source` | MUST | Where the bundle is. See section 5.1. |

The entry duplicates fields that also appear in the bundle's `tutorial.yaml`. That is
deliberate: the duplication is exactly what lets discovery run without opening the
bundle. When the two disagree, the bundle is authoritative — but you learn that only
after the learner has chosen, and a mismatch is worth mentioning then.

An entry missing a MUST field is malformed. The script skips it and names the entry and
the field. Pass that on rather than pretending the catalogue was complete.

**`report` lets a catalogue owner collect reports for a course they do not control.** The
runner takes the target from the bundle's own manifest first, then from this field on the
entry that won the merge for that `id` (section 6), then from the issue page of that
entry's catalogue when it is a Git repository on `github.com` or `gitlab.com` — so an
entry in a bundles repository on one of those hosts needs no `report` at all to reach it.
The validator checks the field on check 3 and reports a malformed one as a **finding**, not
a warning: it is a value a runner builds a link from, not a key it ignores. The reader is
tolerant all the same: a malformed `report` never removes a course from discovery, and the
report command skips it, says why, and moves to the next target.

**A field this document does not define is warned about, never rejected.** A catalogue is
data that a newer runner may extend, and a validator that refused an unknown key would turn
a valid newer catalogue into an unusable one — the same rule `bundle-format.md` section 13
sets for bundles, where an older reader degrades rather than refuses.

So the validator reports an unrecognised entry field as a **warning**, on check 3, and the
catalogue stays usable. A key close to a field this document defines is called out as a
likely misspelling, because that is the case with no other signal anywhere: a runner reads
an entry by field name and ignores a name it does not know, so `optional_lesson_cnt` is
silently absent rather than reported, and the entry simply advertises nothing by it.

**The same rule applies at the top level.** A key beside `catalog_version` and
`tutorials` that this document does not define is warned about, on check 1, and the
catalogue still passes. The validator used to reject it, which contradicted the rule
above and defeated the point of it: the file a newer runner writes is exactly the file an
older validator has never seen, and refusing it is the one failure an additive format
exists to prevent.

**No top-level key needs its unknown neighbours rejected.** A catalogue is unusable when
`catalog_version` or `tutorials` is **absent**, and absence is still a finding —
check 1 for the version, check 2 for the list. A key nobody recognises sitting *beside*
them takes nothing away. So a misspelled `tutorails` produces both reports in one run:
the check 1 warning naming the spelling, and the check 2 finding that `tutorials` is not
there. Softening the unknown key never softened the missing one.

Both checks read the **keys of the parsed mapping** — the document's own for check 1,
each entry's for check 3. Neither searches the file's text. A generated catalogue's header
comment names the fields it derives, and a text search would report those comments as
unknown fields while missing a real one — the same arithmetic that makes a loose
`grep -c` of a field name read as complete exactly when one entry is missing it.

### 5.1 `source`, and where a bundle path resolves from

`source` is the **entire** provider boundary for a bundle. Everything else in this
runner — matching, choice, materialization, state lifecycle, teaching — is written
against the entry and never against its origin.

| `type` | Extra fields | Status |
|---|---|---|
| `local` | `path` | implemented |
| `git` | `url`, `revision` | declared, **not implemented** |
| `archive` | `url` | declared, **not implemented** |

> **A bundle path resolves relative to its own catalogue's root: the directory that holds
> the catalogue file.**

That one rule is what lets a bundles repository ship a `catalog.yaml` at its root listing
its own bundles by relative path. A learner adds the repository with one entry in
`catalogs.yaml`, and the bundles arrive with it. For a `git` catalogue the root is inside
the local cache clone, so `belay-catalogs resolve` prints an absolute path under
`~/.cache/belay/` — that is correct, and `belay-catalogs materialize` copies from there,
inside its own process, so the tutor never names that path.

An absolute path, or one starting with `~`, is used as written. A catalogue fetched from a
repository may **not** do that, and may not climb out of its own directory with `..`: such
an entry is skipped with a reason, because a remote catalogue that can name any directory
on the learner's machine is a different and much larger thing than a list of courses.

A `git` or `archive` **bundle** source is still unimplemented, and the script skips such an
entry with that reason. Say so; do not substitute a clone command and do not quietly drop
it. The repair is to add that repository as a **catalogue**, which is what the whole of
section 3 is for.

### 5.2 `optional_lesson_count`, and why the entry has to carry it

`scope` counts the **main path**. A course with eight main lessons and six optional ones
therefore reads exactly like a course with eight lessons and nothing beside them, and the
two are not the same course.

```yaml
scope: "8 lessons; a few days"
optional_lesson_count: 6
```

> **A runner may not count them. Section 1 holds: discovery opens no bundle, and a remote
> catalogue's bundles may not be on this machine at all.** The fact lives in the entry or
> the learner never learns it.

| | |
|---|---|
| **Shape** | a whole number, zero or more |
| **`0`** | the course has no optional lessons. **Write it.** |
| **Absent** | this catalogue predates the field, or was written by hand. It is **not** a claim that the course has none. |
| **Author** | derived from the length of the bundle's `optional_lessons` map, exactly as `scope` is derived from the length of its `lessons` list. |

**Write the field in every entry, including zero.** An earlier draft of this section said
to omit it at zero, and that made the format contradict itself: if `0` and absence mean the
same thing, then absence *is* the claim "this course has none", which the row above denies.

Written always, the two separate cleanly. `0` says the course has none. Absence says only
that this catalogue is older than the field or was typed by hand — a fact about the
catalogue, never about the course. A reader that cannot tell those apart cannot report
either honestly.

A hand-written catalogue may still omit it; nothing rejects that. A **generator** writes it
every time, and `catalog.py` in `skomp/belay-authoring` does.

**The name is deliberate.** A bundle's `tutorial.yaml` already has a key called
`optional_lessons`, and there it is a **mapping of lesson path to offer metadata**. One
name for two shapes in two files is a confusion this project has paid for before, so the
catalogue field is named for what it holds: a count.

**A count, not a sentence.** `scope` is already the free-text size field, and section 9.2
builds the time-commitment facet out of the distinct `scope` values it finds. A second
sentence would compete with it, could not be validated beyond "is a string", and could not
be generated from the bundle. A number can be checked, compared and derived.

**The count is not proof.** `belay-validate --catalog` checks its shape and nothing
else; no tool opens the bundle to recount. A count that disagrees with the bundle's
`optional_lessons` is wrong metadata of the same kind as a `scope` that under-states the
work, and the bundle is authoritative once the learner has chosen.

**`catalog_version` stays `1`.** The field is additive and optional, so every catalogue
written before it — including the one in the bundles repository — is still valid with no
edit. A reader that has never heard of the field ignores it, exactly as `supplies` is
additive to `bundle_format: 1`.

---

## 6. Precedence, and what you must say about it

> **First match wins, by tutorial `id`. The order in `catalogs.yaml` is the priority
> order.**

The generated default lists user sources before `builtin`, so a user can override a
shipped tutorial with their own.

**When an entry is overridden, say so.** Name the catalogue that supplied the tutorial you
are offering, and name the catalogues that were shadowed. `discover` prints an `OVERRIDES`
line for exactly this, and `resolve` repeats it. A silent substitution of a different
bundle is the same hidden choice the matching rules forbid everywhere else: the learner
believes they are getting the course they know by name, and the content is somebody
else's.

Two different `id`s that describe the same course are two entries, not an override.
Present both.

---

## 7. When a catalogue fails

**A failed refresh must not fail discovery.** Serve what answered. Name what did not.

The script does the mechanics; your job is to pass on three things without flattening
them: which catalogue failed, which of the failures it was, and whether what you are
showing is current.

| Kind | What it means | The repair |
|---|---|---|
| `unreachable` | the host could not be reached | the network, or a mis-spelt host name |
| `no-access` | no access to that repository, or it does not exist | credentials, or the repository name |
| `no-ref` | the repository has no such branch or tag | the `ref` field |
| `no-catalogue` | the repository was fetched and holds no catalogue file at that path | the `path` field |
| `missing-file` | a local catalogue file is not there | the `path` field, or create the file |
| `unreadable` | the file is not UTF-8 text | permissions, or the file itself |
| `malformed` | the file is not a usable catalogue | correct the file; check it with `belay-validate --catalog <path>` |
| `no-git` | the `git` command is not installed | install git |
| `unclassified` | git failed in a way the script does not recognise | read git's own message, which is printed verbatim |

These are not one message. "Check your network" sent to someone whose SSH key is simply
not on that repository wastes their afternoon. Report the kind the script reported, and
the repair that goes with it.

**Never present stale results as current.** When a catalogue is served from cache, the
entries from it are marked `cached` and the report carries the timestamp of the last
successful refresh. Say both: that these results are cached, and how old they are. When a
catalogue could not be served at all, say that too — "nothing matched your subject" is a
false statement when a whole catalogue is missing from the list.

`unclassified` is a real answer and a useful one. It means the script declined to guess.
Show git's message as it stands rather than deciding for it.

---

## 8. Matching

Matching is agent judgement against `subjects`, `aliases`, `title`, `description`,
`level` and `style`. It is not a scoring function, and there is no threshold to tune.

**When the learner names a concept rather than a subject, section 12 is the answer** and
it is not judgement: `belay-catalogs covers <concept>` is deterministic, and it tells you
which bundles teach that concept and why each one is in the list.

Rules, all of which matter more than ranking quality:

- **Never silently choose when more than one entry plausibly matches.** Present them.
- **A single match is offered, never auto-started.** One candidate is still a choice.
- **State why each candidate matched**, so the ranking is inspectable and the learner can
  correct it. "Matched on `rust` and `databases`; you said storage engines, which is in
  its aliases" is a reason. "Best match" is not.
- **Do not discard weak-but-valid alternatives.** Rank them lower and say why they are
  lower. A learner who said "Rust" may want the beginner course even though their
  phrasing sounded advanced.
- **Level mismatch is a note, not a filter.** Say that a course is advanced; let the
  learner decide.
- **When nothing matches**, say so plainly, list what is available by title and subject,
  and offer to register a tutorial. Do not stretch a poor match into a recommendation.
  If any catalogue was cached or unavailable, say that before you say nothing matched.

---

## 9. Presenting the choice

### 9.1 A choice is a selection, not a paragraph

> **Offer the candidates as a list the learner picks from.**

Use whatever interactive selection this host provides for a question with a fixed set of
answers, so the learner picks an option instead of retyping a title. When the host has no
such mechanism, number the candidates and ask for a number. Both of those are a
selection. Three paragraphs describing three courses and ending "which would you like?"
is not one, and it is the failure this section exists to prevent.

This holds for every question a discovery asks, not only the last one. The facet
questions in 9.2 are selections as well.

### 9.2 Narrow only when there are too many candidates

**The trigger is the number of candidates, never the shape of the request.**

- **Four or fewer candidates — present them now.** "I want to learn WebGL" lands on one
  entry. Asking that learner which subject interests them interrogates someone who has
  already answered.
- **More than four — narrow one facet at a time**, in the order people choose a course:
  **subject, then level, then time commitment.** Ask one facet, filter the candidates,
  then count again. Stop as soon as four or fewer remain and present the real choice.

**Every facet's options are built from the candidates in hand, never from a fixed list.**

| Facet | Built from | Offered as |
|---|---|---|
| subject | the `subjects` and `aliases` of the current candidates, gathered into the few families they fall into | a selection of those families |
| level | the distinct `level` values of the current candidates | a selection of those values |
| time commitment | the distinct `scope` values of the current candidates | a selection of those values, in the learner's own terms — "a few hours" against "months of work" |

A facet on which every candidate agrees tells the learner nothing: skip it and go to the
next. A facet with more options than fit one comfortable question is **grouped, not
truncated** — a subject family covering three entries is one option, whereas leaving the
fourth entry out of the question hides it.

Because the options come from the catalogue just loaded, a new bundle's subject appears
in the first question on its own, and this document never has to list one.

### 9.3 Never narrow to zero, and always leave a way out

- **A filter that would empty the list is not applied.** Say that no course carries that
  combination, keep the previous set, and offer another facet or the whole list. This is
  the honesty rule of section 7 in a second place: "nothing matched" is a false statement
  when the truth is "your last two answers do not occur together".
- **Every question carries an escape hatch** — an option that shows everything on offer,
  available at any point — and an answer that is none of the offered options is honoured
  as the learner wrote it. Someone who already knows what they want must never be walked
  down a tree to reach it.
- **Narrowing never chooses.** It shortens a list; the learner still chooses from what
  survives. Section 8 holds throughout: a single survivor is offered and never
  auto-started, weak-but-valid alternatives are ranked lower rather than dropped, and
  every candidate still says why it matched.

### 9.4 What each candidate shows

For each candidate, show:

- `title`
- `description`
- `level`
- `scope` — **and, beside it, `optional_lesson_count` when the entry carries one above
  zero**. It qualifies `scope` and is shown with it rather than as a field of its own: a
  learner comparing two courses of "8 lessons" needs to know that one of them has six more
  on offer. Say nothing at all when the entry omits it — an entry that does not say is not
  an entry that says none.
- `workspace_kind` — in plain terms, because it is the field with a consequence: a course
  that needs a fresh repository is a different commitment from one that uses the current
  project
- the reason it matched
- **which catalogue it came from, when more than one is configured**, and whether that
  catalogue was current or cached
- **that it overrode a shipped or lower-priority entry**, when it did

Do **not** show:

- the lesson list — it is not in the entry, and fetching it means opening the bundle;
- the bundle path, unless the learner asks or two entries would otherwise be
  indistinguishable;
- a guess at content the entry does not state.

A selection whose options are titles alone is not enough: the learner decides on this
metadata, so it belongs beside the options, in the selection or in the sentence that
introduces it.

Then wait for an answer. When the learner has chosen, load `state-lifecycle.md` and run
`belay-catalogs materialize <id>` from the workspace root; that is the first moment
anything under a bundle path may be opened. When it refuses because the bundle is not
there, report it and stop — a cached catalogue can name a bundle the last successful fetch
did not carry.

---

## 10. Adding a catalogue, and registering a tutorial

**To add a whole repository of courses** — the cheap case, and the one to prefer:

1. ask for the repository URL, the branch, and where the catalogue file sits inside it
   (`catalog.yaml` at the root is the convention);
2. if `~/.config/belay/catalogs.yaml` does not exist, run `belay-catalogs status` first and
   write the configuration it prints, so the user's existing catalogue is not dropped;
3. add the entry **above** `builtin`, and below any catalogue the user said they prefer;
4. run `belay-catalogs discover` and show what arrived, including any entry that was skipped.

**To register one local bundle:**

1. ask for the source — a directory path for `local`;
2. open the bundle's `tutorial.yaml` to fill in `id`, `title`, `description`, `subjects`,
   `aliases`, `level`, `style` and `workspace_kind`. Registration is the one operation
   that legitimately opens a bundle without a learner having chosen it, because the
   learner is pointing at that specific bundle;
3. write the entry into `~/.config/belay/catalog.yaml`, creating the file with
   `catalog_version: 1` and a `tutorials:` list if it does not exist;
4. do not add the entry to `catalog/builtin.yaml`. That file ships with the plugin and
   holds only what the plugin ships;
5. show the entry you wrote.

`scope` is not in a bundle's `tutorial.yaml`. Derive it from the length of the manifest's
`lessons` list, and say that you did. Derive `optional_lesson_count` the same way, from the
number of keys in the manifest's `optional_lessons` map, and leave the field out when that
map is absent or empty.

A catalogue file can be checked before it is used: `belay-validate --catalog <path>`,
and `--portable` as well for a `catalog.yaml` that ships inside a bundles repository,
where every bundle must travel with the catalogue.

---

## 11. Failure modes to refuse

- **Peeking into a bundle to improve a recommendation.** It breaks the provider boundary
  and is the change that makes a remote catalogue impossible.
- **Counting a course's optional lessons yourself.** Opening `tutorial.yaml` to read its
  `optional_lessons` map is the same breach by a smaller door, and it is the reason
  `optional_lesson_count` is a catalogue field. Section 5.2.
- **Reading a missing `optional_lesson_count` as "this course has none".** The entry did
  not say. Say that, or say nothing.
- **Auto-starting a single match.** The learner chooses.
- **Presenting a choice as prose.** Candidates are options to pick from, not paragraphs
  to be read and then typed back. Section 9.1.
- **Narrowing a request that is already narrow.** The count decides, not the wording. One
  candidate is presented, not questioned. Section 9.2.
- **Offering a facet option this catalogue does not carry.** Every option comes from the
  candidates in hand. Section 9.2.
- **Narrowing to an empty list.** A filter that would empty the candidates is not
  applied; say so and keep the previous set. Section 9.3.
- **Walking a learner down a tree with no way out.** Every question offers everything.
  Section 9.3.
- **Refreshing per turn, or during a resume.** Once, when discovery starts.
- **Letting one failed catalogue fail the whole discovery.** Serve what answered.
- **Collapsing the failure kinds into one message.** Three problems, three repairs.
- **Presenting cached entries as current**, or saying "nothing matched" while a catalogue
  is missing from the list.
- **Substituting an overridden entry silently.** Say which catalogue supplied it.
- **Inventing a tutorial that is not in a catalogue.** If nothing matches, say nothing
  matches.
- **Editing `catalog/builtin.yaml` on a user's behalf.** User registrations go in the
  user catalogue.
- **Managing credentials.** No tokens, no secrets, no prompting. Git already has the
  user's access, or the user has a repair to make.
- **Materializing before the learner has chosen.** Presenting is free; copying is not.

---

## 12. Concepts — `covers`, `assumes` and recommendations

Four optional entry fields carry the relationships between courses. They are metadata, in
the catalogue, for the same reason `subjects` is: section 1 holds, and a concept question
must be answerable without opening a bundle that may not be on this machine at all.

> **Named bundles are recommendations. Concepts are the educational contract. Neither one
> gates access to a tutorial, and neither one asks the learner to prove anything.**

```yaml
covers:
  retained-event-logs:
    summary: >
      Records remain available after they are read and can be replayed from
      logical offsets.
    aliases: [append-only-log, replayable-log]

assumes:
  go-programming:
    level: working          # awareness | conceptual | working | advanced
    summary: >
      Write, test, and refactor ordinary Go programs using packages,
      goroutines, channels, errors, and contexts.

recommended_follow_ups:
  - bundle: distributed-log-broker
    because: >
      Extend the broker with multi-node placement, replication,
      acknowledgement policies, and failure recovery.

recommended_previous_bundles:
  - bundle: durable-event-broker
    because: >
      It teaches the retained-log, topic-partition, and offset model used here.
```

| Field | Holds | Each concept needs |
|---|---|---|
| `covers` | what the course **teaches** | `summary`; `aliases` optional |
| `assumes` | what the course **uses without teaching from first principles** | `level` and `summary`, both |

A concept id is `[a-z0-9-]+`, names a technical concept and never a lesson filename, and
is stable once published. There is **no central registry**: two authors who pick the same
id have agreed about a concept, and that is the whole mechanism.

| `assumes` level | The learner can |
|---|---|
| `awareness` | recognise the concept and its purpose |
| `conceptual` | explain the model and its major consequences |
| `working` | apply it in ordinary implementation or diagnosis |
| `advanced` | reason about hard edge cases and trade-offs with no introduction |

One concept may appear in both `covers` and `assumes` — a course that expects a baseline
and then teaches it deeper. That overlap is legal, and what decides a "who teaches this"
query is `covers`.

`subjects` keeps its meaning exactly. `covers` does not replace it: `subjects` is broad
classification for finding a course, and `covers` is a precise claim about what it teaches.

### 12.1 `covers` answers "who teaches this". `assumes` never does.

> **A query for bundles covering a concept searches `covers`, and never `assumes`.**

This is the single distinction the whole feature rests on. A course that *assumes*
retained event logs begins where a learner asking about them is stuck, so returning it as
a course that *teaches* them wastes exactly the time the question was asked to save.

`belay-catalogs covers <query>` keeps the rule mechanically. Run it rather than reading the
entries yourself.

### 12.2 The ranking, and why each result explains itself

`covers` ranks its answers on a fixed ladder, and prints the reason on every line:

| Rank | Route | The line it prints |
|---|---|---|
| 1 | the query is a concept id in `covers` | `Exact concept match: partition-offsets` |
| 2 | the query is one of that concept's `aliases` | `Alias match: stream-offsets (an alias of partition-offsets)` |
| 3 | the query's words appear in the concept's id, aliases or summary | `Text match on the summary of retained-event-logs: "logical offsets"` |
| 4 | the bundle **covers** the concept, **and** an author who *assumes* it names this bundle as a previous bundle | `Covers retained-event-logs, and streaming-query-engine - which assumes retained-event-logs - names it as a previous bundle` |
| 5 | the query matches a `subject` or a bundle-level alias | `Related subject: event-streaming` |

Ranks 1 and 2 are exact comparisons on normalised text, so "Partition Offsets",
"partition offsets" and `partition-offsets` are one query and always give the same answer.
**No semantic-search service is used or required**, and there is no scoring function to
tune. A question asked as a whole sentence is tried as written first; only if that finds
nothing is it retried with the question words removed, and the report says so when it was.

**Both halves of rank 4 are required, and the first half is the important one.** A bundle
reaches rank 4 only when its own `covers` declares the concept. The recommendation decides
nothing on its own: an author who writes `recommended_previous_bundles` is recommending a
course **order**, and has said nothing at all about what that earlier course teaches. Drop
the `covers` half and this rank answers "who teaches X" with a course that merely *needs*
X — section 12.1 broken by the one tier that is allowed to read `assumes`.

So what is rank 4 for? The course that *teaches* a concept and the course that *assumes*
it often describe it in different words. Rank 4 is the bridge: the query can match the
assuming author's wording, and still return the course that covers the concept. Every
bundle in a `covers` answer, at every rank, declares the concept in its own `covers`.

Rank 4 is tagged `[not an author recommendation]`, unlike the author routes in
`follow-ups` and `prepare`. It is a **join** of two separate declarations — this bundle's
`covers` and another author's `recommended_previous_bundles` — and neither author wrote
the conjunction. The author's own `because` is still printed and still attributed, because
provenance is never dropped; what is not claimed is that this author recommended this
bundle *as a place to learn the concept*. Section 12.4.

Pass these reasons on to the learner. "Best match" is not a reason; "it covers
`partition-offsets`, which is the phrase you used" is.

### 12.3 Several answers, kept several

- **Never collapse to one result.** A concept a learner asks about may be taught by three
  courses; all three are offered. The one named in someone's `recommended_previous_bundles`
  ranks first and hides nothing.
- **Never drop a lower tier.** A broad subject match is a weaker answer, not a wrong one.
  Rank it lower and say why it is lower. Section 8 applies here unchanged.

### 12.4 Provenance, and the line that must never be crossed

Every result carries **why** it is in the list, and a bundle reached by several routes
keeps **all** of them rather than the best one.

> **An inferred match is never presented as an author recommendation.**

An author recommendation is a sentence a human wrote in `recommended_follow_ups` or
`recommended_previous_bundles`, and it arrives with that author's own `because`. Everything
else — a shared concept id, an overlapping subject — is this runner noticing a pattern. The
report prints the two in separate sections and tags every single line
`[author recommendation]` or `[not an author recommendation]`. Keep that separation when
you present them; do not merge them into one ranked list, and do not paraphrase an
inference into "the author suggests".

**The tag answers the question that was asked, not "did a human type this".** The same
sentence in `recommended_previous_bundles` is an author recommendation in `prepare`, where
the learner asked what to take before a course and the author answered exactly that — and
is **not** one at rank 4 of a `covers` query, where the learner asked who teaches a
concept and the author never spoke about teaching. In a `covers` answer, no route is an
author recommendation: what a bundle teaches is its own `covers`, which is the runner
reading metadata. Section 12.2.

### 12.5 After a course: `follow-ups`, and the reverse index

`belay-catalogs follow-ups <id>` answers "what could I take after this", from three places, in
this order:

1. the finished bundle's own `recommended_follow_ups`, **in author order**;
2. every available bundle that names the finished one in its
   `recommended_previous_bundles` — read **backwards**, across every configured catalogue;
3. bundles that `assume` a concept the finished one `covers`, marked as inferred.

Point 2 is the reason the design is shaped this way. **A third party publishes a follow-up
to somebody else's course by naming it under `recommended_previous_bundles`, and the
original author never has to know, never has to agree, and never has to change a file.**
There is no registry and no central list; the link exists because one author wrote it down,
and it is found because the index reads that field in both directions.

A forward recommendation that no configured catalogue carries is **reported and not
fatal** — it is a pointer to a course that exists somewhere, not a dependency. Say that it
is unavailable; never fail a completed course over it, and never offer it as though it were
on the machine.

### 12.6 Before a course: `prepare`

`belay-catalogs prepare <id>` answers "how do I get ready for this", from the bundle's own
`recommended_previous_bundles` first, then bundles whose authors name it as a follow-up,
then every available bundle that **covers** a concept it **assumes**. An assumed concept
that nothing available covers is stated plainly rather than left as a silent gap.

None of it is a requirement. `assumes` is not a gate, an entitlement check or a completion
check, and this runner has no way to express one:

- **Never ask whether another bundle was completed**, and never look for a previous
  instance, licence or workspace to decide whether a learner may start.
- **Never auto-start, install, purchase or materialise** anything from a recommendation.
- **Never copy a previous course's workspace** because of relationship metadata.
  `recommended_previous_bundles` says *this is a good course to take earlier* and nothing
  else; what a workspace starts from is the workspace contract's business.
- The learner reads `assumes`, and the learner decides.

### 12.7 Exit codes and metadata problems

`covers`, `follow-ups` and `prepare` use the same codes as the rest of the script: `0` all
catalogues answered and something matched, `1` something matched but a catalogue was cached
or missing, `3` nothing matched or the bundle id is unknown, `2` the query is unusable — an
empty query is refused rather than answered with every bundle.

Relationship metadata is **optional**, so a mistake in it never takes a working course out
of the catalogue. A malformed concept or recommendation is dropped from the index and
reported as a `metadata problem` line. Pass those on to whoever can fix the entry;
`validate_bundle.py` is where an author asks to be told about them properly.

### 12.8 Failure modes to refuse, for concepts

- **Answering "who teaches X" from `assumes`.** It sends the learner to the course that
  begins where they are stuck. Section 12.1.
- **Returning a recommended previous bundle that does not `cover` the concept.** Rank 4
  reads `assumes` to find who *needs* a concept; returning that author's recommended
  predecessor without checking its `covers` is the failure above by a longer route.
  Section 12.2.
- **Collapsing a concept query to the one bundle somebody recommended.** Section 12.3.
- **Presenting a shared subject, or a shared concept id, as something the author
  recommended.** Section 12.4.
- **Dropping the reason a bundle matched.** A result that cannot explain itself cannot be
  corrected by the learner. Section 12.2.
- **Treating `assumes` as a prerequisite check**, asking whether an earlier course was
  finished, or refusing to start one. Section 12.6.
- **Failing a completed course because a recommended follow-up is not installed.**
  Section 12.5.
- **Requiring a semantic search service.** Exact ids and aliases are deterministic, and
  nothing here may depend on a service being reachable. Section 12.2.
- **Inventing a concept id an entry does not carry**, or reading a course's content to
  guess at one. Section 1 still holds: discovery loads metadata only.

---

## The reader is tolerant; the validator is strict

Relationship metadata (`covers`, `assumes`, `recommended_follow_ups`,
`recommended_previous_bundles`) is optional, and so is `optional_lesson_count`. **A typo in
optional metadata must never remove a working course from the catalogue.**

So the two sides of this feature deliberately disagree about malformed input:

| | Behaviour on malformed optional metadata |
|---|---|
| **the catalogue reader**, at discovery time | drops the offending concept, recommendation or count, records a note, and **keeps the tutorial discoverable** |
| **`validate_bundle.py`**, at authoring time | rejects it, because an author is asking to be told |

A learner searching for a course must not lose it because its author mistyped one alias.
An author running the validator wants every one of those mistakes named.

The notes are not silent: each dropped item records why, and the tutorial still appears with
its sound metadata intact. Proven by `test_relationship_metadata_never_removes_a_tutorial`,
which fires all five note kinds and asserts a sound concept beside them still matches, and
by `test_optional_lesson_count_is_carried_by_the_entry`, whose third entry carries a count
that is not a number and is still offered with every sound field it has.

**A dropped count is dropped, not defaulted.** `discover --json` reports
`optional_lesson_count: null` and puts the reason in that entry's `metadata_notes`, so no
consumer can read an unusable value as a number and none can mistake it for zero. The
rendered listing prints the same reason as a `metadata problem` line under the entry.

Two consequences worth stating, because both look like bugs otherwise:

- **Normalisation is `lowercase -> runs of [a-z0-9] -> joined with '-'`.** "Partition Offsets"
  and `partition-offsets` are the same query. This is what lets the exact-match tiers be
  string equality, with no fuzzy matcher and no service.
- **Question words are a second pass, and it is announced.** A query runs verbatim first; only
  if that finds nothing is it retried with question words removed, and the result says so.
  An exact id or alias can never be damaged by it, because the first pass would already have
  matched.
