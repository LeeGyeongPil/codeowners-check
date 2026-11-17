"""AC-1: GitHub resolution matches the documented semantics and the PyPI `codeowners` 0.9.0 oracle."""
import random

import pytest
from codeowners import CodeOwners

import _co_github as gh
from conftest import GH, run_json

PROBE_EXPECTED = {
    # path: (deciding line, owners)
    "README.md": (1, ["@org/default"]),
    "docs/guide.md": (2, ["@org/docs"]),
    "docs/deep/x.md": (1, ["@org/default"]),          # 'docs/*' does not reach into subfolders
    "docs/api/v1.md": (3, ["@org/backend"]),
    "docs/legacy/old.md": (1, ["@org/default"]),      # '!docs/legacy/' is skipped by GitHub
    "a.cfg": (1, ["@org/default"]),                   # '[a-z]*.cfg' is skipped by GitHub
    "web/app.js": (7, ["@alice"]),                    # last match wins: line 6 is overridden
    "apps/github/main.go": (8, []),                   # '/apps/github' without owners clears ownership
    "apps/other/main.go": (1, ["@org/default"]),
    "src/a.py": (9, ["@org/src"]),
    "src/core/b.py": (10, ["@org/core"]),
    "src/core/sub/c.py": (10, ["@org/core"]),
    "pkg/src/d.py": (9, ["@org/src"]),
    "logs/x.txt": (11, ["@org/ops"]),
    "svc/logs/y.txt": (11, ["@org/ops"]),
    "logsx/z.txt": (1, ["@org/default"]),
    "src": (1, ["@org/default"]),                     # 'src/' matches folders only
    "docs": (1, ["@org/default"]),
}


def owners_for(text, path):
    parsed = gh.parse(text)
    w = gh.evaluate(parsed.rules, [path])[0][0]
    return (parsed.rules[w].line, parsed.rules[w].owners) if w >= 0 else (None, [])


def test_probe_file_deciding_lines_and_owners():
    text = (GH / "CODEOWNERS").read_text()
    for path, expected in PROBE_EXPECTED.items():
        assert owners_for(text, path) == expected, path


def test_probe_file_through_cli(gh_args):
    proc, data = run_json("resolve", *gh_args)
    assert proc.returncode == 0
    by_path = {f["path"]: f for f in data["files"]}
    assert len(by_path) == 18 == data["files_total"]
    for path, (line, owners) in PROBE_EXPECTED.items():
        assert (by_path[path]["line"], by_path[path]["owners"]) == (line, owners)
    assert by_path["apps/github/main.go"]["status"] == "cleared"
    assert by_path["docs/legacy/old.md"]["status"] == "owned"
    assert [i["line"] for i in data["ignored_lines"]] == [4, 5]


@pytest.mark.parametrize("pattern,path,expected", [
    ("docs", "docs", True), ("docs", "x/docs/y", True), ("docs", "docsx", False),   # no slash: any depth
    ("docs/", "docs/a", True), ("docs/", "x/docs/a", True), ("docs/", "docs", False),
    ("/apps/", "apps/a/b", True), ("/apps/", "x/apps/a", False),
    ("/apps", "apps/a", True), ("/apps", "x/apps", False),
    ("docs/*", "docs/a", True), ("docs/*", "docs/a/b", False),
    ("docs/**", "docs/a/b", True), ("docs/**", "docs", False),
    ("**/logs", "logs/x", True), ("**/logs", "a/b/logs/y", True), ("**/logs", "logsx/z", False),
    ("a/**/b", "a/b", True), ("a/**/b", "a/x/y/b", True), ("a/**/b", "b", False),
    ("*.js", "web/app.js", True), ("*.js", "app.jsx", False), ("*.js", "a/b/c.js", True),
    ("a?c", "abc", True), ("a?c", "a/c", False),
    ("*", "anything/at/all", True),
    ("docs/*.md", "docs/a.md", True), ("docs/*.md", "docs/a/b.md", False),
    ("Docs", "docs", False),                                                          # case sensitive
    ("my\\ file.txt", "my file.txt", True), ("my\\ file.txt", "my_file.txt", False),   # escaped space
])
def test_pattern_boundaries(pattern, path, expected):
    assert bool(gh.pattern_regex(pattern).search(path)) is expected


