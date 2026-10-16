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

The same rule holds at the edge of the subset: for any line, this reader
either returns the value a standard YAML parser returns, or raises. Refusing
something YAML accepts is allowed; returning a different value is the defect.
A comment is found only outside a quoted scalar as YAML delimits it
(belay#57), and a plain scalar that YAML reads as structure - 'a: b' is a
mapping, '- a' a sequence item - is refused, not returned as text (belay#49).
The one deliberate exception is scalar typing, described above.
tests/test_validate_bundle.py compares the two readers on generated lines.
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
        problem = _plain_problem(text, in_flow)
        if problem:
            raise self.fail(problem)
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
        problem = _plain_problem(text, in_flow=True, what="key")
        if problem:
            raise self.fail(problem)
        nxt = self.s[self.i + 1 : self.i + 2]
        if self.peek() == ":" and nxt not in ("", " ", "\t", ",", "]", "}"):
            # YAML reads {a:b} as the single key 'a:b', not as a: b.
            raise self.fail(
                f"expected a space after ':' following the key {text!r} in a "
                f"flow mapping; quote the key if the ':' belongs to it"
            )
        return _plain_to_python(text)


def _quoted_end(line: str, start: int) -> int | None:
    """Index just past the quoted scalar opening at `start`, or None.

    Follows the quoting rules of the scalar itself: inside double quotes a
    backslash makes the next character literal, and inside single quotes ''
    is an escaped apostrophe (belay#57). None means the quote never closes on
    this line, which _FlowParser.quoted reports.
    """
    quote = line[start]
    i = start + 1
    while i < len(line):
        c = line[i]
        if quote == '"' and c == "\\":
            i += 2
            continue
        if c == quote:
            if quote == "'" and line[i + 1 : i + 2] == "'":
                i += 2
                continue
            return i + 1
        i += 1
    return None


def _scan_line(line: str) -> tuple[str, int | None]:
    """Split one line into its content and the column of a stray tab.

    Returns the line without its trailing '# ...' comment, and the index of
    the first tab outside a quoted scalar (or None). YAML allows a tab
    between tokens almost nowhere, and the reference parser refuses one, so
    the caller refuses it too.

    A '#' starts a comment at the start of the line or after a space or tab,
    outside a quoted scalar. A quote character opens a quoted scalar only
    where a scalar can begin - at the start of the line, after '- ', after
    a mapping ':', and after '[', '{' or ',' in a flow collection. In the
    middle of a plain scalar it is an ordinary character: `title: N'? # 1`
    is the plain scalar N'? followed by a comment (belay#57).
    """
    n = len(line)
    i = 0
    depth = 0  # flow-collection nesting
    at_node = True  # a scalar may begin here
    tab: int | None = None
    while i < n:
        c = line[i]
        if c in " \t":
            if c == "\t" and tab is None:
                tab = i
            i += 1
            continue
        if c == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i], tab
        nxt = line[i + 1 : i + 2]
        if at_node and c in "\"'":
            end = _quoted_end(line, i)
            if end is None:
                return line, tab
            i = end
            at_node = False
            continue
        if c in "[{" and (at_node or depth):
            depth += 1
            at_node = True
            i += 1
            continue
        if depth and c in "]}":
            depth -= 1
            at_node = False
            i += 1
            continue
        if depth and c == ",":
            at_node = True
            i += 1
            continue
        if c == ":" and (
            nxt in ("", " ", "\t") or (depth and (nxt in ",[]{}" or not at_node))
        ):
            # A value indicator: ': ', or a ':' that ends the token before it
            # inside a flow collection ({"a":"b"}).
            at_node = True
            i += 1
            continue
        if at_node and c in "-?" and nxt in ("", " ", "\t"):
            # '- ' (a sequence entry) or '? ' (an explicit key): a node
            # follows, so a quote after it still opens a scalar.
            i += 1
            continue
        # A run of plain-scalar characters, up to the next space or tab, the
        # next ': ', or (inside a flow collection) the next flow indicator.
        at_node = False
        while i < n:
            c = line[i]
            if c in " \t":
                break
            nxt = line[i + 1 : i + 2]
            if c == ":" and (nxt in ("", " ", "\t") or (depth and nxt in ",[]{}")):
                break
            if depth and c in ",[]{}":
                break
            i += 1
    return line, tab


def _strip_comment(line: str) -> str:
    """Remove a trailing '# ...' comment, respecting quoted scalars."""
    return _scan_line(line)[0]


# Characters that cannot begin a plain (unquoted) scalar in YAML. '-', '?'
# and ':' may, when the next character is not a space ('-1', ':x', '?x').
_PLAIN_START_INDICATORS = "-?:,[]{}#&*!|>'\"%@`"


def _plain_problem(text: str, in_flow: bool, what: str = "value") -> str | None:
    """Why YAML would not read `text` as one plain scalar, or None.

    yamlite reads a subset of YAML, and must never give a value a standard
    YAML parser would not. A plain scalar that YAML would read as structure -
    'a: b' is a mapping, '- a' a sequence, ']' the end of a flow collection -
    is refused here rather than returned as a string (belay#49).
    """
    if text == "":
        return None
    first, second = text[0], text[1:2]
    if first in _PLAIN_START_INDICATORS:
        safe = first in "-?:" and second not in ("", " ", "\t")
        if in_flow:
            safe = safe and first == "-" and second not in ",[]{}"
        if not safe:
            return (
                f"an unquoted {what} cannot start with {first!r}, which YAML "
                f"reads as structure; quote the {what}"
            )
    if in_flow:
        for c in "[{?":
            if c in text:
                return (
                    f"the unquoted {what} {text!r} contains {c!r}, which YAML "
                    f"reads as structure inside a flow collection; quote the "
                    f"{what}"
                )
    if text.endswith(":") or ": " in text or ":\t" in text:
        where = "ends with ':'" if text.endswith(":") else "contains ': '"
        return (
            f"the unquoted {what} {text!r} {where}, which YAML reads as a "
            f"mapping, not as text; quote the {what}"
        )
    return None


_KEY_TAIL_RE = re.compile(r"""^[ \t]*:(?:[ \t]+(?P<val>.*))?$""")
_PLAIN_KEY_RE = re.compile(r"""^(?P<key>[^:#]+?)[ \t]*:(?:[ \t]+(?P<val>.*))?$""")


def _split_key(text: str, where: str, lineno: int) -> tuple[str, bool, str] | None:
    """Split 'key: value' into (key text, quoted?, value text), or None.

    A quoted key is decoded with the same rules as a quoted value, so
    'it''s': 1 has the key it's and "a\\"b": 1 the key a"b. An unterminated
    quoted key raises.
    """
    if text[:1] in ('"', "'"):
        parser = _FlowParser(text, where, lineno)
        key = parser.quoted()
        tail = _KEY_TAIL_RE.match(text[parser.i :])
        if not tail:
            return None
        return key, True, tail.group("val") or ""
    match = _PLAIN_KEY_RE.match(text)
    if not match:
        return None
    return match.group("key").strip(), False, match.group("val") or ""


def _starts_a_mapping(text: str, where: str, lineno: int) -> bool:
    """Whether a '- ' item's text is 'key: value' rather than a scalar."""
    if text[:1] in "[{":
        return False
    try:
        return _split_key(text, where, lineno) is not None
    except YamlError:
        return False  # an unterminated quote; the value parser reports it


class _RestrictedYaml:
    """Block-structure reader for the shallow YAML the bundle format uses.

    Supported: block mappings, block sequences, sequences of mappings, flow
    sequences and mappings, quoted and plain scalars, '>' and '|' block
    scalars with '-'/'+' chomping, comments, one leading '---'.

    Rejected with an explicit message: anchors, aliases, tags, directives,
    multiple documents, tabs in indentation or between tokens, duplicate
    keys, explicit indentation indicators on block scalars, plain multi-line
    scalars, plain scalars YAML reads as structure (holding ': ', ending in
    ':', starting with an indicator), and any line that is not 'key: value'
    or '- item'.
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
            content, tab = _scan_line(raw)
            content = content.strip()
            if content == "":
                self.n += 1
                continue
            if tab is not None:
                raise self.fail(
                    self.n + 1,
                    "a tab outside quotes; YAML does not allow a tab between "
                    "the parts of a line, use spaces (or quote the value if "
                    "the tab belongs to it)",
                )
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
            split = _split_key(text, self.where, idx + 1)
            if split is None:
                raise self.fail(
                    idx + 1,
                    f"expected 'key: value' (with a space after the colon); "
                    f"found {text!r}",
                )
            key, quoted, rest = split
            if not quoted:
                if key[:1] in _UNSUPPORTED_INDICATORS:
                    raise self.fail(
                        idx + 1,
                        f"{_UNSUPPORTED_INDICATORS[key[0]]} are not supported "
                        f"by the restricted YAML reader",
                    )
                if key == "<<":
                    raise self.fail(idx + 1, "merge keys ('<<') are not supported")
                problem = _plain_problem(key, in_flow=False, what="key")
                if problem:
                    raise self.fail(idx + 1, problem)
            if key in out:
                raise self.fail(idx + 1, f"duplicate key {key!r}")
            rest = rest.strip()
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
            if _starts_a_mapping(rest, self.where, idx + 1):
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
