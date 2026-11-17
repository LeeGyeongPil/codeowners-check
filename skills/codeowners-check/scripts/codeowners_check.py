#!/usr/bin/env python3
"""Resolve and verify CODEOWNERS the way GitHub or GitLab reads it.

Commands: resolve, explain, lint, diff. Offline, standard library only. See --help.
Exit codes: 0 ok, 1 check failed, 2 input error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _co_analysis as an  # noqa: E402
from _co_i18n import LANGS, resolve_lang, translator  # noqa: E402

FAIL_ORDER = {"error": 0, "warning": 1, "info": 2}


# ---------------------------------------------------------------- tables

def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def table(headers: list[str], rows: list[list[object]]) -> str:
    """Plain aligned text table (wide characters count as two columns)."""
    cells = [[str(c) for c in r] for r in rows]
    widths = [max(_width(h), *(_width(r[i]) for r in cells)) if cells else _width(h) for i, h in enumerate(headers)]

    def fmt(row: list[str]) -> str:
        return "  ".join(c + " " * (widths[i] - _width(c)) for i, c in enumerate(row)).rstrip()

    return "\n".join([fmt(headers), fmt(["-" * w for w in widths])] + [fmt(r) for r in cells])


def owners_text(owners: list[str], tr) -> str:
    return " ".join(owners) if owners else "-"


def sections_text(sections: list[dict], tr) -> str:
    parts = []
    for s in sections:
        if s["excluded"]:
            parts.append(f"{s['name']}: {tr('col.excluded').lower()} (L{s['line']})")
        else:
            opt = "^" if s["optional"] else ""
            parts.append(f"{opt}{s['name']}[{s['approvals']}]: {' '.join(s['owners']) or '-'} (L{s['line']})")
    return "; ".join(parts) or "-"


def header_block(r: dict, tr) -> list[str]:
    out = [f"{tr('label.platform')}: {r['platform']} ({tr('label.reason')}: {r['platform_reason']})"]
    if "codeowners" in r:
        out.append(f"{tr('label.codeowners')}: {r['codeowners']}")
    return out


def notes_block(r: dict, tr) -> list[str]:
    return ["", f"{tr('label.notes')}:"] + [f"  - {n}" for n in r.get("notes", [])]


def render_resolve(r: dict, tr) -> str:
    lines = header_block(r, tr) + [f"{tr('label.files')}: {r['files_total']}", ""]
    if r["platform"] == "github":
        rows = [[f["path"], owners_text(f["owners"], tr), f["line"] if f["line"] is not None else "-",
                 f["pattern"] or "-", tr("status." + f["status"])] for f in r["files"]]
        lines.append(table([tr("col.path"), tr("col.owners"), tr("col.line"), tr("col.pattern"), tr("col.status")], rows))
    else:
        rows = [[f["path"], tr("status." + f["status"]), sections_text(f["sections"], tr)] for f in r["files"]]
        lines.append(table([tr("col.path"), tr("col.status"), tr("col.section")], rows))
        lines += ["", f"{tr('label.sections')}:"]
        lines.append(table([tr("col.section"), tr("col.line"), tr("col.optional"), tr("col.approvals"), tr("col.owners")],
                           [[s["name"], ",".join(map(str, s["lines"])) or "-", tr("yes") if s["optional"] else tr("no"),
                             s["approvals"], owners_text(s["default_owners"], tr)] for s in r["sections"]]))
    if r["ignored_lines"]:
        lines += ["", f"{tr('label.ignored_lines')}:"]
        lines += [f"  {i['line']}: {i['pattern']}  ({i['code']}{': ' + i['args']['reason'] if 'reason' in i['args'] else ''})"
                  for i in r["ignored_lines"]]
    return "\n".join(lines + notes_block(r, tr))


def render_explain(r: dict, tr) -> str:
    lines = header_block(r, tr) + [f"{tr('col.path')}: {r['path']}"]
    if r["platform"] == "github":
        lines.append(f"{tr('col.owners')}: {owners_text(r['owners'], tr)}  [{tr('status.' + r['status'])}]")
    else:
        lines.append(f"{tr('col.status')}: {tr('status.' + r['status'])}; {sections_text(r['sections'], tr)}")
    lines += ["", f"{tr('label.matches')}:"]
    if r["matches"]:
        if r["platform"] == "github":
            rows = [[m["line"], m["pattern"], owners_text(m["owners"], tr), tr("yes") if m["winner"] else ""] for m in r["matches"]]
            lines.append(table([tr("col.line"), tr("col.pattern"), tr("col.owners"), tr("col.winner")], rows))
        else:
            rows = [[m["line"], m["pattern"], m["section"], owners_text(m["owners"], tr), m["effect"]] for m in r["matches"]]
            lines.append(table([tr("col.line"), tr("col.pattern"), tr("col.section"), tr("col.owners"), tr("col.effect")], rows))
    else:
        lines.append(f"  {tr('label.none')}")
    if r["hints"]:
        lines += ["", f"{tr('label.hints')}:"] + [f"  - {h['message']}" for h in r["hints"]]
    return "\n".join(lines + notes_block(r, tr))


def render_lint(r: dict, tr) -> str:
    c = r["counts"]
    lines = header_block(r, tr) + [f"{tr('label.files')}: {r['files_total']}",
                                   f"{tr('label.counts')}: error={c['error']} warning={c['warning']} info={c['info']}", ""]
    rows = [[f["severity"], f["code"], f["line"] if f["line"] is not None else "-", f["message"]] for f in r["findings"]]
    if rows:
        lines.append(table([tr("col.severity"), tr("col.code"), tr("col.line"), tr("col.message")], rows))
    else:
        lines.append(f"{tr('label.findings')}: {tr('label.none')}")
    for f in r["findings"]:
        if f["code"] == "unowned-file":
            lines += ["", f"{tr('label.unowned')} ({f['count']}):"]
            lines += [f"  {x['path']}  [{tr('status.' + x['status'])}]" for x in f["files"][:200]]
            if f["count"] > 200:
                lines.append(f"  ... {f['count'] - 200} more (use --format json for the full list)")
    return "\n".join(lines + notes_block(r, tr))


def _view_text(v: object, tr) -> str:
    if v and isinstance(v[0], dict):  # type: ignore[index]
        return "; ".join(f"{'^' if s['optional'] else ''}{s['name']}[{s['approvals']}]: {' '.join(s['owners']) or '-'}" for s in v)  # type: ignore[union-attr]
    return " ".join(v) if v else "-"  # type: ignore[arg-type]


def render_diff(r: dict, tr) -> str:
    lines = header_block(r, tr) + [f"{tr('col.before')}: {r['before']}", f"{tr('col.after')}: {r['after']}",
                                   f"{tr('label.files')}: {r['files_total']}   "
                                   f"{tr('label.changed')}: {r['changed_count']}   {tr('label.unchanged')}: {r['unchanged_count']}", ""]
    if r["changed"]:
        lines.append(table([tr("col.path"), tr("col.before"), tr("col.after")],
                           [[c["path"], _view_text(c["before"], tr), _view_text(c["after"], tr)] for c in r["changed"]]))
    else:
        lines.append(f"{tr('label.changed')}: {tr('label.none')}")
    for key in ("unexpected", "ineffective_expect"):
        if r[key]:
            lines += ["", f"{tr('label.' + key)}:"] + [f"  - {x}" for x in r[key]]
    if r["new_errors"]:
        lines += ["", f"{tr('label.new_errors')}:"] + [f"  - {f['message']}" for f in r["new_errors"]]
    if r["line_only"]:
        lines += ["", f"{tr('label.line_only')}:"] + [
            f"  - {x['path']}: {x['before_pattern']} -> {x['after_pattern']}" for x in r["line_only"][:100]]
    lines += ["", f"{tr('label.result')}: {tr('result.ok') if r['ok'] else tr('result.fail')}"]
    return "\n".join(lines + notes_block(r, tr))


RENDER = {"resolve": render_resolve, "explain": render_explain, "lint": render_lint, "diff": render_diff}


# ---------------------------------------------------------------- command line

def prescan_lang(argv: list[str]) -> str | None:
    """Find --lang before argparse runs, so that --help and argparse errors already use that language."""
    for i, a in enumerate(argv):
        if a == "--lang" and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith("--lang="):
            return a.split("=", 1)[1]
    return None


ARGPARSE_ERRORS = (
    (re.compile(r"^argument (.+?): invalid choice: (.+?) \(choose from (.*)\)$"), "argp.invalid_choice"),
    (re.compile(r"^argument (.+?): expected one argument$"), "argp.expected_one"),
    (re.compile(r"^argument (.+?): ignored explicit argument (.+)$"), "argp.ignored_explicit"),
    (re.compile(r"^unrecognized arguments: (.*)$"), "argp.unrecognized"),
    (re.compile(r"^the following arguments are required: (.*)$"), "argp.required"),
)


def translate_argparse_error(message: str, tr) -> str:
    """Map argparse's English error text to the selected language; unknown shapes pass through unchanged."""
    for pattern, key in ARGPARSE_ERRORS:
        m = pattern.match(message)
        if m:
            return tr(key, **dict(zip("abc", m.groups())))
    return message


