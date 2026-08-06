"""The memory pool: this project's trainable parameters.

A pool is a directory of markdown files under a fixed three-folder layout. Each
file is one reusable writing rule. The optimizer edits these files; nothing else
in the system is learned.

    pool/
      00_general_rules/     what the medium is and what "good" means
      01_craft_elements/    how to write a specific component
      02_genre_specifics/   rules that only hold inside one genre

Each file looks like this:

    ---
    description: when to read this entry, and when not to
    ---

    ## Rules
    ...how to actually write it...

The split matters. `description` is all the forward agent sees when it decides
what to open, so it has to state the boundary. The body is what it reads after
deciding, so it should not repeat the boundary.

The linter below is the only hard constraint in the system. It checks shape and
size, never quality -- a linter that judges writing would just be a second,
slower model. It runs as a git pre-commit hook inside the pool, so an optimizer
that writes a malformed entry cannot commit it.

Runnable on its own:

    python memsgd/memory.py --pool runs/<id>/memory --report /tmp/lint.txt
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

FOLDERS: tuple[tuple[str, str], ...] = (
    (
        "00_general_rules",
        "What the medium is and how the audience consumes it -- the standards a "
        "scene is judged against. The forward agent reads all of these every "
        "time, so keep the folder small and keep it to principles. Anything that "
        "answers 'how do I write X' belongs in 01_craft_elements even if it "
        "applies everywhere.",
    ),
    (
        "01_craft_elements",
        "How to write a specific component: dialogue, action lines, hooks, cold "
        "opens, props, scene transitions, pacing within a scene. Read on demand. "
        "Craft that holds across genres lives here -- being broadly useful is not "
        "a reason to promote it to 00_general_rules.",
    ),
    (
        "02_genre_specifics",
        "Rules that only hold inside one genre or story type: revenge arcs, "
        "workplace romance, supernatural pacts, heist beats. Read only when the "
        "current story matches. Do not generalize these into 00 or 01.",
    ),
)
FOLDER_NAMES: tuple[str, ...] = tuple(name for name, _ in FOLDERS)

# Roughly 50 lines / 1200 tokens / 200 tokens, measured in characters so the
# project stays dependency-free. Entries are rule cards, not essays; a pool that
# grows without limit stops being routable.
MAX_LINES = int(os.environ.get("MEMSGD_MAX_LINES", "50"))
MAX_BODY_CHARS = int(os.environ.get("MEMSGD_MAX_BODY_CHARS", "4800"))
MAX_DESCRIPTION_CHARS = int(os.environ.get("MEMSGD_MAX_DESCRIPTION_CHARS", "800"))

BODY_HEADING = "## Rules"
# A memory entry is a rule you can apply next time, not a record of what went
# wrong last time. These two patterns are how loss-report prose leaks in.
FORBIDDEN = (
    (re.compile(r"\bep(isode)?\s*\.?\s*\d+\b", re.IGNORECASE),
     "no episode numbers -- a rule that only applies to one episode is not a rule"),
    (re.compile(r"\b(the )?(AI|model|agent)('s)? (mistake|error|version|draft|tendency)"
                r"|\b(the )?human('s)? (version|standard|draft)", re.IGNORECASE),
     "no 'the AI did X, the human did Y' -- write what to do, not what went wrong"),
)


# --------------------------------------------------------------------------
# linting
# --------------------------------------------------------------------------

def parse_entry(text: str) -> tuple[dict[str, str], str]:
    """Split a memory file into its frontmatter fields and its body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("must start with a `---` frontmatter block")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise ValueError("frontmatter is never closed with `---`") from None

    fields: dict[str, str] = {}
    for lineno, line in enumerate(lines[1:end], 2):
        if not line.strip():
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter line {lineno} is not `key: value` -- "
                             "keep the whole description on one line")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, "\n".join(lines[end + 1:])


