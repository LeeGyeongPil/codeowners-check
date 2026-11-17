# CODEOWNERS semantics and JSON reference

## Contents

- GitHub and GitLab side by side
- Pattern behaviour (GitHub)
- Status values and JSON fields
- Sources

## GitHub and GitLab side by side

| Topic | GitHub | GitLab |
|---|---|---|
| Which line decides | the last matching line | the last matching line per section |
| File locations (first found is used) | `.github/CODEOWNERS`, `CODEOWNERS`, `docs/CODEOWNERS` | `CODEOWNERS`, `docs/CODEOWNERS`, `.gitlab/CODEOWNERS` |
| Sections, approvals, `^[Optional]`, header owners | not supported | `[Name]`, `[Name][2]`, `^[Name]`, `[Name] @owner`; names are case-insensitive and merged |
| `!pattern` | not supported, the line is skipped | exempts matching files from that section; cannot be undone later in the section |
| `[a-z]` ranges | not supported, the line is skipped | supported (Ruby fnmatch) |
| `{a,b}` | literal text | literal text |
| Pattern without a leading `/` | matches at any depth only if it has no other `/` | always matches at any depth |
| `dir/` | everything below `dir`, at any depth | everything below `dir`, at any depth |
| `dir/*` | files directly in `dir` only | files directly in `dir` only |
| `dir/**` | everything below `dir` | one level only (use `dir/` or `dir/**/*`) |
| Ownerless line | clears ownership for matching paths | has no effect unless the section has header owners |
| Size limit | 3 MB, larger files are not loaded (the script then applies no rule and notes it) | none documented |
| Path case | case-sensitive | case-sensitive |

Both platforms need an owner to be a user, a team or an email; this script treats a line with a malformed owner as skipped (an assumption taken from the GitHub text "that line will be skipped").

## Pattern behaviour (GitHub)

| Pattern | Matches | Does not match |
|---|---|---|
| `docs` | `docs`, `x/docs/y` | `docsx` |
| `docs/` | `docs/a`, `x/docs/a` | the file `docs` |
| `/apps/` | `apps/a/b` | `x/apps/a` |
| `docs/*` | `docs/a` | `docs/a/b` |
| `**/logs` | `logs/x`, `a/b/logs/y` | `logsx/z` |
| `a/**/b` | `a/b`, `a/x/y/b` | `b` |
| `*.js` | `web/app.js`, `a/b/c.js` | `app.jsx` |
| `my\ file.txt` | `my file.txt` | `my_file.txt` |

`--expect` patterns always use this GitHub pattern syntax, also for GitLab files.

## Status values and JSON fields

- `resolve` (GitHub): `files[]` with `path`, `owners`, `line`, `pattern`, `status` (`owned`, `no-rule`, `cleared`); plus `ignored_lines[]` (`line`, `pattern`, `code`, `args`) and `notes[]`.
- `resolve` (GitLab): `files[]` with `path`, `status` (`owned`, `no-owner`, `no-rule`, `excluded`) and `sections[]` (`name`, `optional`, `approvals`, `owners`, `line`, `pattern`, `excluded`); plus the section table `sections[]` (`name`, `lines`, `optional`, `approvals`, `default_owners`, `merged_from`).
- `explain`: `matches[]` (`line`, `pattern`, `owners`, `winner`, and for GitLab `section`, `exclusion`, `effect`), `ignored_but_relevant[]`, `hints[]` (`code`, `line`, `message`), `in_file_list`.
- `lint`: `findings[]` (`code`, `severity`, `line`, `pattern`, `detail_key`, `args`, `message`; `unowned-file` also has `files[]` and `count`), `counts`, `files_total`.
- `diff`: `changed[]` (`path`, `before`, `after`), `changed_count`, `unchanged_count`, `line_only[]`, `expect`, `unexpected`, `ineffective_expect`, `new_errors`, `ok`.
- Every result has `platform` and `platform_reason` (`explicit`, `under-.github`, `under-.gitlab`, `gitlab-marker-in-root`, `default`).
- JSON key order is fixed and file lists are sorted, so the same input gives the same bytes. Only `message` and `notes` depend on `--lang`.

## Sources

- GitHub Docs, About code owners: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners (checked 2026-11-18)
- GitLab Docs, Code Owners syntax reference: https://docs.gitlab.com/user/project/codeowners/reference/ (checked 2026-11-18)
- Reported differences between the GitLab documentation and the server: https://gitlab.com/gitlab-org/gitlab/-/issues/585698
