"""English and Korean messages and language selection (internal module).

Language order: --lang, then CODEOWNERS_CHECK_LANG, then LC_ALL, LC_MESSAGES, LANG (first non-empty value
decides); anything that does not start with "ko" is English. JSON field names and finding codes never change.
"""
from __future__ import annotations

import os
from typing import Callable, Mapping

LANGS = ("en", "ko")
ENV_ORDER = ("CODEOWNERS_CHECK_LANG", "LC_ALL", "LC_MESSAGES", "LANG")

EN: dict[str, str] = {
    # errors (printed as "error: ...", exit code 2)
    "err.prefix": "error",
    "err.not_found": "CODEOWNERS file not found (looked in: {places}). Pass --codeowners PATH or --root DIR.",
    "err.no_files": "no files to check (empty --files-from or --root). Pass --files-from FILE (for example git ls-files output) or a --root with files.",
    "err.diff_args": "--before and --after are required for diff",
    "err.unreadable": "cannot read {path}: {reason}",
    "err.files_from_unreadable": "cannot read the file list {path}: {reason}",
    "err.root_not_dir": "--root is not a folder: {path}",
    "err.write_failed": "cannot write {path}: {reason}",
    "err.bad_expect": "--expect pattern {pattern!r} is not valid; use a CODEOWNERS pattern such as 'docs/**' or '*.js' (no '!' or '[ ]')",
    # notes
    "note.offline": "Owner accounts, team existence and write access are not verified (offline check).",
    "note.invalid_owner_assumption": "Assumption: a line with a malformed owner is skipped as a whole (GitHub: 'that line will be skipped').",
    "note.gitlab_docs": "GitLab behaviour is reproduced from the documentation; no server was contacted (see gitlab-org/gitlab#585698).",
    "note.not_in_list": "The path is not in the file list; it was resolved anyway.",
    "note.gitlab_headers": "Lines {lines} look like GitLab section headers, which GitHub skips. If this repository is on GitLab, run again with --platform gitlab.",
    "note.too_large": "The file is {size} bytes, above the {limit}-byte limit: GitHub does not load it, so no rule applies and every path has no owner.",
    # findings
    "finding.unsupported-syntax.negation": "line {line}: '{pattern}' uses '!' negation, which GitHub does not support; the line is skipped.",
    "finding.unsupported-syntax.escaped-hash": "line {line}: '{pattern}' starts with '\\#', which GitHub does not support; the line is skipped.",
    "finding.unsupported-syntax.char-range": "line {line}: '{pattern}' uses '[ ]' character ranges, which GitHub does not support; the line is skipped.",
    "finding.invalid-owner": "line {line}: owner '{owner}' is not a valid @user, @org/team or email; the line is skipped.",
    "finding.invalid-section-header": "line {line}: '{pattern}' is not a valid section header ([Name], [Name][2], ^[Name]); the line is skipped.",
    "finding.invalid-pattern": "line {line}: '{pattern}' has no path after '!'; the line is skipped.",
    "finding.file-too-large": "the file is {size} bytes, above the {limit}-byte limit; GitHub does not load it.",
    "finding.dead-rule": "line {line}: '{pattern}' matches no file in the list.",
    "finding.shadowed-rule": "line {line}: '{pattern}' matches files, but later lines ({by_lines}) always win, so it never decides an owner.",
    "finding.duplicate-pattern": "line {line}: '{pattern}' repeats line {first_line}; only the last line counts, so earlier owners are dropped.",
    "finding.ineffective-after-exclusion": "line {line}: '{pattern}' only matches files already excluded earlier in section {section}; it has no effect.",
    "finding.multiple-codeowners-files": "several CODEOWNERS files exist; {used} is used and {ignored} is ignored.",
    "finding.unowned-file": "{count} file(s) have no owner.",
    "finding.section-merged": "line {line}: section {name} appears more than once (lines {lines}); the sections are merged.",
    # hints
    "hint.no-rule": "No rule matches this path, so nobody is requested for review.",
    "hint.cleared": "Line {line} ('{pattern}') matches but lists no owner, which clears ownership for this path.",
    "hint.later-wins": "Line {line} ('{pattern}') decides; the earlier matching lines {lines} are overridden.",
    "hint.star-not-recursive": "Line {line} ('{pattern}') does not reach this path: a trailing '/*' covers only files directly inside the folder, not its subfolders. Use '{folder}' or '{recursive}'.",
    "hint.ignored-line": "Line {line} ('{pattern}') would match if read like .gitignore, but it is skipped ({reason}).",
    "hint.excluded-first": "Line {line} ('{pattern}') has no effect for this path: the exclusion on line {line2} removed it from the section.",
    "hint.double-star-one-level": "Line {line} ('{pattern}') does not reach this path: a trailing '/**' covers one level only. Use '{folder}/' for everything below.",
    # table labels
    "col.path": "PATH", "col.owners": "OWNERS", "col.line": "LINE", "col.pattern": "PATTERN", "col.status": "STATUS",
    "col.section": "SECTION", "col.optional": "OPTIONAL", "col.approvals": "APPROVALS", "col.excluded": "EXCLUDED",
    "col.severity": "SEVERITY", "col.code": "CODE", "col.message": "MESSAGE", "col.before": "BEFORE", "col.after": "AFTER",
    "col.winner": "WINNER", "col.effect": "EFFECT",
    "label.platform": "platform", "label.codeowners": "CODEOWNERS", "label.files": "files",
    "label.ignored_lines": "skipped lines", "label.findings": "findings", "label.counts": "counts",
    "label.changed": "changed paths", "label.unexpected": "changed outside --expect",
    "label.ineffective_expect": "--expect patterns that matched no changed path", "label.new_errors": "new errors in the after file",
    "label.line_only": "same owners, different deciding rule", "label.result": "result", "label.matches": "matching lines",
    "label.hints": "hints", "label.sections": "sections", "label.none": "(none)", "label.unowned": "files without an owner",
    "label.notes": "notes", "label.unchanged": "unchanged", "label.reason": "reason",
    "result.ok": "OK", "result.fail": "FAILED",
    "yes": "yes", "no": "no",
    "status.owned": "owned", "status.no-rule": "no rule", "status.cleared": "cleared", "status.no-owner": "no owner",
    "status.excluded": "excluded",
    # argparse wording (headings, -h text, parse errors); a, b, c are the captured parts of argparse's message
    "argp.usage": "usage", "argp.positionals": "positional arguments", "argp.options": "options",
    "argp.help": "show this help message and exit",
    "argp.invalid_choice": "argument {a}: invalid choice: {b} (choose from {c})",
    "argp.expected_one": "argument {a}: expected one argument",
    "argp.ignored_explicit": "argument {a}: ignored explicit argument {b}",
    "argp.unrecognized": "unrecognized arguments: {a}",
    "argp.required": "the following arguments are required: {a}",
    # help
    "help.description": "Resolve and verify CODEOWNERS the way GitHub or GitLab reads it: owner and deciding line per file, ignored and dead rules, and a before/after ownership diff. Offline, standard library only.",
    "help.epilog": "Exit codes: 0 ok, 1 check failed (lint findings at or above --fail-on, diff outside --expect), 2 input error.",
    "help.cmd.resolve": "owner and deciding line for every file (or the given PATHs)",
    "help.cmd.explain": "every line that matches one PATH, which one wins, and how to fix it",
    "help.cmd.lint": "skipped lines, dead and shadowed rules, duplicates, files without an owner",
    "help.cmd.diff": "compare ownership before and after an edit; fail when paths outside --expect change",
    "help.platform": "dialect: github, gitlab, or auto (decided from the CODEOWNERS location; default auto)",
    "help.codeowners": "CODEOWNERS file (default: searched in --root in the platform's location order)",
    "help.root": "repository folder: file list source and CODEOWNERS search base (default: current folder)",
    "help.files_from": "file with one repo-relative path per line (git ls-files output), '-' for standard input",
    "help.format": "output format: json or table (default table; json when --out ends with .json)",
    "help.out": "also write the result to this file (a .json name writes JSON unless --format table is given)",
    "help.lang": "output language: en or ko (default: CODEOWNERS_CHECK_LANG, LC_ALL, LC_MESSAGES, LANG, else en)",
    "help.paths": "repo-relative paths to resolve (default: every file in the list)",
    "help.path": "repo-relative path to explain",
    "help.fail_on": "lowest severity that makes lint exit 1: error, warning (default) or never",
    "help.before": "CODEOWNERS file before the edit",
    "help.after": "CODEOWNERS file after the edit",
    "help.expect": "CODEOWNERS-style pattern the edit is allowed to change (repeatable, GitHub pattern syntax)",
    "help.expect_none": "treat every changed path as unexpected (use for pure clean-ups)",
}

