"""AC-2: lint findings (GitHub), plus the shared exit-code policy of `lint`."""
import pytest

import _co_github as hub
from conftest import GH, run, run_json


def finding(data, code, line=None):
    return [f for f in data["findings"] if f["code"] == code and (line is None or f["line"] == line)]


def test_probe_file_findings(gh_args):
    proc, data = run_json("lint", *gh_args)
    assert proc.returncode == 1
    assert {(f["code"], f["line"]) for f in data["findings"]} == {
        ("unsupported-syntax", 4), ("unsupported-syntax", 5), ("shadowed-rule", 6), ("duplicate-pattern", 7),
        ("unowned-file", None)}
    assert data["counts"] == {"error": 2, "warning": 2, "info": 1}
    assert finding(data, "unsupported-syntax", 4)[0]["detail_key"] == "unsupported-syntax.negation"
    assert finding(data, "unsupported-syntax", 5)[0]["detail_key"] == "unsupported-syntax.char-range"
    shadow = finding(data, "shadowed-rule", 6)[0]
    assert shadow["pattern"] == "*.js" and shadow["args"] == {"by_lines": [7]}
    assert finding(data, "duplicate-pattern", 7)[0]["args"] == {"first_line": 6}
    unowned = finding(data, "unowned-file")[0]
    assert unowned["files"] == [{"path": "apps/github/main.go", "status": "cleared"}] and unowned["count"] == 1


def test_dead_rule_and_clean_file(tmp_path):
    co = tmp_path / "CODEOWNERS"
    files = tmp_path / "files.txt"
    files.write_text("a.py\nb/c.py\n")
    co.write_text("* @a\n/nothing/ @b\n")
    proc, data = run_json("lint", "--codeowners", co, "--files-from", files)
    assert [(f["code"], f["line"]) for f in data["findings"]] == [("dead-rule", 2)]
    co.write_text("* @a\n/b/ @b\n")
    proc, data = run_json("lint", "--codeowners", co, "--files-from", files)
    assert proc.returncode == 0 and data["findings"] == [] and data["counts"] == {"error": 0, "warning": 0, "info": 0}


def test_invalid_owner_is_an_error_and_the_line_is_skipped(tmp_path):
    co = tmp_path / "CODEOWNERS"
    co.write_text("* @a\n*.py not-an-owner\nweb/ @org/\n")
    files = tmp_path / "f.txt"
    files.write_text("x.py\nweb/y.js\n")
    proc, data = run_json("lint", "--codeowners", co, "--files-from", files)
    bad = finding(data, "invalid-owner")
    assert [(f["line"], f["args"]["owner"]) for f in bad] == [(2, "not-an-owner"), (3, "@org/")]
    assert all(f["severity"] == "error" for f in bad)
    _, res = run_json("resolve", "--codeowners", co, "--files-from", files)
    assert [f["owners"] for f in res["files"]] == [["@a"], ["@a"]]       # both bad lines were skipped
    assert any("Assumption" in n for n in res["notes"])


def test_multiple_codeowners_files_choose_github_folder_first(tmp_path):
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "CODEOWNERS").write_text("* @from-github-folder\n")
    (tmp_path / "CODEOWNERS").write_text("* @from-root\n")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "CODEOWNERS").write_text("* @from-docs\n")
    proc, data = run_json("lint", "--root", tmp_path)
    f = finding(data, "multiple-codeowners-files")[0]
    assert f["args"]["used"].endswith(".github/CODEOWNERS") and f["args"]["ignored"] == ["CODEOWNERS", "docs/CODEOWNERS"]
    _, res = run_json("resolve", "--root", tmp_path, "CODEOWNERS")
    assert res["files"][0]["owners"] == ["@from-github-folder"]


def test_file_too_large(tmp_path, monkeypatch):
    co = tmp_path / "CODEOWNERS"
    co.write_text("* @a\n" + "# " + "x" * (3 * 1024 * 1024) + "\n")
    files = tmp_path / "f.txt"
    files.write_text("a.py\n")
    proc, data = run_json("lint", "--codeowners", co, "--files-from", files)
    big = finding(data, "file-too-large")[0]
    assert big["severity"] == "error" and big["args"]["limit"] == hub.MAX_BYTES
    assert proc.returncode == 1


@pytest.mark.parametrize("fail_on,expected", [("error", 1), ("warning", 1), ("never", 0)])
def test_fail_on_levels_with_errors(gh_args, fail_on, expected):
    assert run("lint", *gh_args, "--fail-on", fail_on).returncode == expected


def test_fail_on_error_ignores_warnings(tmp_path):
    co = tmp_path / "CODEOWNERS"
    co.write_text("* @a\n/nothing/ @b\n")
    files = tmp_path / "f.txt"
    files.write_text("a.py\n")
    assert run("lint", "--codeowners", co, "--files-from", files, "--fail-on", "error").returncode == 0
    assert run("lint", "--codeowners", co, "--files-from", files).returncode == 1


def test_explain_gives_the_reason_for_docs_star(gh_args):
    proc, data = run_json("explain", "docs/deep/x.md", *gh_args)
    assert [(m["line"], m["winner"]) for m in data["matches"]] == [(1, True)]
    assert data["owners"] == ["@org/default"]
    assert any(h["code"] == "star-not-recursive" and h["line"] == 2 for h in data["hints"])
    assert data["in_file_list"] is True


def test_explain_shows_skipped_lines_that_would_match_gitignore_style(gh_args):
    _, data = run_json("explain", "docs/legacy/old.md", *gh_args)
    assert data["ignored_but_relevant"] == [{"line": 4, "pattern": "!docs/legacy/", "reason": "negation"}]
    assert data["owners"] == ["@org/default"]
    assert any(h["code"] == "ignored-line" for h in data["hints"])


def test_explain_later_line_wins_and_cleared_hints(gh_args):
    _, data = run_json("explain", "web/app.js", *gh_args)
    assert [(m["line"], m["winner"]) for m in data["matches"]] == [(1, False), (6, False), (7, True)]
    assert any(h["code"] == "later-wins" for h in data["hints"])
    _, data = run_json("explain", "apps/github/main.go", *gh_args)
    assert data["status"] == "cleared" and any(h["code"] == "cleared" for h in data["hints"])


def test_unowned_files_split_no_rule_and_cleared(tmp_path):
    co = tmp_path / "CODEOWNERS"
    co.write_text("/a/ @x\n/b/\n")
    files = tmp_path / "f.txt"
    files.write_text("a/1\nb/2\nc/3\n")
    _, data = run_json("lint", "--codeowners", co, "--files-from", files)
    unowned = finding(data, "unowned-file")[0]
    assert unowned["files"] == [{"path": "b/2", "status": "cleared"}, {"path": "c/3", "status": "no-rule"}]
