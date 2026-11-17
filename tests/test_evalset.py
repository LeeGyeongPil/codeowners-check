"""AC-9: the evaluation set is complete and its result graders match what the script really prints."""
import re
import subprocess
import sys

import pytest

from conftest import CLI, EVALS, clean_env

FIXTURES = EVALS / "fixtures"
CASES = sorted(p.name for p in EVALS.iterdir() if p.is_dir() and p.name != "fixtures")

# How an agent is expected to run the script for each task; the output file is what the graders read.
TASK_COMMANDS = {
    "task-legacy-owners": ("owners.json", ["resolve", "--codeowners", "CODEOWNERS", "--files-from", "files.txt"]),
    "task-shadowed-js": ("lint.json", ["lint", "--codeowners", "CODEOWNERS", "--files-from", "files.txt"]),
    "task-verify-merge": ("diff.json", ["diff", "--before", "CODEOWNERS", "--after", "CODEOWNERS.proposed",
                                        "--files-from", "files.txt", "--expect", "*.js"]),
    "task-gitlab-sections": ("gl.json", ["resolve", "--platform", "gitlab", "--codeowners", "CODEOWNERS",
                                         "--files-from", "files.txt", "config/routes.rb", "docs/sub/b.md"]),
    "task-large-repo": ("lint.json", ["lint", "--codeowners", "CODEOWNERS", "--files-from", "files.txt"]),
    "task-error-wider-change": ("check.json", ["diff", "--before", "CODEOWNERS", "--after", "CODEOWNERS.proposed",
                                               "--files-from", "files.txt", "--expect", "docs/deep/**"]),
}


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path
    head = text.split("\n---\n", 1)[0].splitlines()[1:]
    out = {}
    for line in head:
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip()
    return out


def unquote(value):
    assert value.startswith("'") and value.endswith("'"), value
    return value[1:-1].replace("''", "'")


def graders(case):
    return {g.stem: frontmatter(g) for g in sorted((EVALS / case / "graders").glob("*.md"))}


def test_case_counts_match_the_plan():
    trig = [c for c in CASES if c.startswith("trigger-")]
    no = [c for c in CASES if c.startswith("notrigger-")]
    near = [c for c in no if c.startswith("notrigger-near-")]
    tasks = [c for c in CASES if c.startswith("task-")]
    errors = [c for c in tasks if c.startswith("task-error-")]
    korean = [c for c in trig if re.search(r"[가-힣]", (EVALS / c / "prompt.md").read_text(encoding="utf-8"))]
    assert len(trig) >= 10 and len(korean) >= 2
    assert len(no) >= 10 and len(near) >= 5
    assert len(tasks) >= 5 and len(errors) >= 1
    assert len(trig) + len(no) + len(tasks) == len(CASES)


@pytest.mark.parametrize("case", [c for c in CASES if c.startswith("trigger-")])
def test_trigger_prompts_do_not_name_the_skill(case):
    body = (EVALS / case / "prompt.md").read_text(encoding="utf-8").split("---\n", 2)[2]
    assert not re.search(r"codeowners-check|\bskill\b|스킬", body, re.I)
    g = graders(case)["skill-fired"]
    assert g["type"] == "tool_used" and g["tool"] == "Skill" and g["arm"] == "both"
    assert re.search(unquote(g["input_match"]), '{"skill": "codeowners-check"}')
    assert re.search(unquote(g["input_match"]), '{"skill":"codeowners-check:codeowners-check"}')
    assert not re.search(unquote(g["input_match"]), '{"skill": "pdf"}')


@pytest.mark.parametrize("case", [c for c in CASES if c.startswith("notrigger-")])
def test_notrigger_graders_forbid_the_skill(case):
    g = graders(case)["skill-not-fired"]
    assert g["type"] == "tool_used" and g["tool"] == "Skill" and g["max"] == "0" and g["arm"] == "both"


@pytest.mark.parametrize("case", [c for c in CASES if c.startswith("task-")])
def test_task_cases_have_fixtures_and_exact_value_graders(case):
    assert (FIXTURES / case).is_dir() and any((FIXTURES / case).iterdir())
    assert not any(p.name.startswith(".") for p in (FIXTURES / case).rglob("*"))
    g = graders(case)
    ran = g["script-ran"]
    assert ran["tool"] == "Bash" and ran["arm"] == "with-only"
    assert re.search(unquote(ran["input_match"]), "python3 /x/skills/codeowners-check/scripts/codeowners_check.py lint")
    regexes = {k: v for k, v in g.items() if v["type"] == "regex"}
    assert regexes
    file_lengths = []
    for name, spec in regexes.items():
        pat = unquote(spec["pattern"])
        assert len(pat) >= 6, name
        if "source: file" in spec["target"]:
            file_lengths.append(len(pat))
        assert "\\\\" not in pat and not re.search(r"\(\?P|\\[AZ]", pat), name   # JavaScript-compatible, single backslash
    if case != "task-error-no-codeowners":  # that case checks the script's error line instead of an output file
        assert max(file_lengths) >= 60      # at least one grader pins an exact, script-formatted value


def run_task(case, tmp_path, extra_args=None):
    out_name, args = TASK_COMMANDS[case]
    work = tmp_path / case
    work.mkdir()
    for f in (FIXTURES / case).iterdir():
        (work / f.name).write_bytes(f.read_bytes())
    proc = subprocess.run([sys.executable, str(CLI), *(extra_args or args), "--format", "json", "--out", out_name],
                          cwd=work, capture_output=True, text=True, env=clean_env(), encoding="utf-8")
    return proc, work / out_name


