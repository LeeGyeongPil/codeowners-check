"""Shared helpers: run the real CLI as a separate process (like an agent does) and locate fixtures."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "codeowners-check" / "scripts"
CLI = SCRIPTS / "codeowners_check.py"
FIX = ROOT / "tests" / "fixtures"
GH = FIX / "github"
GL = FIX / "gitlab"
EVALS = ROOT / "evals"

LANG_VARS = ("LANG", "LC_ALL", "LC_MESSAGES", "CODEOWNERS_CHECK_LANG")


def clean_env(extra=None):
    env = {k: v for k, v in os.environ.items() if k not in LANG_VARS}
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(extra or {})
    return env


def run(*args, env=None, cwd=None, stdin=None):
    """Run the CLI; returns CompletedProcess with text output."""
    return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", env=clean_env(env), cwd=cwd, input=stdin)


def run_json(*args, **kw):
    proc = run(*args, "--format", "json", **kw)
    return proc, (json.loads(proc.stdout) if proc.stdout.strip() else None)


@pytest.fixture
def gh_args():
    return ["--codeowners", str(GH / "CODEOWNERS"), "--files-from", str(GH / "files.txt")]


@pytest.fixture
def gl_args():
    return ["--platform", "gitlab", "--codeowners", str(GL / "CODEOWNERS"), "--files-from", str(GL / "files.txt")]