def lint_entry(path: Path) -> list[str]:
    """All problems with one memory file. Never stops at the first one."""
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    if (count := len(text.splitlines())) > MAX_LINES:
        problems.append(f"{count} lines, limit is {MAX_LINES}")
    try:
        fields, body = parse_entry(text)
    except ValueError as e:
        return [*problems, str(e)]

    description = fields.get("description", "")
    if not description:
        problems.append("frontmatter is missing `description`")
    elif len(description) > MAX_DESCRIPTION_CHARS:
        problems.append(f"description is {len(description)} chars, "
                        f"limit is {MAX_DESCRIPTION_CHARS}")
    if extra := sorted(set(fields) - {"description"}):
        problems.append(f"frontmatter may only contain `description`, found {extra}")

    if len(body) > MAX_BODY_CHARS:
        problems.append(f"body is {len(body)} chars, limit is {MAX_BODY_CHARS} -- "
                        "compress it, or split it into two entries with narrower "
                        "descriptions")
    headings = re.findall(r"^##\s+.*$", body, flags=re.MULTILINE)
    if headings != [BODY_HEADING]:
        problems.append(f"body must contain exactly one heading, `{BODY_HEADING}`, "
                        f"found {headings or 'none'}")
    for pattern, message in FORBIDDEN:
        if pattern.search(text):
            problems.append(message)
    return [f"{path.parent.name}/{path.name}: {p}" for p in problems]


def lint_layout(pool: Path) -> list[str]:
    """Check that the pool only uses the three fixed folders, one level deep."""
    problems: list[str] = []
    for name in FOLDER_NAMES:
        if not (pool / name).is_dir():
            problems.append(f"{name}/: required folder is missing")
    for child in sorted(pool.iterdir()):
        if child.name == ".git":
            continue
        if child.is_dir() and child.name not in FOLDER_NAMES:
            problems.append(f"{child.name}/: memory only lives in "
                            f"{', '.join(FOLDER_NAMES)}")
        elif child.is_dir():
            for nested in sorted(child.iterdir()):
                if nested.is_dir():
                    problems.append(f"{child.name}/{nested.name}/: no nested folders")
                elif nested.suffix != ".md":
                    problems.append(f"{child.name}/{nested.name}: only .md files")
        elif child.is_file() and not child.name.startswith("."):
            problems.append(f"{child.name}: nothing goes in the pool root")
    return problems


def entries(pool: Path) -> list[Path]:
    return sorted(p for folder in FOLDER_NAMES for p in (pool / folder).glob("*.md"))


def lint(pool: Path, report_path: Path) -> int:
    """Lint a pool, write a report, return 0 when clean and 1 when not."""
    pool, report_path = pool.resolve(), report_path.resolve()
    if not pool.is_dir():
        raise FileNotFoundError(f"no such pool: {pool}")
    if pool in report_path.parents:
        # The report must not land inside the pool, or the optimizer will see a
        # stray file in `git status` and try to commit it.
        raise ValueError(f"report must live outside the pool: {report_path}")

    files = entries(pool)
    problems = lint_layout(pool)
    for path in files:
        problems.extend(lint_entry(path))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    if problems:
        body = "MEMORY_LINT_FAILED\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    else:
        body = f"MEMORY_LINT_OK entries={len(files)}\n"
    report_path.write_text(body, encoding="utf-8")
    print(body, end="")
    return 1 if problems else 0


# --------------------------------------------------------------------------
# reading the pool
# --------------------------------------------------------------------------

def headers(pool: Path) -> str:
    """The routing view: every entry's path and description, grouped by folder.

    This is the whole pool as the forward agent first sees it. It picks what to
    open from these descriptions alone.
    """
    blocks: list[str] = []
    for folder, purpose in FOLDERS:
        found = sorted((pool / folder).glob("*.md")) if (pool / folder).is_dir() else []
        lines = [f"### {folder}/", "", purpose, ""]
        if not found:
            lines.append("_(empty)_")
        for path in found:
            try:
                fields, _ = parse_entry(path.read_text(encoding="utf-8"))
                description = fields.get("description", "(no description)")
            except ValueError:
                description = "(malformed frontmatter)"
            lines.append(f"- `{folder}/{path.name}` -- {description}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def folder_guide() -> str:
    """The three folders and what belongs in each, for prompts."""
    return "\n".join(f"- `{name}/` -- {purpose}" for name, purpose in FOLDERS)


# --------------------------------------------------------------------------
# the pool's own git repo
# --------------------------------------------------------------------------

def git(pool: Path, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(pool), *args], text=True,
                          capture_output=capture, check=False)


