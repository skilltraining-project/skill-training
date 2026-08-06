"""Turn the CLI's stream-json log into something a human can read.

`claude --output-format stream-json` writes one JSON object per line. We care
about four kinds:

    system (subtype=init)  session metadata
    assistant              thinking / text / tool_use blocks
    user                   tool_result blocks
    result                 final summary with duration and cost

Two products come out of a log: a markdown transcript for reading, and a read
trace -- the ordered list of files the agent opened. The read trace is what
makes credit assignment possible: it tells the optimizer which memory entries
were actually in context when a screenplay was written.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

MAX_BLOCK_CHARS = 2000
# Commands that put a file's contents into the agent's context. An agent that
# reads memory with `cat` instead of the Read tool still read it.
READING_COMMANDS = {"cat", "head", "tail", "less", "more", "bat"}


def _iter_events(path: Path):
    if not path.exists():
        return
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # partial line from a killed subprocess


def _clip(value, limit: int = MAX_BLOCK_CHARS) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n... (truncated, {len(text):,} chars total)"


def _result_text(content) -> str:
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            else:
                parts.append(json.dumps(item, ensure_ascii=False))
        return "\n".join(parts)
    return str(content)


def render_trajectory(log_path: Path) -> str:
    """Render one stream-json log as a markdown transcript."""
    lines: list[str] = [f"# Trajectory: {log_path.name}", ""]
    tool_names: dict[str, str] = {}
    tail: dict | None = None

    for event in _iter_events(log_path):
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            lines += [f"- model: `{event.get('model', '?')}`",
                      f"- session: `{event.get('session_id', '?')}`", ""]
        elif kind == "result":
            tail = event
        elif kind in ("assistant", "user"):
            for block in event.get("message", {}).get("content", []) or []:
                lines += _render_block(block, kind, tool_names)

    if tail:
        cost = tail.get("total_cost_usd")
        lines += ["---", "",
                  f"- turns: {tail.get('num_turns', '?')}",
                  f"- duration: {tail.get('duration_ms', 0) / 1000:.0f}s",
                  f"- cost: {f'${cost:.4f}' if isinstance(cost, (int, float)) else 'n/a'}",
                  ""]
    return "\n".join(lines)


def _render_block(block: dict, source: str, tool_names: dict[str, str]) -> list[str]:
    kind = block.get("type")
    if kind == "thinking":
        text = block.get("thinking", "").strip()
        return ["## thinking", "", "> " + text.replace("\n", "\n> "), ""] if text else []
    if kind == "text":
        text = block.get("text", "").strip()
        label = "assistant" if source == "assistant" else "user"
        return [f"## {label}", "", text, ""] if text else []
    if kind == "tool_use":
        name = block.get("name", "?")
        tool_names[block.get("id", "")] = name
        payload = json.dumps(block.get("input", {}), ensure_ascii=False, indent=2)
        return [f"## tool call: {name}", "", "```json", _clip(payload), "```", ""]
    if kind == "tool_result":
        name = tool_names.get(block.get("tool_use_id", ""), "?")
        flag = " (error)" if block.get("is_error") else ""
        body = _result_text(block.get("content", ""))
        return [f"## tool result: {name}{flag}", "", "```", _clip(body), "```", ""]
    return []


def _paths_from_bash(command: str) -> list[str]:
    """Best-effort file paths from a shell command that reads files.

    Split on shell separators first and only look at commands whose *first*
    word reads a file. A looser rule picks up the rest of a chained command:
    `cat notes.md && echo done && ls` would otherwise record `echo` and `ls`
    as files that were read.
    """
    found: list[str] = []
    for segment in re.split(r"[;|&\n]+", command):
        try:
            tokens = shlex.split(segment)
        except ValueError:
            continue
        if not tokens or tokens[0].rsplit("/", 1)[-1] not in READING_COMMANDS:
            continue
        for token in tokens[1:]:
            if token in (">", ">>"):
                break  # what follows is where output goes, not something read
            if not token.startswith("-") and ("/" in token or "." in token):
                found.append(token)
    return found


def collect_read_trace(log_path: Path) -> list[str]:
    """Ordered, de-duplicated list of files the agent read."""
    seen: dict[str, None] = {}
    for event in _iter_events(log_path):
        if event.get("type") != "assistant":
            continue
        for block in event.get("message", {}).get("content", []) or []:
            if block.get("type") != "tool_use":
                continue
            args = block.get("input", {}) or {}
            name = block.get("name")
            if name == "Read" and args.get("file_path"):
                seen.setdefault(str(args["file_path"]), None)
            elif name == "Bash" and args.get("command"):
                for path in _paths_from_bash(str(args["command"])):
                    seen.setdefault(path, None)
    return list(seen)
