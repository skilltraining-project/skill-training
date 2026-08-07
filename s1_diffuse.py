#!/usr/bin/env python3
"""Step 1 -- add noise.

Take the human screenplay apart and rebuild it as a plain prose summary: the
events stay, the dialogue and staging go. That summary is what the writer will
be given later, with the original held back as the answer key.

This is the forward process of a diffusion model, done in text. The human
screenplay is x0. Noising is a fixed corruption that destroys craft while
preserving story, and the training loop that follows learns the denoiser. Because
the corruption is applied to a real screenplay, every training example comes
with a ground truth for free -- no one has to label anything.

    python s1_diffuse.py --work data/example --noise heavy

Chapters are cached as they finish, so re-running only does what is missing.
"""

from __future__ import annotations

import argparse
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from skilltrain import dataset, prompts
from skilltrain.agent import AgentError, run_text

BANNED = ("INT.", "EXT.", "V.O.", "O.S.", "CUT TO", "FADE IN", "(CONT'D)")
# `startswith(f"# Chapter {n}")` would accept `# Chapter 12` when asking for 1.
HEADING = re.compile(r"^# Chapter (\d+)\b")


def diffuse_episode(work: dataset.Work, number: int, path: Path, *,
                    noise: str, model: str | None, timeout: int,
                    force: bool = False) -> str:
    """Noise one episode into one chapter, using the cache when it is there."""
    # The noise level is part of the cache key. Without it, trying one chapter at
    # `--noise light` would leave a light chapter sitting in the cache, and the
    # full `--noise heavy` run would happily reuse it.
    cached = work.cache_dir / noise / f"ch{number:02d}.md"
    if cached.exists() and not force:
        return cached.read_text(encoding="utf-8")

    prompt = prompts.render(f"diffuse_{noise}", episode_number=number,
                            screenplay=path.read_text(encoding="utf-8"))
    chapter = run_text(prompt, model=model, timeout=timeout).strip()

    heading = HEADING.match(chapter)
    if not heading or int(heading.group(1)) != number:
        raise AgentError(f"chapter {number} does not start with `# Chapter {number}`")
    if leaked := [token for token in BANNED if token in chapter]:
        # Screenplay vocabulary surviving the rewrite means the model transcribed
        # instead of summarising, and the example would be trivially easy.
        raise AgentError(f"chapter {number} still contains screenplay markup: {leaked}")

    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(chapter + "\n", encoding="utf-8")
    print(f"  chapter {number:02d}: {len(chapter):,} chars", flush=True)
    return chapter


def run(work: dataset.Work, *, noise: str = "heavy", model: str | None = None,
        workers: int = 8, timeout: int = 1800, only: list[int] | None = None,
        force: bool = False) -> dict[int, str]:
    """Noise the episodes and, unless `only` was given, assemble `story.md`."""
    episodes = work.human_episodes()
    if not episodes:
        raise SystemExit(f"no epNN.txt files in {work.human_dir}")
    if only:
        if missing := [n for n in only if n not in episodes]:
            raise SystemExit(f"{work.name} has no episode {missing}")
        episodes = {n: episodes[n] for n in only}

    print(f"[diffuse] {work.name}: {len(episodes)} episodes, noise={noise}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {n: pool.submit(diffuse_episode, work, n, path, noise=noise,
                                  model=model, timeout=timeout, force=force)
                   for n, path in sorted(episodes.items())}
        chapters = {n: future.result() for n, future in futures.items()}

    if only:
        # Trying one chapter before spending on the whole screenplay. Print it
        # instead of writing a story.md that would be full of holes.
        for n in sorted(chapters):
            print(f"\n{'=' * 70}\n{chapters[n]}\n", flush=True)
        return chapters

    story = "\n\n".join(chapters[n] for n in sorted(chapters)) + "\n"
    work.story_path.write_text(story, encoding="utf-8")
    print(f"[diffuse] wrote {work.story_path} ({len(story):,} chars)", flush=True)
    return chapters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    parser.add_argument("--work", required=True, type=Path,
                        help="data directory holding human/epNN.txt")
    parser.add_argument("--noise", choices=("light", "heavy"), default="heavy",
                        help="how much of the craft to strip (default: heavy)")
    parser.add_argument("--only", type=int, action="append", metavar="N",
                        help="try one episode and print it, without writing "
                             "story.md; repeat for several")
    parser.add_argument("--force", action="store_true", help="ignore the cache")
    parser.add_argument("--model", default=None, help="passed through to the CLI")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    run(dataset.load(args.work), noise=args.noise, model=args.model,
        workers=args.workers, timeout=args.timeout, only=args.only,
        force=args.force)


if __name__ == "__main__":
    main()
