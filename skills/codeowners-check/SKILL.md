---
name: codeowners-check
description: Resolves and verifies CODEOWNERS files the way GitHub and GitLab read them, with a bundled standard-library script - the owner and deciding line number of every file, lines the platform silently skips (gitignore syntax it does not support), dead and shadowed rules, files without an owner, GitLab sections and exclusions, and a before/after ownership diff that fails when paths outside the intended area change owners. Use when someone asks who owns a file or why a reviewer is not requested, edits, splits or cleans up CODEOWNERS or code owner rules, wants to confirm that a CODEOWNERS change only affects certain paths, asks which GitLab section needs approval, or writes about CODEOWNERS 수정 확인, 리뷰어 자동 배정, 코드 담당자 규칙. Not for branch protection settings, checking that an owner account or team exists, .gitignore or other ignore files, or ownership from git history.
license: MIT
compatibility: Python 3.10+ (standard library only). No network access.
---

# codeowners-check - what a CODEOWNERS file really does

CODEOWNERS looks like .gitignore but is not. A model that reads it by hand gets the platform rules wrong: GitHub uses only the last matching line, silently skips lines that use `!`, `[a-z]` or `\#`, and `docs/*` does not reach `docs/a/b.md`; GitLab has sections, approvals, `!` exclusions and a different `/**`. The script evaluates every file against every rule, so use its numbers and line numbers as printed.

Run everything as `python3 scripts/codeowners_check.py <command> ...` (the path is relative to this skill's folder). Add `--format json` and read the JSON. Messages follow the system locale, so pass `--lang en` or `--lang ko` to match the language you answer in.

Always run the script, even when the CODEOWNERS file looks missing or you think you can read the answer yourself: its output (or its error line) is the answer to report.

## Save results to a file

When the user asks to save, export or hand over a result, let the script write it: add `--out NAME.json` to the same command (a `.json` name writes the JSON report; it is the same text as `--format json`). Do not hand-write, summarise, reorder or pretty-print that file, and do not build your own JSON from the table; tools and reviewers compare the script's fields as printed. Then answer in prose from the same result.

## Set up the inputs

1. Pick the platform: `--platform github` or `--platform gitlab`. If the user says the repo is on GitLab, or the file has section headers such as `[Docs]` or `^[Ruby][2]`, pass `--platform gitlab`; with `auto` (the default) a CODEOWNERS file in the root is read as GitHub. `auto` decides from where the file lives (`.github/`, `.gitlab/` or a `.gitlab-ci.yml` in the root) and prints the reason as `platform_reason`; when it picks GitHub for a file with GitLab headers, a note says so - run again with `--platform gitlab`.
2. Give the file list. In a git repo use the tracked files: `git ls-files | python3 scripts/codeowners_check.py lint --files-from -`. Otherwise pass `--files-from files.txt` (one path per line) or `--root DIR` to walk the folder (it skips `.git`, but includes untracked and ignored files).
3. The CODEOWNERS file is found in `--root` (GitHub: `.github/`, root, `docs/`; GitLab: root, `docs/`, `.gitlab/`) or passed with `--codeowners PATH`.

## Who owns a file, and why is no reviewer requested

1. `resolve PATH [PATH ...]` gives the owners and the deciding line (`line`, `pattern`) for those paths; without paths it resolves the whole list. `status` is `owned`, `no-rule` (nothing matched) or `cleared` (the last match lists no owner, which removes ownership on purpose).
2. `explain PATH` lists every matching line, the winner, lines that are skipped but would match if read like .gitignore (`ignored_but_relevant`) and `hints` with the fix (for example `docs/*` does not cover subfolders: use `docs/` or `docs/**`).
3. Answer with the owner, the line number and the reason. Do not say a path is excluded just because a `!` line exists; check `ignored_lines`.

## Edit CODEOWNERS and prove the edit

1. Before editing, copy the file (`cp CODEOWNERS /tmp/CODEOWNERS.before`) or keep the old text; run `lint` on it to see existing findings.
2. Edit the file. To give a path extra owners put them on the same line: a second line with the same pattern replaces the first line's owners. To carve out an exception on GitHub put a more specific line below the general one (an ownerless line clears ownership); do not use `!`.
3. Run `lint` on the new file and fix every `error`. Review each `warning`: `shadowed-rule` and `duplicate-pattern` usually mean a line that never takes effect; `dead-rule` means no listed file matches.
4. Run `diff --before OLD --after NEW --expect PATTERN ...` with the area you meant to change (GitHub pattern syntax, repeatable). It exits 1 when a path outside `--expect` changes owners (`unexpected`), when an `--expect` pattern changed nothing (`ineffective_expect`), or when the new file has an `error` the old one did not (`new_errors`). For a pure clean-up that must change nothing use `--expect-none`. `line_only` lists paths with the same owners but another deciding rule.
5. Report the changed paths, the deciding line numbers and the exit code. If the diff fails, fix the edit and run it again; do not explain the failure away.

## GitLab sections

Run `resolve --platform gitlab PATH ...` (add `--out NAME.json` when a file is wanted). It gives one entry per matching section for each file: `name`, `optional`, `approvals`, `owners`, `line`, `pattern`, `excluded`. Read it like this:

- A section needs approval for the path when its entry has `excluded: false`, `optional: false` and owners; `approvals` is how many. `(default)` is the part before the first header.
- `optional: true` (a `^[Section]` header) is listed but does not block the merge.
- `excluded: true` means a `!pattern` line (shown in `line` and `pattern`) exempts the path from that section: that section does not apply, even if a later line in it matches. A section with no entry for the path does not apply either.
- Inside one section the last matching line wins; the owners of different sections add up.

Answer per path with each section, its owners, the approval count and the deciding line. Section names merge case-insensitively and a section that is optional in one place and required in another is required. A `!pattern` exempts matching files from that section for good: a later line cannot bring them back (`ineffective-after-exclusion`). A trailing `/**` covers one level; use `/dir/` for everything below.

## Findings and exit codes

- `lint` finding codes: `unsupported-syntax`, `invalid-owner`, `invalid-section-header`, `invalid-pattern`, `file-too-large` (errors); `dead-rule`, `shadowed-rule`, `duplicate-pattern`, `ineffective-after-exclusion`, `multiple-codeowners-files` (warnings); `unowned-file`, `section-merged` (info). Each has `line`, `pattern` and a `message`. Exit 1 when a finding at or above `--fail-on` (default `warning`) exists.
- Exit codes for every command: 0 ok, 1 check failed, 2 input error.
- If the script exits with an error (exit 2), quote its error line as is: it already says how to fix the input (missing file, empty file list, missing `--before` or `--after`). For `CODEOWNERS file not found (looked in: ...)`, tell the user the file was not found, list the places it looked, and ask for the right path (`--codeowners PATH`) or repository folder (`--root DIR`). Do not guess owners from the file list, from other files or from memory.
- Differences between the two platforms and the JSON fields are in `references/syntax.md`; read it only when a result surprises you.

## What this does not check

Whether an owner account or team exists or can review, branch protection, and the real server-side assignment are not checked (the script is offline). GitLab behaviour comes from its documentation, not from a GitLab server. Say so when the answer depends on it.
