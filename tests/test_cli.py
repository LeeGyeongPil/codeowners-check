"""AC-5 and AC-7: error and boundary paths, determinism, platform detection, performance."""
import json
import os
import time

import pytest
from codeowners import CodeOwners

import synth
from conftest import CLI, GH, run, run_json


def write(path, text, mode="w"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def test_missing_codeowners_exits_2_with_the_search_places(tmp_path):
    write(tmp_path / "a.py", "x")
    proc = run("resolve", "--root", tmp_path, "--lang", "en")
    assert proc.returncode == 2 and proc.stdout == ""
    assert proc.stderr.startswith("error: CODEOWNERS file not found (looked in: .github/CODEOWNERS, CODEOWNERS, docs/CODEOWNERS)")
    proc = run("lint", "--root", tmp_path, "--platform", "gitlab", "--lang", "en")
    assert "looked in: CODEOWNERS, docs/CODEOWNERS, .gitlab/CODEOWNERS" in proc.stderr


def test_missing_explicit_codeowners_exits_2(tmp_path):
    proc = run("lint", "--codeowners", tmp_path / "nope" / "CODEOWNERS", "--files-from", GH / "files.txt", "--lang", "en")
    assert proc.returncode == 2 and "error: CODEOWNERS file not found" in proc.stderr and "nope" in proc.stderr


def test_empty_file_list_exits_2(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "* @a\n")
    empty = write(tmp_path / "files.txt", "\n  \n")
    proc = run("lint", "--codeowners", co, "--files-from", empty, "--lang", "en")
    assert proc.returncode == 2 and proc.stderr.startswith("error: no files to check")
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    proc = run("lint", "--codeowners", co, "--root", empty_root, "--lang", "en")
    assert proc.returncode == 2 and "no files to check" in proc.stderr


def test_missing_files_from_and_stdin(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "* @a\n")
    proc = run("lint", "--codeowners", co, "--files-from", tmp_path / "missing.txt", "--lang", "en")
    assert proc.returncode == 2 and "cannot read the file list" in proc.stderr
    proc = run("resolve", "--codeowners", co, "--files-from", "-", "--format", "json", stdin="a.py\nb/c.py\n")
    assert proc.returncode == 0 and [f["path"] for f in json.loads(proc.stdout)["files"]] == ["a.py", "b/c.py"]


def test_diff_requires_before_and_after(tmp_path):
    proc = run("diff", "--files-from", GH / "files.txt", "--lang", "en")
    assert proc.returncode == 2 and proc.stderr.strip() == "error: --before and --after are required for diff"
    proc = run("diff", "--before", GH / "CODEOWNERS", "--files-from", GH / "files.txt", "--lang", "en")
    assert proc.returncode == 2


def test_diff_rejects_unsupported_expect_pattern():
    proc = run("diff", "--before", GH / "CODEOWNERS", "--after", GH / "CODEOWNERS.fixed", "--files-from",
               GH / "files.txt", "--expect", "!docs/", "--lang", "en")
    assert proc.returncode == 2 and "--expect pattern" in proc.stderr


@pytest.mark.parametrize("argv", [["resolve", "--platform", "svn"], ["frobnicate"], [], ["lint", "--fail-on", "maybe"],
                                  ["explain"], ["lint", "--lang", "fr"]])
def test_argparse_errors_exit_2(argv):
    proc = run(*argv)
    assert proc.returncode == 2 and proc.stderr.strip().splitlines()[-1].startswith("error:")


def test_unwritable_out_exits_2(tmp_path, gh_args):
    proc = run("resolve", *gh_args, "--out", tmp_path / "no-such-dir" / "x.json", "--lang", "en")
    assert proc.returncode == 2 and "cannot write" in proc.stderr


def test_out_format_follows_the_file_name(tmp_path, gh_args):
    """--out x.json without --format writes the JSON report; other names and --format table keep the table."""
    as_json = run("resolve", *gh_args, "--format", "json", "--lang", "en").stdout
    run("resolve", *gh_args, "--out", tmp_path / "a.json", "--lang", "en")
    assert (tmp_path / "a.json").read_text(encoding="utf-8") == as_json
    json.loads(as_json)
    run("resolve", *gh_args, "--out", tmp_path / "a.txt", "--lang", "en")
    assert not (tmp_path / "a.txt").read_text(encoding="utf-8").startswith("{")
    run("resolve", *gh_args, "--format", "table", "--out", tmp_path / "b.json", "--lang", "en")
    assert not (tmp_path / "b.json").read_text(encoding="utf-8").startswith("{")


def test_gitlab_headers_note_only_when_platform_was_guessed(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "* @a\n[Docs]\n/docs/ @d\n")
    files = write(tmp_path / "files.txt", "docs/x.md\n")
    _, data = run_json("resolve", "--codeowners", co, "--files-from", files, "--lang", "en")
    assert any("Lines 2 look like GitLab section headers" in n for n in data["notes"])
    _, data = run_json("resolve", "--codeowners", co, "--files-from", files, "--platform", "github", "--lang", "en")
    assert not any("GitLab section headers" in n for n in data["notes"])
    plain = write(tmp_path / "plain" / "CODEOWNERS", "* @a\n[ab].py @b\n")
    _, data = run_json("resolve", "--codeowners", plain, "--files-from", files, "--lang", "en")
    assert not any("GitLab section headers" in n for n in data["notes"])


def test_empty_codeowners_every_file_has_no_rule(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "")
    proc, data = run_json("resolve", "--codeowners", co, "--files-from", GH / "files.txt")
    assert proc.returncode == 0 and {f["status"] for f in data["files"]} == {"no-rule"}
    assert all(f["owners"] == [] and f["line"] is None for f in data["files"])
    proc, data = run_json("lint", "--codeowners", co, "--files-from", GH / "files.txt")
    assert data["findings"][0]["code"] == "unowned-file" and data["findings"][0]["count"] == 18


def test_crlf_bom_and_trailing_comments(tmp_path):
    body = "# owners\r\n* @a  # everyone\r\n\r\n*.js\t@b @c # js owners\r\nweb/ @d # web\r\n"
    co = write(tmp_path / "CODEOWNERS", b"\xef\xbb\xbf" + body.encode())
    files = write(tmp_path / "f.txt", "x.py\napp.js\nweb/y.py\n")
    proc, data = run_json("resolve", "--codeowners", co, "--files-from", files)
    owners = {f["path"]: (f["owners"], f["line"]) for f in data["files"]}
    assert owners["x.py"] == (["@a"], 2)                      # BOM did not hide line 2 or break the pattern
    assert owners["web/y.py"] == (["@d"], 5)                  # trailing comment is not an owner
    assert owners["app.js"] == (["@b", "@c"], 4)            # a tab separates fields and '# ...' ends the line
    assert data["ignored_lines"] == []
    co.write_bytes(b"* @a\r\n*.js @b#glued\r\n")
    _, data = run_json("resolve", "--codeowners", co, "--files-from", files)
    assert data["ignored_lines"] == [{"line": 2, "pattern": "*.js", "code": "invalid-owner", "args": {"owner": "@b#glued"}}]


def test_same_input_gives_identical_json_bytes(gh_args):
    a = run("resolve", *gh_args, "--format", "json")
    b = run("resolve", *gh_args, "--format", "json")
    assert a.stdout == b.stdout and a.stdout
    a = run("lint", *gh_args, "--format", "json")
    b = run("lint", *gh_args, "--format", "json")
    assert a.stdout == b.stdout
    # the file list is normalised and sorted, so its order does not matter
    lines = (GH / "files.txt").read_text().splitlines()
    c = run("resolve", "--codeowners", GH / "CODEOWNERS", "--files-from", "-", "--format", "json",
            stdin="\n".join(reversed(lines)) + "\n")
    assert c.stdout == run("resolve", *gh_args, "--format", "json").stdout


def test_path_normalisation_in_file_list(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "* @a\n")
    files = write(tmp_path / "f.txt", ".\\win\\a.py\n./b.py\nb.py\n\n/c.py\n")
    _, data = run_json("resolve", "--codeowners", co, "--files-from", files)
    assert [f["path"] for f in data["files"]] == ["b.py", "c.py", "win/a.py"]


def test_root_walk_skips_dot_git_and_does_not_follow_symlinked_folders(tmp_path):
    write(tmp_path / "CODEOWNERS", "* @a\n")
    write(tmp_path / "src" / "a.py", "x")
    write(tmp_path / ".git" / "config", "x")
    outside = tmp_path.parent / (tmp_path.name + "-outside")
    write(outside / "secret.txt", "x")
    os.symlink(outside, tmp_path / "linked")
    _, data = run_json("resolve", "--root", tmp_path)
    assert [f["path"] for f in data["files"]] == ["CODEOWNERS", "src/a.py"]


def test_resolve_with_explicit_paths_needs_no_file_list(tmp_path):
    co = write(tmp_path / "CODEOWNERS", "*.py @a\n")
    proc, data = run_json("resolve", "--codeowners", co, "x/y.py", "./z.txt", cwd=tmp_path)
    assert proc.returncode == 0 and [(f["path"], f["owners"]) for f in data["files"]] == [("x/y.py", ["@a"]), ("z.txt", [])]


def test_explain_path_outside_the_list_is_resolved_with_a_note(gh_args):
    proc = run("explain", "brand/new.py", *gh_args, "--lang", "en")
    assert proc.returncode == 0 and "not in the file list" in proc.stdout


@pytest.mark.parametrize("layout,expected,reason", [
    ([".github/CODEOWNERS"], "github", "under-.github"),
    ([".gitlab/CODEOWNERS"], "gitlab", "under-.gitlab"),
    ([".gitlab-ci.yml", "CODEOWNERS"], "gitlab", "gitlab-marker-in-root"),
    (["CODEOWNERS"], "github", "default"),
])
def test_platform_is_decided_by_location_only(tmp_path, layout, expected, reason):
    for name in layout:
        write(tmp_path / name, "* @a\n" if name.endswith("CODEOWNERS") else "x")
    proc, data = run_json("resolve", "--root", tmp_path, "a.py")
    assert (data["platform"], data["platform_reason"]) == (expected, reason)


def test_explicit_platform_overrides_detection(tmp_path):
    write(tmp_path / ".github" / "CODEOWNERS", "* @a\n")
    _, data = run_json("resolve", "--root", tmp_path, "--platform", "gitlab", "--codeowners",
                       tmp_path / ".github" / "CODEOWNERS", "a.py")
    assert (data["platform"], data["platform_reason"]) == ("gitlab", "explicit")


def test_help_works_for_every_command():
    for argv in (["--help"], ["resolve", "--help"], ["explain", "--help"], ["lint", "--help"], ["diff", "--help"]):
        proc = run(*argv, "--lang", "en")
        assert proc.returncode == 0 and "usage:" in proc.stdout


# ---- AC-7 performance and a cross-check on a seeded synthetic repository

def test_synthetic_400_files_40_rules_matches_the_oracle(tmp_path):
    files, text = synth.make_repo(400, 40, 7)
    co = write(tmp_path / "CODEOWNERS", text)
    fl = write(tmp_path / "files.txt", "\n".join(files) + "\n")
    proc, data = run_json("lint", "--codeowners", co, "--files-from", fl)
    oracle = CodeOwners(text)
    expected_unowned = sorted(p for p in files if not oracle.of(p))
    unowned = next(f for f in data["findings"] if f["code"] == "unowned-file")
    assert [x["path"] for x in unowned["files"]] == expected_unowned and unowned["count"] == len(expected_unowned)
    _, res = run_json("resolve", "--codeowners", co, "--files-from", fl)
    assert all(f["owners"] == [o for _, o in oracle.of(f["path"])] for f in res["files"])
    dead = sorted(f["line"] for f in data["findings"] if f["code"] == "dead-rule")
    shadowed = sorted(f["line"] for f in data["findings"] if f["code"] == "shadowed-rule")
    assert dead == [2, 6, 14, 22, 25, 26, 30, 31, 37] and shadowed == [3, 4, 7, 8, 11, 15, 16]


def test_lint_10k_files_under_10s(tmp_path):
    files, text = synth.make_repo(10000, 200, 11)
    co = write(tmp_path / "CODEOWNERS", text)
    fl = write(tmp_path / "files.txt", "\n".join(files) + "\n")
    start = time.perf_counter()
    proc = run("lint", "--codeowners", co, "--files-from", fl, "--format", "json")
    elapsed = time.perf_counter() - start
    assert proc.returncode in (0, 1)
    data = json.loads(proc.stdout)
    assert data["files_total"] == 10000
    assert elapsed < 10, f"lint took {elapsed:.1f}s"


def test_github_file_above_3mb_is_not_loaded(tmp_path):
    """GitHub ignores a CODEOWNERS above 3 MB, so resolve/explain/diff must not apply its rules."""
    big = tmp_path / "big"
    big.write_text("* @x\n# " + "y" * (3 * 1024 * 1024) + "\n")
    small = tmp_path / "small"
    small.write_text("* @x\n")
    files = tmp_path / "f.txt"
    files.write_text("a.py\nb/c.js\n")
    base = ["--platform", "github", "--files-from", files]
    _, res = run_json("resolve", "--codeowners", big, *base)
    assert [(f["owners"], f["status"]) for f in res["files"]] == [([], "no-rule")] * 2
    assert any("3145728" in n for n in res["notes"])
    _, ex = run_json("explain", "--codeowners", big, *base, "a.py")
    assert ex["owners"] == [] and ex["matches"] == [] and any("3145728" in n for n in ex["notes"])
    proc, d = run_json("diff", "--before", big, "--after", small, *base, "--expect", "*.py")
    assert proc.returncode == 1 and d["changed_count"] == 2  # unowned -> @x, so the edit is a real change
    _, ok = run_json("resolve", "--codeowners", small, *base)
    assert ok["files"][0]["owners"] == ["@x"] and not any("3145728" in n for n in ok["notes"])
    ko = run("resolve", "--codeowners", big, *base, "--lang", "ko").stdout
    assert "3145728" in ko and "불러오지 않으므로" in ko
    _, lint = run_json("lint", "--codeowners", big, *base)
    assert {f["code"] for f in lint["findings"]} == {"file-too-large", "unowned-file"}