KO: dict[str, str] = {
    "err.prefix": "오류",
    "err.not_found": "CODEOWNERS 파일을 찾을 수 없습니다 (찾아본 곳: {places}). --codeowners 경로나 --root 폴더를 지정하세요.",
    "err.no_files": "검사할 파일이 없습니다 (--files-from 또는 --root 가 비어 있음). --files-from 에 git ls-files 출력 파일을 주거나 파일이 있는 --root 를 지정하세요.",
    "err.diff_args": "diff 에는 --before 와 --after 가 모두 필요합니다",
    "err.unreadable": "{path} 을(를) 읽을 수 없습니다: {reason}",
    "err.files_from_unreadable": "파일 목록 {path} 을(를) 읽을 수 없습니다: {reason}",
    "err.root_not_dir": "--root 가 폴더가 아닙니다: {path}",
    "err.write_failed": "{path} 에 쓸 수 없습니다: {reason}",
    "err.bad_expect": "--expect 패턴 {pattern!r} 이(가) 올바르지 않습니다. 'docs/**', '*.js' 같은 CODEOWNERS 패턴을 쓰세요 ('!', '[ ]' 불가)",
    "note.offline": "담당자 계정·팀 존재·쓰기 권한은 확인하지 않습니다(오프라인 검사).",
    "note.invalid_owner_assumption": "가정: 형식이 틀린 담당자가 있는 줄은 통째로 건너뜁니다(GitHub 문서: 'that line will be skipped').",
    "note.gitlab_docs": "GitLab 동작은 문서 기준으로 재현했으며 서버에 연결하지 않았습니다(gitlab-org/gitlab#585698 참고).",
    "note.not_in_list": "이 경로는 파일 목록에 없지만 그래도 해석했습니다.",
    "note.gitlab_headers": "{lines}행은 GitLab 섹션 머리줄처럼 보이며 GitHub 는 이 줄을 건너뜁니다. GitLab 저장소라면 --platform gitlab 으로 다시 실행하세요.",
    "note.too_large": "파일이 {size} 바이트로 한도 {limit} 바이트를 넘습니다. GitHub 는 이 파일을 불러오지 않으므로 어떤 규칙도 적용되지 않고 모든 경로에 담당자가 없습니다.",
    "finding.unsupported-syntax.negation": "{line}행: '{pattern}' 은(는) '!' 부정을 쓰는데 GitHub 가 지원하지 않아 이 줄은 건너뜁니다.",
    "finding.unsupported-syntax.escaped-hash": "{line}행: '{pattern}' 은(는) '\\#' 로 시작하는데 GitHub 가 지원하지 않아 이 줄은 건너뜁니다.",
    "finding.unsupported-syntax.char-range": "{line}행: '{pattern}' 은(는) '[ ]' 문자 범위를 쓰는데 GitHub 가 지원하지 않아 이 줄은 건너뜁니다.",
    "finding.invalid-owner": "{line}행: 담당자 '{owner}' 이(가) 올바른 @사용자, @조직/팀, 이메일이 아니어서 이 줄은 건너뜁니다.",
    "finding.invalid-section-header": "{line}행: '{pattern}' 은(는) 올바른 섹션 헤더([이름], [이름][2], ^[이름])가 아니어서 이 줄은 건너뜁니다.",
    "finding.invalid-pattern": "{line}행: '{pattern}' 은(는) '!' 뒤에 경로가 없어 이 줄은 건너뜁니다.",
    "finding.file-too-large": "파일이 {size} 바이트로 한도 {limit} 바이트를 넘어 GitHub 가 불러오지 않습니다.",
    "finding.dead-rule": "{line}행: '{pattern}' 은(는) 목록의 어떤 파일과도 일치하지 않습니다.",
    "finding.shadowed-rule": "{line}행: '{pattern}' 은(는) 파일과 일치하지만 뒤의 줄({by_lines})이 항상 이겨서 담당을 정하지 못합니다.",
    "finding.duplicate-pattern": "{line}행: '{pattern}' 은(는) {first_line}행과 같은 패턴입니다. 마지막 줄만 적용되므로 앞 담당자는 사라집니다.",
    "finding.ineffective-after-exclusion": "{line}행: '{pattern}' 은(는) {section} 섹션에서 앞서 제외된 파일에만 일치해 효과가 없습니다.",
    "finding.multiple-codeowners-files": "CODEOWNERS 파일이 여러 개입니다. {used} 을(를) 쓰고 {ignored} 은(는) 무시됩니다.",
    "finding.unowned-file": "담당자가 없는 파일이 {count}개 있습니다.",
    "finding.section-merged": "{line}행: 섹션 {name} 이(가) 여러 번 나옵니다(줄 {lines}). 하나로 합쳐집니다.",
    "hint.no-rule": "이 경로와 일치하는 규칙이 없어 리뷰어가 지정되지 않습니다.",
    "hint.cleared": "{line}행('{pattern}')이 일치하지만 담당자가 비어 있어 이 경로의 담당이 지워집니다.",
    "hint.later-wins": "{line}행('{pattern}')이 결정합니다. 앞서 일치한 {lines}행은 덮어써집니다.",
    "hint.star-not-recursive": "{line}행('{pattern}')은 이 경로에 닿지 않습니다: 끝의 '/*' 는 그 폴더 바로 아래 파일만 덮고 하위 폴더는 덮지 않습니다. '{folder}' 또는 '{recursive}' 를 쓰세요.",
    "hint.ignored-line": "{line}행('{pattern}')은 .gitignore 식으로 읽으면 일치하지만 건너뛰어집니다({reason}).",
    "hint.excluded-first": "{line}행('{pattern}')은 이 경로에 효과가 없습니다: {line2}행의 제외가 이미 섹션에서 뺐습니다.",
    "hint.double-star-one-level": "{line}행('{pattern}')은 이 경로에 닿지 않습니다: 끝의 '/**' 는 한 단계만 덮습니다. 하위 전체는 '{folder}/' 를 쓰세요.",
    "col.path": "경로", "col.owners": "담당자", "col.line": "줄", "col.pattern": "패턴", "col.status": "상태",
    "col.section": "섹션", "col.optional": "선택", "col.approvals": "승인 수", "col.excluded": "제외",
    "col.severity": "심각도", "col.code": "코드", "col.message": "설명", "col.before": "수정 전", "col.after": "수정 후",
    "col.winner": "결정", "col.effect": "효과",
    "label.platform": "플랫폼", "label.codeowners": "CODEOWNERS", "label.files": "파일 수",
    "label.ignored_lines": "건너뛴 줄", "label.findings": "진단", "label.counts": "개수",
    "label.changed": "담당이 바뀐 경로", "label.unexpected": "--expect 밖에서 바뀐 경로",
    "label.ineffective_expect": "바뀐 경로와 일치하지 않은 --expect 패턴", "label.new_errors": "수정 후 파일에 새로 생긴 오류",
    "label.line_only": "담당자는 같고 결정 규칙만 바뀐 경로", "label.result": "결과", "label.matches": "일치한 줄",
    "label.hints": "힌트", "label.sections": "섹션", "label.none": "(없음)", "label.unowned": "담당자 없는 파일",
    "label.notes": "참고", "label.unchanged": "변화 없음", "label.reason": "이유",
    "result.ok": "통과", "result.fail": "실패",
    "yes": "예", "no": "아니오",
    "status.owned": "담당 있음", "status.no-rule": "규칙 없음", "status.cleared": "담당 지움", "status.no-owner": "담당자 없음",
    "status.excluded": "제외됨",
    "argp.usage": "사용법", "argp.positionals": "위치 인자", "argp.options": "옵션",
    "argp.help": "이 도움말을 보여 주고 종료합니다",
    "argp.invalid_choice": "인자 {a}: 잘못된 선택 {b} (선택 가능: {c})",
    "argp.expected_one": "인자 {a}: 값이 하나 필요합니다",
    "argp.ignored_explicit": "인자 {a}: 명시한 값 {b} 은(는) 사용되지 않습니다",
    "argp.unrecognized": "알 수 없는 인자: {a}",
    "argp.required": "다음 인자가 필요합니다: {a}",
    "help.description": "GitHub·GitLab 이 읽는 방식 그대로 CODEOWNERS 를 해석하고 검증합니다: 파일별 담당자와 결정한 줄, 무시되거나 죽은 규칙, 수정 전후 담당 변화 비교. 오프라인, 표준 라이브러리만 사용.",
    "help.epilog": "종료 코드: 0 통과, 1 검사 실패(--fail-on 이상의 lint 진단, --expect 밖의 diff 변화), 2 입력 오류.",
    "help.cmd.resolve": "모든 파일(또는 지정한 PATH)의 담당자와 결정한 줄",
    "help.cmd.explain": "PATH 하나에 일치한 모든 줄, 이기는 줄, 고치는 방향",
    "help.cmd.lint": "건너뛰는 줄, 죽은·가려진 규칙, 중복, 담당자 없는 파일",
    "help.cmd.diff": "수정 전후 담당을 비교하고 --expect 밖 경로가 바뀌면 실패",
    "help.platform": "방언: github, gitlab, auto (CODEOWNERS 위치로 결정, 기본 auto)",
    "help.codeowners": "CODEOWNERS 파일 (생략하면 --root 에서 플랫폼의 위치 순서로 찾음)",
    "help.root": "저장소 폴더: 파일 목록과 CODEOWNERS 탐색 기준 (기본: 현재 폴더)",
    "help.files_from": "한 줄에 경로 하나(git ls-files 출력)인 파일, '-' 는 표준 입력",
    "help.format": "출력 형식: json 또는 table (기본 table, --out 이 .json 으로 끝나면 json)",
    "help.out": "결과를 이 파일에도 저장 (.json 이름이면 --format table 을 주지 않는 한 JSON 으로 저장)",
    "help.lang": "출력 언어: en 또는 ko (기본: CODEOWNERS_CHECK_LANG, LC_ALL, LC_MESSAGES, LANG, 그 외 en)",
    "help.paths": "해석할 저장소 기준 경로 (생략하면 목록의 모든 파일)",
    "help.path": "설명을 볼 저장소 기준 경로",
    "help.fail_on": "lint 가 종료 코드 1 을 내는 최저 심각도: error, warning(기본), never",
    "help.before": "수정 전 CODEOWNERS 파일",
    "help.after": "수정 후 CODEOWNERS 파일",
    "help.expect": "이 수정이 바꿔도 되는 CODEOWNERS 식 패턴 (여러 번 가능, GitHub 패턴 문법)",
    "help.expect_none": "바뀐 경로를 모두 의도 밖으로 취급 (순수 정리용)",
}

MESSAGES: dict[str, dict[str, str]] = {"en": EN, "ko": KO}


def resolve_lang(cli_value: str | None, env: Mapping[str, str] | None = None) -> str:
    """--lang > CODEOWNERS_CHECK_LANG > LC_ALL > LC_MESSAGES > LANG; non-Korean falls back to English."""
    if cli_value in LANGS:
        return cli_value  # type: ignore[return-value]
    env = os.environ if env is None else env
    for name in ENV_ORDER:
        value = (env.get(name) or "").strip()
        if value:
            return "ko" if value.lower().startswith("ko") else "en"
    return "en"


def _fmt(v: object) -> object:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) or "-"
    return "-" if v is None else v


def translator(lang: str) -> Callable[..., str]:
    """Return tr(key, **args) for a language; unknown keys come back as the key itself."""
    table = MESSAGES[lang]

    def tr(key: str, **args: object) -> str:
        template = table.get(key)
        if template is None:
            return key
        return template.format(**{k: _fmt(v) for k, v in args.items()})

    return tr