def head(pool: Path) -> str | None:
    proc = git(pool, "rev-parse", "--verify", "HEAD", capture=True)
    return proc.stdout.strip() if proc.returncode == 0 else None


def is_clean(pool: Path) -> bool:
    proc = git(pool, "status", "--porcelain", capture=True)
    return proc.returncode == 0 and not proc.stdout.strip()


def reset(pool: Path, commit: str) -> None:
    """Throw away everything since `commit`, including untracked files.

    `git reset --hard` destroys uncommitted work, so this refuses to run unless
    the pool really is its own repository. Without that check, a broken
    `pool/.git` sends git searching up the tree, and the reset lands on
    whatever repository the run directory happens to sit inside.
    """
    require_own_repo(pool)
    git(pool, "reset", "--hard", commit, capture=True)
    # Not scoped to the three folders: an optimizer that left a scratch file in
    # the pool root would otherwise survive the reset and fail the linter on
    # every retry, for something the retry did not do.
    git(pool, "clean", "-fd", capture=True)
    # `git clean` removes a folder that ends up empty; the layout requires all
    # three to exist, so put them back.
    for name in FOLDER_NAMES:
        (pool / name).mkdir(exist_ok=True)


def require_own_repo(pool: Path) -> None:
    """Fail unless `pool` is the root of its own git repository.

    A `pool/.git` that exists but is unusable (an interrupted `git init`, a
    directory copied with `cp -r`, a stale worktree pointer) makes git walk up
    the tree and quietly adopt the enclosing repository. Every git call here
    would then act on the user's own checkout, and `reset --hard` would throw
    away their uncommitted work.
    """
    proc = git(pool, "rev-parse", "--show-toplevel", capture=True)
    top = proc.stdout.strip()
    if proc.returncode != 0 or Path(top).resolve() != pool.resolve():
        raise SystemExit(
            f"{pool} is not the root of its own git repository"
            + (f" (git resolves it to {top})" if top else "")
            + ".\nRefusing to run git here. Remove or repair the pool's .git "
              "directory and try again.")


def init(pool: Path, lint_report: Path) -> None:
    """Create the folders, the git repo, and the pre-commit lint hook.

    Every training step re-installs the hook because each step writes its lint
    report to its own directory. The hook is what makes the linter binding: the
    optimizer commits its own work, and a malformed entry is refused at that
    moment rather than discovered a step later.
    """
    for name in FOLDER_NAMES:
        (pool / name).mkdir(parents=True, exist_ok=True)
    if not (pool / ".git").is_dir():
        git(pool, "init", "-q")
    require_own_repo(pool)
    git(pool, "config", "user.name", "memory-sgd")
    git(pool, "config", "user.email", "memory-sgd@localhost")
    # Two settings from the user's global config would otherwise break the pool
    # silently. `core.hooksPath` makes git ignore the hook installed below, so
    # the linter would stop being binding. `commit.gpgsign` makes every commit
    # fail on a machine without a working key, which reads as "the optimizer
    # never committed" rather than as a configuration problem.
    git(pool, "config", "core.hooksPath", ".git/hooks")
    git(pool, "config", "commit.gpgsign", "false")

    hook = pool / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        f'"{sys.executable}" "{Path(__file__).resolve()}" '
        f'--pool "$(git rev-parse --show-toplevel)" --report "{lint_report.resolve()}"\n',
        encoding="utf-8",
    )
    hook.chmod(0o755)

    if head(pool) is None:
        proc = git(pool, "commit", "--allow-empty", "--no-verify", "-m",
                   "init memory pool", capture=True)
        if head(pool) is None:
            raise SystemExit(f"could not create the pool's first commit in {pool}:\n"
                             + (proc.stderr.strip() or proc.stdout.strip()))


def main() -> None:
    parser = argparse.ArgumentParser(description="Lint a memory pool.")
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    try:
        sys.exit(lint(args.pool, args.report))
    except (FileNotFoundError, ValueError) as e:
        print(f"MEMORY_LINT_ERROR: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
