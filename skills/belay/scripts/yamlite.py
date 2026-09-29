#!/usr/bin/env python3
"""A restricted YAML reader shared by the Belay scripts.

Stdlib only. This is the ONLY reader: the parse never consults the
environment, and PyYAML is not used even when it happens to be importable.
The reader parses the deliberately shallow subset the Belay formats use,
and *rejects* anything outside it rather than guessing.

Two scripts need this reader, so it lives in one place:

  * validate_bundle.py - reads tutorial.yaml and catalogues. An author runs it;
                         the runner also runs it once, at materialization.
  * catalogs.py        - reads catalogs.yaml and catalogue files, on every
                         discovery request.

Both run on a learner's machine, which is why neither may import a third-party
parser.

This module used to prefer PyYAML when it could import it (belay#29). That
made the answer a property of the machine rather than of the document: PyYAML
accepts an anchor and silently collapses a duplicate key, where this reader
refuses both, and it resolves `no`, `0x10` and `2026-09-13` to values this
reader leaves as strings. A bundle that validated for its author could fail
for a learner with no change to the bundle, and the diagnostic an author read
was decided by something the author did not choose. The preference is gone.

Guessing is the failure this module exists to avoid. A reader that silently
mis-parses an anchor, a tag or a multi-line plain scalar turns a structural
error into a wrong value, and every check downstream then certifies the wrong
document. Every construct outside the supported subset raises YamlError with
the line number and the reason.
"""

from __future__ import annotations

import re
from typing import Any



class YamlError(Exception):
    """The document uses something the restricted reader will not guess at."""


_UNSUPPORTED_INDICATORS = {
    "&": "anchors (&name)",
    "*": "aliases (*name)",
    "!": "tags (!name)",
    "%": "directives (%YAML)",
    "`": "the reserved indicator '`'",
    "@": "the reserved indicator '@'",
}

_NULLS = {"", "null", "Null", "NULL", "~"}
_TRUE = {"true", "True", "TRUE"}
_FALSE = {"false", "False", "FALSE"}


def _plain_to_python(text: str) -> Any:
    if text in _NULLS:
        return None
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


