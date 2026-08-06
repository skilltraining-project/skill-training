#!/usr/bin/env python3
"""Step 5 -- the training loop.

Runs the other four in the order that makes them a training loop:

    for each epoch:
        for each step:
            for each work:  forward  ->  loss          (in parallel)
            one backward over all of them             (updates the pool)

A step covers a fixed stretch of episodes across every work, so the works move
through the story together. Forward and loss are independent per work and run
concurrently; backward is single and last, because every work's evidence has to
be on the table before the pool is allowed to change.

    python s5_train.py --work data/example --steps 4 --episodes-per-step 5

Re-running the same command resumes: each stage checks its own artifacts and
skips what is already there. `--no-backward` freezes the pool, and
`--init-pool` starts from an existing one. Together they give the control arm:
the same writer working from notes that have stopped changing.
"""

from __future__ import annotations

import argparse
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import s2_forward
import s3_loss
import s4_backward
from memsgd import dataset, memory, run as runlib


def forward_and_loss(work: dataset.Work, run: runlib.Run, epoch: int, step: int,
                     first: int, last: int, args) -> dict | None:
    """One work's half of a step, with anything it throws contained to itself."""
    out_dir = run.work_dir(epoch, step, work.name)
    report = run.loss_path(epoch, step, work.name)
    try:
        return _forward_and_loss(work, run, out_dir, first, last, args, report)
    except (Exception, SystemExit) as e:  # noqa: BLE001
        # One work going wrong should cost that work, not the whole step. The
        # rest of the batch still carries a usable signal.
        print(f"[warn] {work.name} failed this step: {e}", flush=True)
        return None


def _forward_and_loss(work: dataset.Work, run: runlib.Run, out_dir: Path,
                      first: int, last: int, args, report: Path) -> dict | None:
    if s2_forward.is_done(out_dir, first, last):
        print(f"[skip] forward {work.name} ep{first:02d}-{last:02d}", flush=True)
    elif not s2_forward.run(work=work, out_dir=out_dir, pool=run.pool, first=first,
                            last=last, model=args.model,
                            story_path=run.story_path(work.name),
                            off_limits=[work.human_dir, run.loss_dir],
                            timeout=args.forward_timeout):
        print(f"[warn] forward failed for {work.name}; it sits out this step",
              flush=True)
        return None

    if report.exists():
        print(f"[skip] loss {work.name} ep{first:02d}-{last:02d}", flush=True)
    else:
        s3_loss.run(work=work, scripts_dir=out_dir / "scripts", report_path=report,
                    first=first, last=last, model=args.model,
                    timeout=args.loss_timeout)

    return {"work": work.name, "first": first, "last": last,
            "loss_report": str(report),
            "reads": str(out_dir / "forward_reads.txt"),
            "trajectory": str(out_dir / "forward_trajectory.md")}


def adopt_story(run: runlib.Run, work: dataset.Work) -> None:
    """Copy a work's noised story into the run, once and for good.

    Two reasons. The run becomes self-contained, so it still explains itself
    after the data directory has moved on. And the only story path the forward
    agent is ever handed lives inside the run, nowhere near `data/<work>/human/`.

    Re-noising a work mid-run would change what earlier steps were trained on
    and make the pool's history a lie, so that is refused rather than absorbed.
    """
    destination = run.story_path(work.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(work.story_path, destination)
    elif destination.read_bytes() != work.story_path.read_bytes():
        raise SystemExit(
            f"{work.name} has been re-noised since this run started.\n"
            f"  run input: {destination}\n"
            f"  data:      {work.story_path}\n"
            "Earlier steps trained on the old text. Use a different --run-id.")


def seed_pool(run: runlib.Run, source: Path) -> None:
    """Start a run from an existing pool instead of from nothing.

    This is what makes a real frozen-pool control possible. `--no-backward` on
    its own compares "no notes" against "notes that evolve", which conflates two
    variables. Seeding a frozen run with a pool that was already trained isolates
    the one that matters: whether the notes are allowed to keep changing.
    """
    if any(run.pool.glob("*/*.md")):
        return  # already seeded, or already trained
    entries = sorted(source.glob("*/*.md"))
    if not entries:
        raise SystemExit(f"--init-pool {source} has no entries")
    for entry in entries:
        target = run.pool / entry.parent.name / entry.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry, target)
    print(f"[pool] seeded {len(entries)} entries from {source}", flush=True)


