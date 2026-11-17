"""GitLab CODEOWNERS dialect (internal module).

Behaviour is reproduced from the GitLab documentation (checked 2026-11-18): sections, optional sections,
approval counts, default owners, '!' exclusions, and patterns that are normalised and then matched like
Ruby File.fnmatch? with FNM_PATHNAME | FNM_DOTMATCH. GitLab offers no offline oracle, so this is
"documentation behaviour" (see gitlab-org/gitlab#585698 for reported differences).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from _co_common import char_class, pattern_and_owners, split_lines
from _co_github import Issue, Rule

OWNER_RE = re.compile(r"^(?:@@?[A-Za-z0-9_][A-Za-z0-9_.\-/]*|[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+)$")
_HEADER = re.compile(r"^(\^)?\[([^\]]*)\](?:\[([^\]]*)\])?(?=\s|$)(.*)$")
DEFAULT_KEY = ""


@dataclass
class Section:
    key: str                              # lower-cased name; '' is the implicit section before any header
    name: str                             # spelling of the first header
    optional: bool = False
    approvals: int = 1
    default_owners: list[str] = field(default_factory=list)
    headers: list[int] = field(default_factory=list)   # line numbers of every header with this name
    rules: list[Rule] = field(default_factory=list)


@dataclass
class GitlabFile:
    sections: dict[str, Section]
    issues: list[Issue]

    def all_rules(self) -> list[Rule]:
        return [r for s in self.sections.values() for r in s.rules]


def normalize(pat: str) -> str:
    """GitLab turns every pattern into an absolute glob before matching."""
    if pat == "*":
        return "/**/*"
    if not pat.startswith("/"):
        pat = "/**/" + pat              # no leading slash: match at any depth
    if pat.endswith("/"):
        pat = pat + "**/*"              # trailing slash: everything below, at any depth
    return pat


def glob_regex(pat: str) -> re.Pattern[str]:
    """Regex for a normalised pattern, matched with fullmatch against '/' + repo-relative path.

    Subset of Ruby File.fnmatch? with FNM_PATHNAME | FNM_DOTMATCH: '*' and '?' stay inside one path
    segment, only '**/' crosses folders, '[...]' and '\\x' work, '{a,b}' is literal.
    """
    out: list[str] = []
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if pat.startswith("**/", i) and (i == 0 or pat[i - 1] == "/"):
                out.append("(?:[^/]*/)*")
                i += 3
                continue
            out.append("[^/]*")
            while i < n and pat[i] == "*":
                i += 1
            continue
        if c == "?":
            out.append("[^/]")
        elif c == "[":
            cls = char_class(pat, i)
            if cls is not None:
                out.append(cls[0])
                i = cls[1]
                continue
            out.append("\\[")
        elif c == "\\" and i + 1 < n:
            out.append(re.escape(pat[i + 1]))
            i += 2
            continue
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("".join(out))


def parse(text: str) -> GitlabFile:
    """Parse GitLab CODEOWNERS text into sections (merged by case-insensitive name) and skipped lines."""
    sections: dict[str, Section] = {DEFAULT_KEY: Section(DEFAULT_KEY, "")}
    issues: list[Issue] = []
    current = sections[DEFAULT_KEY]
    for number, raw in enumerate(split_lines(text), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") or line.startswith("^["):
            m = _HEADER.match(line)
            name = m.group(2).strip() if m else ""
            count = m.group(3) if m else None
            if not m or not name or (count is not None and not count.isdigit()):
                issues.append(Issue(number, line.split()[0], "invalid-section-header", {}))
                continue
            owners = pattern_and_owners("x " + m.group(4))[1]
            bad = next((o for o in owners if not OWNER_RE.match(o)), None)
            if bad is not None:
                issues.append(Issue(number, line.split()[0], "invalid-owner", {"owner": bad}))
                continue
            key = name.lower()
            optional = m.group(1) is not None
            if key not in sections:
                sections[key] = Section(key, name, optional)
            else:
                sections[key].optional = sections[key].optional and optional   # optional + required -> required
            sec = sections[key]
            sec.headers.append(number)
            if count is not None:
                sec.approvals = max(int(count), 1)
            if owners:
                sec.default_owners = owners
            current = sec
            continue
        pattern, owners = pattern_and_owners(line)
        exclusion = pattern.startswith("!")
        body = pattern[1:] if exclusion else pattern
        if not body:
            issues.append(Issue(number, pattern, "invalid-pattern", {}))
            continue
        bad = next((o for o in owners if not OWNER_RE.match(o)), None)
        if bad is not None:
            issues.append(Issue(number, pattern, "invalid-owner", {"owner": bad}))
            continue
        current.rules.append(Rule(number, pattern, owners, glob_regex(normalize(body)), current.key, exclusion))
    for sec in sections.values():           # a rule without owners inherits the section's default owners
        for r in sec.rules:
            r.owners = [] if r.exclusion else (r.owners or list(sec.default_owners))
    return GitlabFile(sections, issues)


@dataclass
class SectionHit:
    """What one section says about one file."""

    key: str
    name: str
    optional: bool
    approvals: int
    owners: list[str]
    line: int
    pattern: str
    excluded: bool


def evaluate(gl: GitlabFile, files: list[str]) -> tuple[list[list[SectionHit]], dict[int, dict[str, int]]]:
    """Resolve every file in every section.

    Returns (hits per file, stats per rule line). stats[line] has: matched (any file),
    live (matched a file that no earlier exclusion of the section had removed) and wins.
    """
    stats: dict[int, dict[str, int]] = {r.line: {"matched": 0, "live": 0, "wins": 0} for r in gl.all_rules()}
    per_file: list[list[SectionHit]] = []
    sections = [s for s in gl.sections.values() if s.rules]
    for path in files:
        target = "/" + path
        hits: list[SectionHit] = []
        for sec in sections:
            win: Rule | None = None
            excl: Rule | None = None
            for r in sec.rules:
                if not r.rx.fullmatch(target):
                    continue
                stats[r.line]["matched"] = 1
                if r.exclusion:
                    if excl is None:
                        excl = r
                else:
                    if excl is None:
                        stats[r.line]["live"] = 1
                    win = r
            if excl is not None:
                hits.append(SectionHit(sec.key, sec.name or "(default)", sec.optional, sec.approvals, [],
                                       excl.line, excl.pattern, True))
            elif win is not None:
                stats[win.line]["wins"] += 1
                hits.append(SectionHit(sec.key, sec.name or "(default)", sec.optional, sec.approvals,
                                       list(win.owners), win.line, win.pattern, False))
        per_file.append(hits)
    return per_file, stats
