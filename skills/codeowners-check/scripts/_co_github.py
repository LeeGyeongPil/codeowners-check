"""GitHub CODEOWNERS dialect (internal module).

Semantics follow the GitHub documentation (checked 2026-11-18):
the last matching line wins, patterns are not full gitignore patterns (no '!' negation, no '[ ]' ranges,
no '\\#'), lines with an invalid owner are skipped, and a line without owners clears ownership.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from _co_common import char_class, pattern_and_owners, split_lines

MAX_BYTES = 3 * 1024 * 1024  # GitHub does not load a CODEOWNERS file larger than 3 MB

_EMAIL = r"[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+"
OWNER_RE = re.compile(rf"^(?:@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)?|{_EMAIL})$")


@dataclass
class Rule:
    """One effective CODEOWNERS rule (a line that GitHub or GitLab does not skip)."""

    line: int
    pattern: str
    owners: list[str]
    rx: re.Pattern[str]
    section: str = ""          # GitLab only: section key ('' = the implicit default section)
    exclusion: bool = False    # GitLab only: '!pattern'


@dataclass
class Issue:
    """A line that the platform skips, or a structural problem worth reporting."""

    line: int
    pattern: str
    code: str                  # unsupported-syntax | invalid-owner | invalid-section-header | invalid-pattern
    args: dict = field(default_factory=dict)


@dataclass
class GithubFile:
    rules: list[Rule]
    issues: list[Issue]


def unsupported_reason(pat: str) -> str | None:
    """Why GitHub skips this pattern (a gitignore feature it does not support), or None."""
    if pat.startswith("!"):
        return "negation"
    if pat.startswith("\\#"):
        return "escaped-hash"
    i = 0
    while i < len(pat):
        if pat[i] == "\\":
            i += 2
            continue
        if pat[i] in "[]":
            return "char-range"
        i += 1
    return None


def pattern_regex(pat: str, brackets: bool = False) -> re.Pattern[str]:
    """Translate a GitHub CODEOWNERS pattern to a regex that is searched in a repo-relative path.

    brackets=True also understands '[a-z]' (used only to explain what a gitignore-style reading would match).
    """
    slash = pat.find("/")
    anchored = slash != -1 and slash != len(pat) - 1     # a slash anywhere but the end anchors to the root
    ends_dir = pat.endswith("/")
    ends_one_level = pat.endswith("/*")                   # 'docs/*' does not reach into subfolders
    body = pat.strip("/")
    out = ["\\A" if anchored else "(?:\\A|/)"]
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n:
            out.append(re.escape(body[i + 1]))
            i += 2
            continue
        if c == "*":
            if i + 1 < n and body[i + 1] == "*":
                left = i == 0 or body[i - 1] == "/"
                at_end = i + 2 == n
                slash_after = i + 2 < n and body[i + 2] == "/"
                if left and (at_end or slash_after):      # a whole path segment made of '**'
                    if slash_after:
                        out.append("(?:.*/)?")
                        i += 3
                    else:
                        out.append(".*")
                        i += 2
                    continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c == "[" and brackets:
            cls = char_class(body, i)
            if cls is not None:
                out.append(cls[0])
                i = cls[1]
                continue
        out.append(re.escape(c))
        i += 1
    if ends_dir:
        out.append("/")
    elif ends_one_level:
        out.append("\\Z")
    else:
        out.append("(?:\\Z|/)")
    return re.compile("".join(out))


def parse(text: str) -> GithubFile:
    """Parse GitHub CODEOWNERS text into effective rules and skipped lines."""
    rules: list[Rule] = []
    issues: list[Issue] = []
    for number, raw in enumerate(split_lines(text), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, owners = pattern_and_owners(line)
        reason = unsupported_reason(pattern)
        if reason:
            issues.append(Issue(number, pattern, "unsupported-syntax", {"reason": reason}))
            continue
        bad = next((o for o in owners if not OWNER_RE.match(o)), None)
        if bad is not None:
            issues.append(Issue(number, pattern, "invalid-owner", {"owner": bad}))
            continue
        rules.append(Rule(number, pattern, owners, pattern_regex(pattern)))
    return GithubFile(rules, issues)


def evaluate(rules: list[Rule], files: list[str]) -> tuple[list[int], list[bool], list[int]]:
    """Resolve every file. Returns (winner index per file or -1, rule matched any file, wins per rule)."""
    n = len(rules)
    matched = [False] * n
    wins = [0] * n
    searchers = [r.rx.search for r in rules]
    winners: list[int] = []
    for path in files:
        w = -1
        for i in range(n - 1, -1, -1):          # last match wins, so look from the bottom up
            if w < 0:
                if searchers[i](path):
                    w = i
                    matched[i] = True
                    wins[i] += 1
            elif not matched[i] and searchers[i](path):
                matched[i] = True                # still count that the earlier rule matches something
        winners.append(w)
    return winners, matched, wins