def train(run: runlib.Run, works: list[dataset.Work], args) -> None:
    memory.init(run.pool, run.root / "lint_report.txt")
    if args.init_pool:
        seed_pool(run, args.init_pool.resolve())
    for work in works:
        adopt_story(run, work)

    for epoch in range(args.epochs):
        for step in range(args.steps):
            first, last = run.episodes(step)
            active = [w for w in works if last in w.human_episodes()]
            if not active:
                # Out of data for this epoch. Break, not return: the next epoch
                # starts over at step 0 and has plenty left to do.
                print(f"\n=== epoch {epoch}: no work reaches episode {last}, "
                      f"moving on after {step} steps ===", flush=True)
                break

            print(f"\n=== epoch {epoch} step {step} | episodes {first}-{last} | "
                  f"{len(active)} works ===", flush=True)

            with ThreadPoolExecutor(max_workers=args.workers) as threads:
                batch = [s for s in threads.map(
                    lambda w: forward_and_loss(w, run, epoch, step, first, last,
                                               args), active) if s]

            if not batch:
                raise SystemExit("every work failed this step; stopping")
            if args.no_backward:
                print("[backward] skipped (--no-backward)", flush=True)
                continue

            out_dir = run.backward_dir(epoch, step)
            if (out_dir / "commit.txt").exists():
                print(f"[skip] backward epoch {epoch} step {step}", flush=True)
                continue
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "batch.json").write_text(json.dumps(batch, indent=2) + "\n",
                                                encoding="utf-8")
            if not s4_backward.run(pool=run.pool, samples=batch, out_dir=out_dir,
                                   label=f"epoch {epoch} step {step}",
                                   model=args.model, timeout=args.backward_timeout):
                # A failed backward leaves the pool in an unknown state, and every
                # later step would build on it. Stop and let a human look.
                raise SystemExit(f"backward failed at epoch {epoch} step {step}")

    print(f"\n=== done: {run.root} ===", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--work", action="append", required=True, type=Path,
                        dest="works", help="data directory; repeat for a batch")
    parser.add_argument("--steps", type=int, default=4)
    parser.add_argument("--episodes-per-step", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4,
                        help="works running forward+loss at once")
    parser.add_argument("--no-backward", action="store_true",
                        help="freeze the pool: no backward pass, no updates")
    parser.add_argument("--init-pool", type=Path, default=None,
                        help="start from a copy of an existing memory/ pool; "
                             "with --no-backward this is the frozen-pool control")
    parser.add_argument("--model", default=None, help="passed through to the CLI")
    parser.add_argument("--runs-dir", type=Path, default=Path("runs"))
    parser.add_argument("--run-id", default=None, help="default: derived from the settings")
    parser.add_argument("--forward-timeout", type=int, default=2400)
    parser.add_argument("--loss-timeout", type=int, default=1800)
    parser.add_argument("--backward-timeout", type=int, default=5400)
    args = parser.parse_args()

    works = [dataset.load(path) for path in args.works]
    if len({w.name for w in works}) != len(works):
        # Work directories are identified by their basename, so two named
        # `example` would write over each other's screenplays and logs.
        raise SystemExit("two --work directories have the same name; "
                         "give them distinct basenames")
    for work in works:
        if not work.story_path.exists():
            raise SystemExit(f"{work.story_path} is missing -- run s1_diffuse.py first")

    config = {"works": sorted(w.name for w in works),
              "episodes_per_step": args.episodes_per_step,
              "steps": args.steps, "epochs": args.epochs,
              "model": args.model, "no_backward": args.no_backward,
              "init_pool": str(args.init_pool.resolve()) if args.init_pool else None}
    run_id = args.run_id or runlib.auto_run_id(config)
    run = runlib.open_run(args.runs_dir.resolve() / run_id, config)
    print(f"run: {run.root}", flush=True)
    train(run, works, args)


if __name__ == "__main__":
    main()
