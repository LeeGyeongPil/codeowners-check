"""AC-6: English and Korean output, language selection order, identical message keys."""
import json

import pytest

import _co_i18n as i18n
from conftest import GH, run, run_json


def test_both_languages_have_identical_keys():
    assert set(i18n.EN) == set(i18n.KO)
    assert all(i18n.EN[k].strip() and i18n.KO[k].strip() for k in i18n.EN)


def test_placeholders_match_between_languages():
    import string
    fmt = string.Formatter()
    for key in i18n.EN:
        en = {f for _, f, _, _ in fmt.parse(i18n.EN[key]) if f}
        ko = {f for _, f, _, _ in fmt.parse(i18n.KO[key]) if f}
        assert en == ko, key


@pytest.mark.parametrize("cli,env,expected", [
    ("ko", {"CODEOWNERS_CHECK_LANG": "en"}, "ko"),                                    # --lang beats everything
    ("en", {"LANG": "ko_KR.UTF-8"}, "en"),
    (None, {"CODEOWNERS_CHECK_LANG": "ko", "LC_ALL": "en_US.UTF-8"}, "ko"),           # tool variable beats locale
    (None, {"CODEOWNERS_CHECK_LANG": "en", "LANG": "ko_KR.UTF-8"}, "en"),
    (None, {"LC_ALL": "ko_KR.UTF-8", "LC_MESSAGES": "en_US", "LANG": "en_US"}, "ko"),  # LC_ALL beats LC_MESSAGES
    (None, {"LC_MESSAGES": "ko_KR", "LANG": "en_US"}, "ko"),
    (None, {"LANG": "ko_KR.UTF-8"}, "ko"),
    (None, {"LANG": "fr_FR.UTF-8"}, "en"),                                            # not Korean -> English
    (None, {"LC_ALL": "C"}, "en"),
    (None, {"LC_ALL": "", "LANG": "ko_KR"}, "ko"),                                    # empty values are skipped
    (None, {}, "en"),
    ("xx", {"LANG": "ko_KR"}, "ko"),                                                  # unknown --lang value is ignored
])
def test_resolve_lang_order(cli, env, expected):
    assert i18n.resolve_lang(cli, env) == expected


def test_translator_falls_back_to_the_key_and_formats_lists():
    tr = i18n.translator("en")
    assert tr("no.such.key") == "no.such.key"
    assert "3, 4" in tr("finding.shadowed-rule", line=1, pattern="x", by_lines=[3, 4])
    assert "-" in tr("finding.dead-rule", line=None, pattern=None)


def test_cli_language_switch_changes_table_headers_and_messages(gh_args):
    en = run("lint", *gh_args, "--lang", "en").stdout
    ko = run("lint", *gh_args, "--lang", "ko").stdout
    assert "SEVERITY" in en and "files:" in en and "심각도" not in en
    assert "심각도" in ko and "파일 수:" in ko and "SEVERITY" not in ko
    en = run("resolve", *gh_args, "--lang", "en").stdout
    ko = run("resolve", *gh_args, "--lang", "ko").stdout
    assert "PATTERN" in en and "STATUS" in en and "패턴" in ko and "상태" in ko and "PATTERN" not in ko


def test_cli_environment_selects_language(gh_args):
    assert "심각도" in run("lint", *gh_args, env={"CODEOWNERS_CHECK_LANG": "ko"}).stdout
    assert "SEVERITY" in run("lint", *gh_args, env={"LANG": "en_US.UTF-8"}).stdout
    assert "심각도" in run("lint", *gh_args, env={"LANG": "ko_KR.UTF-8"}).stdout
    assert "SEVERITY" in run("lint", *gh_args, "--lang", "en", env={"CODEOWNERS_CHECK_LANG": "ko"}).stdout
    assert "SEVERITY" in run("lint", *gh_args, env={"LC_ALL": "de_DE"}).stdout


def test_help_and_errors_are_localised(tmp_path):
    en = run("--help", "--lang", "en").stdout
    ko = run("--help", "--lang", "ko").stdout
    assert "Resolve and verify CODEOWNERS" in en and "Resolve and verify" not in ko and "해석하고 검증" in ko
    sub_en = run("lint", "--help", "--lang", "en").stdout
    sub_ko = run("lint", "--help", "--lang", "ko").stdout
    assert "lowest severity" in sub_en and "최저 심각도" in sub_ko
    err_en = run("diff", "--lang", "en", "--files-from", GH / "files.txt").stderr
    err_ko = run("diff", "--lang", "ko", "--files-from", GH / "files.txt").stderr
    assert err_en.startswith("error:") and err_ko.startswith("오류:")
    assert run("lint", "--root", tmp_path, "--lang", "ko").stderr.startswith("오류: ")


def test_lang_can_come_before_the_command(gh_args):
    assert "심각도" in run("--lang", "ko", "lint", *gh_args).stdout


def test_json_fields_and_codes_do_not_depend_on_language(gh_args):
    _, en = run_json("lint", *gh_args, "--lang", "en")
    _, ko = run_json("lint", *gh_args, "--lang", "ko")

    def skeleton(data):
        return [{k: v for k, v in f.items() if k != "message"} for f in data["findings"]], data["counts"]

    assert skeleton(en) == skeleton(ko)
    assert [list(f) for f in en["findings"]] == [list(f) for f in ko["findings"]]
    assert en["findings"][0]["message"] != ko["findings"][0]["message"]
    _, en = run_json("resolve", *gh_args, "--lang", "en")
    _, ko = run_json("resolve", *gh_args, "--lang", "ko")
    assert en["files"] == ko["files"] and en["ignored_lines"] == ko["ignored_lines"]
    assert en["notes"] != ko["notes"]


def test_korean_table_alignment_uses_display_width(gh_args):
    from codeowners_check import _width, table
    rows = table(["경로", "A"], [["가나", "x"], ["abc", "y"]]).splitlines()
    assert _width(rows[2][:rows[2].index("x")]) == _width(rows[3][:rows[3].index("y")])


# ---- argparse's own wording follows --lang too (no English headings or errors on a Korean screen)

ENGLISH_ARGPARSE = ("usage:", "options:", "positional arguments", "show this help", "invalid choice",
                    "unrecognized arguments", "the following arguments are required", "expected one argument")


@pytest.mark.parametrize("argv", [["--help"], ["diff", "--help"], ["lint", "--help"], ["resolve", "--help"]])
def test_ko_help_has_no_english_argparse_wording(argv):
    out = run("--lang", "ko", *argv).stdout
    assert out.startswith("사용법: codeowners_check.py") and "옵션:" in out
    assert not [w for w in ENGLISH_ARGPARSE if w in out]
    assert "usage:" in run("--lang", "en", *argv).stdout


@pytest.mark.parametrize("argv,expected", [
    (["lint", "--platform", "bogus"], "잘못된 선택"),
    (["lint", "--bogus"], "알 수 없는 인자"),
    ([], "다음 인자가 필요합니다"),
    (["lint", "--fail-on"], "값이 하나 필요"),
])
def test_ko_argparse_errors_are_korean(argv, expected):
    proc = run("--lang", "ko", *argv)
    assert proc.returncode == 2 and expected in proc.stderr and proc.stderr.count("오류:") == 1
    assert not [w for w in ENGLISH_ARGPARSE if w in proc.stderr]


def test_en_argparse_errors_stay_english():
    proc = run("--lang", "en", "lint", "--bogus")
    assert proc.returncode == 2 and "unrecognized arguments: --bogus" in proc.stderr
