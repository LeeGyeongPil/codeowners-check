"""File collection, CODEOWNERS location, resolving, linting, explaining and diffing (internal module).

Every public function returns plain dicts/lists so the CLI can print them as JSON or as a table.
Text that humans read comes from the translator `tr(key, **args)`; JSON field names and finding codes
never depend on the language.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Callable

import _co_github as gh
import _co_gitlab as gl
from _co_common import decode

Tr = Callable[..., str]

GITHUB_PLACES = [".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"]
GITLAB_PLACES = ["CODEOWNERS", "docs/CODEOWNERS", ".gitlab/CODEOWNERS"]
SEVERITIES = ("error", "warning", "info")
# GitLab 섹션 머리줄 모양: [Docs], ^[Ruby][2] (GitHub 는 이 줄을 '[ ]' 문법으로 보고 건너뛴다)
GITLAB_HEADER = re.compile(r"^\^?\[[^\]]+\](?:\[\d+\])?$")


class CheckError(Exception):
    """An input problem; the CLI prints `error: <message>` and exits with 2."""

    def __init__(self, key: str, **args: object) -> None:
        super().__init__(key)
        self.key = key
        self.args_ = args


# ---------------------------------------------------------------- files and locations

def normalize_path(p: str) -> str:
    p = p.strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def clean_paths(paths: list[str]) -> list[str]:
    """Normalise, de-duplicate and sort a list of repo-relative paths."""
    return sorted({q for q in (normalize_path(p) for p in paths) if q})


def collect_files(root: Path | None, files_from: str | None) -> list[str]:
    """The file list: --files-from (a path or '-' for stdin) wins, otherwise walk --root (no .git, no symlinked dirs)."""
    if files_from is not None:
        try:
            if files_from == "-":
                raw = sys.stdin.read()
            else:
                raw = decode(Path(files_from).read_bytes())
        except OSError as e:
            raise CheckError("files_from_unreadable", path=files_from, reason=e.strerror or str(e))
        files = clean_paths(raw.splitlines())
    else:
        base = root or Path(".")
        if not base.is_dir():
            raise CheckError("root_not_dir", path=str(base))
        files = []
        for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d != ".git")
            rel = Path(dirpath).relative_to(base).as_posix()
            for name in filenames:
                files.append(name if rel == "." else f"{rel}/{name}")
        files = clean_paths(files)
    if not files:
        raise CheckError("no_files")
    return files


def detect_platform(codeowners: Path | None, root: Path) -> tuple[str, str]:
    """Pick the platform from locations only (never from file content). Returns (platform, reason key)."""
    if codeowners is not None:
        parent = codeowners.parent.name
        if parent == ".github":
            return "github", "under-.github"
        if parent == ".gitlab":
            return "gitlab", "under-.gitlab"
    if (root / ".gitlab-ci.yml").exists() or (root / ".gitlab").is_dir():
        return "gitlab", "gitlab-marker-in-root"
    return "github", "default"


def locate(platform_arg: str, codeowners_arg: str | None, root: Path) -> tuple[str, str, Path, list[str]]:
    """Return (platform, platform_reason, CODEOWNERS path, other CODEOWNERS files that are ignored)."""
    given = Path(codeowners_arg) if codeowners_arg else None
    if platform_arg == "auto":
        platform, reason = detect_platform(given, root)
    else:
        platform, reason = platform_arg, "explicit"
    if given is not None:
        if not given.is_file():
            raise CheckError("not_found", places=str(given))
        return platform, reason, given, []
    places = GITHUB_PLACES if platform == "github" else GITLAB_PLACES
    found = [p for p in places if (root / p).is_file()]
    if not found:
        raise CheckError("not_found", places=", ".join(places))
    chosen = root / found[0]
    if platform_arg == "auto":                      # the file that was actually found can give a more precise reason
        found_platform, found_reason = detect_platform(chosen, root)
        if found_platform == platform and found_reason.startswith("under-"):
            reason = found_reason
    return platform, reason, chosen, found[1:]


def read_codeowners(path: Path) -> tuple[str, int]:
    try:
        data = path.read_bytes()
    except OSError as e:
        raise CheckError("unreadable", path=str(path), reason=e.strerror or str(e))
    return decode(data), len(data)


# ---------------------------------------------------------------- findings

def make_finding(tr: Tr, detail_key: str, severity: str, line: int | None = None, pattern: str | None = None,
                 args: dict | None = None, **extra: object) -> dict:
    args = dict(args or {})
    out: dict = {"code": detail_key.split(".")[0], "severity": severity, "line": line, "pattern": pattern,
                 "detail_key": detail_key, "args": args}
    out.update(extra)
    out["message"] = tr("finding." + detail_key, **{"line": line, "pattern": pattern, **args})
    return out


def _sort_findings(findings: list[dict]) -> list[dict]:
    rank = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(findings, key=lambda f: (rank[f["severity"]], f["line"] if f["line"] is not None else 10 ** 9,
                                           f["code"], f["pattern"] or ""))


def _counts(findings: list[dict]) -> dict:
    return {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}


def issue_findings(issues: list[gh.Issue], tr: Tr) -> list[dict]:
    out = []
    for i in issues:
        key = i.code + (f".{i.args['reason']}" if i.code == "unsupported-syntax" else "")
        out.append(make_finding(tr, key, "error", i.line, i.pattern, {k: v for k, v in i.args.items()}))
    return out


# ---------------------------------------------------------------- GitHub model

class GithubModel:
    platform = "github"

    def __init__(self, text: str, size: int, meta: dict, files: list[str], tr: Tr) -> None:
        self.size, self.meta, self.files, self.tr = size, meta, files, tr
        # GitHub does not load a file above the limit: no rule applies and no line is analysed
        self.too_large = size > gh.MAX_BYTES
        self.parsed = gh.GithubFile([], []) if self.too_large else gh.parse(text)
        self._eval: tuple[list[int], list[bool], list[int]] | None = None

    def evaluation(self) -> tuple[list[int], list[bool], list[int]]:
        if self._eval is None:
            self._eval = gh.evaluate(self.parsed.rules, self.files)
        return self._eval

    def _entry(self, path: str, w: int) -> dict:
        if w < 0:
            return {"path": path, "owners": [], "line": None, "pattern": None, "status": "no-rule"}
        r = self.parsed.rules[w]
        return {"path": path, "owners": list(r.owners), "line": r.line, "pattern": r.pattern,
                "status": "owned" if r.owners else "cleared"}

    def entries(self, paths: list[str] | None = None) -> list[dict]:
        if paths is None:
            winners = self.evaluation()[0]
            return [self._entry(p, w) for p, w in zip(self.files, winners)]
        winners = gh.evaluate(self.parsed.rules, paths)[0]
        return [self._entry(p, w) for p, w in zip(paths, winners)]

    def ignored_lines(self) -> list[dict]:
        return [{"line": i.line, "pattern": i.pattern, "code": i.code, "args": i.args} for i in self.parsed.issues]

    def notes(self) -> list[str]:
        notes = [self.tr("note.offline")]
        if self.too_large:
            notes.append(self.tr("note.too_large", size=self.size, limit=gh.MAX_BYTES))
        if any(i.code == "invalid-owner" for i in self.parsed.issues):
            notes.append(self.tr("note.invalid_owner_assumption"))
        # 플랫폼을 자동으로 GitHub 로 골랐는데 GitLab 섹션 머리줄([Docs], ^[Ruby][2])이 보이면 다시 돌리라고 알려 준다
        headers = [str(i.line) for i in self.parsed.issues
                   if i.code == "unsupported-syntax" and GITLAB_HEADER.match(i.pattern)]
        if headers and self.meta["reason"] != "explicit":
            notes.append(self.tr("note.gitlab_headers", lines=", ".join(headers)))
        return notes

    def resolve(self, paths: list[str] | None) -> dict:
        entries = self.entries(paths)
        return {"platform": "github", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "files_total": len(entries), "files": entries, "ignored_lines": self.ignored_lines(),
                "notes": self.notes()}

    def error_findings(self) -> list[dict]:
        out = issue_findings(self.parsed.issues, self.tr)
        if self.size > gh.MAX_BYTES:
            out.append(make_finding(self.tr, "file-too-large", "error", args={"size": self.size, "limit": gh.MAX_BYTES}))
        return out

    def lint(self) -> dict:
        tr = self.tr
        findings = self.error_findings()
        rules = self.parsed.rules
        winners, matched, wins = self.evaluation()
        seen: dict[str, int] = {}
        for i, r in enumerate(rules):
            if r.pattern in seen:
                findings.append(make_finding(tr, "duplicate-pattern", "warning", r.line, r.pattern,
                                             {"first_line": seen[r.pattern]}))
            else:
                seen[r.pattern] = r.line
            if not matched[i]:
                findings.append(make_finding(tr, "dead-rule", "warning", r.line, r.pattern))
            elif wins[i] == 0:
                by = sorted({rules[winners[k]].line for k, p in enumerate(self.files)
                             if winners[k] >= 0 and r.rx.search(p)})
                findings.append(make_finding(tr, "shadowed-rule", "warning", r.line, r.pattern,
                                             {"by_lines": by[:5]}))
        if self.meta["others"]:
            findings.append(make_finding(tr, "multiple-codeowners-files", "warning", args={
                "used": self.meta["path"], "ignored": self.meta["others"]}))
        unowned = [e for e in self.entries() if not e["owners"]]
        if unowned:
            findings.append(make_finding(tr, "unowned-file", "info", args={"count": len(unowned)},
                                         files=[{"path": e["path"], "status": e["status"]} for e in unowned],
                                         count=len(unowned)))
        findings = _sort_findings(findings)
        return {"platform": "github", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "files_total": len(self.files), "findings": findings, "counts": _counts(findings),
                "notes": self.notes()}

    def explain(self, path: str, listed: bool | None) -> dict:
        tr = self.tr
        rules = self.parsed.rules
        hit = [i for i, r in enumerate(rules) if r.rx.search(path)]
        win = hit[-1] if hit else -1
        matches = [{"line": rules[i].line, "pattern": rules[i].pattern, "owners": list(rules[i].owners),
                    "winner": i == win} for i in hit]
        relevant = []
        for iss in self.parsed.issues:
            if iss.code == "unsupported-syntax":
                reading = {"negation": iss.pattern[1:], "escaped-hash": iss.pattern[1:]}.get(iss.args["reason"], iss.pattern)
                reason = iss.args["reason"]
            else:
                reading, reason = iss.pattern, iss.code
            try:
                if gh.pattern_regex(reading, brackets=True).search(path):
                    relevant.append({"line": iss.line, "pattern": iss.pattern, "reason": reason})
            except re.error:
                continue
        hints = []
        if win < 0:
            hints.append(self._hint("no-rule"))
        elif not rules[win].owners:
            hints.append(self._hint("cleared", rules[win].line, rules[win].pattern))
        if len(hit) > 1:
            hints.append(self._hint("later-wins", rules[win].line, rules[win].pattern,
                                    lines=", ".join(str(rules[i].line) for i in hit[:-1])))
        for i, r in enumerate(rules):
            if i in hit or not r.pattern.endswith("/*"):
                continue
            folder = r.pattern[:-1]
            if gh.pattern_regex(folder).search(path):
                hints.append(self._hint("star-not-recursive", r.line, r.pattern, folder=folder,
                                        recursive=r.pattern + "*"))
        for item in relevant:
            hints.append(self._hint("ignored-line", item["line"], item["pattern"], reason=item["reason"]))
        entry = self._entry(path, win)
        return {"platform": "github", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "path": path, "in_file_list": listed, "owners": entry["owners"], "status": entry["status"],
                "matches": matches, "ignored_but_relevant": relevant, "hints": hints, "notes": self.notes()}

    def _hint(self, code: str, line: int | None = None, pattern: str | None = None, **args: object) -> dict:
        return {"code": code, "line": line, "pattern": pattern,
                "message": self.tr("hint." + code, line=line, pattern=pattern, **args)}

    # -- diff support
    def compare_key(self, entry: dict) -> object:
        return tuple(sorted(entry["owners"]))

    def rule_key(self, entry: dict) -> object:
        return entry["pattern"]

    def view(self, entry: dict) -> object:
        return entry["owners"]


# ---------------------------------------------------------------- GitLab model

class GitlabModel:
    platform = "gitlab"

    def __init__(self, text: str, size: int, meta: dict, files: list[str], tr: Tr) -> None:
        self.parsed = gl.parse(text)
        self.size, self.meta, self.files, self.tr = size, meta, files, tr
        self._eval = None

    def evaluation(self):
        if self._eval is None:
            self._eval = gl.evaluate(self.parsed, self.files)
        return self._eval

    @staticmethod
    def _entry(path: str, hits: list[gl.SectionHit]) -> dict:
        sections = [{"name": h.name, "optional": h.optional, "approvals": h.approvals, "owners": h.owners,
                     "line": h.line, "pattern": h.pattern, "excluded": h.excluded} for h in hits]
        if not hits:
            status = "no-rule"
        elif any(not h.excluded and h.owners for h in hits):
            status = "owned"
        elif any(not h.excluded for h in hits):
            status = "no-owner"
        else:
            status = "excluded"
        return {"path": path, "sections": sections, "status": status}

    def entries(self, paths: list[str] | None = None) -> list[dict]:
        if paths is None:
            hits = self.evaluation()[0]
            return [self._entry(p, h) for p, h in zip(self.files, hits)]
        hits = gl.evaluate(self.parsed, paths)[0]
        return [self._entry(p, h) for p, h in zip(paths, hits)]

    def ignored_lines(self) -> list[dict]:
        return [{"line": i.line, "pattern": i.pattern, "code": i.code, "args": i.args} for i in self.parsed.issues]

    def section_table(self) -> list[dict]:
        out = []
        for s in self.parsed.sections.values():
            if not s.rules and not s.headers:
                continue
            out.append({"name": s.name or "(default)", "lines": list(s.headers), "optional": s.optional,
                        "approvals": s.approvals, "default_owners": list(s.default_owners),
                        "merged_from": s.headers[1:]})
        return out

    def notes(self) -> list[str]:
        return [self.tr("note.offline"), self.tr("note.gitlab_docs")]

    def resolve(self, paths: list[str] | None) -> dict:
        entries = self.entries(paths)
        return {"platform": "gitlab", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "files_total": len(entries), "files": entries, "sections": self.section_table(),
                "ignored_lines": self.ignored_lines(), "notes": self.notes()}

    def error_findings(self) -> list[dict]:
        return issue_findings(self.parsed.issues, self.tr)

    def lint(self) -> dict:
        tr = self.tr
        findings = self.error_findings()
        hits, stats = self.evaluation()
        for sec in self.parsed.sections.values():
            if len(sec.headers) > 1:
                findings.append(make_finding(tr, "section-merged", "info", sec.headers[1], sec.name,
                                             {"name": sec.name, "lines": sec.headers}))
            seen: dict[str, int] = {}
            for r in sec.rules:
                if r.pattern in seen:
                    findings.append(make_finding(tr, "duplicate-pattern", "warning", r.line, r.pattern,
                                                 {"first_line": seen[r.pattern]}))
                else:
                    seen[r.pattern] = r.line
                st = stats[r.line]
                if not st["matched"]:
                    findings.append(make_finding(tr, "dead-rule", "warning", r.line, r.pattern))
                elif not r.exclusion and st["wins"] == 0:
                    code = "shadowed-rule" if st["live"] else "ineffective-after-exclusion"
                    findings.append(make_finding(tr, code, "warning", r.line, r.pattern,
                                                 {"section": sec.name or "(default)"}))
        if self.meta["others"]:
            findings.append(make_finding(tr, "multiple-codeowners-files", "warning", args={
                "used": self.meta["path"], "ignored": self.meta["others"]}))
        unowned = [e for e in self.entries() if e["status"] != "owned"]
        if unowned:
            findings.append(make_finding(tr, "unowned-file", "info", args={"count": len(unowned)},
                                         files=[{"path": e["path"], "status": e["status"]} for e in unowned],
                                         count=len(unowned)))
        findings = _sort_findings(findings)
        return {"platform": "gitlab", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "files_total": len(self.files), "findings": findings, "counts": _counts(findings),
                "notes": self.notes()}

    def explain(self, path: str, listed: bool | None) -> dict:
        target = "/" + path
        matches, hints = [], []
        for sec in self.parsed.sections.values():
            excl = next((r for r in sec.rules if r.exclusion and r.rx.fullmatch(target)), None)
            hit = [r for r in sec.rules if r.rx.fullmatch(target)]
            last = next((r for r in reversed(hit) if not r.exclusion), None)
            for r in hit:
                if r.exclusion:
                    effect = "excludes" if r is excl else "excludes-again"
                elif excl is not None:
                    effect = "ineffective-after-exclusion" if r.line > excl.line else "removed-by-exclusion"
                else:
                    effect = "decides" if r is last else "overridden"
                matches.append({"line": r.line, "pattern": r.pattern, "owners": list(r.owners),
                                "section": sec.name or "(default)", "exclusion": r.exclusion,
                                "effect": effect, "winner": effect in ("decides", "excludes")})
                if effect in ("ineffective-after-exclusion", "removed-by-exclusion"):
                    hints.append(self._hint("excluded-first", r.line, r.pattern, line2=excl.line if excl else 0))
            hit_ids = {id(h) for h in hit}
            for r in sec.rules:
                if id(r) in hit_ids or r.exclusion or not r.pattern.endswith("/**"):
                    continue
                if gl.glob_regex(gl.normalize(r.pattern[:-2])).fullmatch(target):
                    hints.append(self._hint("double-star-one-level", r.line, r.pattern, folder=r.pattern[:-2]))
        entry = self._entry(path, gl.evaluate(self.parsed, [path])[0][0])
        if not entry["sections"]:
            hints.append(self._hint("no-rule"))
        return {"platform": "gitlab", "platform_reason": self.meta["reason"], "codeowners": self.meta["path"],
                "path": path, "in_file_list": listed, "sections": entry["sections"], "status": entry["status"],
                "matches": matches, "ignored_but_relevant": [], "hints": hints, "notes": self.notes()}

    def _hint(self, code: str, line: int | None = None, pattern: str | None = None, **args: object) -> dict:
        return {"code": code, "line": line, "pattern": pattern,
                "message": self.tr("hint." + code, line=line, pattern=pattern, **args)}

    # -- diff support
    def compare_key(self, entry: dict) -> object:
        return tuple(sorted((s["name"].lower(), tuple(sorted(s["owners"])), s["approvals"], s["optional"])
                            for s in entry["sections"] if not s["excluded"]))

    def rule_key(self, entry: dict) -> object:
        return tuple(sorted((s["name"].lower(), s["pattern"], s["excluded"]) for s in entry["sections"]))

    def view(self, entry: dict) -> object:
        return sorted(({"name": s["name"], "owners": s["owners"], "approvals": s["approvals"],
                        "optional": s["optional"]} for s in entry["sections"] if not s["excluded"]),
                      key=lambda s: s["name"].lower())


# ---------------------------------------------------------------- loading

def build_model(platform: str, text: str, size: int, meta: dict, files: list[str], tr: Tr):
    cls = GithubModel if platform == "github" else GitlabModel
    return cls(text, size, meta, files, tr)


def load_model(platform_arg: str, codeowners_arg: str | None, root: Path, files: list[str], tr: Tr):
    platform, reason, path, others = locate(platform_arg, codeowners_arg, root)
    text, size = read_codeowners(path)
    meta = {"reason": reason, "path": path.as_posix(), "others": others}
    return build_model(platform, text, size, meta, files, tr)


# ---------------------------------------------------------------- diff

def expect_regex(pattern: str) -> re.Pattern[str]:
    """--expect patterns always use GitHub CODEOWNERS pattern semantics, on every platform."""
    if not pattern.strip() or gh.unsupported_reason(pattern):
        raise CheckError("bad_expect", pattern=pattern)
    return gh.pattern_regex(pattern)


def diff_models(before, after, expects: list[str] | None, expect_none: bool, tr: Tr) -> dict:
    rxs = [(p, expect_regex(p)) for p in (expects or [])]
    be, ae = before.entries(), after.entries()
    changed, line_only = [], []
    for b, a in zip(be, ae):
        if before.compare_key(b) != after.compare_key(a):
            changed.append({"path": b["path"], "before": before.view(b), "after": after.view(a)})
        elif before.rule_key(b) != after.rule_key(a):
            line_only.append({"path": b["path"], "before_line": b.get("line"), "after_line": a.get("line"),
                              "before_pattern": b.get("pattern"), "after_pattern": a.get("pattern")})
    paths = [c["path"] for c in changed]
    unexpected = ([p for p in paths if not any(rx.search(p) for _, rx in rxs)] if rxs
                  else (paths if expect_none else []))
    ineffective = [p for p, rx in rxs if not any(rx.search(x) for x in paths)]
    known = {(f["code"], f["pattern"], str(sorted(f["args"].items()))) for f in before.error_findings()}
    new_errors = [f for f in after.error_findings()
                  if (f["code"], f["pattern"], str(sorted(f["args"].items()))) not in known]
    ok = not unexpected and not ineffective and not new_errors
    return {"platform": after.platform, "platform_reason": after.meta["reason"], "before": before.meta["path"],
            "after": after.meta["path"], "files_total": len(be), "changed": changed, "changed_count": len(changed),
            "unchanged_count": len(be) - len(changed), "line_only": line_only, "expect": list(expects or []),
            "expect_none": bool(expect_none), "unexpected": unexpected, "ineffective_expect": ineffective,
            "new_errors": new_errors, "ok": ok, "notes": after.notes()}