def build_parser(tr) -> argparse.ArgumentParser:
    def usage_word(text: str) -> str:
        # argparse's "usage: " prefix is built differently across Python versions; translate the finished text
        return f"{tr('argp.usage')}: " + text[len("usage: "):] if text.startswith("usage: ") else text

    class Parser(argparse.ArgumentParser):
        def __init__(self, *a: object, **kw: object) -> None:
            kw["add_help"] = False
            super().__init__(*a, **kw)  # type: ignore[arg-type]
            # argparse's group titles and -h text are English; replace them with the selected language
            self._positionals.title = tr("argp.positionals")
            self._optionals.title = tr("argp.options")
            self.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS, help=tr("argp.help"))

        def format_usage(self) -> str:
            return usage_word(super().format_usage())

        def format_help(self) -> str:
            return usage_word(super().format_help())

        def error(self, message: str) -> None:  # type: ignore[override]
            self.print_usage(sys.stderr)
            print(f"{tr('err.prefix')}: {translate_argparse_error(message, tr)}", file=sys.stderr)
            raise SystemExit(2)

    def common(p: argparse.ArgumentParser, top: bool) -> None:
        sup = {} if top else {"default": argparse.SUPPRESS}
        p.add_argument("--platform", choices=["github", "gitlab", "auto"], default="auto", help=tr("help.platform"))
        p.add_argument("--codeowners", metavar="PATH", help=tr("help.codeowners"))
        p.add_argument("--root", metavar="DIR", default=".", help=tr("help.root"))
        p.add_argument("--files-from", metavar="FILE", help=tr("help.files_from"))
        p.add_argument("--format", choices=["json", "table"], default=None, help=tr("help.format"))
        p.add_argument("--out", metavar="FILE", help=tr("help.out"))
        p.add_argument("--lang", choices=list(LANGS), help=tr("help.lang"), **({} if top else sup))

    parser = Parser(prog="codeowners_check.py", description=tr("help.description"), epilog=tr("help.epilog"))
    parser.add_argument("--lang", choices=list(LANGS), help=tr("help.lang"))
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)

    p = sub.add_parser("resolve", help=tr("help.cmd.resolve"), description=tr("help.cmd.resolve"))
    common(p, False)
    p.add_argument("paths", nargs="*", metavar="PATH", help=tr("help.paths"))
    p = sub.add_parser("explain", help=tr("help.cmd.explain"), description=tr("help.cmd.explain"))
    common(p, False)
    p.add_argument("path", metavar="PATH", help=tr("help.path"))
    p = sub.add_parser("lint", help=tr("help.cmd.lint"), description=tr("help.cmd.lint"))
    common(p, False)
    p.add_argument("--fail-on", choices=["error", "warning", "never"], default="warning", help=tr("help.fail_on"))
    p = sub.add_parser("diff", help=tr("help.cmd.diff"), description=tr("help.cmd.diff"))
    common(p, False)
    p.add_argument("--before", metavar="FILE", help=tr("help.before"))
    p.add_argument("--after", metavar="FILE", help=tr("help.after"))
    p.add_argument("--expect", metavar="PATTERN", action="append", default=[], help=tr("help.expect"))
    p.add_argument("--expect-none", action="store_true", help=tr("help.expect_none"))
    return parser


