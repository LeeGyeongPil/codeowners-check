"""AC-3: GitLab resolution reproduces the documented behaviour (sections, exclusions, fnmatch edges)."""
import json

import pytest

import _co_gitlab as gl
from _co_analysis import GitlabModel
from conftest import GL, run_json

CASES = json.loads((GL / "doc_examples.json").read_text())["cases"]


def tr(key, **args):
    return key


def model(text, files):
    return GitlabModel(text, len(text), {"reason": "explicit", "path": "CODEOWNERS", "others": []}, files, tr)


def sections_of(text, path):
    entry = model(text, [path]).entries()[0]
    return {s["name"]: s for s in entry["sections"]}


@pytest.mark.parametrize("pattern,path,expected", CASES)
def test_documented_pattern_behaviour(pattern, path, expected):
    rx = gl.glob_regex(gl.normalize(pattern))
    assert bool(rx.fullmatch("/" + path)) is expected, (pattern, path)


def test_probe_file_sections():
    text = (GL / "CODEOWNERS").read_text()
    m = model(text, [p for p in (GL / "files.txt").read_text().split()])
    by_path = {e["path"]: {s["name"]: s for s in e["sections"]} for e in m.entries()}
    assert by_path["docs/a.md"]["Docs"]["owners"] == ["@docs-shallow"]          # '/docs/**' is one level
    assert by_path["docs/a.md"]["Docs"]["line"] == 5
    assert by_path["docs/sub/b.md"]["Docs"]["owners"] == ["@docs"]              # the '/docs/' line decides
    assert by_path["docs/sub/b.md"]["Docs"]["line"] == 4
    assert by_path["x/docs/README.md"]["Docs"]["owners"] == ["@readme"]         # no leading slash: any depth
    assert by_path["docs/internal/z.md"]["Docs"]["owners"] == ["@internal"]     # '[docs]' merges into 'Docs'
    assert by_path["docs/internal/z.md"]["Docs"]["line"] == 12
    assert by_path["app/m.rb"]["Ruby"]["owners"] == ["@ruby-default"]           # header default owners
    assert by_path["app/m.rb"]["Ruby"]["optional"] is True
    assert by_path["app/m.rb"]["Ruby"]["approvals"] == 2
    assert by_path["config/routes.rb"]["Ruby"]["excluded"] is True              # '!' cannot be undone later
    assert by_path["config/routes.rb"]["Ruby"]["owners"] == []
    assert by_path["config/routes.rb"]["(default)"]["owners"] == ["@default"]
    assert "(default)" in by_path["x/docs/README.md"]
    assert by_path["pom.xml"]["(default)"]["excluded"] is True                  # '!pom.xml' exempts it


def test_section_names_merge_case_insensitively_and_required_wins():
    text = "[Docs] @a\n/a/ @x\n^[docs][3] @b\n/b/ @y\n"
    gl_file = gl.parse(text)
    assert list(gl_file.sections) == ["", "docs"]
    sec = gl_file.sections["docs"]
    assert sec.name == "Docs" and sec.optional is False        # optional + required -> required
    assert sec.approvals == 3 and sec.default_owners == ["@b"]
    assert sec.headers == [1, 3]


def test_optional_only_when_every_header_is_optional():
    sec = gl.parse("^[A]\n^[a]\n").sections["a"]
    assert sec.optional is True


def test_section_approvals_and_rules_without_owner_use_default_owners():
    text = "[Ruby][2] @ops @sec\n*.rb\n/lib/ @lib\n"
    e = sections_of(text, "app/m.rb")["Ruby"]
    assert (e["approvals"], e["owners"], e["optional"]) == (2, ["@ops", "@sec"], False)
    assert sections_of(text, "lib/x.rb")["Ruby"]["owners"] == ["@lib"]   # last match wins inside the section


def test_each_section_is_decided_separately():
    text = "* @everyone\n[Docs]\n*.md @docs\n[Sec]\ndocs/ @sec\n"
    got = sections_of(text, "docs/a.md")
    assert {k: v["owners"] for k, v in got.items()} == {"(default)": ["@everyone"], "Docs": ["@docs"], "Sec": ["@sec"]}


