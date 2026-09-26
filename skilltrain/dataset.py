"""Training data: one screenplay, split into episodes, plus its noised version.

    data/<work>/
      human/ep01.txt ...   the human screenplay, split into equal stretches
      story.md             the same story after noising -- the training input
      .cache/heavy/ch01.md per-chapter noising cache, keyed by noise level

`human/` is the ground truth: it is what the loss compares against, and the
writer never sees it. `story.md` is one markdown file with `# Chapter N:`
headings, one chapter per episode, same numbering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EPISODE = re.compile(r"^ep(\d+)$", re.IGNORECASE)
CHAPTER = re.compile(r"^# Chapter (\d+)", re.MULTILINE)


@dataclass(frozen=True)
class Work:
    """One screenplay's data directory."""

    root: Path

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def human_dir(self) -> Path:
        return self.root / "human"

    @property
    def story_path(self) -> Path:
        return self.root / "story.md"

    @property
    def cache_dir(self) -> Path:
        return self.root / ".cache"

    def human_episodes(self) -> dict[int, Path]:
        """Episode number -> file, for every `epNN.txt` in `human/`."""
        found = {}
        for path in sorted(self.human_dir.glob("ep*.txt")):
            if match := EPISODE.fullmatch(path.stem):
                found[int(match.group(1))] = path
        return found

    def human_text(self, first: int, last: int) -> str:
        """The human screenplay for a range of episodes, concatenated."""
        episodes = self.human_episodes()
        parts = [f"=== Human EP {n:02d} ===\n\n{episodes[n].read_text(encoding='utf-8')}"
                 for n in range(first, last + 1) if n in episodes]
        return "\n\n".join(parts)

    def chapters(self, first: int, last: int) -> str:
        """The noised story for a range of chapters, concatenated."""
        return chapters_from(self.story_path, first, last)


def chapters_from(story_path: Path, first: int, last: int) -> str:
    """Chapters `first..last` of a noised story file."""
    text = story_path.read_text(encoding="utf-8")
    bounds = [(int(m.group(1)), m.start()) for m in CHAPTER.finditer(text)]
    numbers = [n for n, _ in bounds]
    if len(set(numbers)) != len(numbers):
        # A dict keyed by chapter number would keep the last of each duplicate
        # and lose the rest, which reads as a story that quietly skips a chapter.
        raise SystemExit(f"{story_path} has more than one copy of some chapters: "
                         f"{sorted({n for n in numbers if numbers.count(n) > 1})}")
    offsets = {n: (start, bounds[i + 1][1] if i + 1 < len(bounds) else len(text))
               for i, (n, start) in enumerate(bounds)}
    parts = []
    for n in range(first, last + 1):
        if n not in offsets:
            raise SystemExit(f"{story_path} has no Chapter {n}")
        start, end = offsets[n]
        parts.append(text[start:end].strip())
    return "\n\n---\n\n".join(parts)


def load(root: Path) -> Work:
    work = Work(root=root.resolve())
    if not work.human_dir.is_dir():
        raise SystemExit(f"{work.human_dir} does not exist -- run python -m skilltrain prepare first")
    return work