class _FlowParser:
    """Parses a single line's worth of YAML flow syntax.

    Supports: plain scalars, single- and double-quoted scalars, flow
    sequences [a, b], flow mappings {k: v}. Everything else raises.
    """

    def __init__(self, text: str, where: str, lineno: int) -> None:
        self.s = text
        self.i = 0
        self.where = where
        self.lineno = lineno

    def fail(self, msg: str) -> "YamlError":
        return YamlError(f"{self.where}: line {self.lineno}: {msg}")

    def parse(self) -> Any:
        value = self.value(in_flow=False)
        self.ws()
        if self.i < len(self.s):
            raise self.fail(
                f"unexpected text after the value: {self.s[self.i:]!r}"
            )
        return value

    def ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def value(self, in_flow: bool) -> Any:
        self.ws()
        c = self.peek()
        if c == "[":
            return self.sequence()
        if c == "{":
            return self.mapping()
        if c in ('"', "'"):
            return self.quoted()
        if c in _UNSUPPORTED_INDICATORS:
            raise self.fail(
                f"{_UNSUPPORTED_INDICATORS[c]} are not supported by the "
                f"restricted YAML reader; rewrite the value literally"
            )
        return self.plain(in_flow)

    def plain(self, in_flow: bool) -> Any:
        start = self.i
        while self.i < len(self.s):
            c = self.s[self.i]
            if in_flow and c in ",]}":
                break
            self.i += 1
        text = self.s[start : self.i].strip()
        if in_flow and text == "":
            raise self.fail("empty value in a flow collection")
        return _plain_to_python(text)

    def quoted(self) -> str:
        quote = self.s[self.i]
        self.i += 1
        out: list[str] = []
        while True:
            if self.i >= len(self.s):
                raise self.fail(f"unterminated {quote}-quoted string")
            c = self.s[self.i]
            if quote == "'":
                if c == "'":
                    if self.s[self.i + 1 : self.i + 2] == "'":
                        out.append("'")
                        self.i += 2
                        continue
                    self.i += 1
                    return "".join(out)
                out.append(c)
                self.i += 1
                continue
            # double quoted
            if c == "\\":
                esc = self.s[self.i + 1 : self.i + 2]
                simple = {
                    "n": "\n",
                    "t": "\t",
                    "r": "\r",
                    '"': '"',
                    "\\": "\\",
                    "/": "/",
                    "0": "\0",
                    " ": " ",
                }
                if esc not in simple:
                    raise self.fail(
                        f"escape sequence '\\{esc}' is not supported by the "
                        f"restricted YAML reader"
                    )
                out.append(simple[esc])
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1

    def sequence(self) -> list:
        self.i += 1  # consume '['
        out: list = []
        self.ws()
        if self.peek() == "]":
            self.i += 1
            return out
        while True:
            out.append(self.value(in_flow=True))
            self.ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.ws()
                if self.peek() == "]":
                    self.i += 1
                    return out
                continue
            if c == "]":
                self.i += 1
                return out
            raise self.fail(
                f"expected ',' or ']' in a flow sequence, found {c!r}"
                if c
                else "unterminated flow sequence '['"
            )

    def mapping(self) -> dict:
        self.i += 1  # consume '{'
        out: dict = {}
        self.ws()
        if self.peek() == "}":
            self.i += 1
            return out
        while True:
            self.ws()
            key = self.flow_key()
            self.ws()
            if self.peek() != ":":
                raise self.fail(
                    f"expected ':' after the key {key!r} in a flow mapping"
                )
            self.i += 1
            value = self.value(in_flow=True)
            if key in out:
                raise self.fail(f"duplicate key {key!r} in a flow mapping")
            out[key] = value
            self.ws()
            c = self.peek()
            if c == ",":
                self.i += 1
                self.ws()
                if self.peek() == "}":
                    self.i += 1
                    return out
                continue
            if c == "}":
                self.i += 1
                return out
            raise self.fail(
                f"expected ',' or '}}' in a flow mapping, found {c!r}"
                if c
                else "unterminated flow mapping '{'"
            )

    def flow_key(self) -> Any:
        if self.peek() in ('"', "'"):
            return self.quoted()
        start = self.i
        while self.i < len(self.s) and self.s[self.i] not in ":,]}":
            self.i += 1
        text = self.s[start : self.i].strip()
        if text == "":
            raise self.fail("empty key in a flow mapping")
        if text[0] in _UNSUPPORTED_INDICATORS:
            raise self.fail(
                f"{_UNSUPPORTED_INDICATORS[text[0]]} are not supported by the "
                f"restricted YAML reader"
            )
        return _plain_to_python(text)


def _strip_comment(line: str) -> str:
    """Remove a trailing '# ...' comment, respecting quotes.

    A '#' only starts a comment at the start of the line or after a space.
    """
    out: list[str] = []
    quote = ""
    for idx, c in enumerate(line):
        if quote:
            out.append(c)
            if c == quote:
                quote = ""
            continue
        if c in ('"', "'"):
            quote = c
            out.append(c)
            continue
        if c == "#" and (idx == 0 or line[idx - 1] in " \t"):
            break
        out.append(c)
    return "".join(out)


_KEY_RE = re.compile(
    r"""^(?P<key>"[^"]*"|'[^']*'|[^:#]+?)\s*:(?:[ \t]+(?P<val>.*))?$"""
)
_SEQ_KEY_RE = re.compile(r"""^("[^"]*"|'[^']*'|[^:#\[\]{},]+?)\s*:([ \t]|$)""")