def execute(args: argparse.Namespace, tr) -> tuple[dict, int]:
    root = Path(args.root)
    cmd = args.command
    if cmd == "diff":
        if not args.before or not args.after:
            raise an.CheckError("diff_args")
        files = an.collect_files(root, args.files_from)
        platform, reason, after_path, _ = an.locate(args.platform, args.after, root)
        before_path = an.locate(platform, args.before, root)[2]
        models = []
        for path in (before_path, after_path):
            text, size = an.read_codeowners(path)
            models.append(an.build_model(platform, text, size, {"reason": reason, "path": path.as_posix(), "others": []},
                                         files, tr))
        result = an.diff_models(models[0], models[1], args.expect, args.expect_none, tr)
        return result, 0 if result["ok"] else 1

    paths: list[str] | None = None
    files: list[str] = []
    listed: bool | None = None
    if cmd == "explain":
        paths = [an.normalize_path(args.path)]
        if args.files_from is not None:
            listed = paths[0] in an.collect_files(root, args.files_from)
    elif cmd == "resolve" and args.paths:
        paths = an.clean_paths(args.paths)
    else:
        files = an.collect_files(root, args.files_from)
    model = an.load_model(args.platform, args.codeowners, root, files, tr)
    if cmd == "resolve":
        return model.resolve(paths), 0
    if cmd == "explain":
        result = model.explain(paths[0], listed)  # type: ignore[index]
        if listed is False:
            result["notes"].append(tr("note.not_in_list"))
        return result, 0
    result = model.lint()
    if args.fail_on == "never":
        return result, 0
    limit = FAIL_ORDER[args.fail_on]
    failed = any(FAIL_ORDER[f["severity"]] <= limit for f in result["findings"])
    return result, 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    lang = resolve_lang(prescan_lang(argv))
    tr = translator(lang)
    args = build_parser(tr).parse_args(argv)
    try:
        result, code = execute(args, tr)
        # --format 을 주지 않았으면 표가 기본이지만, --out 이름이 .json 이면 JSON 으로 쓴다(표가 든 .json 파일 방지)
        fmt = args.format or ("json" if args.out and args.out.lower().endswith(".json") else "table")
        text = json.dumps(result, ensure_ascii=False) if fmt == "json" else RENDER[args.command](result, tr)
        if args.out:
            try:
                Path(args.out).write_text(text + "\n", encoding="utf-8")
            except OSError as e:
                raise an.CheckError("write_failed", path=args.out, reason=e.strerror or str(e))
    except an.CheckError as e:
        print(f"{tr('err.prefix')}: {tr('err.' + e.key, **e.args_)}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
