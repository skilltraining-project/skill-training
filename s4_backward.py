#!/usr/bin/env python3
"""Step 4 -- backward pass.

One agent reads this step's loss reports together with the read traces that go
with them, decides which rules helped and which misled, edits the pool, and
commits. That commit is the gradient step: the whole update is a diff over
markdown files, readable in `git log`.

Batching several works into one backward pass is doing the same work that
mini-batch SGD does. A difference that appears in four stories at once is worth
acting on. A difference that appears in one is usually that story's genre, and
acting on it would overfit the pool to a single example.

With many works, one agent cannot read every loss report, so the step is split
into micro-steps. `reduce` first folds a small group of reports into one
commonality report, and each micro-step then edits the pool from one such
summary. The micro-steps run one after another on the same pool, so a later one
sees what the earlier ones already changed.

Three checks stand between the agent and a finished step: the linter passes, a
commit actually exists, and the working tree is clean. Only then is `commit.txt`
written -- which is also what tells a resumed run that this step is done.

    python s4_backward.py --batch runs/.../backward/batch.json \\
        --pool runs/demo/memory --out runs/.../backward --label "epoch 0 step 0"
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from skilltrain import memory, prompts
from skilltrain.agent import AgentError, run_agent, run_text

REQUIRED_KEYS = ("work", "first", "last", "loss_report", "reads", "trajectory")


def load_batch(path: Path) -> list[dict]:
    samples = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(samples, list) or not samples:
        raise SystemExit(f"{path} must be a non-empty list")
    for i, sample in enumerate(samples):
        if missing := [k for k in REQUIRED_KEYS if k not in sample]:
            raise SystemExit(f"{path}[{i}] is missing {missing}")
        if not Path(sample["loss_report"]).exists():
            raise SystemExit(f"{path}[{i}]: no loss report at {sample['loss_report']}")
    return samples


def reduce(*, samples: list[dict], out_path: Path, model: str | None = None,
           timeout: int = 1800) -> Path:
    """Fold a group's loss reports into one commonality report."""
    sections = []
    for sample in samples:
        text = Path(sample["loss_report"]).read_text(encoding="utf-8")
        sections.append(f"## {sample['work']} (episodes "
                        f"{sample['first']}-{sample['last']})\n\n{text.strip()}")
    prompt = prompts.render("reduce", n=len(samples),
                            reports_section="\n\n".join(sections))
    names = ", ".join(s["work"] for s in samples)
    print(f"[reduce] {names}, prompt {len(prompt):,} chars", flush=True)
    try:
        summary = run_text(prompt, model=model, timeout=timeout)
    except AgentError as e:
        raise SystemExit(f"[reduce] failed: {e}") from e
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(summary + "\n", encoding="utf-8")
    print(f"[reduce] wrote {out_path} ({out_path.stat().st_size:,} bytes)", flush=True)
    return out_path


def batch_section(samples: list[dict], summary: Path | None = None) -> str:
    """The evidence list the optimizer is handed, one block per work."""
    blocks = []
    if summary is not None:
        blocks.append(
            f"### Commonality report for this micro-step\n"
            f"- `{summary}`\n\n"
            "Start here. It folds the loss reports below into one summary and "
            "names the works behind every pattern. Open an individual loss report "
            "only when you need the original evidence.")
    for sample in samples:
        blocks.append(
            f"### {sample['work']} (episodes {sample['first']}-{sample['last']})\n"
            f"- loss report: `{sample['loss_report']}`\n"
            f"- files the writer read: `{sample['reads']}`\n"
            f"- full trajectory: `{sample['trajectory']}`"
        )
    return "\n\n".join(blocks)


def lint_section(pool: Path, report_path: Path) -> str:
    """Tell the optimizer about entries that are already over the limits."""
    if memory.lint(pool, report_path) == 0:
        return "## Existing lint problems\n\nNone -- the pool is within limits."
    return ("## Existing lint problems\n\nThese are already in the pool. Fix any "
            "entry you touch; you do not have to fix the rest.\n\n```\n"
            + report_path.read_text(encoding="utf-8") + "```")


