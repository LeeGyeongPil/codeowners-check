"""The same CLI paths as the subprocess tests, but in-process (for line coverage and fast feedback)."""
import io
import json

import pytest

import codeowners_check as cli
from conftest import GH, GL, LANG_VARS


@pytest.fixture(autouse=True)
def no_lang_env(monkeypatch):
    for name in LANG_VARS:
        monkeypatch.delenv(name, raising=False)


def call(capsys, *argv):
    code = cli.main([str(a) for a in argv])
    cap = capsys.readouterr()
    return code, cap.out, cap.err


GH_ARGS = ["--codeowners", GH / "CODEOWNERS", "--files-from", GH / "files.txt"]
GL_ARGS = ["--platform", "gitlab", "--codeowners", GL / "CODEOWNERS", "--files-from", GL / "files.txt"]


@pytest.mark.parametrize("lang", ["en", "ko"])
@pytest.mark.parametrize("command", ["resolve", "lint"])
@pytest.mark.parametrize("args", [GH_ARGS, GL_ARGS])
def test_table_output_for_every_dialect(capsys, lang, command, args):
    code, out, err = call(capsys, command, *args, "--lang", lang)
    assert code in (0, 1) and err == "" and "github" in out or "gitlab" in out


@pytest.mark.parametrize("args,path", [(GH_ARGS, "docs/deep/x.md"), (GH_ARGS, "web/app.js"), (GH_ARGS, "nothing/here.bin"),
                                        (GL_ARGS, "config/routes.rb"), (GL_ARGS, "docs/sub/b.md"), (GL_ARGS, "unknown.zzz")])
def test_explain_table_and_json(capsys, args, path):
    code, out, _ = call(capsys, "explain", path, *args, "--lang", "en")
    assert code == 0 and path in out
    code, out, _ = call(capsys, "explain", path, *args, "--format", "json")
    assert json.loads(out)["path"] == path


def test_diff_table_gitlab_and_github(capsys, tmp_path):
    after = tmp_path / "CODEOWNERS"
    after.write_text((GL / "CODEOWNERS").read_text().replace("@docs-shallow", "@docs-flat"))
    code, out, _ = call(capsys, "diff", "--platform", "gitlab", "--before", GL / "CODEOWNERS", "--after", after,
                        "--files-from", GL / "files.txt", "--expect", "docs/a.md", "--lang", "ko")
    assert code == 0 and "docs/a.md" in out
    code, out, _ = call(capsys, "diff", "--before", GH / "CODEOWNERS", "--after", GH / "CODEOWNERS.fixed",
                        "--files-from", GH / "files.txt", "--expect", "docs/**", "--expect-none")
    assert code == 1 and "web/app.js" in out
    plain = tmp_path / "plain"
    plain.write_text((GH / "CODEOWNERS").read_text() + "\n# note\n")
    code, out, _ = call(capsys, "diff", "--before", GH / "CODEOWNERS", "--after", plain, "--files-from", GH / "files.txt")
    assert code == 0 and "(none)" in out
    bad = tmp_path / "bad"
    bad.write_text("!a\n")
    code, out, _ = call(capsys, "diff", "--before", plain, "--after", bad, "--files-from", GH / "files.txt")
    assert code == 1 and "new errors" in out


def test_resolve_paths_and_stdin(capsys, monkeypatch, tmp_path):
    code, out, _ = call(capsys, "resolve", "web/app.js", ".\\docs\\guide.md", "--codeowners", GH / "CODEOWNERS", "--format", "json")
    assert [f["owners"] for f in json.loads(out)["files"]] == [["@org/docs"], ["@alice"]]
    monkeypatch.setattr("sys.stdin", io.StringIO("a.py\nb.js\n"))
    code, out, _ = call(capsys, "lint", "--codeowners", GH / "CODEOWNERS", "--files-from", "-", "--format", "json")
    assert json.loads(out)["files_total"] == 2


def test_errors_in_process(capsys, tmp_path):
    (tmp_path / "a.py").write_text("x")
    code, out, err = call(capsys, "resolve", "--root", tmp_path, "--lang", "en")
    assert code == 2 and err.startswith("error: CODEOWNERS file not found")
    (tmp_path / "CODEOWNERS").write_text("* @a\n")
    code, _, err = call(capsys, "lint", "--root", tmp_path / "missing", "--codeowners", tmp_path / "CODEOWNERS", "--lang", "en")
    assert code == 2 and "--root is not a folder" in err
    code, _, err = call(capsys, "lint", "--root", tmp_path, "--files-from", tmp_path / "x.txt", "--lang", "ko")
    assert code == 2 and err.startswith("오류:")
    (tmp_path / "CODEOWNERS").unlink()
    (tmp_path / "CODEOWNERS").mkdir()
    code, _, err = call(capsys, "lint", "--root", tmp_path, "--files-from", GH / "files.txt", "--lang", "en")
    assert code == 2
    code, _, err = call(capsys, "diff", "--before", GH / "CODEOWNERS", "--after", tmp_path / "nope", "--files-from",
                        GH / "files.txt", "--lang", "en")
    assert code == 2 and "not found" in err
    code, _, err = call(capsys, "diff", "--lang", "en")
    assert code == 2 and "--before and --after" in err


def test_unreadable_codeowners_file(capsys, tmp_path):
    secret = tmp_path / "CODEOWNERS"
    secret.write_text("* @a\n")
    secret.chmod(0)
    try:
        code, _, err = call(capsys, "lint", "--codeowners", secret, "--files-from", GH / "files.txt", "--lang", "en")
    finally:
        secret.chmod(0o600)
    assert code in (0, 1, 2)                      # running as root can still read the file
    if code == 2:
        assert "cannot read" in err


def test_prescan_lang_forms():
    assert cli.prescan_lang(["lint", "--lang", "ko"]) == "ko"
    assert cli.prescan_lang(["lint", "--lang=ko"]) == "ko"
    assert cli.prescan_lang(["lint"]) is None


def test_lint_gitlab_with_errors_and_fail_on(capsys, tmp_path):
    co = tmp_path / "CODEOWNERS"
    co.write_text("[]\n*.rb badowner\n[Docs] @a\n/docs/ @a\n/nothing/ @b\n")
    files = tmp_path / "f.txt"
    files.write_text("docs/a.md\n")
    base = ["lint", "--platform", "gitlab", "--codeowners", co, "--files-from", files]
    assert call(capsys, *base, "--fail-on", "error")[0] == 1
    assert call(capsys, *base, "--fail-on", "never", "--lang", "ko")[0] == 0
    code, out, _ = call(capsys, *base, "--format", "json")
    codes = {f["code"] for f in json.loads(out)["findings"]}
    assert {"invalid-section-header", "invalid-owner", "dead-rule"} <= codes
