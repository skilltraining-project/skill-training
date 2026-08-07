"""Load and fill the prompt templates in `prompts/`.

Every prompt the system sends lives in that folder as plain markdown with
`{{placeholder}}` slots. Nothing is built by string-concatenation in Python, so
adapting this project to a different craft means editing markdown, not code.
"""

from __future__ import annotations

import re
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SLOT = re.compile(r"\{\{(\w+)\}\}")


def render(name: str, **values: object) -> str:
    """Fill `prompts/<name>.md`. Every slot must be given a value."""
    template = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    missing = {slot for slot in _SLOT.findall(template)} - set(values)
    if missing:
        raise KeyError(f"prompts/{name}.md needs {sorted(missing)}")
    return _SLOT.sub(lambda m: str(values[m.group(1)]), template)
