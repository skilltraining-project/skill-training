#!/usr/bin/env python3
"""Step 3 -- the loss.

Put the model's screenplay next to the human original and write up how they
differ. Both were made from the same story, so plot is not the subject; craft is.

This is the one place where the answer key is opened. The report that comes out
is the training signal -- a paragraph of prose instead of a number, but playing
the same role: it says what to change, and it is the only thing the optimizer
is allowed to learn from.

    python s3_loss.py --work data/example --scripts runs/.../scripts \\
        --out runs/.../loss_report.md --first 1 --last 5
"""

from __future__ import annotations

import argparse
from pathlib import Path

from memsgd import dataset, prompts
from memsgd.agent import AgentError, run_text


def read_scripts(scripts_dir: Path, first: int, last: int) -> str:
    parts = []
    for n in range(first, last + 1):
        path = scripts_dir / f"ep{n:02d}.txt"
        if path.exists():
            parts.append(f"=== Model EP {n:02d} ===\n\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def run(*, work: dataset.Work, scripts_dir: Path, report_path: Path,
        first: int, last: int, model: str | None = None, timeout: int = 1800) -> Path:
    """Write the difference report for episodes `first..last`."""
    human = work.human_text(first, last)
    if not human.strip():
        raise SystemExit(f"no human episodes {first}-{last} in {work.human_dir}")
    written = read_scripts(scripts_dir, first, last)
    if not written.strip():
        # Comparing a screenplay against nothing produces a confident report
        # about a gap that does not exist, and that report is the training signal.
        raise SystemExit(f"no model episodes {first}-{last} in {scripts_dir}")

    fields = dict(work=work.name, episode_range=f"{first}-{last}",
                  model_scripts=written)
    prompt = prompts.render("loss", human_scripts=human, **fields)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    # Archive the prompt with the human screenplay left out. Keeping a verbatim
    # copy of the answer key inside the run directory is how a later epoch's
    # closed-book writer would find it.
    report_path.with_name(f"{report_path.stem}_prompt.md").write_text(
        prompts.render("loss", human_scripts="[human screenplay omitted from "
                                             "this archive]", **fields),
        encoding="utf-8")

    print(f"[loss] {work.name} ep{first:02d}-{last:02d}, "
          f"prompt {len(prompt):,} chars", flush=True)
    try:
        report = run_text(prompt, model=model, timeout=timeout)
    except AgentError as e:
        raise SystemExit(f"[loss] failed: {e}") from e

    report_path.write_text(report + "\n", encoding="utf-8")
    print(f"[loss] wrote {report_path} ({report_path.stat().st_size:,} bytes)", flush=True)
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--scripts", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    run(work=dataset.load(args.work), scripts_dir=args.scripts.resolve(),
        report_path=args.out.resolve(), first=args.first, last=args.last,
        model=args.model, timeout=args.timeout)


if __name__ == "__main__":
    main()
