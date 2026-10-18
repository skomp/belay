#!/usr/bin/env python3
"""Claude Code PreToolUse hook: the ownership rules, enforced on file edits.

hooks/hooks.json at the plugin root runs this for Write, Edit, MultiEdit and
NotebookEdit. It reads the hook payload on stdin and answers with Claude
Code's documented PreToolUse output:

    {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                            "permissionDecision": "deny" | "ask",
                            "permissionDecisionReason": "..."}}

This is defence in depth. runner-protocol.md section 5 is the rule and the
tutor follows it on every host; this hook is a second line on the one host
that can intercept a write. It never grants anything: it either says nothing
or narrows what the host would otherwise allow.

Three properties are the whole contract, and tests/test_ownership.py proves
each:

  * Silent outside a course. Unless the session's working directory (or the
    project directory) holds tutorial/tutorial.yaml with an `instance:` stamp,
    it exits 0 and prints nothing. A plugin that is installed is loaded in
    every session, and this must be invisible in all of them but a course.
  * Fail open. Any error - a payload it does not expect, a manifest that does
    not parse, an unknown policy - exits 0 with no output. A guard that breaks
    ordinary editing is worse than none.
  * No second rule. Every verdict comes from ownership.resolve, so the hook
    and the protocol cannot disagree about who owns a path.

It cannot see a write made through a shell command (sed -i, a redirect, a
generator). Those stay protocol-only; references/runner-protocol.md section
5 says so.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True

GUARDED_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _workspace(payload: dict) -> Path | None:
    """The workspace holding a stamped instance, or None.

    The payload's `cwd` first, then CLAUDE_PROJECT_DIR, which stays at the
    project root when the session's directory moves below it."""
    candidates = [payload.get("cwd"), os.environ.get("CLAUDE_PROJECT_DIR")]
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate:
            continue
        manifest = Path(candidate) / "tutorial" / "tutorial.yaml"
        try:
            text = manifest.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # A cheap look before any import: no stamp line, no instance.
        if any(line.startswith("instance:") for line in text.splitlines()):
            return Path(candidate)
    return None


def _target(payload: dict) -> str | None:
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    for key in ("file_path", "notebook_path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _relative(target: str, workspace: Path, ownership) -> str | None:
    """Workspace-relative path for `target`, or None when it is outside.

    Lexical first; if that says outside, compare the resolved real paths too,
    so a workspace reached through a symlink still matches itself."""
    absolute = target if os.path.isabs(target) else str(workspace / target)
    rel = ownership.normalise(absolute, workspace)
    if rel is None:
        rel = ownership.normalise(os.path.realpath(absolute),
                                  os.path.realpath(workspace))
    return rel


def _copies_a_bundle_file(content: str, workspace: Path) -> bool:
    """True when `content` is byte-identical to a file the instance carries
    under tutorial/lessons/.

    runner-protocol.md section 10.1 lets the tutor create a learner-owned
    file only when it is one the bundle ships and the lesson prose says where
    it goes. Whether the prose says so is a judgement the hook cannot make,
    so for such a create it steps back and leaves the protocol to decide."""
    lessons = workspace / "tutorial" / "lessons"
    wanted = content.encode("utf-8")
    for dirpath, _dirnames, filenames in os.walk(lessons):
        for name in filenames:
            path = Path(dirpath) / name
            try:
                if path.stat().st_size == len(wanted) and path.read_bytes() == wanted:
                    return True
            except OSError:
                continue
    return False


def decide(payload: dict) -> dict | None:
    """The hook output for one payload, or None for no decision."""
    if not isinstance(payload, dict):
        return None
    if payload.get("tool_name") not in GUARDED_TOOLS:
        return None
    target = _target(payload)
    if target is None:
        return None
    workspace = _workspace(payload)
    if workspace is None:
        return None

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ownership  # noqa: E402 - only imported inside a course

    manifest = ownership.load_instance_manifest(workspace)
    if manifest is None:
        return None
    rel = _relative(target, workspace, ownership)
    if rel is None:
        return None
    absolute = workspace / rel
    tool = payload["tool_name"]
    operation = (ownership.CREATE if tool == "Write" and not absolute.exists()
                 else ownership.MODIFY)
    supplies = ownership.collect_supplies_targets(manifest, workspace)
    result = ownership.resolve(rel, operation, manifest, True, supplies)

    if result.verdict == ownership.ALLOW:
        return None
    if (operation == ownership.CREATE and result.owner == ownership.LEARNER):
        content = payload["tool_input"].get("content")
        if isinstance(content, str) and _copies_a_bundle_file(content, workspace):
            return None

    if result.owner == ownership.READ_ONLY:
        # Asked, not denied: the one legitimate write here is an update the
        # learner asked for (state-lifecycle.md section 3.2), which copies the
        # bundle's lessons in, and only the learner can say that is happening.
        decision = "ask"
        reason = (f"Belay: {rel} is a lesson copy. {result.rule}. The only write "
                  f"there is a course update you asked for; approve only if "
                  f"that is what this is.")
    elif result.verdict == ownership.NEEDS_LEARNER_REQUEST:
        decision = "ask"
        reason = (f"Belay: {rel} is yours ({result.rule}). The tutor may change "
                  f"it only because you asked for this change; approve only if "
                  f"you did.")
    else:
        decision = "deny"
        reason = (f"Belay ownership guard: {rel} - {result.rule}. Do not write "
                  f"it by another route; teach the learner to make the change.")
        if result.owner == ownership.SUPPLIES_TARGET:
            reason = (f"Belay ownership guard: {rel} - {result.rule}. Leave the "
                      f"file as it is.")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        output = decide(payload)
    except Exception:  # fail open: no decision is the only safe error
        return 0
    if output is not None:
        sys.stdout.write(json.dumps(output))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
