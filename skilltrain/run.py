"""Run directories: where a training run keeps its parameters and its evidence.

    runs/<run-id>/
      config.json                     the settings this run was started with
      memory/                         the pool being trained (its own git repo)
      input/<work>.md                 the noised story, as this run saw it
      loss/epoch_00/step_00/<work>.md the training signal, kept away from the
                                      step directories because it quotes the
                                      human screenplay
      epoch_00/step_00/
        <work>/                       one work's forward pass for this step
          scripts/ep01.txt ...        what the agent wrote
          forward_prompt.md
          forward.jsonl
          forward_trajectory.md
          forward_reads.txt           which memory entries it opened
        backward/
          batch.json                  the inputs the optimizer was given
          backward_prompt.md
          backward.jsonl
          backward_trajectory.md
          memory_before/  memory_after/  memory.patch
          lint_report.txt
          commit.txt                  written only after every check passes

Resuming is deliberately boring: there is no bookkeeping file to fall out of
sync. Re-run the same command and each stage checks whether its own artifacts
are already on disk. `commit.txt` is the one that matters -- it is written after
the linter passes, a commit exists, and the pool is clean, so a step is only
skipped when it genuinely finished.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = "config.json"
# Works per micro-step. Four is what the paper used.
DEFAULT_GROUP_SIZE = 4
# Changing any of these mid-run would make the pool's history meaningless, so a
# resume that disagrees on them stops instead of silently continuing.
PINNED = ("works", "episodes_per_step", "model", "no_backward", "init_pool",
          "group_size")


@dataclass(frozen=True)
class Run:
    """One training run, rooted at a directory."""

    root: Path
    config: dict

    @property
    def pool(self) -> Path:
        return self.root / "memory"

    def story_path(self, work: str) -> Path:
        """The run's own copy of a work's noised story.

        Copying it in makes the run self-contained, and it keeps the forward
        agent's world inside the run directory. The path it is given has no
        human screenplay anywhere near it.
        """
        return self.root / "input" / f"{work}.md"

    @property
    def loss_dir(self) -> Path:
        """Where the loss reports live.

        Deliberately not inside the step directories. A loss report quotes the
        human screenplay, and the forward agent works inside a step directory,
        so keeping the two apart is what stops a later epoch from finding the
        previous epoch's answer key next door.
        """
        return self.root / "loss"

    def loss_path(self, epoch: int, step: int, work: str) -> Path:
        return self.loss_dir / f"epoch_{epoch:02d}" / f"step_{step:02d}" / f"{work}.md"

    def step_dir(self, epoch: int, step: int) -> Path:
        return self.root / f"epoch_{epoch:02d}" / f"step_{step:02d}"

    def work_dir(self, epoch: int, step: int, work: str) -> Path:
        return self.step_dir(epoch, step) / work

    def summary_path(self, epoch: int, step: int, group: int) -> Path:
        """A micro-step's commonality report. It quotes the loss reports, which
        quote the human screenplay, so it lives beside them and not in a step
        directory."""
        return (self.loss_dir / f"epoch_{epoch:02d}" / f"step_{step:02d}"
                / f"summary_g{group:02d}.md")

    def backward_dir(self, epoch: int, step: int, group: int) -> Path:
        """One micro-step: one group's backward pass."""
        return self.step_dir(epoch, step) / "backward" / f"g{group:02d}"

    def episodes(self, step: int) -> tuple[int, int]:
        """Which episodes this step covers, 1-based and inclusive."""
        size = self.config["episodes_per_step"]
        start = step * size + 1
        return start, start + size - 1


def open_run(root: Path, config: dict) -> Run:
    """Create the run directory, or resume into an existing one.

    A new run refuses to start on a non-empty pool: the whole point of a run is
    that its git history explains how the pool got the way it is, and inheriting
    an unexplained pool breaks that.
    """
    root.mkdir(parents=True, exist_ok=True)
    path = root / CONFIG_NAME

    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        conflicts = [k for k in PINNED if previous.get(k) != config.get(k)]
        if conflicts:
            raise SystemExit(
                f"cannot resume {root.name}: {conflicts} differ from the original run.\n"
                f"  was: {({k: previous.get(k) for k in conflicts})}\n"
                f"  now: {({k: config.get(k) for k in conflicts})}\n"
                "Use a different --run-id for a different configuration."
            )
        # Extending the schedule is fine; the earlier steps are still a prefix.
        previous.update({k: v for k, v in config.items() if k not in PINNED})
        config = previous
    else:
        pool = root / "memory"
        if pool.is_dir() and any(pool.glob("*/*.md")):
            raise SystemExit(f"{pool} already has entries but no {CONFIG_NAME}; "
                             "start a new run somewhere else.")

    path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return Run(root=root, config=config)


def auto_run_id(config: dict) -> str:
    """A run id built from the settings that cannot change: 3w_e5_sonnet.

    The number of steps and epochs is deliberately left out. Those are the two
    things a resume is allowed to extend, and putting them in the name would
    send `--steps 8` to a fresh empty run instead of continuing the one that
    already did four.
    """
    works = len(config["works"])
    model = (config.get("model") or "default").replace("claude-", "").replace("/", "-")
    name = f"{works}w_e{config['episodes_per_step']}_{model}"
    if config.get("group_size", DEFAULT_GROUP_SIZE) != DEFAULT_GROUP_SIZE:
        name += f"_g{config['group_size']}"
    if config.get("init_pool"):
        name += "_seeded"
    return name + ("_frozen" if config.get("no_backward") else "")
