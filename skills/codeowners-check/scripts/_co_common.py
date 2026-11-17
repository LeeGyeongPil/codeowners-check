"""Shared helpers: text decoding, line tokenizing and character classes (internal module)."""
from __future__ import annotations

import re

_NEWLINE = re.compile(r"\r\n|\r|\n")


def decode(data: bytes) -> str:
    """Decode a CODEOWNERS file; a UTF-8 byte order mark is dropped, bad bytes are replaced."""
    return data.decode("utf-8-sig", errors="replace")


def split_lines(text: str) -> list[str]:
    """Split on CRLF, CR or LF only (str.splitlines would also split on exotic separators)."""
    return _NEWLINE.split(text)


def tokenize(line: str) -> list[str]:
    """Split a line on unescaped whitespace. Escape sequences such as '\\ ' stay inside their token."""
    tokens: list[str] = []
    cur: list[str] = []
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line):
            cur.append(line[i:i + 2])
            i += 2
            continue
        if c.isspace():
            if cur:
                tokens.append("".join(cur))
                cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    if cur:
        tokens.append("".join(cur))
    return tokens


def pattern_and_owners(line: str) -> tuple[str, list[str]]:
    """Return (pattern token, owner tokens). A token that starts with '#' after the pattern starts a comment."""
    tokens = tokenize(line)
    owners: list[str] = []
    for tok in tokens[1:]:
        if tok.startswith("#"):
            break
        owners.append(tok)
    return tokens[0], owners


def char_class(body: str, i: int) -> tuple[str, int] | None:
    """Translate a bracket expression starting at body[i] == '[' to a regex class.

    Returns (regex, next_index) or None when the bracket is not closed. The class never matches '/'.
    """
    n = len(body)
    j = i + 1
    negate = False
    if j < n and body[j] in "!^":
        negate = True
        j += 1
    first = j
    if j < n and body[j] == "]":
        j += 1
    while j < n and body[j] != "]":
        j += 2 if body[j] == "\\" else 1
    if j >= n:
        return None
    inner = body[first:j].replace("\\", "\\\\").replace("[", "\\[")
    if negate:
        return f"(?!/)[^{inner}]", j + 1
    return f"(?!/)[{inner}]", j + 1
