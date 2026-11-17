"""AC-4: ownership diff and its exit codes."""
import json

from conftest import GH, GL, run, run_json

BASE = ["diff", "--before", str(GH / "CODEOWNERS"), "--after", str(GH / "CODEOWNERS.fixed"),
        "--files-from", str(GH / "files.txt")]


def test_merging_the_two_js_lines_changes_only_web_app_js():
    proc, data = run_json(*BASE, "--expect", "*.js")
    assert proc.returncode == 0
    assert data["changed"] == [{"path": "web/app.js", "before": ["@alice"], "after": ["@org/js", "@alice"]}]
    assert data["unchanged_count"] == 17 and data["unexpected"] == [] and data["ok"] is True
    assert '"changed": [{"path": "web/app.js"' in proc.stdout


def test_change_outside_expect_fails_with_unexpected_and_ineffective_expect():
    proc, data = run_json(*BASE, "--expect", "docs/**")
    assert proc.returncode == 1
    assert data["unexpected"] == ["web/app.js"] and data["ineffective_expect"] == ["docs/**"] and data["ok"] is False


def test_without_expect_the_diff_is_informational():
    proc, data = run_json(*BASE)
    assert proc.returncode == 0 and data["changed_count"] == 1 and data["unexpected"] == []


def test_expect_none_fails_on_any_change_and_passes_a_pure_cleanup(tmp_path):
    proc, data = run_json(*BASE, "--expect-none")
    assert proc.returncode == 1 and data["unexpected"] == ["web/app.js"]
    clean = tmp_path / "CODEOWNERS"
    clean.write_text((GH / "CODEOWNERS").read_text().replace("src/ @org/src\n", "# source\nsrc/ @org/src\n"))
    proc, data = run_json("diff", "--before", GH / "CODEOWNERS", "--after", clean, "--files-from", GH / "files.txt",
                          "--expect-none")
    assert proc.returncode == 0 and data["changed"] == [] and data["changed_count"] == 0


def test_owner_identical_move_goes_to_line_only(tmp_path):
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.write_text("* @a\n/docs/ @b\n")
    after.write_text("* @a\n/docs/ @b\ndocs/ @b\n")         # same owner, another rule decides now
    files = tmp_path / "f.txt"
    files.write_text("docs/x.md\nsrc/y.py\n")
    proc, data = run_json("diff", "--before", before, "--after", after, "--files-from", files, "--expect", "*.nothing")
    assert data["changed"] == []
    assert data["line_only"] == [{"path": "docs/x.md", "before_line": 2, "after_line": 3,
                                  "before_pattern": "/docs/", "after_pattern": "docs/"}]
    assert data["ineffective_expect"] == ["*.nothing"] and proc.returncode == 1


def test_new_unsupported_line_in_after_is_a_new_error(tmp_path):
    after = tmp_path / "after"
    after.write_text((GH / "CODEOWNERS.fixed").read_text() + "!docs/api/ @org/nobody\n")
    proc, data = run_json("diff", "--before", GH / "CODEOWNERS", "--after", after, "--files-from", GH / "files.txt",
                          "--expect", "*.js")
    assert proc.returncode == 1 and data["ok"] is False
    assert [(f["code"], f["pattern"], f["line"]) for f in data["new_errors"]] == [
        ("unsupported-syntax", "!docs/api/", 11)]


def test_old_errors_in_both_files_are_not_new(tmp_path):
    proc, data = run_json(*BASE, "--expect", "*.js")
    assert data["new_errors"] == []                            # lines 4 and 5 were skipped before and after


def test_order_of_owners_is_not_a_change(tmp_path):
    before, after = tmp_path / "b", tmp_path / "a"
    before.write_text("* @a @b\n")
    after.write_text("* @b @a\n")
    files = tmp_path / "f.txt"
    files.write_text("x\n")
    proc, data = run_json("diff", "--before", before, "--after", after, "--files-from", files, "--expect-none")
    assert proc.returncode == 0 and data["changed"] == []


def test_gitlab_diff_compares_sections(tmp_path):
    before = GL / "CODEOWNERS"
    after = tmp_path / "CODEOWNERS"
    after.write_text(before.read_text().replace("^[Ruby][2] @ruby-default", "^[Ruby][3] @ruby-default"))
    proc, data = run_json("diff", "--platform", "gitlab", "--before", before, "--after", after,
                          "--files-from", GL / "files.txt", "--expect", "*.rb")
    assert proc.returncode == 0
    assert [c["path"] for c in data["changed"]] == ["app/m.rb"]
    assert data["changed"][0]["before"][1] == {"name": "Ruby", "owners": ["@ruby-default"], "approvals": 2, "optional": True}
    assert data["changed"][0]["after"][1]["approvals"] == 3


def test_table_output_mentions_result(tmp_path):
    proc = run(*BASE, "--expect", "docs/**", "--lang", "en")
    assert proc.returncode == 1 and "result: FAILED" in proc.stdout and "changed outside --expect" in proc.stdout
    proc = run(*BASE, "--expect", "*.js", "--lang", "en")
    assert proc.returncode == 0 and "result: OK" in proc.stdout


def test_out_file_receives_the_json(tmp_path):
    out = tmp_path / "diff.json"
    proc = run(*BASE, "--expect", "*.js", "--format", "json", "--out", out)
    assert json.loads(out.read_text())["changed"][0]["path"] == "web/app.js" and proc.returncode == 0