@pytest.mark.parametrize("pattern,reason", [
    ("!docs/legacy/", "negation"), ("\\#notes", "escaped-hash"), ("[a-z]*.cfg", "char-range"), ("a]b", "char-range"),
])
def test_unsupported_patterns_are_reported_and_skipped(pattern, reason):
    parsed = gh.parse(f"* @a\n{pattern} @b\n")
    assert [(i.line, i.code, i.args["reason"]) for i in parsed.issues] == [(2, "unsupported-syntax", reason)]
    assert [r.line for r in parsed.rules] == [1]


def test_owners_and_comments():
    parsed = gh.parse("# header\n\n*.md @a @org/team dev@example.com # trailing comment\n")
    assert parsed.rules[0].owners == ["@a", "@org/team", "dev@example.com"]


def test_escaped_space_pattern_in_file():
    parsed = gh.parse("my\\ file.txt @a\n")
    assert parsed.rules[0].pattern == "my\\ file.txt"
    assert parsed.rules[0].owners == ["@a"]


def test_gitignore_reading_of_skipped_lines_is_explained():
    from _co_analysis import GithubModel
    text = (GH / "CODEOWNERS").read_text()
    model = GithubModel(text, len(text), {"reason": "x", "path": "CODEOWNERS", "others": []}, [], lambda k, **a: k)
    out = model.explain("docs/legacy/old.md", None)
    assert [(i["line"], i["reason"]) for i in out["ignored_but_relevant"]] == [(4, "negation")]
    out = model.explain("a.cfg", None)
    assert [(i["line"], i["reason"]) for i in out["ignored_but_relevant"]] == [(5, "char-range")]


# ---- oracle comparison (seeded, > 500 pattern x path cases)

SEGMENTS = ["docs", "src", "a", "b", "logs", "lib", "x.js", "*.js", "*", "**", "?x", "a*", "*b", "d?cs"]
PATH_PARTS = ["docs", "src", "a", "b", "logs", "lib", "ax", "bx", "x.js", "y.py", "bx.js", "docsx", "logsx"]


def random_pattern(rng):
    segs = [rng.choice(SEGMENTS) for _ in range(rng.randint(1, 3))]
    p = "/".join(segs)
    if rng.random() < 0.3:
        p = "/" + p
    if rng.random() < 0.3:
        p += "/"
    return p


def random_path(rng):
    return "/".join(rng.choice(PATH_PARTS) for _ in range(rng.randint(1, 4)))


def test_matches_oracle_on_seeded_random_cases():
    rng = random.Random(20261118)
    cases = checked = 0
    for _ in range(60):
        patterns = [random_pattern(rng) for _ in range(rng.randint(3, 8))]
        text = "\n".join(f"{p} @u{i}" for i, p in enumerate(patterns)) + "\n"
        oracle = CodeOwners(text)
        parsed = gh.parse(text)
        paths = sorted({random_path(rng) for _ in range(12)})
        winners = gh.evaluate(parsed.rules, paths)[0]
        for path, w in zip(paths, winners):
            mine = parsed.rules[w].owners if w >= 0 else []
            theirs = [o for _, o in oracle.of(path)]
            assert mine == theirs, (text, path, mine, theirs)
            checked += 1
            cases += len(patterns)
    assert checked >= 500 and cases >= 500


def test_oracle_agrees_on_probe_file_for_valid_lines():
    text = "\n".join(l for l in (GH / "CODEOWNERS").read_text().splitlines()
                     if not l.startswith(("!", "[")))
    oracle = CodeOwners(text)
    parsed = gh.parse(text)
    for path in PROBE_EXPECTED:
        w = gh.evaluate(parsed.rules, [path])[0][0]
        assert (parsed.rules[w].owners if w >= 0 else []) == [o for _, o in oracle.of(path)], path
