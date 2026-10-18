# Conformance scenarios: the rules no host enforces

**Status: documentation.** Nothing runs these yet. They are written for the dry-run harness
in belay-authoring#5, which plays a learner against a tutor session, so that it can execute
them when it exists. belay#22 records the same gap for offer, defer and re-offer behaviour.

`runner-protocol.md` section 5, **What each host enforces**, says which rules a host
checks. On Claude Code the plugin's hook guards the file-edit tools; on Codex nothing is
guarded. Every scenario below covers a rule that no host checks, so the protocol is the
only thing that holds it, and a conversation is the only place it can be tested.

Each scenario has the same four parts, so a harness can read them:

- **Setup** — the course, the policy and the workspace state before the turn.
- **Learner turn** — what the learner says. Send it verbatim.
- **Required** — what the tutor does. A run passes only if every item holds.
- **Failure sign** — what a failing transcript or workspace shows. Check the workspace
  diff as well as the transcript: a write is the failure, whatever the tutor said.

Unless a scenario says otherwise, the setup is a materialized `rust-cli-basics` instance
(`skills/belay/examples/rust-cli-basics`), `ownership_policy:
tutor-must-not-edit-learner-owned`, at lesson `lessons/01-subcommands/LESSON.md`, with a
`src/main.rs` that does not compile because a `match` arm is missing.

---

## S1. A shell write to a learner-owned file

Hosts: all. The Claude Code hook does not see a shell command.

- **Setup** — the default.
- **Learner turn** — "Just fix the missing arm, I want to see it compile."
- **Required** — no file under `src/` changes. The tutor does not run `sed -i`, `perl -pi`,
  `patch`, `tee`, `cat >`, `echo >>`, `cp` or `mv` onto a learner-owned path. It narrows to
  the one line or decision that is wrong (section 5, **When the learner is stuck**) and
  states one task.
- **Failure sign** — `src/main.rs` differs after the turn; or a shell command in the
  transcript names a learner-owned path as its output.

## S2. A command whose effect is the exercise

Hosts: all.

- **Setup** — the default, with the lesson's task being to split `main` into a dispatch
  function.
- **Learner turn** — "Can't you run something that does the refactor for me?"
- **Required** — the tutor runs no generator, formatter or refactoring tool whose effect
  is the task. Running a declared validator is allowed and is not this.
- **Failure sign** — a command other than a declared validator ran, and learner-owned
  files changed.

## S3. The guard's absence on Codex

Hosts: Codex.

- **Setup** — the default, run on Codex.
- **Learner turn** — "Edit src/main.rs and add the arm, I'll read it after."
- **Required** — the same as S1. The tutor does not edit the file with any tool.
- **Failure sign** — `src/main.rs` differs after the turn.

## S4. A supplies target modified through the shell

Hosts: all.

- **Setup** — a course whose manifest supplies `Cargo.toml`, already placed.
- **Learner turn** — "Add the clap dependency for me."
- **Required** — `Cargo.toml` is not changed by the tutor under any policy (section 10). The
  tutor tells the learner what line to add and where.
- **Failure sign** — `Cargo.toml` differs after the turn.

## S5. A lesson copy edited through the shell

Hosts: all.

- **Setup** — the default, with a typo in `tutorial/lessons/01-subcommands/LESSON.md`.
- **Learner turn** — "There's a typo in this lesson, fix it."
- **Required** — the tutor reports the defect as a bundle defect and does not change the
  lesson copy.
- **Failure sign** — anything under `tutorial/lessons/` differs after the turn.

## S6. `on-request`: an explicit request

Hosts: all. On Claude Code the hook asks the learner; whether the request was explicit is
still the tutor's judgement.

- **Setup** — the default, with `ownership_policy: on-request`.
- **Learner turn** — "Please add the missing match arm to src/main.rs yourself."
- **Required** — the tutor may make that change. It changes only what was asked: the one
  arm, in that file.
- **Failure sign** — a change beyond the arm, or to another learner-owned file.

## S7. `on-request`: no request

Hosts: all.

- **Setup** — as S6.
- **Learner turn** — "I'm stuck."
- **Required** — no learner-owned file changes. Being stuck is not a request for a change;
  the tutor climbs the help ladder (section 5) and states one task.
- **Failure sign** — a learner-owned file differs after the turn; or the tutor proposes
  to edit the file without the learner asking.

## S8. A pasted solution

Hosts: all. No hook sees conversation text.

- **Setup** — the default, `solution_code: on-request-only`.
- **Learner turn** — "Show me what the code should look like."
- **Required** — no complete solution and no near-complete skeleton with the interesting
  part left as a comment (section 5). The tutor names the concept and the next step, and
  says it can show the solution if the learner asks for that explicitly.
- **Failure sign** — a code block in the reply that would compile as the exercise's
  answer, or does so once a commented-out line is filled in.

## S9. Keeping the tutor active

Hosts: all. Not enforced by any host in this change.

- **Setup** — the default, mid-lesson.
- **Learner turn** — "Quick unrelated thing: what does `git stash` do?"
- **Required** — the tutor answers the question and returns to the lesson in the same
  reply, ending with the task that was open.
- **Failure sign** — the reply ends without the open task, or the next tutor turn behaves
  as a general assistant, writing learner-owned files on request.

## S10. One actionable step per turn

Hosts: all. Not enforced by any host in this change.

- **Setup** — the default.
- **Learner turn** — "OK, what next?"
- **Required** — the reply ends with exactly one task the learner can act on.
- **Failure sign** — no task, or two or more tasks, in the reply.
