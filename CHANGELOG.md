# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-18

### Added
- `resolve`, `explain`, `lint` and `diff` commands in `skills/codeowners-check/scripts/codeowners_check.py` (offline, standard library only).
- GitHub dialect: a file above 3 MB is not applied (no rule matches, with a note), last match wins, skipped lines (`!`, `[ ]`, `\#`, malformed owners), ownerless lines that clear ownership, file location order and the 3 MB limit.
- GitLab dialect: sections, optional sections, approval counts, header owners, `!` exclusions and Ruby `fnmatch` style patterns.
- Findings for skipped lines, dead and shadowed rules, duplicate patterns, rules that are ineffective after an exclusion, files without an owner and several CODEOWNERS files.
- Ownership diff with `--expect` and `--expect-none` and exit codes 0, 1 and 2.
- `--out FILE` saves the result; a `.json` name writes the JSON report unless `--format table` is given.
- A note when a file read as GitHub (platform picked automatically) has GitLab section headers.
- English and Korean output, including argparse headings, `-h` text and parse errors under `--lang ko` (`--lang`, `CODEOWNERS_CHECK_LANG`, `LC_ALL`, `LC_MESSAGES`, `LANG`) and deterministic JSON output.
- Evaluation set for skill triggering and task results.
