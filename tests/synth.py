"""Seeded synthetic repository generator (file list + CODEOWNERS text). Deterministic for a given seed."""
import random

TOP = ["apps", "libs", "docs", "tools", "infra", "web", "services", "scripts", "data", "ops"]
MID = ["core", "api", "ui", "db", "auth", "utils", "jobs", "models", "views", "cli", "tests", "cfg"]
EXT = [".py", ".js", ".md", ".yml", ".json", ".go", ".sql", ".txt"]
TEAMS = ["@acme/core", "@acme/web", "@acme/data", "@acme/infra", "@acme/docs", "@acme/sec", "@acme/ml",
         "@acme/qa", "@alice", "@bob", "@carol", "@dave"]


def make_files(n_files, seed):
    rng = random.Random(seed)
    files = set()
    while len(files) < n_files:
        depth = rng.randint(1, 3)
        parts = [rng.choice(TOP)] + [rng.choice(MID) for _ in range(depth - 1)]
        files.add("/".join(parts + [f"f{rng.randint(0, 9999)}{rng.choice(EXT)}"]))
    return sorted(files)


def make_rules(n_rules, seed):
    """Rules are drawn from a pool of realistic shapes; later lines may shadow earlier ones, some never match."""
    rng = random.Random(seed + 1)
    lines = ["* @acme/core"]
    while len(lines) < n_rules:
        kind = rng.randint(0, 9)
        owners = " ".join(rng.sample(TEAMS, rng.choice([1, 1, 1, 2])))
        top, mid = rng.choice(TOP), rng.choice(MID)
        if kind <= 2:
            pat = f"/{top}/"
        elif kind == 3:
            pat = f"/{top}/{mid}/"
        elif kind == 4:
            pat = f"*{rng.choice(EXT)}"
        elif kind == 5:
            pat = f"**/{mid}"
        elif kind == 6:
            pat = f"{top}/*"
        elif kind == 7:
            pat = f"/{top}/**/{mid}/"
        elif kind == 8:
            pat = f"/{rng.choice(TOP)}x/"          # a folder that does not exist -> dead rule
        else:
            pat = f"/{top}/f{rng.randint(0, 9999)}{rng.choice(EXT)}"
        if rng.random() < 0.05:
            owners = ""                             # an ownerless line clears ownership
        lines.append(f"{pat} {owners}".rstrip())
    return lines


def make_repo(n_files, n_rules, seed):
    return make_files(n_files, seed), "\n".join(make_rules(n_rules, seed)) + "\n"