def snapshot(pool: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(pool, dest, ignore=shutil.ignore_patterns(".git"))


def run(*, pool: Path, samples: list[dict], out_dir: Path, label: str,
        summary: Path | None = None, model: str | None = None,
        timeout: int = 5400, retries: int = 2) -> bool:
    """Run one backward pass. True when every check passed."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lint_report = out_dir / "lint_report.txt"
    memory.init(pool, lint_report)

    before = memory.head(pool)
    if before is None:
        raise SystemExit(f"{pool} has no git history")
    if not memory.is_clean(pool):
        # A previous attempt died partway and left edits behind. Starting on top
        # of them would fold work this step never did into this step's gradient,
        # and every check downstream would still pass.
        print("[backward] the pool has leftover edits from an earlier attempt; "
              "rolling back to the last commit", flush=True)
        memory.reset(pool, before)
    snapshot(pool, out_dir / "memory_before")

    subject = f"train {label}"
    body = "\n".join(f"{s['work']} ep{s['first']:02d}-{s['last']:02d}" for s in samples)
    prompt = prompts.render(
        "backward",
        pool_dir=pool,
        batch_section=batch_section(samples, summary),
        memory_headers=memory.headers(pool),
        lint_section=lint_section(pool, lint_report),
        memory_policy=prompts.render(
            "memory_policy",
            folder_guide=memory.folder_guide(),
            body_heading=memory.BODY_HEADING,
            max_lines=memory.MAX_LINES,
            max_body_chars=memory.MAX_BODY_CHARS,
            max_description_chars=memory.MAX_DESCRIPTION_CHARS,
        ),
        folder_add_targets=" ".join(memory.FOLDER_NAMES),
        commit_subject=subject,
        commit_body=body,
    )

    print(f"[backward] {label}: {len(samples)} works", flush=True)
    # Work inside the pool. The prompt spells out `git -C <pool>`, but if the
    # agent ever drops the `-C`, a bare git command should still land on the
    # pool rather than on whatever repository the run directory sits inside.
    rc = run_agent(role="backward", prompt=prompt, workdir=pool, out_dir=out_dir,
                   model=model, timeout=timeout, retries=retries, retry_on_error=True,
                   before_retry=lambda: memory.reset(pool, before))

    ok = rc == 0
    if ok and memory.lint(pool, lint_report) != 0:
        print("[backward] rejected: the pool does not pass the linter", flush=True)
        ok = False
    if ok and memory.head(pool) == before:
        # No commit means no gradient step. An empty commit is allowed and says
        # "nothing was worth changing"; no commit at all means the agent stopped early.
        print("[backward] rejected: no commit was made", flush=True)
        ok = False
    if ok and not memory.is_clean(pool):
        # Half-committed edits would silently ride along into the next step.
        print("[backward] rejected: uncommitted changes left in the pool", flush=True)
        ok = False

    snapshot(pool, out_dir / "memory_after")
    diff = subprocess.run(["diff", "-ruN", str(out_dir / "memory_before"),
                           str(out_dir / "memory_after")],
                          capture_output=True, text=True, check=False)
    (out_dir / "memory.patch").write_text(diff.stdout, encoding="utf-8")

    if ok:
        (out_dir / "commit.txt").write_text(
            f"before={before}\nafter={memory.head(pool)}\nsubject={subject}\n",
            encoding="utf-8")
        print(f"[backward] committed: {subject}", flush=True)
    else:
        print("[backward] failed -- the pool is left as-is so you can inspect it",
              flush=True)
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--batch", required=True, type=Path)
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--label", default="manual")
    parser.add_argument("--summary", type=Path, default=None,
                        help="a commonality report from reduce, if there is one")
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=5400)
    args = parser.parse_args()
    ok = run(pool=args.pool.resolve(), samples=load_batch(args.batch.resolve()),
             out_dir=args.out.resolve(), label=args.label,
             summary=args.summary.resolve() if args.summary else None,
             model=args.model,
             timeout=args.timeout)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
