#!/usr/bin/env python3
"""Step 0 -- turn a screenplay into training data.

A feature screenplay is one long document; this loop wants a series. The script
extracts the text, finds the scene boundaries, and groups scenes into episodes
of roughly equal length, so that each step of training covers a comparable
stretch of story.

    python s0_prepare_data.py --pdf data/example/source.pdf --episodes 20

PDFs go through `pdftotext -layout`, which keeps the indentation that screenplay
format depends on. Install it with `brew install poppler` or
`apt install poppler-utils`. If you already have plain text, pass `--text`
instead and nothing else is needed.

Output lands in `<work>/human/ep01.txt ...`, each file starting with `EP n`.
Read a couple of them before training -- if the extraction mangled the layout,
everything downstream inherits it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Screenplays mark scenes in two styles and plenty of them use both at once:
# a numbered heading (`14) INT. KITCHEN - NIGHT`, and montages like
# `16) * VARIOUS SCENES`), or a bare slugline. Match either, then collapse hits
# that landed on the same line.
NUMBERED = re.compile(r"^[ \t]{0,20}\d{1,4}[).][ \t]+\S", re.MULTILINE)
SLUGLINE = re.compile(r"^[ \t]{0,30}(?:INT\.|EXT\.|INT ?/ ?EXT|EXT ?/ ?INT|I/E\.)",
                      re.MULTILINE)
# Page furniture that survives extraction and means nothing to a reader.
NOISE = (
    re.compile(r"^\s*\d+\s*\.?\s*$"),                       # a bare page number
    re.compile(r"^\s*\(?\s*(CONTINUED|MORE)\s*\)?\s*$", re.I),
    re.compile(r"^\s*\f\s*$"),                              # form feed
)


def extract_text(pdf: Path) -> str:
    if not shutil.which("pdftotext"):
        raise SystemExit(
            "pdftotext is not installed. Install poppler "
            "(`brew install poppler` / `apt install poppler-utils`), "
            "or extract the text yourself and pass --text.")
    proc = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0 or len(proc.stdout.strip()) < 1000:
        raise SystemExit(
            f"pdftotext got almost nothing out of {pdf}. It is probably a scan "
            "with no text layer; find another copy or OCR it first.")
    return proc.stdout


def clean(text: str) -> str:
    kept = [line.rstrip() for line in text.replace("\f", "\n").splitlines()
            if not any(p.match(line) for p in NOISE)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def split_scenes(text: str) -> list[str]:
    """Cut the screenplay at every scene heading, dropping the title page."""
    hits = {text.rfind("\n", 0, m.start()) + 1
            for pattern in (NUMBERED, SLUGLINE)
            for m in pattern.finditer(text)}
    starts = sorted(hits)
    if len(starts) < 4:
        raise SystemExit(
            f"only found {len(starts)} scene headings. This may not be a "
            "screenplay, or the extraction lost the layout. Check the text.")
    # Anything before the first heading is the title page.
    bounds = [*starts, len(text)]
    return [text[bounds[i]:bounds[i + 1]].strip() for i in range(len(starts))]


def group(scenes: list[str], count: int) -> list[list[str]]:
    """Pack scenes into `count` episodes of roughly equal length."""
    if count > len(scenes):
        raise SystemExit(f"asked for {count} episodes but there are only "
                         f"{len(scenes)} scenes")
    target = sum(len(s) for s in scenes) / count
    episodes: list[list[str]] = [[]]
    size = 0.0
    for i, scene in enumerate(scenes):
        unplaced = len(scenes) - i          # this scene and everything after it
        slots = count - len(episodes)       # episodes still to be opened
        # Close this episode when the next scene would take it further past the
        # target than stopping here leaves it short. Close it regardless once
        # every scene left is needed to fill an episode of its own.
        full = size and size + len(scene) / 2 >= target
        if episodes[-1] and slots > 0 and (unplaced <= slots or full):
            episodes.append([])
            size = 0.0
        episodes[-1].append(scene)
        size += len(scene)
    return episodes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[2])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf", type=Path)
    source.add_argument("--text", type=Path)
    parser.add_argument("--work", type=Path, default=None,
                        help="output directory (default: alongside the source)")
    parser.add_argument("--episodes", type=int, default=20)
    args = parser.parse_args()
    if args.episodes < 1:
        raise SystemExit("--episodes must be at least 1")

    src = args.pdf or args.text
    work = (args.work or src.parent).resolve()
    text = clean(extract_text(args.pdf) if args.pdf
                 else args.text.read_text(encoding="utf-8", errors="replace"))

    scenes = split_scenes(text)
    episodes = group(scenes, args.episodes)

    out = work / "human"
    out.mkdir(parents=True, exist_ok=True)
    # Clear the previous split first. Re-running with a smaller --episodes would
    # otherwise leave the old high-numbered files in place, and the ground truth
    # would silently become two incompatible splits mixed together.
    for stale in out.glob("ep*.txt"):
        stale.unlink()
    for n, scene_group in enumerate(episodes, 1):
        body = "\n\n".join(scene_group)
        (out / f"ep{n:02d}.txt").write_text(f"EP {n}\n\n{body}\n", encoding="utf-8")

    total = sum(len(s) for s in scenes)
    print(f"{src.name}: {len(scenes)} scenes, {total:,} chars", file=sys.stderr)
    print(f"-> {len(episodes)} episodes in {out}", file=sys.stderr)
    for n, scene_group in enumerate(episodes, 1):
        print(f"   ep{n:02d}  {len(scene_group):>3} scenes  "
              f"{sum(len(s) for s in scene_group):>7,} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