class _RestrictedYaml:
    """Block-structure reader for the shallow YAML the bundle format uses.

    Supported: block mappings, block sequences, sequences of mappings, flow
    sequences and mappings, quoted and plain scalars, '>' and '|' block
    scalars with '-'/'+' chomping, comments, one leading '---'.

    Rejected with an explicit message: anchors, aliases, tags, directives,
    multiple documents, tabs in indentation, duplicate keys, explicit
    indentation indicators on block scalars, plain multi-line scalars, and
    any line that is not 'key: value' or '- item'.
    """

    def __init__(self, text: str, where: str) -> None:
        self.lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.n = 0
        self.where = where
        self.seen_doc_start = False

    def fail(self, lineno: int, msg: str) -> YamlError:
        return YamlError(f"{self.where}: line {lineno}: {msg}")

    # -- line scanning -----------------------------------------------------

    def peek(self) -> tuple[int, int, str] | None:
        """Return (index, indent, stripped text) of the next significant line."""
        while self.n < len(self.lines):
            raw = self.lines[self.n]
            # Measure the leading whitespace run over BOTH spaces and tabs, so
            # a tab-indented line is caught here rather than being read as an
            # un-indented one and reported as some unrelated syntax error.
            indent = len(raw) - len(raw.lstrip(" \t"))
            if "\t" in raw[:indent]:
                raise self.fail(
                    self.n + 1,
                    "a tab is used for indentation; YAML forbids this, use spaces",
                )
            content = _strip_comment(raw).strip()
            if content == "":
                self.n += 1
                continue
            if content == "...":
                raise self.fail(
                    self.n + 1,
                    "the document-end marker '...' is not supported",
                )
            if content == "---":
                if self.seen_doc_start or any(
                    _strip_comment(x).strip() for x in self.lines[: self.n]
                ):
                    raise self.fail(
                        self.n + 1,
                        "multiple YAML documents in one file are not supported",
                    )
                self.seen_doc_start = True
                self.n += 1
                continue
            return self.n, indent, content
        return None

    # -- entry point -------------------------------------------------------

    def parse(self) -> Any:
        first = self.peek()
        if first is None:
            return None
        _, indent, _ = first
        if indent != 0:
            raise self.fail(first[0] + 1, "the document starts with an indented line")
        value = self.parse_block(0)
        trailing = self.peek()
        if trailing is not None:
            raise self.fail(trailing[0] + 1, f"unexpected line {trailing[2]!r}")
        return value

    def parse_block(self, indent: int) -> Any:
        peeked = self.peek()
        if peeked is None:
            return None
        _, _, text = peeked
        if text == "-" or text.startswith("- "):
            return self.parse_sequence(indent)
        return self.parse_mapping(indent)

    # -- structures --------------------------------------------------------

    def parse_mapping(self, indent: int) -> dict:
        out: dict = {}
        while True:
            peeked = self.peek()
            if peeked is None:
                break
            idx, ind, text = peeked
            if ind < indent:
                break
            if ind > indent:
                raise self.fail(
                    idx + 1,
                    f"unexpected indentation (expected {indent} spaces, found {ind}); "
                    f"a plain scalar cannot continue onto the next line - use '>' "
                    f"or quote the value",
                )
            if text == "-" or text.startswith("- "):
                raise self.fail(
                    idx + 1, "expected 'key: value' but found a sequence item"
                )
            match = _KEY_RE.match(text)
            if not match:
                raise self.fail(
                    idx + 1,
                    f"expected 'key: value' (with a space after the colon); "
                    f"found {text!r}",
                )
            raw_key = match.group("key").strip()
            if raw_key[:1] in _UNSUPPORTED_INDICATORS:
                raise self.fail(
                    idx + 1,
                    f"{_UNSUPPORTED_INDICATORS[raw_key[0]]} are not supported "
                    f"by the restricted YAML reader",
                )
            if raw_key == "<<":
                raise self.fail(idx + 1, "merge keys ('<<') are not supported")
            if raw_key[:1] in ('"', "'"):
                key = raw_key[1:-1]
            else:
                key = raw_key
            if key in out:
                raise self.fail(idx + 1, f"duplicate key {key!r}")
            rest = (match.group("val") or "").strip()
            self.n = idx + 1
            if rest == "":
                nxt = self.peek()
                if nxt is not None and nxt[1] > indent:
                    out[key] = self.parse_block(nxt[1])
                else:
                    out[key] = None
            elif rest[0] in "|>":
                out[key] = self.block_scalar(rest, indent, idx + 1)
            else:
                out[key] = _FlowParser(rest, self.where, idx + 1).parse()
        return out

    def parse_sequence(self, indent: int) -> list:
        out: list = []
        while True:
            peeked = self.peek()
            if peeked is None:
                break
            idx, ind, text = peeked
            if ind < indent:
                break
            if ind > indent:
                raise self.fail(
                    idx + 1,
                    f"unexpected indentation in a sequence "
                    f"(expected {indent} spaces, found {ind})",
                )
            if not (text == "-" or text.startswith("- ")):
                raise self.fail(
                    idx + 1,
                    f"expected a sequence item starting with '- '; found {text!r}",
                )
            rest = text[1:].strip()
            self.n = idx + 1
            if rest == "":
                nxt = self.peek()
                if nxt is not None and nxt[1] > indent:
                    out.append(self.parse_block(nxt[1]))
                else:
                    out.append(None)
                continue
            if _SEQ_KEY_RE.match(rest):
                # A mapping that starts on the '-' line. Rewrite the line so
                # the mapping's own column is its indentation, then reparse.
                gap = len(text) - 1 - len(text[1:].lstrip(" "))
                col = ind + 1 + gap
                self.lines[idx] = " " * col + rest
                self.n = idx
                out.append(self.parse_mapping(col))
                continue
            if rest[0] in "|>":
                out.append(self.block_scalar(rest, indent, idx + 1))
                continue
            out.append(_FlowParser(rest, self.where, idx + 1).parse())
        return out

    def block_scalar(self, header: str, parent_indent: int, lineno: int) -> str:
        style = header[0]
        modifiers = header[1:].strip()
        chomp = ""
        if modifiers in ("-", "+"):
            chomp = modifiers
        elif modifiers != "":
            raise self.fail(
                lineno,
                f"block scalar header {header!r} is not supported; only "
                f"'{style}', '{style}-' and '{style}+' are",
            )
        body: list[str] = []
        while self.n < len(self.lines):
            raw = self.lines[self.n]
            if raw.strip() == "":
                body.append("")
                self.n += 1
                continue
            indent = len(raw) - len(raw.lstrip(" \t"))
            if "\t" in raw[:indent]:
                raise self.fail(
                    self.n + 1, "a tab is used for indentation inside a block scalar"
                )
            if indent <= parent_indent:
                break
            body.append(raw)
            self.n += 1
        while body and body[-1] == "":
            body.pop()
        if not body:
            return ""
        block_indent = min(
            len(line) - len(line.lstrip(" ")) for line in body if line.strip()
        )
        stripped = [line[block_indent:] if line.strip() else "" for line in body]
        if style == "|":
            text = "\n".join(stripped)
        else:
            parts: list[str] = []
            for line in stripped:
                if line == "":
                    parts.append("\n")
                elif parts and parts[-1] not in ("\n",):
                    parts.append(" " + line)
                else:
                    parts.append(line)
            text = "".join(parts)
        if chomp == "-":
            return text
        return text + "\n"


# A fixed string, kept so that a report can say which reader produced a
# diagnostic. There is no second reader to select and nothing reads this to
# choose one: it never varies, by machine or by flag. If it ever becomes
# conditional again, belay#29 explains why that was a defect.
YAML_READER = "restricted (built in, stdlib only)"


def load_yaml(text: str, where: str) -> Any:
    """Parse YAML with the restricted reader, whatever the environment holds."""
    return _RestrictedYaml(text, where).parse()
