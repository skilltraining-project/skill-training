#!/usr/bin/env python3
"""Step 2 -- forward pass.

Give the writer the noised story and the memory pool, and ask for screenplays.
This is a closed-book exam: the human original is never shown, never mentioned,
and never reachable from the run directory the agent is pointed at. The only way
to write well is to have learned how.

The agent sees every memory entry's description and opens the ones it judges
relevant. Which ones it opened is recorded, and that record is what makes credit
assignment possible two steps later -- a rule can only be blamed for a screenplay
it was actually present for.

    python -m skilltrain forward --work data/example --out runs/demo/epoch_00/step_00/example \\
        --pool runs/demo/memory --first 1 --last 5
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from skilltrain import dataset, memory, prompts
from skilltrain.agent import run_agent


def run(*, work: dataset.Work, out_dir: Path, pool: Path, first: int, last: int,
        model: str | None = None, timeout: int = 2400, retries: int = 2,
        story_path: Path | None = None,
        off_limits: Sequence[Path] | None = None) -> bool:
    """Write episodes `first..last`. True when every file landed.

    `story_path` overrides where the noised story is read from. The training
    loop points it at the run's own copy, so the only story path the agent ever
    sees is inside the run directory, nowhere near the human screenplay.
    `off_limits` are directories the agent must not read from. Opening one fails
    the pass.
    """
    story_path = story_path or work.story_path
    scripts_dir = out_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    wanted = [scripts_dir / f"ep{n:02d}.txt" for n in range(first, last + 1)]
    # Clear anything a previous attempt left behind, so a file existing
    # afterwards is evidence that this attempt wrote it. Otherwise a stale
    # episode satisfies the retry check and the agent gets no second chance.
    for path in wanted:
        path.unlink(missing_ok=True)

    prompt = prompts.render(
        "forward",
        episode_range=f"{first}-{last}",
        episode_count=last - first + 1,
        pool_dir=pool,
        memory_headers=memory.headers(pool),
        output_paths="\n".join(f"- {p}" for p in wanted),
        story_path=story_path,
        chapters=dataset.chapters_from(story_path, first, last),
    )

    print(f"[forward] {work.name} ep{first:02d}-{last:02d}", flush=True)
    run_agent(role="forward", prompt=prompt, workdir=out_dir, out_dir=out_dir,
              model=model, timeout=timeout, expect=wanted, retries=retries)

    written = [p for p in wanted if p.exists()]
    print(f"[forward] {len(written)}/{len(wanted)} episodes written", flush=True)
    if not check_closed_book(out_dir / "forward_reads.txt", off_limits or ()):
        return False
    return len(written) == len(wanted)


def check_closed_book(reads_path: Path, off_limits: Sequence[Path]) -> bool:
    """Fail the pass if the writer opened anything it was told to stay out of.

    The prompt asks the agent not to hunt for the human screenplay, and the run
    directory is arranged so it is not lying around. Neither is a guarantee: the
    agent runs with permissions skipped and can read the disk. This is the part
    that would actually notice. A pass that saw the answer is not a measurement
    of anything, so it fails loudly rather than quietly scoring well.
    """
    if not reads_path.exists():
        return True
    # Compare resolved and unresolved forms on both sides. A read trace holds
    # whatever path the agent typed, and on macOS `/var` is a symlink to
    # `/private/var`, so string-matching one form against the other misses.
    banned = {form for p in off_limits
              for form in (str(Path(p)), str(Path(p).resolve()))}

    def forbidden(line: str) -> bool:
        if not line.strip():
            return False
        forms = {line, str(Path(line).resolve())}
        return (any(f.startswith(b) for f in forms for b in banned)
                or any(marker in line for marker in ("loss_report", "loss_prompt", "/loss/")))

    caught = [line for line in reads_path.read_text(encoding="utf-8").splitlines()
              if forbidden(line)]
    if caught:
        print("[forward] FAILED: the writer opened material it was not supposed "
              "to see, so this pass is not a closed-book result:", flush=True)
        for line in caught:
            print(f"  {line}", flush=True)
    return not caught


def is_done(out_dir: Path, first: int, last: int) -> bool:
    """A forward pass counts as finished only with its read trace.

    Without the trace there is no record of which rules were in context, so the
    optimizer could never attribute anything to this work. A half-finished pass
    is worth less than no pass at all.
    """
    scripts = all((out_dir / "scripts" / f"ep{n:02d}.txt").exists()
                  for n in range(first, last + 1))
    return scripts and (out_dir / "forward_reads.txt").exists()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m skilltrain forward", description=__doc__.split("\n")[2])
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--pool", required=True, type=Path)
    parser.add_argument("--first", type=int, required=True)
    parser.add_argument("--last", type=int, required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout", type=int, default=2400)
    args = parser.parse_args(argv)
    work = dataset.load(args.work)
    ok = run(work=work, out_dir=args.out.resolve(), pool=args.pool.resolve(),
             first=args.first, last=args.last, model=args.model,
             timeout=args.timeout, off_limits=[work.human_dir])
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