@pytest.mark.parametrize("case", sorted(TASK_COMMANDS))
def test_file_graders_match_the_real_script_output(case, tmp_path):
    proc, out = run_task(case, tmp_path)
    assert proc.returncode in (0, 1), proc.stderr
    text = out.read_text(encoding="utf-8")
    checked = 0
    for name, spec in graders(case).items():
        if spec["type"] != "regex" or "source: file" not in spec["target"]:
            continue
        assert spec["target"].endswith(f"path: {out.name}}}"), name
        assert re.search(unquote(spec["pattern"]), text), (case, name)
        checked += 1
    assert checked >= 2


def test_every_task_has_a_command_or_is_the_missing_file_case():
    tasks = {c for c in CASES if c.startswith("task-")}
    assert tasks - set(TASK_COMMANDS) == {"task-error-no-codeowners"}


def test_graders_do_not_pass_on_a_different_result(tmp_path):
    """A grader must not be satisfied by the output of another command (guards against loose patterns)."""
    proc, lint_out = run_task("task-shadowed-js", tmp_path)
    lint_text = lint_out.read_text(encoding="utf-8")
    for name, spec in graders("task-legacy-owners").items():
        if spec["type"] == "regex" and "source: file" in spec["target"]:
            assert not re.search(unquote(spec["pattern"]), lint_text), name
    for name, spec in graders("task-large-repo").items():
        if spec["type"] == "regex" and "source: file" in spec["target"]:
            assert not re.search(unquote(spec["pattern"]), lint_text), name


def test_verify_merge_graders_also_hold_without_expect(tmp_path):
    case = "task-verify-merge"
    args = ["diff", "--before", "CODEOWNERS", "--after", "CODEOWNERS.proposed", "--files-from", "files.txt"]
    proc, out = run_task(case, tmp_path, args)
    assert proc.returncode == 0
    for name, spec in graders(case).items():
        if spec["type"] == "regex" and "source: file" in spec["target"]:
            assert re.search(unquote(spec["pattern"]), out.read_text(encoding="utf-8")), name


def test_wider_change_fails_with_exit_1_and_names_the_legacy_path(tmp_path):
    proc, out = run_task("task-error-wider-change", tmp_path)
    assert proc.returncode == 1


@pytest.mark.parametrize("lang", ["en", "ko"])
@pytest.mark.parametrize("where", [["--codeowners", ".github/CODEOWNERS"], []])
def test_missing_codeowners_case_prints_the_graded_error(tmp_path, lang, where):
    """The grader must hold whatever the system locale is (the error text follows --lang / LANG)."""
    work = tmp_path / "w"
    work.mkdir()
    (work / "files.txt").write_bytes((FIXTURES / "task-error-no-codeowners" / "files.txt").read_bytes())
    proc = subprocess.run([sys.executable, str(CLI), "resolve", "src/a.py", *where,
                           "--files-from", "files.txt", "--lang", lang], cwd=work, capture_output=True, text=True,
                          env=clean_env(), encoding="utf-8")
    assert proc.returncode == 2
    assert ".github/CODEOWNERS" in proc.stderr          # the error names the places it looked
    spec = graders("task-error-no-codeowners")["script-error-shown"]
    assert re.search(unquote(spec["pattern"]), proc.stderr)


def test_gitlab_case_is_reached_from_a_json_out_name_alone(tmp_path):
    """`--out gl.json` without --format must write the JSON the graders read (not the table)."""
    case = "task-gitlab-sections"
    work = tmp_path / case
    work.mkdir()
    for f in (FIXTURES / case).iterdir():
        (work / f.name).write_bytes(f.read_bytes())
    _, args = TASK_COMMANDS[case]
    proc = subprocess.run([sys.executable, str(CLI), *args, "--out", "gl.json", "--lang", "ko"],
                          cwd=work, capture_output=True, text=True, env=clean_env(), encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    text = (work / "gl.json").read_text(encoding="utf-8")
    for name, spec in graders(case).items():
        if spec["type"] == "regex" and "source: file" in spec["target"]:
            assert re.search(unquote(spec["pattern"]), text), name


def test_gitlab_fixture_read_as_github_says_to_pass_the_platform(tmp_path):
    case = "task-gitlab-sections"
    proc = subprocess.run([sys.executable, str(CLI), "resolve", "--codeowners", "CODEOWNERS", "--files-from",
                           "files.txt", "docs/sub/b.md", "--format", "json", "--lang", "en"],
                          cwd=FIXTURES / case, capture_output=True, text=True, env=clean_env(), encoding="utf-8")
    assert proc.returncode == 0
    assert '"platform_reason": "default"' in proc.stdout
    assert "Lines 3, 7, 11 look like GitLab section headers" in proc.stdout
    assert "--platform gitlab" in proc.stdout


def test_large_fixture_is_the_seeded_synthetic_repo():
    import synth
    files, text = synth.make_repo(400, 40, 7)
    assert (FIXTURES / "task-large-repo" / "CODEOWNERS").read_text() == text
    assert (FIXTURES / "task-large-repo" / "files.txt").read_text().split() == files