def test_exclusion_is_not_undone_by_a_later_rule_or_changed_by_an_earlier_one():
    text = "[S]\n*.rb @a\n!/x/*.rb\n/x/y.rb @b\n"
    assert sections_of(text, "x/y.rb")["S"]["excluded"] is True     # excluded although a rule matched first
    assert sections_of(text, "z/y.rb")["S"]["owners"] == ["@a"]


def test_exclusion_only_affects_its_own_section():
    text = "* @a\n[S]\n*.rb @b\n!x.rb\n"
    got = sections_of(text, "x.rb")
    assert got["(default)"]["owners"] == ["@a"] and got["S"]["excluded"] is True


def test_invalid_section_headers_and_owners_are_skipped():
    gl_file = gl.parse("[]\n[Name][x] @a\n[Ok]\n*.rb notanowner\n!\n*.py @@maintainers\n")
    assert [(i.line, i.code) for i in gl_file.issues] == [
        (1, "invalid-section-header"), (2, "invalid-section-header"), (4, "invalid-owner"), (5, "invalid-pattern")]
    assert gl_file.sections["ok"].rules[0].owners == ["@@maintainers"]


@pytest.mark.parametrize("pattern,path,expected", [
    ("{a,b}.rb", "{a,b}.rb", True), ("{a,b}.rb", "a.rb", False),    # braces are literal without FNM_EXTGLOB
    ("[!x].md", "a.md", True), ("[!x].md", "x.md", False),
    ("[^x].md", "a.md", True), ("[^x].md", "x.md", False),
    ("\\*.md", "*.md", True), ("\\*.md", "a.md", False),
    ("a[", "a[", True), ("[a-c].md", "b.md", True), ("[a-c].md", "d.md", False),
])
def test_fnmatch_edges(pattern, path, expected):
    assert bool(gl.glob_regex(gl.normalize(pattern)).fullmatch("/" + path)) is expected


def test_normalize():
    assert gl.normalize("*") == "/**/*"
    assert gl.normalize("a.md") == "/**/a.md"
    assert gl.normalize("/docs/") == "/docs/**/*"
    assert gl.normalize("docs/") == "/**/docs/**/*"
    assert gl.normalize("/a/**") == "/a/**"


def test_lint_reports_ineffective_after_exclusion_and_merge(gl_args):
    proc, data = run_json("lint", *gl_args)
    codes = {(f["code"], f["line"]) for f in data["findings"]}
    assert ("ineffective-after-exclusion", 10) in codes
    assert ("section-merged", 11) in codes
    unowned = next(f for f in data["findings"] if f["code"] == "unowned-file")
    assert unowned["files"] == [{"path": "pom.xml", "status": "excluded"}]
    assert proc.returncode == 1                                    # a warning is present


def test_resolve_cli_gitlab_shape(gl_args):
    proc, data = run_json("resolve", *gl_args)
    assert proc.returncode == 0
    names = [s["name"] for s in data["sections"]]
    assert names == ["(default)", "Docs", "Ruby"]
    docs = next(s for s in data["sections"] if s["name"] == "Docs")
    assert docs["lines"] == [3, 11] and docs["merged_from"] == [11]
    assert data["platform"] == "gitlab" and data["platform_reason"] == "explicit"


def test_dead_and_shadowed_rules_in_gitlab():
    text = "[S]\n*.md @a\n*.md @b\n/nothing/ @c\n"
    m = model(text, ["a.md", "b.md"])
    codes = {(f["code"], f["line"]) for f in m.lint()["findings"]}
    assert ("shadowed-rule", 2) in codes and ("duplicate-pattern", 3) in codes and ("dead-rule", 4) in codes


def test_explain_gitlab_marks_effects():
    text = (GL / "CODEOWNERS").read_text()
    out = model(text, []).explain("config/routes.rb", None)
    effects = {(m["line"], m["effect"]) for m in out["matches"]}
    assert (9, "excludes") in effects and (10, "ineffective-after-exclusion") in effects
    out = model(text, []).explain("docs/sub/b.md", None)
    assert any(h["code"] == "double-star-one-level" and h["line"] == 5 for h in out["hints"])
